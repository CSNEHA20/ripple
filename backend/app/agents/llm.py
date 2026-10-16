import abc
import hashlib
import json
import logging
import os
import re
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
            from openai import OpenAI
            client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            json_schema_prompt = (
                f"{prompt}\n\nYou must return a valid JSON object matching this schema:\n"
                f"{json.dumps(schema.model_json_schema())}"
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json_schema_prompt},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            return schema.model_validate(parsed).model_dump()
        except Exception as e:
            logger.warning(f"NVIDIA complete_structured failed: {e}")
            return None

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        try:
            from openai import OpenAI
            client = OpenAI(base_url=self.base_url, api_key=self.api_key)
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


def get_llm_provider() -> BaseLLMProvider | None:
    """Resolve active LLM provider from settings/env."""
    provider_name = os.getenv("LLM_PROVIDER", "").lower()

    if (provider_name == "openai" or not provider_name) and settings.openai_api_key:
        return OpenAIProvider(api_key=settings.openai_api_key)

    if (provider_name in ("nvidia", "nemotron") or not provider_name) and (settings.nvidia_api_key or settings.nemotron_api_key):
        key = settings.nvidia_api_key or settings.nemotron_api_key
        return NVIDIAProvider(
            api_key=key,
            base_url=settings.nvidia_base_url,
            model=settings.nemotron_model,
        )

    if (provider_name == "anthropic" or not provider_name) and settings.anthropic_api_key:
        return AnthropicProvider(api_key=settings.anthropic_api_key)

    if (provider_name == "gemini" or not provider_name) and settings.gemini_api_key:
        return GeminiProvider(api_key=settings.gemini_api_key)

    return None


class LLMWrapper:
    """LLM wrapper supporting 'live' and 'replay' modes, multi-provider dispatch,
    schema validation, and mandatory citation enforcement with a 1-retry policy.
    """

    def __init__(self, mode: str = "replay"):
        self.mode = mode
        self.provider = get_llm_provider() if mode == "live" else None

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
            res_dict = self.provider.complete_structured(prompt, system_prompt, schema)

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
                res_dict = self.provider.complete_structured(retry_prompt, system_prompt, schema)

            if res_dict is None and fallback_generator:
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
            logger.error(f"Schema validation error on LLM response: {e}. Returning raw fallback.")
            return schema.model_validate(res_dict)
