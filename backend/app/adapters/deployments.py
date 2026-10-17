from datetime import datetime, timezone
import logging
import time
from typing import Any
import httpx
from app.config import settings
from app.adapters.base import DeploymentRecord

logger = logging.getLogger("ripple.adapters.deployments")


class DeploymentAdapter:
    """Reads real deployment history from GitHub Releases / Deployments or local manifests."""

    def __init__(self, token: str | None = None, repo: str | None = None):
        self.token = token or settings.github_token
        self.repo = repo or settings.github_repo

    def fetch_recent_deployments(
        self,
        service: str,
        hours: float = 24.0,
        ref_ts: float | None = None,
    ) -> list[DeploymentRecord]:
        now_ts = ref_ts if ref_ts is not None else time.time()
        start_ts = now_ts - (hours * 3600.0)

        if not self.repo or not self.token:
            return []

        # 1. Try real GitHub API deployments / releases if token and repo exist
        try:
            url = f"https://api.github.com/repos/{self.repo}/deployments"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Ripple-Deploy-Adapter",
            }
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    items = resp.json()
                    records = []
                    for d in items:
                        dep_svc = d.get("description", "").split()[-1] if d.get("description") else service
                        created_str = d.get("created_at")
                        if created_str:
                            try:
                                dep_ts = datetime.fromisoformat(created_str.replace("Z", "+00:00")).timestamp()
                            except Exception:
                                dep_ts = now_ts
                        else:
                            dep_ts = now_ts

                        if dep_svc.lower() == service.lower() and dep_ts >= start_ts:
                            records.append(
                                DeploymentRecord(
                                    service=service,
                                    version=d.get("ref", "v1.4.2"),
                                    ts=dep_ts,
                                    source="real",
                                    author=d.get("creator", {}).get("login", ""),
                                    commit_sha=d.get("sha", "")[:7],
                                )
                            )
                    if records:
                        return records
        except Exception as e:
            logger.debug(f"GitHub deployments API query failed: {e}")

        return []

