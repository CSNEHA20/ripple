import hashlib
import json
import logging
import time
from typing import Any
import httpx
from app.config import settings
from app.tenancy import TenantGraph
from app.actions.executors.base import ActionExecutor, ExecutionReceipt

logger = logging.getLogger("ripple.actions.executors.github_dispatch")


class GitHubDispatchExecutor(ActionExecutor):
    """Triggers GitHub Actions workflow_dispatch to execute real rollback or mitigation workflows."""

    def __init__(self, token: str | None = None, repo: str | None = None):
        self.token = token or settings.github_token
        self.repo = repo or settings.github_repo

    def execute(
        self,
        graph: TenantGraph,
        incident_id: str,
        action_id: str,
        action_kind: str,
        payload: dict[str, Any],
        approver: str = "operator",
        dry_run: bool = False,
    ) -> ExecutionReceipt:
        now_ts = time.time()
        idempotency_key = f"gh_{action_id}_{hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]}"
        audit_content = f"{idempotency_key}:{approver}:{now_ts}"
        audit_hash = hashlib.sha256(audit_content.encode()).hexdigest()

        status = "executed"
        details: dict[str, Any] = {"repo": self.repo, "workflow": "rollback.yml", "action_kind": action_kind}

        if dry_run or not self.token:
            status = "dry_run" if dry_run else "executed (simulated: no GITHUB_TOKEN)"
            details["simulated"] = True
            logger.info(f"[GitHubDispatchExecutor] Dry-run/simulated action {action_kind} on {self.repo}: {payload}")
        else:
            url = f"https://api.github.com/repos/{self.repo}/actions/workflows/rollback.yml/dispatches"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Ripple-OnCall-Agent",
            }
            body = {
                "ref": "main",
                "inputs": {
                    "service": payload.get("service", "unknown"),
                    "incident_id": incident_id,
                    "target_version": payload.get("version", "previous"),
                },
            }
            try:
                with httpx.Client(timeout=8.0) as client:
                    resp = client.post(url, headers=headers, json=body)
                    details["http_status"] = resp.status_code
                    if resp.status_code not in (200, 204):
                        status = "failed"
                        details["error"] = resp.text
            except Exception as e:
                logger.error(f"GitHub workflow dispatch failed: {e}")
                status = "failed"
                details["error"] = str(e)

        receipt = ExecutionReceipt(
            idempotency_key=idempotency_key,
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
