import hashlib
import json
import logging
import time
from typing import Any
import httpx
from app.config import settings
from app.tenancy import TenantGraph
from app.actions.executors.base import ActionExecutor, ExecutionReceipt
from app.tenant_settings import get_tenant_settings, mask_secret

logger = logging.getLogger("ripple.actions.executors.github_dispatch")


_GITHUB_EXECUTED_KEYS: set[str] = set()


class GitHubDispatchExecutor(ActionExecutor):
    """Triggers GitHub Actions workflow_dispatch to execute real rollback or mitigation workflows."""

    def __init__(
        self,
        token: str | None = None,
        repo: str | None = None,
        workflow: str | None = None,
        ref: str | None = None,
    ):
        self.token = token
        self.repo = repo
        self.workflow = workflow
        self.ref = ref

    def execute(
        self,
        graph: TenantGraph | None,
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

        # 1. Enforce persisted idempotency across restarts
        if not dry_run:
            persisted = self.check_persisted_idempotency(graph, idempotency_key)
            if persisted:
                return persisted
            if idempotency_key in _GITHUB_EXECUTED_KEYS:
                return ExecutionReceipt(
                    idempotency_key=idempotency_key,
                    action_id=action_id,
                    incident_id=incident_id,
                    action_kind=action_kind,
                    approver=approver,
                    executed_ts=now_ts,
                    status="idempotent_skip",
                    details={"message": f"GitHub workflow dispatch with key {idempotency_key} already sent. Skipping duplicate."},
                    audit_hash=audit_hash,
                )
            _GITHUB_EXECUTED_KEYS.add(idempotency_key)

        # 2. Resolve tenant-scoped integration settings
        tenant_id = getattr(graph, "tenant_id", None)
        t_cfg = get_tenant_settings(tenant_id, graph=graph) if graph else {}

        effective_repo = self.repo or t_cfg.get("github_repo")
        effective_token = self.token or t_cfg.get("github_token")
        effective_workflow = self.workflow or t_cfg.get("github_workflow") or "rollback.yml"
        effective_ref = self.ref or t_cfg.get("github_ref") or "main"

        # 3. Refuse cleanly if repository is not configured for this tenant
        if not effective_repo or (effective_repo == "GoogleCloudPlatform/microservices-demo" and not effective_token):
            details = {
                "error": "No GitHub repository configured for this tenant. Configure repository and workflow in Integrations settings.",
                "action_kind": action_kind,
                "configured": False,
            }
            logger.warning(f"[GitHubDispatchExecutor] Refused action {action_kind}: no repo configured for tenant '{tenant_id}'.")
            receipt = ExecutionReceipt(
                idempotency_key=idempotency_key,
                action_id=action_id,
                incident_id=incident_id,
                action_kind=action_kind,
                approver=approver,
                executed_ts=now_ts,
                status="refused",
                details=details,
                audit_hash=audit_hash,
            )
            self.record_audit_log(graph, receipt)
            return receipt

        status = "executed"
        details: dict[str, Any] = {
            "repo": effective_repo,
            "workflow": effective_workflow,
            "ref": effective_ref,
            "action_kind": action_kind,
        }

        if dry_run or not effective_token:
            status = "dry_run" if dry_run else "executed (simulated: no GITHUB_TOKEN)"
            details["simulated"] = True
            logger.info(f"[GitHubDispatchExecutor] Dry-run/simulated action {action_kind} on {effective_repo} ({effective_workflow}@{effective_ref})")
        else:
            url = f"https://api.github.com/repos/{effective_repo}/actions/workflows/{effective_workflow}/dispatches"
            headers = {
                "Authorization": f"Bearer {effective_token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Ripple-OnCall-Agent",
            }
            body = {
                "ref": effective_ref,
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

