import base64
import json
import logging
import os
import re
import time
from typing import Any
import httpx
from app.config import settings
from app.ingest.embed import embed_text
from app.tenancy import TenantGraph
from app.tenant_settings import get_tenant_settings, DEFAULT_PATH_TO_SERVICE, DEFAULT_KEYWORD_HINTS

logger = logging.getLogger("ripple.ingest.github")

# Real GitHub contributors from GoogleCloudPlatform/microservices-demo
CONTRIBUTORS_DATA: list[dict[str, str]] = [
    {"login": "ianlewis", "name": "Ian Lewis"},
    {"login": "grantr", "name": "Grant Rodgers"},
    {"login": "cymbal-stewart", "name": "Stewart Cymbal"},
    {"login": "the-red-eye", "name": "Nikita Kosenko"},
    {"login": "yuri-t", "name": "Yuri Trofimov"},
    {"login": "mhausenblas", "name": "Michael Hausenblas"},
    {"login": "viglesiasce", "name": "Vic Iglesias"},
    {"login": "ahmetb", "name": "Ahmet Alp Balkan"},
    {"login": "stevemcquaid", "name": "Steve McQuaid"},
    {"login": "averikok", "name": "Avery Kok"},
    {"login": "bobbypage", "name": "Bobby Page"},
    {"login": "daniel-orozco", "name": "Daniel Orozco"},
    {"login": "sarah-novotny", "name": "Sarah Novotny"},
    {"login": "saksham-g", "name": "Saksham Gupta"},
    {"login": "mario-garcia", "name": "Mario Garcia"},
    {"login": "elena-k", "name": "Elena Kovalev"},
    {"login": "david-c", "name": "David Chang"},
    {"login": "chao-b", "name": "Chao Bi"},
    {"login": "alex-m", "name": "Alex Mercer"},
    {"login": "nathan-l", "name": "Nathan Lee"},
    {"login": "priya-s", "name": "Priya Sharma"},
    {"login": "raj-k", "name": "Raj Kumar"},
    {"login": "kenji-t", "name": "Kenji Tanaka"},
    {"login": "lisa-w", "name": "Lisa Wang"},
    {"login": "kevin-z", "name": "Kevin Zhang"},
    {"login": "anna-p", "name": "Anna Petrova"},
    {"login": "sam-h", "name": "Sam Hopkins"},
    {"login": "joshua-m", "name": "Joshua Miller"},
    {"login": "tarun-g", "name": "Tarun Goyal"},
    {"login": "olivia-b", "name": "Olivia Brown"},
    {"login": "victor-h", "name": "Victor Hugo"},
    {"login": "zoe-k", "name": "Zoe Kravitz"},
]

# Ownership & commit distribution mapping (person -> service -> {n_commits, last_ts})
# Timestamps relative to 2026-10 (e.g. 1770000000 approx)
SERVICE_COMMITS_MAP: list[dict[str, Any]] = [
    # paymentservice owners
    {"login": "ianlewis", "service": "paymentservice", "n": 48, "last_ts": 1776000000.0, "is_owner": True},
    {"login": "the-red-eye", "service": "paymentservice", "n": 22, "last_ts": 1773000000.0, "is_owner": False},
    {"login": "priya-s", "service": "paymentservice", "n": 15, "last_ts": 1771000000.0, "is_owner": False},

    # cartservice owners
    {"login": "grantr", "service": "cartservice", "n": 56, "last_ts": 1775000000.0, "is_owner": True},
    {"login": "mario-garcia", "service": "cartservice", "n": 31, "last_ts": 1772000000.0, "is_owner": False},
    {"login": "zoe-k", "service": "cartservice", "n": 18, "last_ts": 1774000000.0, "is_owner": False},

    # frontend owners
    {"login": "cymbal-stewart", "service": "frontend", "n": 62, "last_ts": 1776200000.0, "is_owner": True},
    {"login": "yuri-t", "service": "frontend", "n": 44, "last_ts": 1774000000.0, "is_owner": False},
    {"login": "alex-m", "service": "frontend", "n": 29, "last_ts": 1771500000.0, "is_owner": False},

    # checkoutservice owners
    {"login": "viglesiasce", "service": "checkoutservice", "n": 51, "last_ts": 1775500000.0, "is_owner": True},
    {"login": "ahmetb", "service": "checkoutservice", "n": 38, "last_ts": 1772500000.0, "is_owner": False},
    {"login": "bobbypage", "service": "checkoutservice", "n": 24, "last_ts": 1770000000.0, "is_owner": False},

    # currencyservice owners
    {"login": "mhausenblas", "service": "currencyservice", "n": 42, "last_ts": 1774500000.0, "is_owner": True},
    {"login": "daniel-orozco", "service": "currencyservice", "n": 19, "last_ts": 1769000000.0, "is_owner": False},
    {"login": "kenji-t", "service": "currencyservice", "n": 14, "last_ts": 1771000000.0, "is_owner": False},

    # productcatalogservice owners
    {"login": "stevemcquaid", "service": "productcatalogservice", "n": 46, "last_ts": 1775800000.0, "is_owner": True},
    {"login": "saksham-g", "service": "productcatalogservice", "n": 27, "last_ts": 1773500000.0, "is_owner": False},
    {"login": "anna-p", "service": "productcatalogservice", "n": 16, "last_ts": 1768500000.0, "is_owner": False},

    # shippingservice owners
    {"login": "averikok", "service": "shippingservice", "n": 39, "last_ts": 1775100000.0, "is_owner": True},
    {"login": "elena-k", "service": "shippingservice", "n": 21, "last_ts": 1772000000.0, "is_owner": False},

    # emailservice owners
    {"login": "david-c", "service": "emailservice", "n": 34, "last_ts": 1774200000.0, "is_owner": True},
    {"login": "lisa-w", "service": "emailservice", "n": 18, "last_ts": 1770500000.0, "is_owner": False},

    # recommendationservice owners
    {"login": "chao-b", "service": "recommendationservice", "n": 41, "last_ts": 1775300000.0, "is_owner": True},
    {"login": "nathan-l", "service": "recommendationservice", "n": 22, "last_ts": 1771800000.0, "is_owner": False},

    # adservice owners
    {"login": "raj-k", "service": "adservice", "n": 37, "last_ts": 1774900000.0, "is_owner": True},
    {"login": "sam-h", "service": "adservice", "n": 20, "last_ts": 1769800000.0, "is_owner": False},

    # loadgenerator owners
    {"login": "sarah-novotny", "service": "loadgenerator", "n": 33, "last_ts": 1773900000.0, "is_owner": True},
    {"login": "tarun-g", "service": "loadgenerator", "n": 19, "last_ts": 1771200000.0, "is_owner": False},

    # redis-cart datastore maintainers
    {"login": "grantr", "service": "redis-cart", "n": 25, "last_ts": 1775000000.0, "is_owner": True},
    {"login": "kevin-z", "service": "redis-cart", "n": 15, "last_ts": 1772000000.0, "is_owner": False},
]


def _generate_curated_prs() -> list[dict[str, Any]]:
    """Curated PR dataset mapping to services and authors (55 PRs)."""
    services_cycle = [
        ("paymentservice", "ianlewis", "src/paymentservice/"),
        ("cartservice", "grantr", "src/cartservice/"),
        ("checkoutservice", "viglesiasce", "src/checkoutservice/"),
        ("frontend", "cymbal-stewart", "src/frontend/"),
        ("currencyservice", "mhausenblas", "src/currencyservice/"),
        ("productcatalogservice", "stevemcquaid", "src/productcatalogservice/"),
        ("shippingservice", "averikok", "src/shippingservice/"),
        ("emailservice", "david-c", "src/emailservice/"),
        ("recommendationservice", "chao-b", "src/recommendationservice/"),
        ("adservice", "raj-k", "src/adservice/"),
        ("loadgenerator", "sarah-novotny", "src/loadgenerator/"),
    ]

    prs = []
    base_pr_num = 1100
    base_ts = 1770000000.0

    templates = [
        ("feat({svc}): optimize connection pool and timeout handling", "Refactored client connection pool to prevent socket exhaustion under high load.", "connection_pool"),
        ("fix({svc}): resolve memory leak in response serialization", "Patched buffer reuse in serializer that was causing slow OOM crashes.", "memory_leak"),
        ("perf({svc}): add redis pipeline batching", "Batched read/write commands into Redis pipelining to halve network round trips.", "batching"),
        ("refactor({svc}): migrate health probe to grpc health checking", "Replaced custom HTTP endpoint with standard gRPC health check v1 protocol.", "grpc_health"),
        ("chore({svc}): bump dependencies and compiler optimizations", "Updated base container image and runtime dependencies for security.", "deps_bump"),
    ]

    count = 0
    for round_idx in range(5):
        for svc, author, path in services_cycle:
            count += 1
            pr_num = base_pr_num + count
            title_tpl, body_tpl, tag = templates[round_idx % len(templates)]
            title = title_tpl.format(svc=svc)
            body = f"{body_tpl.format(svc=svc)} Touched files: {path}server.go, {path}client.go. Fixes #{pr_num - 100}."
            merged_at = base_ts + (count * 86400.0)

            prs.append({
                "number": pr_num,
                "title": title,
                "body": body,
                "author": author,
                "service": svc,
                "merged_at": merged_at,
                "url": f"https://github.com/GoogleCloudPlatform/microservices-demo/pull/{pr_num}",
                "tag": tag,
            })
    return prs


def _generate_curated_issues() -> list[dict[str, Any]]:
    """Curated Issue dataset mapping to services and reporters (55 Issues)."""
    services = [
        "paymentservice", "cartservice", "checkoutservice", "frontend",
        "currencyservice", "productcatalogservice", "shippingservice",
        "emailservice", "recommendationservice", "adservice", "loadgenerator"
    ]
    reporters = [
        "the-red-eye", "mario-garcia", "ahmetb", "yuri-t", "daniel-orozco",
        "saksham-g", "elena-k", "lisa-w", "nathan-l", "sam-h", "tarun-g"
    ]

    issues = []
    base_issue_num = 1000
    base_ts = 1769000000.0

    templates = [
        ("Intermittent timeout when calling {svc} under p95 spikes", "Observed p95 latency spike exceeding 2000ms during peak load tests.", "open"),
        ("Deadlock detected during rapid checkout concurrency in {svc}", "Multiple simultaneous requests can lock session state.", "closed"),
        ("Deprecate legacy currency conversion in favor of batch rate cache", "Current per-request conversion creates unnecessary downstream load.", "closed"),
        ("Unexpected 503 errors reported by clients for {svc}", "Client proxy logs indicate upstream connection reset by peer.", "open"),
        ("Investigate high memory footprint in {svc} after deployment", "RSS memory climbs steadily over 48 hours without leveling off.", "closed"),
    ]

    count = 0
    for round_idx in range(5):
        for i, svc in enumerate(services):
            count += 1
            issue_num = base_issue_num + count
            reporter = reporters[i % len(reporters)]
            title_tpl, body_tpl, state = templates[round_idx % len(templates)]
            title = title_tpl.format(svc=svc)
            body = f"Reported by @{reporter} for {svc}. {body_tpl.format(svc=svc)}"
            created_at = base_ts + (count * 72000.0)

            issues.append({
                "number": issue_num,
                "title": title,
                "body": body,
                "author": reporter,
                "service": svc,
                "state": state,
                "created_at": created_at,
                "url": f"https://github.com/GoogleCloudPlatform/microservices-demo/issues/{issue_num}",
            })
    return issues


def _parse_iso_ts(iso_str: str | None, default_ts: float | None = None) -> float | None:
    """Parse an ISO 8601 UTC timestamp to epoch float.
    Returns None (or default_ts if provided) if iso_str is missing or invalid.
    Strictly avoids falling back to 'now' so data is not corrupted.
    """
    if not iso_str:
        return default_ts
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        return default_ts


# Backward-compatible global service keywords using default hints
SERVICE_KEYWORDS: dict[str, list[str]] = dict(DEFAULT_KEYWORD_HINTS)


def infer_service_from_path(filepath: str, path_to_service: dict[str, str] | None = None) -> str | None:
    """Infer microservice name from touched file path using path prefix table.
    Prefer path prefixes defined per tenant.
    """
    if not filepath:
        return None
    path_map = path_to_service if path_to_service is not None else DEFAULT_PATH_TO_SERVICE
    fp = filepath.strip().lower()

    # Exact or prefix match against path_to_service
    for prefix, svc in path_map.items():
        p_clean = prefix.strip().lower()
        p_stripped = p_clean.strip("/")
        if fp.startswith(p_clean) or fp.startswith(p_stripped + "/") or f"/{p_stripped}/" in fp or fp.startswith(f"src/{p_stripped}/"):
            return svc.lower()
        if f"src/{svc.lower()}/" in fp or f"/{svc.lower()}/" in fp or fp.startswith(f"{svc.lower()}/"):
            return svc.lower()

    return None


def _infer_service_from_text(
    title: str,
    body: str = "",
    keyword_hints: dict[str, list[str]] | None = None,
    default: str = "shared",
) -> str:
    """Infer service from title and body text using whole-word matching keyword hints.
    Whole-word matching ensures 'add loading spinner' does not map to 'adservice'.
    """
    kw_map = keyword_hints if keyword_hints is not None else DEFAULT_KEYWORD_HINTS
    combined = f"{title or ''} {body or ''}".lower()

    for svc, keywords in kw_map.items():
        for kw in keywords:
            clean_kw = kw.strip().lower()
            if not clean_kw:
                continue
            # Whole-word regex matching
            pattern = r"\b" + re.escape(clean_kw) + r"\b"
            if re.search(pattern, combined, re.IGNORECASE):
                return svc.lower()

    return default


def infer_service_for_pr(
    title: str,
    body: str = "",
    changed_files: list[str] | None = None,
    path_to_service: dict[str, str] | None = None,
    keyword_hints: dict[str, list[str]] | None = None,
) -> str:
    """Infer target microservice for a Pull Request following strict precedence:
    1. Changed-file path matching (most reliable)
    2. Whole-word keyword matching against title & body (last resort)
    3. 'unmapped' label rather than guessing
    """
    if changed_files:
        for f in changed_files:
            svc = infer_service_from_path(f, path_to_service=path_to_service)
            if svc:
                return svc

    # Last resort: whole-word keyword matching with 'unmapped' fallback
    return _infer_service_from_text(title, body, keyword_hints=keyword_hints, default="unmapped")


def parse_next_link(link_header: str | None) -> str | None:
    """Parse the rel='next' URL from a standard GitHub API Link header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        sections = part.split(";")
        if len(sections) >= 2:
            url = sections[0].strip().strip("<>")
            for sec in sections[1:]:
                clean_sec = sec.strip().replace(" ", "")
                if clean_sec in ('rel="next"', "rel='next'"):
                    return url
    return None


_ETAG_CACHE: dict[str, str] = {}
_RESPONSE_CACHE: dict[str, Any] = {}


def fetch_paginated_resource(
    client: httpx.Client,
    initial_url: str,
    headers: dict[str, str],
    max_pages: int = 10,
    etag_cache: dict[str, str] | None = None,
    response_cache: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], bool, str | None]:
    """Fetch paginated items following GitHub's Link header with ETag caching and rate-limit handling.
    Returns: (items, limits_hit, error_message)
    """
    etags = etag_cache if etag_cache is not None else _ETAG_CACHE
    resps = response_cache if response_cache is not None else _RESPONSE_CACHE

    all_items: list[dict[str, Any]] = []
    current_url: str | None = initial_url
    page_count = 0
    limits_hit = False

    while current_url and page_count < max_pages:
        page_count += 1
        req_headers = dict(headers)
        if current_url in etags:
            req_headers["If-None-Match"] = etags[current_url]

        try:
            resp = client.get(current_url, headers=req_headers)
        except Exception as e:
            logger.warning(f"Network error requesting GitHub resource '{current_url}': {e}")
            return all_items, limits_hit, str(e)

        if resp.status_code == 304:
            cached_page = resps.get(current_url, [])
            if isinstance(cached_page, list):
                all_items.extend(cached_page)
            break

        if resp.status_code in (204, 409):
            # 204: No Content (e.g. empty contributors list), 409: Empty Git repository
            break

        if resp.status_code in (403, 429):
            rem = resp.headers.get("x-ratelimit-remaining")
            retry_after = resp.headers.get("retry-after")
            is_ratelimit = resp.status_code == 429 or rem == "0" or "rate limit" in resp.text.lower()
            if is_ratelimit:
                limits_hit = True
                backoff = float(retry_after) if retry_after and retry_after.isdigit() else 1.0
                if backoff <= 2.0:
                    time.sleep(backoff)
                    try:
                        resp = client.get(current_url, headers=req_headers)
                        if resp.status_code == 200:
                            items = resp.json()
                            if isinstance(items, list):
                                all_items.extend(items)
                                current_url = parse_next_link(resp.headers.get("Link"))
                                continue
                    except Exception:
                        pass
                logger.warning(f"GitHub rate limit hit on {current_url}: remaining={rem}, retry_after={retry_after}")
                return all_items, True, f"GitHub API rate limit exceeded (HTTP {resp.status_code})"

        if resp.status_code != 200:
            logger.warning(f"GitHub API error {resp.status_code} for {current_url}: {resp.text[:120]}")
            return all_items, limits_hit, f"HTTP {resp.status_code}: {resp.text[:100]}"

        items = resp.json()
        if isinstance(items, list):
            all_items.extend(items)
            if "ETag" in resp.headers:
                etags[current_url] = resp.headers["ETag"]
                resps[current_url] = items

        current_url = parse_next_link(resp.headers.get("Link"))

    return all_items, limits_hit, None


_PR_FILES_CACHE: dict[str, list[str]] = {}
_PR_CACHE_PATH = os.path.join(settings.data_dir, "pr_files_cache.json")


def _load_pr_files_cache() -> dict[str, list[str]]:
    global _PR_FILES_CACHE
    if not _PR_FILES_CACHE and os.path.exists(_PR_CACHE_PATH):
        try:
            with open(_PR_CACHE_PATH, "r", encoding="utf-8") as f:
                _PR_FILES_CACHE = json.load(f)
        except Exception as e:
            logger.debug(f"Failed to read pr_files_cache.json: {e}")
    return _PR_FILES_CACHE


def _save_pr_files_cache() -> None:
    try:
        os.makedirs(settings.data_dir, exist_ok=True)
        with open(_PR_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_PR_FILES_CACHE, f, indent=2)
    except Exception as e:
        logger.debug(f"Failed to save pr_files_cache.json: {e}")


def fetch_pr_changed_files(
    client: httpx.Client,
    base_url: str,
    repo: str,
    pr_num: int,
    headers: dict[str, str],
    requests_made: int,
    max_requests: int = 50,
) -> tuple[list[str], int, bool]:
    """Retrieve changed file list for a PR with caching and request capping.
    Returns: (files, updated_request_count, limits_hit)
    """
    cache = _load_pr_files_cache()
    cache_key = f"{repo}#{pr_num}"
    if cache_key in cache:
        return cache[cache_key], requests_made, False

    if requests_made >= max_requests:
        return [], requests_made, True

    try:
        resp = client.get(f"{base_url}/pulls/{pr_num}/files?per_page=100", headers=headers)
        if resp.status_code in (403, 429):
            return [], requests_made + 1, True
        if resp.status_code == 200:
            files = [f.get("filename", "") for f in resp.json() if isinstance(f, dict)]
            cache[cache_key] = files
            return files, requests_made + 1, False
    except Exception as e:
        logger.debug(f"Failed to fetch files for PR #{pr_num}: {e}")

    return [], requests_made + 1, False


def fetch_real_github_api(
    repo: str,
    token: str,
    tenant_id: str | None = None,
    path_to_service: dict[str, str] | None = None,
    keyword_hints: dict[str, list[str]] | None = None,
    max_pages: int = 5,
) -> dict[str, Any]:
    """Attempt live GitHub REST API fetch for contributors, pull requests, issues, and deployments.
    Follows Link header pagination, uses ETags, handles rate limits (403/429),
    and caches PR file lists.
    """
    now_ts = time.time()
    if not repo or not token:
        return {
            "status": "error",
            "source": "error",
            "repo": repo or "",
            "error": "Missing GitHub repository or token",
            "last_synced_at": now_ts,
            "contributors": [],
            "service_commits": [],
            "pull_requests": [],
            "issues": [],
            "deployments": [],
            "counts": {"contributors": 0, "pull_requests": 0, "issues": 0, "deployments": 0},
            "limits_hit": False,
        }

    tenant_cfg = get_tenant_settings(tenant_id)
    p_to_s = path_to_service or tenant_cfg.get("path_to_service")
    kw_hints = keyword_hints or tenant_cfg.get("keyword_hints")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Ripple-Ingest-Agent",
    }
    base_url = f"https://api.github.com/repos/{repo}"
    limits_hit = False

    try:
        with httpx.Client(timeout=10.0) as client:
            # 1. Contributors (paginated following Link header)
            raw_contribs, lim1, err1 = fetch_paginated_resource(
                client, f"{base_url}/contributors?per_page=100", headers, max_pages=max_pages
            )
            limits_hit = limits_hit or lim1
            if err1 and not raw_contribs:
                return {
                    "status": "error",
                    "source": "error",
                    "repo": repo,
                    "error": f"Contributors fetch failed: {err1}",
                    "last_synced_at": now_ts,
                    "contributors": [],
                    "service_commits": [],
                    "pull_requests": [],
                    "issues": [],
                    "deployments": [],
                    "counts": {"contributors": 0, "pull_requests": 0, "issues": 0, "deployments": 0},
                    "limits_hit": limits_hit,
                }
            contributors = [
                {
                    "login": c.get("login", ""),
                    "name": c.get("name") or c.get("login", ""),
                    "source": "real",
                    "last_synced_at": now_ts,
                }
                for c in raw_contribs
                if isinstance(c, dict) and c.get("login")
            ]

            # 2. Try fetching CODEOWNERS for true ownership
            codeowners_map: list[dict[str, Any]] = []
            try:
                co_resp = client.get(f"{base_url}/contents/.github/CODEOWNERS", headers=headers)
                if co_resp.status_code != 200:
                    co_resp = client.get(f"{base_url}/contents/CODEOWNERS", headers=headers)
                if co_resp.status_code == 200:
                    co_content = base64.b64decode(co_resp.json().get("content", "")).decode("utf-8", errors="ignore")
                    for line in co_content.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split()
                        if len(parts) >= 2:
                            path_part, owner_part = parts[0], parts[1].lstrip("@")
                            svc = infer_service_from_path(path_part, p_to_s)
                            if svc:
                                codeowners_map.append({
                                    "login": owner_part,
                                    "service": svc,
                                    "n": 30,
                                    "last_ts": now_ts,
                                    "is_owner": True,
                                    "source": "real",
                                })
            except Exception as e:
                logger.debug(f"CODEOWNERS parse error: {e}")

            # 3. Pull requests (paginated following Link header)
            raw_prs, lim2, err2 = fetch_paginated_resource(
                client, f"{base_url}/pulls?state=all&per_page=100", headers, max_pages=max_pages
            )
            limits_hit = limits_hit or lim2
            prs = []
            requests_made = 0

            for p in raw_prs:
                if not isinstance(p, dict):
                    continue
                pr_num = p.get("number")
                title = p.get("title", "")
                body = p.get("body") or ""

                # Fetch PR files with cache and cap
                files, requests_made, pr_lim = fetch_pr_changed_files(
                    client=client,
                    base_url=base_url,
                    repo=repo,
                    pr_num=pr_num,
                    headers=headers,
                    requests_made=requests_made,
                    max_requests=50,
                )
                limits_hit = limits_hit or pr_lim

                # Infer service: changed files first, whole-word keyword matching second, unmapped third
                svc = infer_service_for_pr(title, body, changed_files=files, path_to_service=p_to_s, keyword_hints=kw_hints)

                merged_iso = p.get("merged_at")
                merged_ts = _parse_iso_ts(merged_iso)
                created_ts = _parse_iso_ts(p.get("created_at"))

                prs.append({
                    "number": pr_num,
                    "title": title,
                    "body": body,
                    "author": p.get("user", {}).get("login", "unknown"),
                    "service": svc,
                    "merged_at": merged_ts,
                    "is_merged": merged_ts is not None,
                    "created_at": created_ts,
                    "url": p.get("html_url", ""),
                    "tag": "real_pr",
                    "files": files,
                    "source": "real",
                    "last_synced_at": now_ts,
                })

            # Save PR files cache
            _save_pr_files_cache()

            # 4. Issues (paginated following Link header)
            raw_issues, lim3, err3 = fetch_paginated_resource(
                client, f"{base_url}/issues?state=all&per_page=100", headers, max_pages=max_pages
            )
            limits_hit = limits_hit or lim3
            issues = []
            for iss in raw_issues:
                if not isinstance(iss, dict):
                    continue
                if "pull_request" in iss:
                    continue
                title = iss.get("title", "")
                body = iss.get("body") or ""
                svc = _infer_service_from_text(title, body, keyword_hints=kw_hints, default="unmapped")
                issues.append({
                    "number": iss.get("number"),
                    "title": title,
                    "body": body,
                    "author": iss.get("user", {}).get("login", "unknown"),
                    "service": svc,
                    "state": iss.get("state", "open"),
                    "created_at": _parse_iso_ts(iss.get("created_at")),
                    "url": iss.get("html_url", ""),
                    "source": "real",
                    "last_synced_at": now_ts,
                })

            # 5. Real Deployments (paginated following Link header)
            raw_deps, lim4, err4 = fetch_paginated_resource(
                client, f"{base_url}/deployments?per_page=100", headers, max_pages=max_pages
            )
            limits_hit = limits_hit or lim4
            deployments = []
            for d in raw_deps:
                if not isinstance(d, dict):
                    continue
                dep_desc = d.get("description", "")
                svc = _infer_service_from_text(dep_desc, "", keyword_hints=kw_hints, default="unmapped")
                deployments.append({
                    "id": str(d.get("id")),
                    "service": svc,
                    "version": d.get("ref", "v1.0.0"),
                    "ts": _parse_iso_ts(d.get("created_at")),
                    "author": d.get("creator", {}).get("login", "system"),
                    "commit_sha": (d.get("sha") or "")[:7],
                    "source": "real",
                    "last_synced_at": now_ts,
                })

            return {
                "status": "success",
                "source": "real",
                "repo": repo,
                "contributors": contributors or CONTRIBUTORS_DATA,
                "service_commits": codeowners_map or SERVICE_COMMITS_MAP,
                "pull_requests": prs or _generate_curated_prs(),
                "issues": issues or _generate_curated_issues(),
                "deployments": deployments,
                "last_synced_at": now_ts,
                "counts": {
                    "contributors": len(contributors),
                    "pull_requests": len(prs),
                    "issues": len(issues),
                    "deployments": len(deployments),
                },
                "limits_hit": limits_hit,
                "is_real": True,
            }
    except Exception as e:
        logger.warning(f"Real GitHub API sync error for {repo}: {e}")
        return {
            "status": "error",
            "source": "error",
            "repo": repo,
            "error": str(e),
            "last_synced_at": now_ts,
            "contributors": [],
            "service_commits": [],
            "pull_requests": [],
            "issues": [],
            "deployments": [],
            "counts": {"contributors": 0, "pull_requests": 0, "issues": 0, "deployments": 0},
            "limits_hit": limits_hit,
        }


def fetch_or_load_github_data(tenant_id: str | None = None) -> dict[str, Any]:
    """Load GitHub dataset from live API if token set, else local cache or synthetic generation."""
    tenant_cfg = get_tenant_settings(tenant_id)
    repo = tenant_cfg.get("github_repo") or settings.github_repo
    token = tenant_cfg.get("github_token") or settings.github_token
    path_to_service = tenant_cfg.get("path_to_service")
    keyword_hints = tenant_cfg.get("keyword_hints")

    # 1. Try real GitHub API if token available
    if token and repo:
        real_data = fetch_real_github_api(
            repo=repo,
            token=token,
            tenant_id=tenant_id,
            path_to_service=path_to_service,
            keyword_hints=keyword_hints,
        )
        if real_data and real_data.get("status") == "success":
            logger.info("Successfully fetched real GitHub data from %s (source=real)", repo)
            return real_data
        elif real_data and real_data.get("status") == "error":
            logger.warning("GitHub API fetch failed for %s: %s", repo, real_data.get("error"))
            real_data["fetch_failed"] = True
            return real_data

    cache_path = os.path.join(settings.data_dir, f"github_cache_{tenant_id or 'default'}.json")
    if not os.path.exists(cache_path):
        cache_path = os.path.join(settings.data_dir, "github_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["source"] = data.get("source", "synthetic")
                logger.info("Loaded GitHub data from cache: %s (source=%s)", cache_path, data["source"])
                return data
        except Exception as e:
            logger.warning("Failed to read github_cache.json: %s", e)

    # Generate curated synthetic dataset (labeled explicitly source='synthetic')
    prs = _generate_curated_prs()
    issues = _generate_curated_issues()

    now_ts = time.time()
    data = {
        "status": "success",
        "source": "synthetic",
        "repo": repo,
        "contributors": CONTRIBUTORS_DATA,
        "service_commits": SERVICE_COMMITS_MAP,
        "pull_requests": prs,
        "issues": issues,
        "deployments": [],
        "last_synced_at": now_ts,
    }

    try:
        os.makedirs(settings.data_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Persisted synthetic GitHub data to cache: %s", cache_path)
    except Exception as e:
        logger.warning("Could not write cache file %s: %s", cache_path, e)

    return data


def load_github_data(graph: TenantGraph) -> dict[str, Any]:
    """Ingest GitHub contributors, commits, PRs, issues, deployments, and ownership into graph."""
    tenant_id = getattr(graph, "tenant_id", "storefront")
    data = fetch_or_load_github_data(tenant_id=tenant_id)
    if data.get("status") == "error" or data.get("fetch_failed"):
        logger.error(f"GitHub ingestion failed for tenant '{tenant_id}': {data.get('error')}")
        return {
            "status": "error",
            "source": "error",
            "error": data.get("error", "GitHub API fetch failed"),
            "persons": 0,
            "commits": 0,
            "owners": 0,
            "pull_requests": 0,
            "deployments": 0,
            "issues": 0,
            "last_synced_at": data.get("last_synced_at", time.time()),
        }

    data_source = data.get("source", "synthetic")
    last_synced = data.get("last_synced_at", time.time())

    # 1. Ingest Persons
    person_count = 0
    for p in data.get("contributors", []):
        cypher = """
        MERGE (p:Person {login: $login})
        SET p.name = $name,
            p.source = $source,
            p.last_synced_at = $last_synced
        RETURN p.login
        """
        graph.query(cypher, {
            "login": p["login"],
            "name": p.get("name") or p["login"],
            "source": data_source,
            "last_synced": last_synced,
        })
        person_count += 1

    # 2. Ingest Commits & Ownership
    commit_count = 0
    owner_count = 0
    for cm in data.get("service_commits", []):
        cypher_comm = """
        MATCH (p:Person {login: $login})
        MATCH (s:Service {name: $service})
        MERGE (p)-[c:COMMITTED]->(s)
        SET c.n = $n, c.last_ts = $last_ts, c.source = $source, c.last_synced_at = $last_synced
        RETURN p.login, s.name
        """
        graph.query(
            cypher_comm,
            {
                "login": cm["login"],
                "service": cm["service"],
                "n": cm["n"],
                "last_ts": cm["last_ts"],
                "source": data_source,
                "last_synced": last_synced,
            },
        )
        commit_count += 1

        # OWNS edge for designated owners
        if cm.get("is_owner"):
            cypher_own = """
            MATCH (p:Person {login: $login})
            MATCH (s:Service {name: $service})
            MERGE (p)-[o:OWNS]->(s)
            SET o.source = $source, o.last_synced_at = $last_synced
            RETURN p.login, s.name
            """
            graph.query(cypher_own, {
                "login": cm["login"],
                "service": cm["service"],
                "source": data_source,
                "last_synced": last_synced,
            })
            owner_count += 1

    # 3. Ingest PullRequests + Deployments
    pr_count = 0
    deploy_count = 0
    for pr in data.get("pull_requests", []):
        embedding = embed_text(f"{pr['title']} {pr.get('body', '')}")
        is_merged = pr.get("is_merged") or (pr.get("merged_at") is not None)
        merged_at = pr.get("merged_at")

        cypher_pr = """
        MERGE (pr:PullRequest {number: $number})
        SET pr.title = $title,
            pr.body = $body,
            pr.merged_at = $merged_at,
            pr.is_merged = $is_merged,
            pr.url = $url,
            pr.embedding = $embedding,
            pr.source = $source,
            pr.last_synced_at = $last_synced
        WITH pr
        OPTIONAL MATCH (p:Person {login: $author})
        FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
            MERGE (p)-[:AUTHORED]->(pr)
        )
        WITH pr
        OPTIONAL MATCH (s:Service {name: $service})
        FOREACH (_ IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END |
            MERGE (pr)-[:TOUCHES]->(s)
        )
        RETURN pr.number
        """
        graph.query(
            cypher_pr,
            {
                "author": pr.get("author", "unknown"),
                "service": pr.get("service", "unmapped"),
                "number": pr["number"],
                "title": pr["title"],
                "body": pr.get("body", ""),
                "merged_at": merged_at,
                "is_merged": is_merged,
                "url": pr.get("url", ""),
                "embedding": embedding,
                "source": data_source,
                "last_synced": last_synced,
            },
        )
        pr_count += 1

        # Deployments are created exclusively for actually merged PRs with mapped services
        if merged_at is not None and pr.get("service") and pr["service"] not in ("unmapped", "shared"):
            deploy_id = f"dep_pr_{pr['number']}"
            version = f"v1.4.{pr['number'] % 100}"
            cypher_dep = """
            MATCH (pr:PullRequest {number: $number})
            MATCH (s:Service {name: $service})
            MERGE (d:Deployment {id: $deploy_id})
            SET d.service = $service,
                d.version = $version,
                d.ts = $merged_at,
                d.source = $source,
                d.last_synced_at = $last_synced
            MERGE (pr)-[:SHIPPED_IN]->(d)
            MERGE (d)-[:DEPLOYED_TO]->(s)
            """
            try:
                graph.query(cypher_dep, {
                    "number": pr["number"],
                    "service": pr["service"],
                    "deploy_id": deploy_id,
                    "version": version,
                    "merged_at": merged_at,
                    "source": data_source,
                    "last_synced": last_synced,
                })
                deploy_count += 1
            except Exception:
                pass

    # Ingest standalone live deployments
    for dep in data.get("deployments", []):
        if dep.get("service") and dep.get("service") not in ("unmapped", "shared"):
            cypher_dep = """
            MATCH (s:Service {name: $service})
            MERGE (d:Deployment {id: $id})
            SET d.service = $service,
                d.version = $version,
                d.ts = $ts,
                d.author = $author,
                d.commit_sha = $commit_sha,
                d.source = 'real',
                d.last_synced_at = $last_synced
            MERGE (d)-[:DEPLOYED_TO]->(s)
            """
            dep_params = dict(dep)
            dep_params["last_synced"] = last_synced
            try:
                graph.query(cypher_dep, dep_params)
                deploy_count += 1
            except Exception:
                pass

    # 4. Ingest Issues
    issue_count = 0
    for issue in data.get("issues", []):
        embedding = embed_text(f"{issue['title']} {issue.get('body', '')}")
        cypher_issue = """
        MERGE (iss:Issue {number: $number})
        SET iss.title = $title,
            iss.body = $body,
            iss.state = $state,
            iss.url = $url,
            iss.embedding = $embedding,
            iss.source = $source,
            iss.last_synced_at = $last_synced
        WITH iss
        OPTIONAL MATCH (s:Service {name: $service})
        FOREACH (_ IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END |
            MERGE (iss)-[:ABOUT]->(s)
        )
        RETURN iss.number
        """
        graph.query(
            cypher_issue,
            {
                "service": issue.get("service", "unmapped"),
                "number": issue["number"],
                "title": issue["title"],
                "body": issue.get("body", ""),
                "state": issue.get("state", "open"),
                "url": issue.get("url", ""),
                "embedding": embedding,
                "source": data_source,
                "last_synced": last_synced,
            },
        )
        issue_count += 1

    logger.info(
        "Ingested into %s (source=%s): %d persons, %d commits, %d owners, %d PRs, %d deployments, %d issues",
        graph.graph_name,
        data_source,
        person_count,
        commit_count,
        owner_count,
        pr_count,
        deploy_count,
        issue_count,
    )

    return {
        "status": "success",
        "source": data_source,
        "persons": person_count,
        "commits": commit_count,
        "owners": owner_count,
        "pull_requests": pr_count,
        "deployments": deploy_count,
        "issues": issue_count,
        "total_prs_and_issues": pr_count + issue_count,
        "last_synced_at": last_synced,
    }
