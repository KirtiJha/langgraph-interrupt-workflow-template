"""Provider-agnostic LLM factory — any provider, any model.

Three ways to point the template at a model, all via environment variables:

1. **A native provider** (via LangChain's ``init_chat_model``)::

       LLM_MODEL=claude-sonnet-4-5          # any model id
       LLM_PROVIDER=anthropic               # optional; inferred when omitted
       # …or both at once:  LLM_MODEL=anthropic:claude-sonnet-4-5

   Works for openai, anthropic, google_genai, groq, mistralai, bedrock, ibm,
   ollama, … (install the matching ``langchain-<provider>`` package; OpenAI,
   Anthropic and Google ship by default) with that provider's usual API key.

2. **Any OpenAI-compatible endpoint** — OpenRouter, Groq, Together, Fireworks,
   DeepSeek, Ollama, LM Studio, vLLM, LiteLLM, Azure-style proxies::

       LLM_BASE_URL=https://openrouter.ai/api/v1
       LLM_API_KEY=...
       LLM_MODEL=meta-llama/llama-3.3-70b-instruct

3. **Vercel AI Gateway** — one key, models from every provider::

       AI_GATEWAY_API_KEY=...
       LLM_MODEL=anthropic/claude-sonnet-4.6     # or openai/gpt-5, google/gemini-2.5-pro …

Optional: ``LLM_TEMPERATURE`` (omit it for reasoning models that only accept
their default), ``LLM_REQUESTS_PER_SECOND`` (client-side rate limit).

If nothing is configured, the template uses a small built-in ``MockChatModel``
so it runs end-to-end (including token streaming) with zero configuration. If a
model *is* configured but fails to initialise (missing package, bad name), the
mock is still used so the app stays up — but the error is recorded and surfaced
by ``/capabilities`` and the UI, never silently swallowed.
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional
from urllib.parse import urlparse

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

logger = logging.getLogger(__name__)

# Vercel AI Gateway's OpenAI-compatible endpoint.
AI_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"

# API-key environment variables we recognise for auto-detection. When none of
# these (and no explicit model or endpoint) are set, we use the mock model for a
# zero-config demo experience.
_KNOWN_PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "FIREWORKS_API_KEY",
    "TOGETHER_API_KEY",
    "WATSONX_API_KEY",
    "AI_GATEWAY_API_KEY",
    "LLM_API_KEY",
)

# The last model-initialisation error, surfaced via model_status().
_MODEL_ERROR: Optional[str] = None


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def text_of(content: Any) -> str:
    """Normalize a message's ``content`` to plain text.

    Newer models (e.g. Gemini 3.x, Claude with thinking) return ``content`` as a
    list of typed blocks rather than a string. This flattens either form to the
    concatenated text, so provider-agnostic code can treat every response the
    same way.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                # Only surface text blocks (skip thinking/tool-use/etc).
                if block.get("type", "text") == "text":
                    parts.append(str(block.get("text", "")))
            else:
                parts.append(str(getattr(block, "text", "")))
        return "".join(parts)
    return str(content)


def _has_tool_result(messages: List[BaseMessage]) -> bool:
    return any(getattr(m, "type", None) == "tool" for m in messages)


def _last_human(messages: List[BaseMessage]) -> str:
    for msg in reversed(messages):
        if getattr(msg, "type", None) in ("human", "user"):
            return str(msg.content)
    return "the topic"


class MockChatModel(BaseChatModel):
    """A tiny offline chat model used when no provider is configured.

    It produces context-aware canned responses and supports streaming so the
    full workflow runs without API keys. When tools are bound (e.g. by
    ``create_agent``), it drives one tool call and then a final answer, so the
    agent engine — including human-in-the-loop tool approval — also works
    offline.
    """

    # Populated by ``bind_tools`` as a list of [tool_name, first_arg_name].
    tool_specs: list = []

    @property
    def _llm_type(self) -> str:
        return "mock-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "MockChatModel":
        specs: list = []
        for t in tools:
            name = getattr(t, "name", None) or (
                t.get("name") if isinstance(t, dict) else None
            )
            arg_names = list(getattr(t, "args", {}) or {})
            if name:
                specs.append([name, arg_names[0] if arg_names else "query"])
        return self.model_copy(update={"tool_specs": specs})

    def _tool_call_message(self, messages: List[BaseMessage]) -> Optional[dict]:
        """Return a single tool call to make, or None to answer directly."""
        if self.tool_specs and not _has_tool_result(messages):
            name, arg = self.tool_specs[0]
            return {"name": name, "args": {arg: _last_human(messages)}, "id": "mock_call_1"}
        return None

    @staticmethod
    def _canned_response(messages: List[BaseMessage]) -> str:
        human = ""
        for msg in reversed(messages):
            if msg.type in ("human", "user"):
                human = str(msg.content)
                break

        text = human.lower()
        if "synthesize" in text or "analyst" in text:
            return (
                "Synthesis: the findings converge on a clear picture. Key "
                "patterns, trade-offs, and a few caveats are highlighted below "
                "so you can act on them with confidence."
            )
        if "research query" in text or "research the current question" in text:
            return (
                "Finding A: a strong, well-supported result.\n"
                "Finding B: a useful nuance that refines the headline answer.\n"
                "Finding C: a practical implication worth keeping in mind."
            )
        return (
            "Here is a clear, structured answer to your question. (This is the "
            "built-in mock model — set LLM_MODEL and a provider API key to use a "
            "real LLM.)"
        )

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        tool_call = self._tool_call_message(messages)
        if tool_call:
            message = AIMessage(content="", tool_calls=[tool_call])
        else:
            message = AIMessage(content=self._canned_response(messages))
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, **kwargs)

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ):
        import json

        tool_call = self._tool_call_message(messages)
        if tool_call:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": tool_call["name"],
                            "args": json.dumps(tool_call["args"]),
                            "id": tool_call["id"],
                            "index": 0,
                        }
                    ],
                )
            )
            return
        for token in self._canned_response(messages).split(" "):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=token + " "))
            if run_manager:
                run_manager.on_llm_new_token(token + " ", chunk=chunk)
            yield chunk


def using_mock_llm() -> bool:
    """Return True when ``get_llm`` would return the built-in mock model."""
    if _truthy(os.getenv("USE_MOCK_LLM")):
        return True
    has_model = bool(os.getenv("LLM_MODEL"))
    has_endpoint = bool(os.getenv("LLM_BASE_URL"))
    has_key = any(os.getenv(key) for key in _KNOWN_PROVIDER_KEYS)
    return not has_model and not has_endpoint and not has_key


def requests_per_second() -> Optional[float]:
    """Client-side request rate cap (``LLM_REQUESTS_PER_SECOND``); ``None`` = off.

    Free/low-tier provider keys throttle aggressively, and this template can
    issue several calls at once (the workflow fans out one call per
    sub-question). Without a cap those bursts hit 429s and the provider SDK's
    own retries stall the run. Setting this smooths calls out instead.
    """
    raw = os.getenv("LLM_REQUESTS_PER_SECOND", "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
        return value if value > 0 else None
    except ValueError:
        return None


def _build_rate_limiter():
    """Return an ``InMemoryRateLimiter`` when a rate cap is configured."""
    rps = requests_per_second()
    if rps is None:
        return None
    try:
        from langchain_core.rate_limiters import InMemoryRateLimiter

        # Allow a tiny burst (or 1 request) before throttling kicks in.
        return InMemoryRateLimiter(
            requests_per_second=rps,
            check_every_n_seconds=min(0.1, 1 / rps),
            max_bucket_size=max(1.0, rps),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not enable the LLM rate limiter: %s", exc)
        return None


def resolve_model_config() -> dict:
    """Work out model / provider / endpoint / key from the environment.

    Precedence: an explicit ``LLM_BASE_URL`` (+ ``LLM_API_KEY``) wins; otherwise
    ``AI_GATEWAY_API_KEY`` routes through Vercel AI Gateway; otherwise the
    provider's own SDK and key are used. An OpenAI-compatible endpoint uses the
    ``openai`` provider unless ``LLM_PROVIDER`` says otherwise (e.g. an
    Anthropic-compatible proxy with ``LLM_PROVIDER=anthropic``).
    """
    base_url = os.getenv("LLM_BASE_URL", "").strip() or None
    api_key = os.getenv("LLM_API_KEY", "").strip() or None
    via = "provider"
    if base_url:
        via = "openai-compatible"
    elif os.getenv("AI_GATEWAY_API_KEY", "").strip():
        base_url = AI_GATEWAY_BASE_URL
        api_key = api_key or os.getenv("AI_GATEWAY_API_KEY", "").strip()
        via = "vercel-ai-gateway"

    default_model = "openai/gpt-4o-mini" if via == "vercel-ai-gateway" else "gpt-4o-mini"
    model = os.getenv("LLM_MODEL", "").strip() or default_model
    provider = os.getenv("LLM_PROVIDER", "").strip() or None
    # A bare model name on a custom endpoint means "OpenAI-compatible". A
    # "provider:model" string carries its own provider, so leave it alone.
    if base_url and not provider and ":" not in model:
        provider = "openai"

    return {"model": model, "provider": provider, "base_url": base_url, "api_key": api_key, "via": via}


def model_status() -> dict:
    """What model the app is really using — for ``/capabilities`` and the UI.

    Never includes the API key; the base URL is reduced to its host.
    """
    if using_mock_llm():
        return {"mock": True, "name": None, "provider": None, "via": None, "endpoint": None, "error": None}
    get_llm()  # construction only (no network): refreshes _MODEL_ERROR
    cfg = resolve_model_config()
    host = urlparse(cfg["base_url"]).netloc if cfg["base_url"] else None
    return {
        "mock": _MODEL_ERROR is not None,  # a failed init falls back to the mock
        "name": cfg["model"],
        "provider": cfg["provider"] or (cfg["model"].split(":", 1)[0] if ":" in cfg["model"] else "auto"),
        "via": cfg["via"],
        "endpoint": host,
        "error": _MODEL_ERROR,
    }


def get_llm(**overrides: Any) -> BaseChatModel:
    """Return a chat model based on environment configuration.

    Falls back to :class:`MockChatModel` when nothing is configured or when
    initialisation fails, so the template always runs — a failure is recorded
    in :func:`model_status` and logged loudly rather than hidden.
    """
    global _MODEL_ERROR
    if using_mock_llm():
        logger.info(
            "Using built-in MockChatModel (no LLM_MODEL/provider key configured). "
            "Set LLM_MODEL and a provider API key for real responses."
        )
        return MockChatModel()

    cfg = resolve_model_config()
    params: dict[str, Any] = {}
    # Only send temperature when asked: some reasoning models reject anything
    # but their default.
    if os.getenv("LLM_TEMPERATURE", "").strip():
        params["temperature"] = float(os.getenv("LLM_TEMPERATURE"))
    if cfg["base_url"]:
        params["base_url"] = cfg["base_url"]
    if cfg["api_key"]:
        params["api_key"] = cfg["api_key"]

    # Throttle client-side so bursts don't trip provider rate limits.
    rate_limiter = _build_rate_limiter()
    if rate_limiter is not None:
        params["rate_limiter"] = rate_limiter
        logger.info("LLM rate limiting enabled (%.3g req/s)", requests_per_second())

    params.update(overrides)

    try:
        model = init_chat_model(cfg["model"], model_provider=cfg["provider"], **params)
        _MODEL_ERROR = None
        return model
    except Exception as exc:
        _MODEL_ERROR = f"{type(exc).__name__}: {exc}"[:300]
        logger.error(
            "Failed to initialise model '%s' (provider=%s): %s — FALLING BACK TO THE "
            "MOCK MODEL. Check LLM_MODEL / LLM_PROVIDER and that the provider's "
            "langchain package is installed.",
            cfg["model"], cfg["provider"], exc,
        )
        return MockChatModel()
