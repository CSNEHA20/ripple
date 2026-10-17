import logging
from typing import Any
from app.config import settings
from app.actions.executors.slack import SlackActionExecutor
from app.tenancy import TenantGraph

logger = logging.getLogger("ripple.notifications")

_slack_executor = SlackActionExecutor()


def notify_incident_event(
    graph: TenantGraph,
    event_type: str,
    incident_id: str,
    data: dict[str, Any],
) -> None:
    """Publish real-time notification to registered webhook and Slack channels."""
    if not settings.slack_webhook_url:
        return

    text = ""
    if event_type == "incident_opened":
        svc = data.get("service", "unknown")
        text = f"🔥 *INCIDENT OPENED*: `{incident_id}` on `{svc}`\n*Alert*: {data.get('alert', {}).get('text', '')}"
    elif event_type == "approval_needed":
        action_id = data.get("action_id", "")
        runbook = data.get("runbook_id", "")
        text = f"⚠️ *ACTION APPROVAL REQUIRED*: `{action_id}` ({runbook}) for incident `{incident_id}`"
    elif event_type == "incident_closed":
        status = data.get("status", "resolved")
        text = f"✅ *INCIDENT CLOSED*: `{incident_id}` marked as *{status.upper()}*."

    if text:
        try:
            _slack_executor.execute(
                graph=graph,
                incident_id=incident_id,
                action_id=f"notif_{event_type}_{incident_id}",
                action_kind="notify_slack",
                payload={"text": text},
                approver="system",
            )
        except Exception as e:
            logger.debug(f"Slack notification failed: {e}")
