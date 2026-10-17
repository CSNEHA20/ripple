import hashlib
import json
import logging
import time
from typing import Any
import httpx
from app.config import settings
from app.tenancy import TenantGraph
from app.actions.executors.base import ActionExecutor, ExecutionReceipt

logger = logging.getLogger("ripple.actions.executors.slack")


class SlackActionExecutor(ActionExecutor):
    """Executes notifications and interactive alerts to Slack channels via incoming webhooks."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or settings.slack_webhook_url

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
        idempotency_key = f"slack_{action_id}_{hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]}"
        audit_content = f"{idempotency_key}:{approver}:{now_ts}"
        audit_hash = hashlib.sha256(audit_content.encode()).hexdigest()

        status = "executed"
        details: dict[str, Any] = {"channel": "on-call-alerts", "action_kind": action_kind}

        if dry_run or not self.webhook_url:
            status = "dry_run" if dry_run else "executed (simulated: no SLACK_WEBHOOK_URL)"
            details["simulated"] = True
            logger.info(f"[SlackExecutor] Dry-run/simulated action {action_kind} for incident {incident_id}: {payload}")
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
                    resp = client.post(self.webhook_url, json={"blocks": blocks, "text": message_text})
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
