import abc
import hashlib
import json
import logging
import time
from typing import Any
from pydantic import BaseModel
from app.tenancy import TenantGraph

logger = logging.getLogger("ripple.actions.executors")


class ExecutionReceipt(BaseModel):
    idempotency_key: str
    action_id: str
    incident_id: str
    action_kind: str
    approver: str
    executed_ts: float
    status: str  # "executed", "dry_run", "failed"
    details: dict[str, Any] = {}
    audit_hash: str


class ActionExecutor(abc.ABC):
    """Abstract base class for real action execution."""

    @abc.abstractmethod
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
        pass

    def record_audit_log(
        self,
        graph: TenantGraph,
        receipt: ExecutionReceipt,
    ) -> None:
        """Write immutable audit record into graph linked to Action."""
        cypher = """
        MATCH (a:Action {id: $action_id})
        MERGE (audit:AuditLog {id: $audit_id})
        SET audit.idempotency_key = $idempotency_key,
            audit.incident_id = $incident_id,
            audit.action_kind = $action_kind,
            audit.approver = $approver,
            audit.executed_ts = $executed_ts,
            audit.status = $status,
            audit.audit_hash = $audit_hash,
            audit.details = $details
        MERGE (a)-[:EXECUTED_WITH]->(audit)
        """
        audit_id = f"audit_{receipt.action_id}_{int(receipt.executed_ts)}"
        params = {
            "action_id": receipt.action_id,
            "audit_id": audit_id,
            "idempotency_key": receipt.idempotency_key,
            "incident_id": receipt.incident_id,
            "action_kind": receipt.action_kind,
            "approver": receipt.approver,
            "executed_ts": receipt.executed_ts,
            "status": receipt.status,
            "audit_hash": receipt.audit_hash,
            "details": json.dumps(receipt.details),
        }
        try:
            graph.query(cypher, params)
        except Exception as e:
            logger.warning(f"Failed to record audit log for action {receipt.action_id}: {e}")
