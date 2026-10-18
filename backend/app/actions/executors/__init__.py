import logging
from typing import Any
from app.tenancy import TenantGraph
from app.actions.executors.base import ActionExecutor, ExecutionReceipt
from app.actions.executors.slack import SlackActionExecutor
from app.actions.executors.github_dispatch import GitHubDispatchExecutor
from app.actions.executors.sandbox import SandboxActionExecutor

logger = logging.getLogger("ripple.actions.executors")

_DEFAULT_SANDBOX = SandboxActionExecutor()
_DEFAULT_SLACK = SlackActionExecutor()
_DEFAULT_GITHUB = GitHubDispatchExecutor()


def get_executor_for_action(action_kind: str) -> ActionExecutor:
    """Resolve appropriate executor based on action kind."""
    clean = action_kind.lower().strip().replace(" ", "_")
    if clean in ("notify_slack", "page_oncall", "page_team", "draft_status_update"):
        return SlackActionExecutor()
    elif clean in ("github_rollback", "workflow_dispatch"):
        return GitHubDispatchExecutor()
    return _DEFAULT_SANDBOX


def execute_action(
    graph: TenantGraph,
    incident_id: str,
    action_id: str,
    action_kind: str,
    payload: dict[str, Any],
    approver: str = "operator",
    dry_run: bool = False,
) -> ExecutionReceipt:
    """Execute action through registered executor and record audit trail."""
    executor = get_executor_for_action(action_kind)
    receipt = executor.execute(
        graph=graph,
        incident_id=incident_id,
        action_id=action_id,
        action_kind=action_kind,
        payload=payload,
        approver=approver,
        dry_run=dry_run,
    )
    # Also notify Slack if configured for any approved destructive action
    if not dry_run and clean_action_is_destructive(action_kind):
        try:
            slack_exec = SlackActionExecutor()
            slack_exec.execute(
                graph=graph,
                incident_id=incident_id,
                action_id=f"notify_{action_id}",
                action_kind="notify_slack",
                payload={"text": f"Remediation '{action_kind}' executed by `{approver}` for incident `{incident_id}`."},
                approver=approver,
            )
        except Exception:
            pass

    return receipt


def clean_action_is_destructive(kind: str) -> bool:
    clean = kind.lower().strip().replace(" ", "_")
    return clean in ("rollback", "restart", "rollback_deployment", "restart_service", "apply_hotfix")


__all__ = [
    "ActionExecutor",
    "ExecutionReceipt",
    "SlackActionExecutor",
    "GitHubDispatchExecutor",
    "SandboxActionExecutor",
    "get_executor_for_action",
    "execute_action",
]
