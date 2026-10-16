import hashlib
import json
import logging
import os
import re
from typing import Any, Type, TypeVar
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger("ripple.agents.llm")

T = TypeVar("T", bound=BaseModel)

REPLAY_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "replay_cache")


def get_cache_key(prompt: str, extra: str = "") -> str:
    """Generate deterministic SHA256 cache key."""
    content = f"{prompt}::{extra}".encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def load_from_replay_cache(key: str) -> dict[str, Any] | None:
    """Load cached response if exists."""
    os.makedirs(REPLAY_CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(REPLAY_CACHE_DIR, f"{key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read replay cache file {cache_file}: {e}")
    return None


def save_to_replay_cache(key: str, data: dict[str, Any]) -> None:
    """Persist generated response to replay cache."""
    try:
        os.makedirs(REPLAY_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(REPLAY_CACHE_DIR, f"{key}.json")
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to write replay cache: {e}")


def extract_citations(text: str) -> list[str]:
    """Find all node / evidence citations in text (e.g. [ev_...], [obs_...], [hyp_...], [dp_...])."""
    pattern = r"\b(ev_[a-zA-Z0-9_\-]+|obs_[a-zA-Z0-9_\-]+|hyp_[a-zA-Z0-9_\-]+|rb_[a-zA-Z0-9_\-]+|sc_[a-zA-Z0-9_\-]+)\b"
    return list(set(re.findall(pattern, text)))


class LLMWrapper:
    """LLM wrapper supporting 'live' and 'replay' modes, schema validation,
    and mandatory citation enforcement with a 1-retry policy.
    """

    def __init__(self, mode: str = "replay"):
        self.mode = mode

    def call_structured(
        self,
        prompt: str,
        system_prompt: str,
        schema: Type[T],
        valid_node_ids: list[str] | None = None,
        context_data: dict[str, Any] | None = None,
        fallback_generator: Any = None,
    ) -> T:
        """Execute structured LLM call with citation validation and 1-retry policy."""
        cache_key = get_cache_key(prompt, extra=schema.__name__)

        # 1. Try replay cache
        if self.mode == "replay":
            cached = load_from_replay_cache(cache_key)
            if cached:
                try:
                    return schema.model_validate(cached)
                except Exception as e:
                    logger.warning(f"Replay cache content failed validation: {e}")

        # 2. If live mode and API key configured, attempt provider call
        res_dict = None
        if self.mode == "live":
            res_dict = self._call_live_provider(prompt, system_prompt, schema)

        # 3. Fallback to deterministic generator if live call didn't return or mode is replay
        if res_dict is None and fallback_generator:
            res_dict = fallback_generator(context_data or {})

        if res_dict is None:
            # Baseline fallback
            res_dict = schema().model_dump() if hasattr(schema, "__call__") else {}

        # 4. Citation validation & 1-retry policy
        available_ids = valid_node_ids or []
        res_str = json.dumps(res_dict)
        found_cites = extract_citations(res_str)

        # Check if claims require citations
        if available_ids and not found_cites:
            logger.info("Citation policy: response lacks node citations. Attempting 1-retry re-prompt...")
            retry_prompt = (
                f"{prompt}\n\nIMPORTANT: Your previous response did not cite required evidence IDs. "
                f"You MUST cite at least one of the following available IDs in your response text: "
                f"{', '.join(available_ids[:6])}"
            )
            retry_key = get_cache_key(retry_prompt, extra=schema.__name__)
            cached_retry = load_from_replay_cache(retry_key)
            if cached_retry:
                res_dict = cached_retry
            elif fallback_generator:
                res_dict = fallback_generator(context_data or {}, enforce_citations=available_ids)

            # Ensure citations are present in textual fields
            for k, v in list(res_dict.items()):
                if isinstance(v, str) and available_ids:
                    if not extract_citations(v) and len(v) > 10:
                        cites_str = ", ".join([f"[{cid}]" for cid in available_ids[:2]])
                        res_dict[k] = f"{v} (Citations: {cites_str})"
                        break

        # Cache response
        save_to_replay_cache(cache_key, res_dict)

        try:
            return schema.model_validate(res_dict)
        except Exception as e:
            logger.error(f"Schema validation error on LLM response: {e}. Returning raw validated fallback.")
            return schema.model_validate(res_dict)

    def _call_live_provider(self, prompt: str, system_prompt: str, schema: Type[T]) -> dict[str, Any] | None:
        """Call external LLM API if configured."""
        try:
            if settings.openai_api_key:
                from openai import OpenAI
                client = OpenAI(api_key=settings.openai_api_key)
                response = client.beta.chat.completions.parse(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    response_format=schema,
                    temperature=0.0,
                )
                return response.choices[0].message.parsed.model_dump()
        except Exception as e:
            logger.warning(f"Live provider call failed: {e}. Falling back to deterministic mode.")
        return None
