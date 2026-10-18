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

logger = logging.getLogger("ripple.actions.executors.slack")


_SLACK_EXECUTED_KEYS: set[str] = set()


class SlackActionExecutor(ActionExecutor):
    """Executes notifications and interactive alerts to Slack channels via incoming webhooks."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url

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
        idempotency_key = f"slack_{action_id}_{hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]}"
        audit_content = f"{idempotency_key}:{approver}:{now_ts}"
        audit_hash = hashlib.sha256(audit_content.encode()).hexdigest()

        # 1. Enforce persisted graph & in-memory idempotency across restarts
        if not dry_run:
            persisted = self.check_persisted_idempotency(graph, idempotency_key)
            if persisted:
                return persisted
            if idempotency_key in _SLACK_EXECUTED_KEYS:
                return ExecutionReceipt(
                    idempotency_key=idempotency_key,
                    action_id=action_id,
                    incident_id=incident_id,
                    action_kind=action_kind,
                    approver=approver,
                    executed_ts=now_ts,
                    status="idempotent_skip",
                    details={"message": f"Slack notification with key {idempotency_key} already sent. Skipping duplicate."},
                    audit_hash=audit_hash,
                )
            _SLACK_EXECUTED_KEYS.add(idempotency_key)

        # 2. Resolve tenant-scoped settings
        tenant_id = getattr(graph, "tenant_id", None)
        t_cfg = get_tenant_settings(tenant_id, graph=graph) if graph else {}
        effective_webhook = self.webhook_url or t_cfg.get("slack_webhook_url")

        # 3. Clean refusal if tenant is unconfigured
        if graph is not None and not effective_webhook:
            details = {
                "error": "No Slack webhook URL configured for this tenant. Configure webhook in Integrations settings.",
                "action_kind": action_kind,
                "configured": False,
            }
            logger.warning(f"[SlackActionExecutor] Refused action {action_kind}: no Slack webhook configured for tenant '{tenant_id}'.")
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
            "channel": "on-call-alerts",
            "action_kind": action_kind,
            "webhook_url": mask_secret(effective_webhook) if effective_webhook else None,
        }

        if dry_run or not effective_webhook:
            status = "dry_run" if dry_run else "executed (simulated: no SLACK_WEBHOOK_URL)"
            details["simulated"] = True
            logger.info(f"[SlackExecutor] Dry-run/simulated action {action_kind} for incident {incident_id}: tenant={tenant_id}")

        else:
            message_text = payload.get("text") or f"Ripple Alert: {action_kind} for incident {incident_id}"
            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"🚨 Ripple Incident Action: {action_kind.upper()}"},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Incident:*\n`{incident_id}`"},
                        {"type": "mrkdwn", "text": f"*Approver:*\n{approver}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{message_text}*"},
                },
            ]
            try:
                with httpx.Client(timeout=5.0) as client:
                    resp = client.post(effective_webhook, json={"blocks": blocks, "text": message_text})
                    details["http_status"] = resp.status_code
                    if resp.status_code != 200:
                        status = "failed"
                        details["error"] = resp.text
            except Exception as e:
                logger.error(f"Failed to post Slack notification: {e}")
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

