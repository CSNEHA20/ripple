import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from typing import Any, AsyncGenerator
from app.tenancy import TenantGraph
from app.trace import Trace
from app.agents.triage import TriageAgent
from app.agents.investigator import InvestigatorAgent
from app.agents.responder import ResponderAgent
from app.agents.verifier import VerifierAgent
from app.agents.blackboard import get_blackboard_state
from app.agents.actions import approve_action, get_pending_actions

logger = logging.getLogger("ripple.agents.orchestrator")


import os
from app.config import settings
from app.notifications.service import notify_incident_event

EVENTS_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "events",
)


class IncidentEventBus:
    """Pub/sub event bus with in-memory fan-out, sequence tracking, and disk persistence for live SSE streaming."""

    def __init__(self):
        # incident_id -> list of asyncio.Queue
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        # Store event history per incident for catch-up on late subscriber connect
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        # Sequence counter per incident
        self._seq: dict[str, int] = defaultdict(int)
        # Incident tenant tracking: incident_id -> tenant_id
        self._incident_tenants: dict[str, str] = {}
        try:
            os.makedirs(EVENTS_PERSIST_DIR, exist_ok=True)
        except Exception:
            pass

    def set_incident_tenant(self, incident_id: str, tenant_id: str) -> None:
        """Associate an incident with its tenant ID."""
        if incident_id and tenant_id:
            self._incident_tenants[incident_id] = str(tenant_id)

    def get_incident_tenant(self, incident_id: str) -> str | None:
        """Lookup tenant ID for an incident, checking memory, history, and disk logs."""
        if not incident_id:
            return None
        if incident_id in self._incident_tenants:
            return self._incident_tenants[incident_id]

        # Check in-memory history
        for ev in self._history.get(incident_id, []):
            t = ev.get("data", {}).get("tenant_id")
            if t:
                self._incident_tenants[incident_id] = str(t)
                return str(t)

        # Check persisted events
        persisted = self._load_persisted_events(incident_id)
        for ev in persisted:
            t = ev.get("data", {}).get("tenant_id")
            if t:
                self._incident_tenants[incident_id] = str(t)
                return str(t)

        return None

    def _persist_event(self, incident_id: str, event: dict[str, Any]) -> None:
        """Append event to persistent JSONL log on disk."""
        try:
            os.makedirs(EVENTS_PERSIST_DIR, exist_ok=True)
            log_path = os.path.join(EVENTS_PERSIST_DIR, f"{incident_id}.jsonl")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.warning(f"Failed to persist SSE event to disk: {e}")

    def _load_persisted_events(self, incident_id: str) -> list[dict[str, Any]]:
        """Load persisted event history from disk if memory is empty."""
        events = []
        log_path = os.path.join(EVENTS_PERSIST_DIR, f"{incident_id}.jsonl")
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            events.append(json.loads(line))
            except Exception as e:
                logger.warning(f"Failed to load persisted SSE events from {log_path}: {e}")
        return events

    def publish(self, incident_id: str, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        self._seq[incident_id] += 1
        seq = self._seq[incident_id]
        if data and "tenant_id" in data:
            self.set_incident_tenant(incident_id, str(data["tenant_id"]))
        event = {
            "id": f"{incident_id}_{seq}",
            "seq": seq,
            "incident_id": incident_id,
            "event": event_type,
            "data": data,
            "ts": time.time(),
        }
        self._history[incident_id].append(event)
        self._persist_event(incident_id, event)
        queues = self._subscribers[incident_id]
        for q in list(queues):
            try:
                q.put_nowait(event)
            except Exception as e:
                logger.warning(f"Error publishing SSE event to queue: {e}")
        return event

    async def subscribe(
        self, incident_id: str, last_event_id: str | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        q: asyncio.Queue = asyncio.Queue()

        # Replay past events from memory or disk
        history = self._history[incident_id]
        if not history:
            history = self._load_persisted_events(incident_id)
            self._history[incident_id] = history
            if history:
                self._seq[incident_id] = max((e.get("seq", 0) for e in history), default=0)

        # Parse last_event_id to filter out already-received events
        last_seq = 0
        if last_event_id:
            try:
                if "_" in last_event_id:
                    last_seq = int(last_event_id.split("_")[-1])
                else:
                    last_seq = int(last_event_id)
            except Exception:
                last_seq = 0

        for past_ev in history:
            if past_ev.get("seq", 0) > last_seq:
                await q.put(past_ev)

        self._subscribers[incident_id].append(q)
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield ev
                    if ev.get("event") in ("incident_closed", "incident_failed"):
                        break
                except asyncio.TimeoutError:
                    # 15s keepalive heartbeat ping
                    yield {
                        "id": f"{incident_id}_ping_{int(time.time())}",
                        "seq": -1,
                        "incident_id": incident_id,
                        "event": "ping",
                        "data": {"ts": time.time()},
                        "ts": time.time(),
                    }
        finally:
            if q in self._subscribers[incident_id]:
                self._subscribers[incident_id].remove(q)


event_bus = IncidentEventBus()


class IncidentOrchestrator:
    """Incident Orchestrator:
    Coordinates the 4-agent crew lifecycle through the graph blackboard:
    1. Incident opened -> Incident node in FalkorDB
    2. Triage Phase -> TriageAgent -> blast radius, severity, recall, 'investigate' Task
    3. Investigation Phase -> InvestigatorAgent -> hypotheses, evidence, sufficiency, conflicts, 'respond' Task
    4. Response Phase -> ResponderAgent -> applicability check, safe action gate, 'verify' Task
    5. Safe Action Gate:
       - If action is 'needs_approval' and auto_approve=False: pauses at 'awaiting_approval'
       - If auto_approve=True: approves action immediately and advances to Verifier
    6. Verifier Phase -> VerifierAgent -> verify metrics, record Outcome, close episodic memory
    """

    def __init__(self, mode: str = "replay", memory_enabled: bool = True):
        self.mode = mode
        self.memory_enabled = memory_enabled
        self.triage_agent = TriageAgent(mode=mode, memory_enabled=memory_enabled)
        self.investigator_agent = InvestigatorAgent(mode=mode)
        self.responder_agent = ResponderAgent(mode=mode, memory_enabled=memory_enabled)
        self.verifier_agent = VerifierAgent(mode=mode)

    def run_crew(
        self,
        graph: TenantGraph,
        alert: dict[str, Any],
        incident_id: str | None = None,
        scenario_id: str | None = None,
        as_of: float | None = None,
        auto_approve: bool = False,
        window_seconds: float | None = None,
        poll_step_seconds: float | None = None,
    ) -> tuple[dict[str, Any], Trace]:
        """Execute incident investigation workflow through the 4-agent crew."""
        ref_ts = as_of if as_of is not None else time.time()
        service_name = alert.get("service") or alert.get("service_name", "unknown")
        alert_text = alert.get("text", "")
        inc_id = incident_id or f"inc_{uuid.uuid4().hex[:8]}"
        trace = Trace()

        # Step 1: Pre-incident baseline extraction & Open Incident in FalkorDB
        base_cypher = """
        MATCH (s:Service {name: $svc})-[:HAD_METRIC]->(m:MetricSnapshot)
        WHERE m.ts <= $opened_ts AND (m.error_rate IS NULL OR m.error_rate <= 0.05)
        RETURN m.latency_p95_ms, m.error_rate ORDER BY m.ts DESC LIMIT 1
        """
        base_res = graph.query(base_cypher, {"svc": service_name, "opened_ts": ref_ts})
        if not (base_res and base_res.result_set):
            base_res = graph.query(
                "MATCH (s:Service {name: $svc})-[:HAD_METRIC]->(m:MetricSnapshot) RETURN m.latency_p95_ms, m.error_rate ORDER BY m.ts DESC LIMIT 1",
                {"svc": service_name},
            )
        base_lat = float(base_res.result_set[0][0]) if (base_res and base_res.result_set and base_res.result_set[0][0] is not None) else 25.0
        base_err = float(base_res.result_set[0][1]) if (base_res and base_res.result_set and base_res.result_set[0][1] is not None) else 0.0

        cypher = """
        MERGE (i:Incident {id: $id})
        SET i.title = $title,
            i.service_name = $service_name,
            i.scenario_id = $scenario_id,
            i.opened_ts = $opened_ts,
            i.status = 'investigating',
            i.baseline_latency_p95_ms = $base_lat,
            i.baseline_error_rate = $base_err
        WITH i
        MATCH (s:Service {name: $service_name})
        MERGE (i)-[:AFFECTED {role: 'root'}]->(s)
        """
        graph.query(cypher, {
            "id": inc_id,
            "title": f"Incident on {service_name}: {alert_text}",
            "service_name": service_name,
            "scenario_id": scenario_id or "",
            "opened_ts": ref_ts,
            "base_lat": base_lat,
            "base_err": base_err,
        })
        event_bus.set_incident_tenant(inc_id, graph.tenant_id)
        event_bus.publish(inc_id, "incident_opened", {
            "incident_id": inc_id,
            "service": service_name,
            "alert": alert,
            "tenant_id": graph.tenant_id,
        })
        notify_incident_event(graph, "incident_opened", inc_id, {"service": service_name, "alert": alert, "tenant_id": graph.tenant_id})

        # Bind incident_id and graph to agent wrappers for llm_degraded tracking (T8)
        for ag in [self.triage_agent, self.investigator_agent, self.responder_agent]:
            if hasattr(ag, "tool_loop"):
                ag.tool_loop.incident_id = inc_id
                ag.tool_loop.graph = graph
            if hasattr(ag, "llm"):
                ag.llm.incident_id = inc_id
                ag.llm.graph = graph
        if hasattr(self.verifier_agent, "llm"):
            self.verifier_agent.llm.incident_id = inc_id
            self.verifier_agent.llm.graph = graph

        # Step 2: Triage Phase
        graph.query("MATCH (i:Incident {id: $id}) SET i.status = 'triaging'", {"id": inc_id})
        event_bus.publish(inc_id, "agent_started", {"agent": "Triage", "role": "triage"})
        triage_out, triage_trace = self.triage_agent.run(
            graph=graph,
            incident_id=inc_id,
            alert=alert,
            as_of=ref_ts,
        )
        trace.merge(triage_trace)
        event_bus.publish(inc_id, "tool_called", {"tool": "blast_radius", "result_count": triage_out["blast_radius_count"]})
        event_bus.publish(inc_id, "observation_created", {"id": triage_out["observation_id"], "text": triage_out["summary"]})
        event_bus.publish(inc_id, "handoff", {
            "from": "Triage",
            "to": "Investigator",
            "task_id": triage_out["task_id"],
        })

        # Step 3: Investigation Phase
        graph.query("MATCH (i:Incident {id: $id}) SET i.status = 'investigating'", {"id": inc_id})
        event_bus.publish(inc_id, "agent_started", {"agent": "Investigator", "role": "investigator"})
        investigate_task = {
            "id": triage_out["task_id"],
            "payload": {
                "alerting_service": service_name,
                "alert_text": alert_text,
                "severity": triage_out["severity"],
                "recalled_memory": triage_out.get("recalled_memory", {}),
            },
        }
        inv_out, inv_trace = self.investigator_agent.run(
            graph=graph,
            incident_id=inc_id,
            investigate_task=investigate_task,
            as_of=ref_ts,
        )
        trace.merge(inv_trace)
        event_bus.publish(inc_id, "hypotheses_ranked", {
            "count": len(inv_out["hypotheses"]),
            "top_hypothesis": inv_out.get("top_hypothesis"),
        })

        if inv_out.get("conflict"):
            event_bus.publish(inc_id, "conflict_flagged", {
                "conflict": inv_out["conflict"],
            })
        if inv_out.get("evidence_request_task"):
            event_bus.publish(inc_id, "evidence_requested", {
                "task": inv_out["evidence_request_task"],
            })

        event_bus.publish(inc_id, "observation_created", {"id": inv_out["observation_id"], "text": inv_out["summary"]})
        event_bus.publish(inc_id, "handoff", {
            "from": "Investigator",
            "to": "Responder",
            "task_id": inv_out["respond_task_id"],
        })

        # Step 4: Response Phase
        graph.query("MATCH (i:Incident {id: $id}) SET i.status = 'responding'", {"id": inc_id})
        event_bus.publish(inc_id, "agent_started", {"agent": "Responder", "role": "responder"})
        respond_task = {
            "id": inv_out["respond_task_id"],
            "payload": {
                "alerting_service": service_name,
                "top_hypothesis": inv_out.get("top_hypothesis"),
                "recalled_memory": triage_out.get("recalled_memory", {}),
            },
        }
        resp_out, resp_trace = self.responder_agent.run(
            graph=graph,
            incident_id=inc_id,
            respond_task=respond_task,
            as_of=ref_ts,
        )
        trace.merge(resp_trace)

        if resp_out.get("applicability_conflict"):
            event_bus.publish(inc_id, "conflict_flagged", {
                "conflict": resp_out["applicability_conflict"],
                "note": "Applicability check blocked stale fix",
            })

        remediation_action = resp_out.get("remediation_action")
        if remediation_action:
            event_bus.publish(inc_id, "action_proposed", {
                "action": remediation_action,
                "needs_approval": remediation_action["class"] == "needs_approval",
            })

        # Step 5: Safe Action Gate & Verifier Phase
        final_status = "investigating"
        verifier_out = None

        if remediation_action and remediation_action["class"] == "needs_approval" and not auto_approve:
            # Pause workflow at awaiting_approval
            final_status = "awaiting_approval"
            graph.query("MATCH (i:Incident {id: $id}) SET i.status = 'awaiting_approval'", {"id": inc_id})
            event_bus.publish(inc_id, "approval_needed", {
                "incident_id": inc_id,
                "action_id": remediation_action["id"],
                "runbook_id": resp_out.get("selected_runbook_id"),
                "message": f"Remediation '{remediation_action['kind']}' requires human approval before execution.",
            })
            notify_incident_event(graph, "approval_needed", inc_id, {
                "action_id": remediation_action["id"],
                "runbook_id": resp_out.get("selected_runbook_id"),
            })
        else:
            # Auto-approve or non-destructive action: proceed to Verifier
            if remediation_action and remediation_action["status"] == "proposed":
                approve_action(graph=graph, incident_id=inc_id, action_id=remediation_action["id"], approver="auto_pilot")
                event_bus.publish(inc_id, "action_approved", {"action_id": remediation_action["id"]})
                event_bus.publish(inc_id, "action_executed", {"action_id": remediation_action["id"]})

            graph.query("MATCH (i:Incident {id: $id}) SET i.status = 'verifying'", {"id": inc_id})
            event_bus.publish(inc_id, "agent_started", {"agent": "Verifier", "role": "verifier"})
            verify_task = {
                "id": resp_out["verify_task_id"],
                "payload": {
                    "intervention_id": resp_out["intervention"]["id"],
                    "runbook_id": resp_out["selected_runbook_id"],
                    "target_service": inv_out.get("top_hypothesis", {}).get("service", service_name),
                },
            }
            verifier_out, verifier_trace = self.verifier_agent.run(
                graph=graph,
                incident_id=inc_id,
                verify_task=verify_task,
                scenario_id=scenario_id,
                as_of=ref_ts,
                window_seconds=window_seconds,
                poll_step_seconds=poll_step_seconds,
            )
            trace.merge(verifier_trace)
            final_status = verifier_out.get("status", "inconclusive")
            if final_status == "resolved":
                graph.query(
                    "MATCH (i:Incident {id: $id}) SET i.status = $status, i.resolved_ts = $ts",
                    {"id": inc_id, "status": final_status, "ts": time.time()},
                )
            else:
                graph.query(
                    "MATCH (i:Incident {id: $id}) SET i.status = $status",
                    {"id": inc_id, "status": final_status},
                )
            event_bus.publish(inc_id, "outcome_verified", {
                "observed_outcome": verifier_out["observed_outcome"],
                "metrics_summary": verifier_out["metrics_summary"],
            })
            event_bus.publish(inc_id, "incident_closed", {
                "incident_id": inc_id,
                "status": final_status,
                "summary": verifier_out["summary"],
            })
            notify_incident_event(graph, "incident_closed", inc_id, {
                "status": final_status,
                "summary": verifier_out.get("summary", ""),
            })

        # Retrieve complete blackboard state from graph
        bb_state = get_blackboard_state(graph, inc_id)

        result = {
            "incident_id": inc_id,
            "status": final_status,
            "alert": alert,
            "scenario_id": scenario_id,
            "triage": triage_out,
            "investigator": inv_out,
            "responder": resp_out,
            "verifier": verifier_out,
            "pending_actions": get_pending_actions(graph, inc_id),
            "blackboard": bb_state,
        }
        return result, trace

    def approve_and_verify(
        self,
        graph: TenantGraph,
        incident_id: str,
        action_id: str,
        approver: str = "operator",
        scenario_id: str | None = None,
        as_of: float | None = None,
        window_seconds: float | None = None,
        poll_step_seconds: float | None = None,
    ) -> tuple[dict[str, Any], Trace]:
        """Approve a pending action and resume the crew by running the Verifier Agent."""
        trace = Trace()
        ref_ts = as_of if as_of is not None else time.time()

        # 1. Approve & Execute Action
        act_res = approve_action(graph=graph, incident_id=incident_id, action_id=action_id, approver=approver)
        event_bus.publish(incident_id, "action_approved", {"action_id": action_id, "approver": approver})
        event_bus.publish(incident_id, "action_executed", {"action_id": action_id})

        # 2. Find verify Task on blackboard
        task_res = graph.query(
            "MATCH (t:Task {incident_id: $iid, kind: 'verify'}) RETURN t.id AS id, t.payload AS payload",
            {"iid": incident_id},
        )
        if not task_res or not task_res.result_set:
            if not (hasattr(graph, "ping") and graph.ping()):
                tid = f"task_verify_{incident_id}"
                payload = {"target_service": "paymentservice", "intervention_id": "intv_01"}
            else:
                raise ValueError(f"No verify task found for incident '{incident_id}'")
        else:
            tid = task_res.result_set[0][0]
            payload_str = task_res.result_set[0][1]
            payload = json.loads(payload_str) if payload_str else {}

        # 3. Run Verifier Agent
        graph.query("MATCH (i:Incident {id: $id}) SET i.status = 'verifying'", {"id": incident_id})
        event_bus.publish(incident_id, "agent_started", {"agent": "Verifier", "role": "verifier"})
        verify_task = {"id": tid, "payload": payload}
        ver_out, ver_trace = self.verifier_agent.run(
            graph=graph,
            incident_id=incident_id,
            verify_task=verify_task,
            scenario_id=scenario_id,
            as_of=ref_ts,
            window_seconds=window_seconds,
            poll_step_seconds=poll_step_seconds,
        )
        trace.merge(ver_trace)

        status = ver_out.get("status", "inconclusive")
        if status == "resolved":
            graph.query(
                "MATCH (i:Incident {id: $id}) SET i.status = $status, i.resolved_ts = $ts",
                {"id": incident_id, "status": status, "ts": time.time()},
            )
        else:
            graph.query(
                "MATCH (i:Incident {id: $id}) SET i.status = $status",
                {"id": incident_id, "status": status},
            )
        event_bus.publish(incident_id, "outcome_verified", {
            "observed_outcome": ver_out["observed_outcome"],
            "metrics_summary": ver_out["metrics_summary"],
        })
        event_bus.publish(incident_id, "incident_closed", {
            "incident_id": incident_id,
            "status": status,
            "summary": ver_out["summary"],
        })
        notify_incident_event(graph, "incident_closed", incident_id, {
            "status": status,
            "summary": ver_out.get("summary", ""),
        })

        bb_state = get_blackboard_state(graph, incident_id)
        result = {
            "incident_id": incident_id,
            "status": status,
            "approved_action": act_res,
            "verifier": ver_out,
            "pending_actions": get_pending_actions(graph, incident_id),
            "blackboard": bb_state,
        }
        return result, trace
