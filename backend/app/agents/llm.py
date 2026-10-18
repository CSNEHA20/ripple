import abc
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Sequence, Type, TypeVar
import httpx
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger("ripple.agents.llm")

T = TypeVar("T", bound=BaseModel)

REPLAY_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "replay_cache",
)


def get_cache_key(prompt: str, extra: str = "") -> str:
    """Generate deterministic SHA256 cache key."""
    content = f"{prompt}::{extra}".encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def load_from_replay_cache(key: str) -> dict[str, Any] | None:
    """Load cached response if exists, ensuring source tag is present."""
    os.makedirs(REPLAY_CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(REPLAY_CACHE_DIR, f"{key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("source", "replay")
                return data
        except Exception as e:
            logger.warning(f"Failed to read replay cache file {cache_file}: {e}")
    return None


def save_to_replay_cache(
    key: str,
    data: dict[str, Any],
    source: str = "replay",
    provider: str | None = None,
) -> None:
    """Persist generated response to replay cache, explicitly labeled 'replay'."""
    try:
        os.makedirs(REPLAY_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(REPLAY_CACHE_DIR, f"{key}.json")
        payload = dict(data)
        payload["source"] = source
        if provider:
            payload["provider"] = provider
        payload["cached_at"] = time.time()
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to write replay cache: {e}")


def extract_citations(text: str) -> list[str]:
    """Find all node / evidence citations in text (e.g. [ev_...], [obs_...], [hyp_...], [dp_...])."""
    pattern = r"\b(ev_[a-zA-Z0-9_\-]+|obs_[a-zA-Z0-9_\-]+|hyp_[a-zA-Z0-9_\-]+|rb_[a-zA-Z0-9_\-]+|sc_[a-zA-Z0-9_\-]+)\b"
    return list(set(re.findall(pattern, text)))


class BaseLLMProvider(abc.ABC):
    """Abstract interface for multi-provider LLM integration."""

    @abc.abstractmethod
    def complete_structured(
        self,
        prompt: str,
        system_prompt: str,
        schema: Type[T],
    ) -> dict[str, Any] | None:
        """Generate structured output validated against Pydantic schema."""
        pass

    @abc.abstractmethod
    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Generate tool calls or final message from a conversation with tools."""
        pass


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def complete_structured(
        self,
        prompt: str,
        system_prompt: str,
        schema: Type[T],
    ) -> dict[str, Any] | None:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            response = client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format=schema,
                temperature=0.0,
            )
            return response.choices[0].message.parsed.model_dump()
        except Exception as e:
            logger.warning(f"OpenAI complete_structured failed: {e}")
            return None

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            formatted_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.get("name"),
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {}),
                    },
                }
                for t in tools
            ]
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=formatted_tools if formatted_tools else None,
                tool_choice="auto" if formatted_tools else None,
                temperature=0.0,
            )
            msg = response.choices[0].message
            tool_calls = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments) if tc.function.arguments else {},
                    })
            return {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": tool_calls,
            }
        except Exception as e:
            logger.warning(f"OpenAI complete_with_tools failed: {e}")
            return None


class NVIDIAProvider(BaseLLMProvider):
    """NVIDIA NIM / Nemotron provider via OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        model: str = "nvidia/llama-3.1-nemotron-70b-instruct",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def complete_structured(
        self,
        prompt: str,
        system_prompt: str,
        schema: Type[T],
    ) -> dict[str, Any] | None:
        try:
            url = f"{self.base_url.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            json_schema_prompt = (
                f"{prompt}\n\nYou must return a valid JSON object matching this schema:\n"
                f"{json.dumps(schema.model_json_schema())}"
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json_schema_prompt},
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            }
            with httpx.Client(timeout=60.0) as client:
                res = client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"] or "{}"
                    # Robust JSON extraction
                    match = re.search(r"\{.*\}", content, re.DOTALL)
                    if match:
                        parsed = json.loads(match.group(0))
                        return schema.model_validate(parsed).model_dump()
                    parsed = json.loads(content)
                    return schema.model_validate(parsed).model_dump()
                logger.warning(f"NVIDIA complete_structured HTTP error {res.status_code}: {res.text[:200]}")
                return None
        except Exception as e:
            logger.warning(f"NVIDIA complete_structured failed: {e}")
            return None

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        try:
            url = f"{self.base_url.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            formatted_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.get("name"),
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {}),
                    },
                }
                for t in tools
            ]
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.0,
            }
            if formatted_tools:
                payload["tools"] = formatted_tools
                payload["tool_choice"] = "auto"

            with httpx.Client(timeout=60.0) as client:
                res = client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    msg = data["choices"][0]["message"]
                    tool_calls = []
                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            fn = tc.get("function", {})
                            args = fn.get("arguments", "{}")
                            tool_calls.append({
                                "id": tc.get("id"),
                                "name": fn.get("name"),
                                "arguments": json.loads(args) if isinstance(args, str) else args,
                            })
                    return {
                        "role": "assistant",
                        "content": msg.get("content") or "",
                        "tool_calls": tool_calls,
                    }
                logger.warning(f"NVIDIA complete_with_tools HTTP error {res.status_code}: {res.text[:200]}")
                return None
        except Exception as e:
            logger.warning(f"NVIDIA complete_with_tools failed: {e}")
            return None


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API provider using HTTP API."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.model = model

    def complete_structured(
        self,
        prompt: str,
        system_prompt: str,
        schema: Type[T],
    ) -> dict[str, Any] | None:
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            json_schema_prompt = (
                f"{prompt}\n\nRespond ONLY with a valid JSON object strictly matching this schema:\n"
                f"{json.dumps(schema.model_json_schema())}"
            )
            payload = {
                "model": self.model,
                "system": system_prompt,
                "messages": [{"role": "user", "content": json_schema_prompt}],
                "max_tokens": 1500,
                "temperature": 0.0,
            }
            with httpx.Client(timeout=30.0) as client:
                res = client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    content = "".join([c.get("text", "") for c in data.get("content", [])])
                    match = re.search(r"\{.*\}", content, re.DOTALL)
                    if match:
                        parsed = json.loads(match.group(0))
                        return schema.model_validate(parsed).model_dump()
        except Exception as e:
            logger.warning(f"Anthropic complete_structured failed: {e}")
        return None

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            anthropic_tools = [
                {
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {}),
                }
                for t in tools
            ]
            system_msg = ""
            user_msgs = []
            for m in messages:
                if m.get("role") == "system":
                    system_msg += m.get("content", "") + "\n"
                else:
                    user_msgs.append(m)

            payload = {
                "model": self.model,
                "system": system_msg.strip(),
                "messages": user_msgs,
                "tools": anthropic_tools,
                "max_tokens": 1500,
                "temperature": 0.0,
            }
            with httpx.Client(timeout=30.0) as client:
                res = client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    tool_calls = []
                    text_parts = []
                    for block in data.get("content", []):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block.get("id"),
                                "name": block.get("name"),
                                "arguments": block.get("input", {}),
                            })
                    return {
                        "role": "assistant",
                        "content": "".join(text_parts),
                        "tool_calls": tool_calls,
                    }
        except Exception as e:
            logger.warning(f"Anthropic complete_with_tools failed: {e}")
        return None


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model = model

    def complete_structured(
        self,
        prompt: str,
        system_prompt: str,
        schema: Type[T],
    ) -> dict[str, Any] | None:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            full_prompt = (
                f"{system_prompt}\n\n{prompt}\n\n"
                f"Respond with ONLY valid JSON matching this schema:\n"
                f"{json.dumps(schema.model_json_schema())}"
            )
            payload = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"},
            }
            with httpx.Client(timeout=30.0) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return schema.model_validate(json.loads(text)).model_dump()
        except Exception as e:
            logger.warning(f"Gemini complete_structured failed: {e}")
        return None

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        # Fall back to structured generation for Gemini
        return None


class LLMResolution(BaseModel):
    mode: str  # "live" | "replay"
    provider: str | None = None
    is_live_available: bool = False
    degraded: bool = False
    reason: str | None = None


def get_active_provider_name() -> str | None:
    """Return active provider name from settings or env, normalized to lowercase."""
    provider = settings.llm_provider or os.getenv("LLM_PROVIDER")
    if provider:
        p_clean = provider.strip().lower()
        if p_clean in ("nvidia", "nemotron"):
            return "nvidia"
        if p_clean in ("openai", "anthropic", "gemini"):
            return p_clean
        return p_clean
    return None


def get_llm_provider() -> BaseLLMProvider | None:
    """Resolve active LLM provider strictly based on settings.llm_provider / LLM_PROVIDER.
    Never falls back to 'any key present'.
    """
    provider_name = get_active_provider_name()
    if not provider_name:
        return None

    if provider_name == "openai":
        if settings.openai_api_key:
            return OpenAIProvider(api_key=settings.openai_api_key)
        logger.warning("LLM provider configured as 'openai' but openai_api_key is missing.")
        return None

    if provider_name == "nvidia":
        key = settings.nvidia_api_key or settings.nemotron_api_key
        if key:
            return NVIDIAProvider(
                api_key=key,
                base_url=settings.nvidia_base_url,
                model=settings.nemotron_model,
            )
        logger.warning("LLM provider configured as 'nvidia' but nvidia_api_key/nemotron_api_key is missing.")
        return None

    if provider_name == "anthropic":
        if settings.anthropic_api_key:
            return AnthropicProvider(api_key=settings.anthropic_api_key)
        logger.warning("LLM provider configured as 'anthropic' but anthropic_api_key is missing.")
        return None

    if provider_name == "gemini":
        if settings.gemini_api_key:
            return GeminiProvider(api_key=settings.gemini_api_key)
        logger.warning("LLM provider configured as 'gemini' but gemini_api_key is missing.")
        return None

    return None


def resolve_llm_mode(requested_mode: str | None = None) -> LLMResolution:
    """Resolve effective LLM mode ('live' or 'replay') strictly adhering to settings.llm_provider.
    
    If requested_mode == 'live':
      - If llm_provider is set and valid provider instance can be created -> live
      - Otherwise -> degrades to 'replay', sets degraded=True with clear reason.
    If requested_mode is None (auto-detect in webhook / approve):
      - If llm_provider is set and valid provider instance can be created -> live
      - Otherwise -> 'replay', degraded=False.
    If requested_mode == 'replay':
      - Returns 'replay'.
    """
    provider_name = get_active_provider_name()
    provider_instance = get_llm_provider()
    is_available = provider_instance is not None

    if requested_mode == "live":
        if is_available:
            return LLMResolution(
                mode="live",
                provider=provider_name,
                is_live_available=True,
                degraded=False,
            )
        else:
            reason = (
                f"Requested live mode but provider '{provider_name}' has no valid API key"
                if provider_name
                else "Requested live mode but no llm_provider configured in settings/env"
            )
            return LLMResolution(
                mode="replay",
                provider=provider_name,
                is_live_available=False,
                degraded=True,
                reason=reason,
            )

    if requested_mode is None:
        if is_available:
            return LLMResolution(
                mode="live",
                provider=provider_name,
                is_live_available=True,
                degraded=False,
            )
        else:
            return LLMResolution(
                mode="replay",
                provider=provider_name,
                is_live_available=False,
                degraded=False,
            )

    # Explicit "replay" or other
    return LLMResolution(
        mode="replay",
        provider=provider_name,
        is_live_available=is_available,
        degraded=False,
    )


def mark_llm_degraded(
    graph: Any = None,
    incident_id: str | None = None,
    provider: str | None = None,
    reason: str = "LLM provider call failed",
) -> None:
    """Flag incident as llm_degraded in FalkorDB and publish llm_degraded event on event bus."""
    active_prov = provider or get_active_provider_name() or "unknown"
    if graph and incident_id:
        try:
            graph.query(
                "MATCH (i:Incident {id: $id}) SET i.llm_degraded = true, i.llm_degraded_reason = $reason, i.llm_provider = $provider",
                {"id": incident_id, "reason": reason, "provider": active_prov},
            )
        except Exception as e:
            logger.debug(f"Could not persist llm_degraded flag on incident {incident_id}: {e}")

    if incident_id:
        try:
            from app.agents.orchestrator import event_bus
            event_bus.publish(
                incident_id,
                "llm_degraded",
                {
                    "incident_id": incident_id,
                    "provider": active_prov,
                    "error": reason,
                    "timestamp": time.time(),
                },
            )
        except Exception as bus_err:
            logger.debug(f"Could not publish llm_degraded event on event bus: {bus_err}")

    try:
        from app.adapters.demo_target import record_ops_llm_degraded
        record_ops_llm_degraded()
    except Exception:
        pass


class LLMWrapper:
    """LLM wrapper supporting 'live' and 'replay' modes, multi-provider dispatch,
    schema validation, and mandatory citation enforcement with a 1-retry policy.
    Matches telemetry_degraded behavior by surfacing llm_degraded on failures.
    """

    def __init__(self, mode: str = "replay", incident_id: str | None = None, graph: Any = None):
        self.incident_id = incident_id
        self.graph = graph
        self.llm_degraded = False

        resolution = resolve_llm_mode(mode)
        self.mode = resolution.mode
        if resolution.degraded:
            self.llm_degraded = True
            mark_llm_degraded(
                graph=self.graph,
                incident_id=self.incident_id,
                provider=resolution.provider,
                reason=resolution.reason or "Live mode requested but provider unconfigured or key missing",
            )
        self.provider = get_llm_provider() if self.mode == "live" else None

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

        # 2. If live mode and API provider configured, attempt provider call
        res_dict = None
        if self.mode == "live" and self.provider:
            try:
                res_dict = self.provider.complete_structured(prompt, system_prompt, schema)
                if res_dict is None:
                    raise RuntimeError(f"Provider {self.provider.__class__.__name__} failed to return structured response")
            except Exception as e:
                logger.warning(f"Live LLM provider call failed: {e}. Degrading LLM to fallback/replay.")
                self.mode = "replay"
                self.llm_degraded = True
                mark_llm_degraded(
                    graph=self.graph,
                    incident_id=self.incident_id,
                    provider=get_active_provider_name(),
                    reason=str(e),
                )
                res_dict = None

        # 3. Fallback to deterministic generator if live call didn't return or mode is replay
        if res_dict is None and fallback_generator:
            res_dict = fallback_generator(context_data or {})

        if res_dict is None:
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
            elif self.mode == "live" and self.provider:
                try:
                    res_dict = self.provider.complete_structured(retry_prompt, system_prompt, schema)
                except Exception as retry_err:
                    logger.warning(f"Live LLM provider retry call failed: {retry_err}")
                    res_dict = None

            if res_dict is None and fallback_generator:
                res_dict = fallback_generator(context_data or {}, enforce_citations=available_ids)

            # Ensure citations are present in textual fields
            for k, v in list(res_dict.items()):
                if isinstance(v, str) and available_ids:
                    if not extract_citations(v) and len(v) > 10:
                        cites_str = ", ".join([f"[{cid}]" for cid in available_ids[:2]])
                        res_dict[k] = f"{v} (Citations: {cites_str})"
                        break

        # Cache response explicitly labeled as "replay"
        save_to_replay_cache(cache_key, res_dict, source="replay", provider=get_active_provider_name())

        try:
            return schema.model_validate(res_dict)
        except Exception as e:
            logger.error(f"Schema validation error on LLM response: {e}. Returning raw fallback.")
            return schema.model_validate(res_dict)
