import hashlib
import json
import logging
import time
from typing import Any
from app.tenancy import TenantGraph
from app.actions.executors.base import ActionExecutor, ExecutionReceipt

logger = logging.getLogger("ripple.actions.executors.sandbox")


_EXECUTED_KEYS: set[str] = set()


class SandboxActionExecutor(ActionExecutor):
    """Executes safe container restarts, deployment rollbacks, and scale adjustments
    against the local environment / simulator with strict idempotency and audit trails.
    """

    def execute(
        self,
        graph: TenantGraph | None,
        incident_id: str,
        action_id: str,
        action_kind: str,
        payload: dict[str, Any],
        approver: str = "operator",
        dry_run: bool = False,
        idempotency_key: str | None = None,
    ) -> ExecutionReceipt:
        now_ts = time.time()
        payload_str = json.dumps(payload, sort_keys=True)
        key = idempotency_key or f"sandbox_{action_id}_{hashlib.sha256(payload_str.encode()).hexdigest()[:12]}"
        audit_content = f"{key}:{approver}:{now_ts}"
        audit_hash = hashlib.sha256(audit_content.encode()).hexdigest()

        target_service = payload.get("service") or payload.get("target_service") or "unknown"
        runbook_id = payload.get("runbook_id") or "rb_rollback"

        details = {
            "target_service": target_service,
            "runbook_id": runbook_id,
            "action_kind": action_kind,
            "dry_run": dry_run,
        }

        if not dry_run:
            # 1. Check persistent graph idempotency
            persisted = self.check_persisted_idempotency(graph, key)
            if persisted:
                return persisted

            # 2. Check in-memory idempotency
            if key in _EXECUTED_KEYS:
                return ExecutionReceipt(
                    idempotency_key=key,
                    action_id=action_id,
                    incident_id=incident_id,
                    action_kind=action_kind,
                    approver=approver,
                    executed_ts=now_ts,
                    status="idempotent_skip",
                    details={"message": f"Action with key {key} already executed. Skipping."},
                    audit_hash=audit_hash,
                )

        _EXECUTED_KEYS.add(key)

        if dry_run:
            status = "dry_run"
            details["message"] = f"Dry-run simulation for {action_kind} on {target_service} succeeded. No state changed."
        else:
            status = "executed"
            from app.adapters.demo_target import restore_service
            # Healing rule: rollback or restart heals the demo target service
            if action_kind in ("rollback", "restart", "rollback_deployment", "restart_service", "apply_hotfix"):
                if target_service and target_service != "unknown":
                    restore_service(target_service)
                    details["healed"] = True
                    details["message"] = f"Action {action_kind} executed: healed target service '{target_service}' to normal."
                    logger.info(f"[SandboxExecutor] Executed {action_kind} and restored demo service '{target_service}'.")
                else:
                    details["healed"] = False
                    details["message"] = f"Action {action_kind} executed without a known target service."
            else:
                # Wrong fix does not heal the broken service!
                details["healed"] = False
                details["message"] = f"Action {action_kind} executed on {target_service}, but fault condition was not resolved by this action."
                logger.info(f"[SandboxExecutor] Executed wrong/non-healing action {action_kind} on {target_service}.")

        receipt = ExecutionReceipt(
            idempotency_key=key,
            action_id=action_id,
            incident_id=incident_id,
            action_kind=action_kind,
            approver=approver,
            executed_ts=now_ts,
            status=status,
            details=details,
            audit_hash=audit_hash,
        )
        self.record_audit_log(graph, receipt)
        return receipt

