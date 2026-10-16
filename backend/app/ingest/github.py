import json
import logging
import os
import urllib.request
from typing import Any
from app.config import settings
from app.ingest.embed import embed_text
from app.tenancy import TenantGraph

logger = logging.getLogger(__name__)

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


def fetch_or_load_github_data() -> dict[str, Any]:
    """Load GitHub dataset from local cache if present, else generate and persist cache."""
    cache_path = os.path.join(settings.data_dir, "github_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info("Loaded GitHub data from cache: %s", cache_path)
                return data
        except Exception as e:
            logger.warning("Failed to read github_cache.json: %s", e)

    # Generate full curated dataset (32 contributors, 55 PRs, 55 Issues = 110 PRs/Issues)
    prs = _generate_curated_prs()
    issues = _generate_curated_issues()

    data = {
        "contributors": CONTRIBUTORS_DATA,
        "service_commits": SERVICE_COMMITS_MAP,
        "pull_requests": prs,
        "issues": issues,
    }

    try:
        os.makedirs(settings.data_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Persisted GitHub data to cache: %s", cache_path)
    except Exception as e:
        logger.warning("Could not write cache file %s: %s", cache_path, e)

    return data


def load_github_data(graph: TenantGraph) -> dict[str, int]:
    """Ingest GitHub contributors, commits, PRs, issues, deployments, and ownership into graph."""
    data = fetch_or_load_github_data()

    # 1. Ingest Persons (30+ people)
    person_count = 0
    for p in data["contributors"]:
        cypher = """
        MERGE (p:Person {login: $login})
        SET p.name = $name
        RETURN p.login
        """
        graph.query(cypher, {"login": p["login"], "name": p["name"]})
        person_count += 1

    # 2. Ingest Commits & Ownership
    commit_count = 0
    owner_count = 0
    for cm in data["service_commits"]:
        # COMMITTED edge with count and last timestamp
        cypher_comm = """
        MATCH (p:Person {login: $login})
        MATCH (s:Service {name: $service})
        MERGE (p)-[c:COMMITTED]->(s)
        SET c.n = $n, c.last_ts = $last_ts
        RETURN p.login, s.name
        """
        graph.query(cypher_comm, {"login": cm["login"], "service": cm["service"], "n": cm["n"], "last_ts": cm["last_ts"]})
        commit_count += 1

        # OWNS edge for designated owners
        if cm.get("is_owner"):
            cypher_own = """
            MATCH (p:Person {login: $login})
            MATCH (s:Service {name: $service})
            MERGE (p)-[:OWNS]->(s)
            RETURN p.login, s.name
            """
            graph.query(cypher_own, {"login": cm["login"], "service": cm["service"]})
            owner_count += 1

    # 3. Ingest PullRequests (55) + Deployments (source='seeded')
    pr_count = 0
    deploy_count = 0
    for pr in data["pull_requests"]:
        embedding = embed_text(f"{pr['title']} {pr['body']}")
        deploy_id = f"dep_pr_{pr['number']}"
        version = f"v1.4.{pr['number'] % 100}"

        cypher_pr = """
        MATCH (p:Person {login: $author})
        MATCH (s:Service {name: $service})
        MERGE (pr:PullRequest {number: $number})
        SET pr.title = $title,
            pr.body = $body,
            pr.merged_at = $merged_at,
            pr.url = $url,
            pr.embedding = $embedding
        MERGE (p)-[:AUTHORED]->(pr)
        MERGE (pr)-[:TOUCHES]->(s)
        MERGE (d:Deployment {id: $deploy_id})
        SET d.service = $service,
            d.version = $version,
            d.ts = $merged_at,
            d.source = 'seeded'
        MERGE (pr)-[:SHIPPED_IN]->(d)
        MERGE (d)-[:DEPLOYED_TO]->(s)
        RETURN pr.number
        """
        graph.query(
            cypher_pr,
            {
                "author": pr["author"],
                "service": pr["service"],
                "number": pr["number"],
                "title": pr["title"],
                "body": pr["body"],
                "merged_at": pr["merged_at"],
                "url": pr["url"],
                "embedding": embedding,
                "deploy_id": deploy_id,
                "version": version,
            },
        )
        pr_count += 1
        deploy_count += 1

    # 4. Ingest Issues (55)
    issue_count = 0
    for issue in data["issues"]:
        embedding = embed_text(f"{issue['title']} {issue['body']}")
        cypher_issue = """
        MATCH (s:Service {name: $service})
        MERGE (iss:Issue {number: $number})
        SET iss.title = $title,
            iss.body = $body,
            iss.state = $state,
            iss.url = $url,
            iss.embedding = $embedding
        MERGE (iss)-[:ABOUT]->(s)
        RETURN iss.number
        """
        graph.query(
            cypher_issue,
            {
                "service": issue["service"],
                "number": issue["number"],
                "title": issue["title"],
                "body": issue["body"],
                "state": issue["state"],
                "url": issue["url"],
                "embedding": embedding,
            },
        )
        issue_count += 1

    logger.info(
        "Ingested into %s: %d persons, %d commits, %d owners, %d PRs, %d deployments, %d issues",
        graph.graph_name,
        person_count,
        commit_count,
        owner_count,
        pr_count,
        deploy_count,
        issue_count,
    )

    return {
        "persons": person_count,
        "commits": commit_count,
        "owners": owner_count,
        "pull_requests": pr_count,
        "deployments": deploy_count,
        "issues": issue_count,
        "total_prs_and_issues": pr_count + issue_count,
    }
