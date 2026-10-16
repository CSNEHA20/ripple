import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCENARIOS_CACHE: dict[str, dict[str, Any]] | None = None
_RUNBOOKS_CACHE: dict[str, dict[str, Any]] | None = None


def _find_data_file(filename: str) -> Path:
    """Find data JSON file across docker and local working directories."""
    candidates = [
        Path("/app/data") / filename,
        Path(__file__).resolve().parent.parent.parent.parent / "data" / filename,
        Path(__file__).resolve().parent.parent.parent / "data" / filename,
        Path.cwd() / "data" / filename,
        Path.cwd() / "backend" / "data" / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Could not locate '{filename}' in candidate paths: {[str(p) for p in candidates]}")


def load_catalog_data() -> dict[str, dict[str, Any]]:
    """Load scenarios from disk into in-memory cache."""
    global _SCENARIOS_CACHE
    if _SCENARIOS_CACHE is not None:
        return _SCENARIOS_CACHE

    try:
        path = _find_data_file("scenarios.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            scenarios_list = data.get("scenarios", [])
            _SCENARIOS_CACHE = {sc["id"]: sc for sc in scenarios_list}
            logger.info("Loaded %d scenarios from %s", len(_SCENARIOS_CACHE), path)
            return _SCENARIOS_CACHE
    except Exception as e:
        logger.error("Failed to load scenarios.json: %s", e)
        _SCENARIOS_CACHE = {}
        return _SCENARIOS_CACHE


def load_runbooks_data() -> dict[str, dict[str, Any]]:
    """Load runbooks from disk into in-memory cache."""
    global _RUNBOOKS_CACHE
    if _RUNBOOKS_CACHE is not None:
        return _RUNBOOKS_CACHE

    try:
        path = _find_data_file("runbooks.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            rb_list = data.get("runbooks", [])
            _RUNBOOKS_CACHE = {rb["id"]: rb for rb in rb_list}
            logger.info("Loaded %d runbooks from %s", len(_RUNBOOKS_CACHE), path)
            return _RUNBOOKS_CACHE
    except Exception as e:
        logger.error("Failed to load runbooks.json: %s", e)
        _RUNBOOKS_CACHE = {}
        return _RUNBOOKS_CACHE


def get_scenario(scenario_id: str) -> dict[str, Any] | None:
    """Retrieve scenario definition by ID."""
    scenarios = load_catalog_data()
    return scenarios.get(scenario_id)


def list_scenarios(family: str | None = None) -> list[dict[str, Any]]:
    """List scenarios, optionally filtered by family."""
    scenarios = load_catalog_data()
    all_scenarios = list(scenarios.values())
    if family:
        return [sc for sc in all_scenarios if sc.get("family") == family]
    return all_scenarios


def get_runbook(runbook_id: str) -> dict[str, Any] | None:
    """Retrieve runbook definition by ID."""
    runbooks = load_runbooks_data()
    return runbooks.get(runbook_id)


def list_runbooks() -> list[dict[str, Any]]:
    """List all available runbooks."""
    runbooks = load_runbooks_data()
    return list(runbooks.values())
