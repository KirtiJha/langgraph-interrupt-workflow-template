"""Model choice from the UI — bring your own model and key, per request.

The browser sends its model settings as headers on every API call::

    X-LLM-Provider:    anthropic | openai | google | gateway | openrouter | groq |
                       together | deepseek | ollama | custom | mock
    X-LLM-Model:       claude-sonnet-4-5            (provider-specific id)
    X-LLM-API-Key:     sk-…                         (the visitor's own key)
    X-LLM-Base-URL:    https://…/v1                 (custom endpoints only)
    X-LLM-Temperature: 0.2                          (optional)

:class:`ClientModelConfigMiddleware` validates them and makes them the model
for *that request only* (a ``ContextVar``), so every engine — workflow nodes,
the agent, the deep agent, the approval drafter, AG-UI — uses the visitor's
choice. Nothing is persisted, logged, or echoed back; omit the headers and the
server's environment-configured model is used.

Owner controls (environment):

- ``LLM_CLIENT_CONFIG=false`` — ignore UI model settings entirely.
- ``LLM_CLIENT_CAN_USE_SERVER_KEY=true`` — let a UI-chosen model fall back to
  the server's own key (fine for a personal deployment; off by default so a
  public demo can't spend the owner's credits on arbitrary models).
- ``LLM_CLIENT_ALLOW_PRIVATE_HOSTS`` — custom base URLs may not point at
  private / loopback / link-local addresses when deployed (``VERCEL`` set), to
  avoid turning the API into a proxy into internal networks. Defaults to
  allowed locally so ``http://localhost:11434`` (Ollama) works in development.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
from contextvars import ContextVar
from typing import Any, Optional
from urllib.parse import urlparse

from langchain.agents.middleware import AgentMiddleware

logger = logging.getLogger(__name__)

AI_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"

# id -> how to build it. ``model_provider`` is LangChain's init_chat_model name.
PROVIDERS: list[dict] = [
    {"id": "gateway", "env_key": "AI_GATEWAY_API_KEY", "label": "Vercel AI Gateway", "model_provider": "openai",
     "base_url": AI_GATEWAY_BASE_URL, "key_label": "AI Gateway API key",
     "models": ["anthropic/claude-sonnet-4.6", "openai/gpt-5", "google/gemini-2.5-pro",
                "xai/grok-4", "meta/llama-4-maverick"],
     "note": "One key, models from every provider."},
    {"id": "openai", "label": "OpenAI", "model_provider": "openai", "base_url": None,
     "key_label": "OpenAI API key", "models": ["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o-mini"]},
    {"id": "anthropic", "label": "Anthropic", "model_provider": "anthropic", "base_url": None,
     "key_label": "Anthropic API key", "models": ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"]},
    {"id": "google", "label": "Google Gemini", "model_provider": "google_genai", "base_url": None,
     "key_label": "Gemini API key", "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-3.5-flash"]},
    {"id": "openrouter", "env_key": "OPENROUTER_API_KEY", "label": "OpenRouter", "model_provider": "openai",
     "base_url": "https://openrouter.ai/api/v1", "key_label": "OpenRouter API key",
     "models": ["anthropic/claude-sonnet-4.5", "openai/gpt-5", "meta-llama/llama-3.3-70b-instruct"]},
    {"id": "groq", "env_key": "GROQ_API_KEY", "label": "Groq", "model_provider": "openai",
     "base_url": "https://api.groq.com/openai/v1", "key_label": "Groq API key",
     "models": ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]},
    {"id": "together", "env_key": "TOGETHER_API_KEY", "label": "Together AI", "model_provider": "openai",
     "base_url": "https://api.together.xyz/v1", "key_label": "Together API key",
     "models": ["meta-llama/Llama-3.3-70B-Instruct-Turbo", "deepseek-ai/DeepSeek-V3"]},
    {"id": "deepseek", "env_key": "DEEPSEEK_API_KEY", "label": "DeepSeek", "model_provider": "openai",
     "base_url": "https://api.deepseek.com/v1", "key_label": "DeepSeek API key",
     "models": ["deepseek-chat", "deepseek-reasoner"]},
    {"id": "ollama", "label": "Ollama (local)", "model_provider": "openai",
     "base_url": "http://localhost:11434/v1", "key_label": "API key (any value)",
     "models": ["llama3.2", "qwen2.5", "mistral"], "key_optional": True,
     "note": "Runs on the backend's machine — local development only."},
    {"id": "custom", "env_key": "LLM_API_KEY", "label": "Custom (OpenAI-compatible)", "model_provider": "openai",
     "base_url": None, "key_label": "API key", "models": [], "custom_base_url": True,
     "note": "vLLM, LM Studio, LiteLLM, Azure-style proxies…"},
    {"id": "mock", "label": "Mock (offline demo)", "model_provider": None, "base_url": None,
     "key_label": None, "models": ["mock"], "key_optional": True,
     "note": "No key needed — canned responses."},
]
_BY_ID = {p["id"]: p for p in PROVIDERS}

_OVERRIDE: ContextVar[Optional[dict]] = ContextVar("llm_client_override", default=None)


class ClientModelConfigError(ValueError):
    """Bad or disallowed model settings from the client (→ HTTP 400)."""


def _truthy(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def client_config_enabled() -> bool:
    return _truthy("LLM_CLIENT_CONFIG", True)


def server_key_shared() -> bool:
    return _truthy("LLM_CLIENT_CAN_USE_SERVER_KEY", False)


def private_hosts_allowed() -> bool:
    # Locally you want http://localhost:11434 (Ollama); deployed, you don't want
    # visitors steering the backend at internal addresses.
    return _truthy("LLM_CLIENT_ALLOW_PRIVATE_HOSTS", not os.getenv("VERCEL"))


def get_override() -> Optional[dict]:
    """The current request's model settings, if the client sent any."""
    return _OVERRIDE.get()


def scrub(text: str) -> str:
    """Remove the current request's API key from a string (error messages)."""
    override = get_override()
    key = (override or {}).get("api_key")
    return text.replace(key, "•••") if key and len(key) >= 6 else text


def _check_base_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ClientModelConfigError("Base URL must be an http(s) URL.")
    if private_hosts_allowed():
        return url
    if parsed.scheme != "https":
        raise ClientModelConfigError("Base URL must use https.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise ClientModelConfigError(f"Can't resolve host '{parsed.hostname}'.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise ClientModelConfigError(
                "Base URL points at a private or internal address, which this "
                "deployment doesn't allow."
            )
    return url


def parse_headers(headers: dict[str, str]) -> Optional[dict]:
    """Turn ``X-LLM-*`` headers into a model config, or ``None`` if absent."""
    provider_id = (headers.get("x-llm-provider") or "").strip().lower()
    if not provider_id:
        return None
    if not client_config_enabled():
        return None  # owner disabled UI model config: silently use the server's
    preset = _BY_ID.get(provider_id)
    if preset is None:
        raise ClientModelConfigError(f"Unknown provider '{provider_id}'.")
    if provider_id == "mock":
        return {"provider_id": "mock", "mock": True, "model": "mock", "provider": None,
                "base_url": None, "api_key": None, "temperature": None}

    model = (headers.get("x-llm-model") or "").strip()
    if not model:
        raise ClientModelConfigError("Choose a model.")
    api_key = (headers.get("x-llm-api-key") or "").strip() or None
    base_url = preset["base_url"]
    if preset.get("custom_base_url"):
        base_url = (headers.get("x-llm-base-url") or "").strip()
        if not base_url:
            raise ClientModelConfigError("Enter the endpoint's base URL.")
    if base_url:
        base_url = _check_base_url(base_url)
    if api_key is None and not preset.get("key_optional"):
        if not server_key_shared():
            raise ClientModelConfigError(
                f"Enter your {preset['key_label'] or 'API key'} — this server doesn't "
                "share its own key with models chosen in the browser."
            )
    if api_key is None and preset.get("env_key"):
        # Shared server key for an OpenAI-compatible endpoint: the OpenAI SDK
        # would otherwise send OPENAI_API_KEY, so pass the matching one.
        api_key = os.getenv(preset["env_key"], "").strip() or None
    if preset.get("key_optional") and api_key is None and provider_id == "ollama":
        api_key = "ollama"  # OpenAI SDK requires *some* key

    temperature = None
    raw_temp = (headers.get("x-llm-temperature") or "").strip()
    if raw_temp:
        try:
            temperature = float(raw_temp)
        except ValueError:
            raise ClientModelConfigError("Temperature must be a number.")

    return {
        "provider_id": provider_id,
        "mock": False,
        "model": model,
        "provider": preset["model_provider"],
        "base_url": base_url,
        "api_key": api_key,  # None → the provider SDK falls back to the server's env key
        "temperature": temperature,
    }


def public_providers() -> list[dict]:
    """Presets for the UI (no secrets here — just labels and suggestions)."""
    hidden = ("model_provider", "env_key")
    return [{k: v for k, v in p.items() if k not in hidden} for p in PROVIDERS]


def policy() -> dict:
    return {
        "enabled": client_config_enabled(),
        "server_key_shared": server_key_shared(),
        "private_hosts_allowed": private_hosts_allowed(),
    }


class ClientModelConfigMiddleware:
    """Pure-ASGI middleware: scope the request's ``X-LLM-*`` config to it.

    Pure ASGI (not ``BaseHTTPMiddleware``) so the ContextVar is visible for the
    whole request — including streamed SSE bodies and the tasks LangGraph spawns.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        try:
            override = parse_headers(headers)
        except ClientModelConfigError as exc:
            body = json.dumps({"detail": f"Model settings: {exc}"}).encode()
            await send({"type": "http.response.start", "status": 400,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"access-control-allow-origin", b"*")]})
            await send({"type": "http.response.body", "body": body})
            return
        token = _OVERRIDE.set(override)
        try:
            await self.app(scope, receive, send)
        finally:
            _OVERRIDE.reset(token)


class ClientModelMiddleware(AgentMiddleware):
    """Agent middleware: use the request's UI-chosen model for each model call.

    The agent is compiled once at startup with the server's model; this swaps
    in the visitor's model per call (tools and structured output are bound to
    the swapped model by ``create_agent``). No-op when no override is active.
    """

    def _swap(self, request):
        if get_override() is None:
            return request
        from llm import get_llm  # local import: llm imports this module

        return request.override(model=get_llm())

    def wrap_model_call(self, request, handler):
        return handler(self._swap(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._swap(request))
