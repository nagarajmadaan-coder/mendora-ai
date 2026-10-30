"""
AI providers. Each one turns a DiagnosisInput into the raw JSON dict described in prompts.DIAGNOSIS_JSON_SCHEMA.

- AnthropicProvider: Claude Messages API, using a forced tool call for structured output.
- OpenAIProvider:    OpenAI Chat Completions with a strict JSON schema. Also works with
                     OpenAI-compatible APIs by setting MENDORA_AI_BASE_URL.

To add another provider, write a class with `name`, `model` and `generate()`, and register it in service.py.
"""

import json
import re
import logging
import time
from typing import Protocol

from .errors import AIInvalidResponse, AIProviderError, AIRateLimited, AITimeout
from .http import HttpResponse, Transport
from .prompts import DIAGNOSIS_JSON_SCHEMA, SYSTEM_PROMPT, TOOL_NAME, DiagnosisInput, build_user_message

log = logging.getLogger("mendora.ai")

RETRYABLE_STATUSES = {500, 502, 503, 504, 529}


class DiagnosisProvider(Protocol):
    name: str
    model: str

    def generate(self, data: DiagnosisInput) -> dict: ...


def _post_with_retry(transport: Transport, url: str, headers: dict, payload: dict, timeout: float, provider: str) -> dict:
    """POST JSON; retry once on temporary server errors; turn HTTP problems into clear AI errors."""
    body = json.dumps(payload).encode("utf-8")
    response: HttpResponse | None = None
    for attempt in (1, 2):
        response = transport(url, headers, body, timeout)
        if response.status in RETRYABLE_STATUSES and attempt == 1:
            log.warning("%s returned %s; retrying once", provider, response.status)
            time.sleep(1.0)
            continue
        break
    assert response is not None

    if response.status == 200:
        try:
            return json.loads(response.body)
        except json.JSONDecodeError as exc:
            raise AIInvalidResponse(f"{provider} returned non-JSON body") from exc

    # Log the provider's error for the developer (without request content or keys).
    log.error("%s API error %s: %s", provider, response.status, response.body[:500])
    if response.status == 429:
        raise AIRateLimited(f"{provider} rate limit (429)")
    if response.status in (408, 504):
        raise AITimeout(f"{provider} gateway timeout ({response.status})")
    if response.status in (401, 403):
        raise AIProviderError(f"{provider} rejected the API key ({response.status}). Check the key in backend/.env.")
    raise AIProviderError(f"{provider} returned HTTP {response.status}")


class AnthropicProvider:
    name = "anthropic"
    DEFAULT_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self, *, api_key: str, model: str, transport: Transport, timeout: float, max_tokens: int, base_url: str | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._url = (base_url.rstrip("/") + "/v1/messages") if base_url else self.DEFAULT_URL

    def generate(self, data: DiagnosisInput) -> dict:
        payload = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": build_user_message(data)}],
            "tools": [
                {
                    "name": TOOL_NAME,
                    "description": "Submit the structured home-repair assessment.",
                    "input_schema": DIAGNOSIS_JSON_SCHEMA,
                }
            ],
            "tool_choice": {"type": "tool", "name": TOOL_NAME},
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        result = _post_with_retry(self._transport, self._url, headers, payload, self._timeout, self.name)

        if result.get("stop_reason") == "max_tokens":
            raise AIInvalidResponse("Anthropic response was cut off (max_tokens)")
        for block in result.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == TOOL_NAME:
                if isinstance(block.get("input"), dict):
                    return block["input"]
        raise AIInvalidResponse("Anthropic response contained no submit_diagnosis tool call")


def parse_json_content(text: str, provider: str) -> dict:
    """
    Read the model's JSON answer defensively. Some models wrap it in ```json fences or put
    <think>…</think> reasoning before it; only the JSON object itself is used.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise AIInvalidResponse(f"{provider} message content was not valid JSON") from None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIInvalidResponse(f"{provider} message content was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise AIInvalidResponse(f"{provider} JSON was not an object")
    return parsed


class OpenAIProvider:
    name = "openai"
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    TOKEN_PARAM = "max_completion_tokens"
    MIN_OUTPUT_TOKENS = 0

    def __init__(self, *, api_key: str, model: str, transport: Transport, timeout: float, max_tokens: int, base_url: str | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._url = (base_url or self.DEFAULT_BASE_URL).rstrip("/") + "/chat/completions"

    def generate(self, data: DiagnosisInput) -> dict:
        payload = {
            "model": self.model,
            self.TOKEN_PARAM: max(self._max_tokens, self.MIN_OUTPUT_TOKENS),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.replace("by calling the submit_diagnosis tool", "as JSON matching the schema")},
                {"role": "user", "content": build_user_message(data)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": TOOL_NAME, "strict": True, "schema": DIAGNOSIS_JSON_SCHEMA},
            },
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        result = _post_with_retry(self._transport, self._url, headers, payload, self._timeout, self.name)

        try:
            choice = result["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIInvalidResponse(f"{self.name} response missing choices[0].message") from exc
        if message.get("refusal"):
            raise AIInvalidResponse(f"{self.name} model refused the request")
        if choice.get("finish_reason") == "length":
            raise AIInvalidResponse(f"{self.name} response was cut off (length)")
        return parse_json_content(message.get("content") or "", self.name)


class NebiusProvider(OpenAIProvider):
    """
    Nebius Token Factory — an OpenAI-compatible API (https://docs.tokenfactory.nebius.com).
    Same request as OpenAI with response_format json_schema; uses `max_tokens`, and allows extra room
    because some models (e.g. reasoning models) spend tokens thinking before they answer.
    """

    name = "nebius"
    DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
    TOKEN_PARAM = "max_tokens"
    MIN_OUTPUT_TOKENS = 4000
