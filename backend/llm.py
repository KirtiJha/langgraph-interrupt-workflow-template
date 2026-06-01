"""Provider-agnostic LLM factory.

This template is intentionally LLM-agnostic. Pick any provider supported by
LangChain's ``init_chat_model`` (OpenAI, Anthropic, Google, Groq, Mistral,
IBM watsonx, Ollama, ...) by setting a couple of environment variables:

    LLM_MODEL=gpt-4o-mini            # any model id
    LLM_PROVIDER=openai              # optional, inferred from the model when omitted
    LLM_TEMPERATURE=0.7              # optional

If no provider credentials are configured, the template falls back to a small
built-in ``MockChatModel`` so it runs end-to-end (including token streaming)
with zero configuration. That makes the repo clone-and-run for newcomers.
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

logger = logging.getLogger(__name__)

# API-key environment variables we recognise for auto-detection. When none of
# these (and no explicit model) are set, we use the mock model for a zero-config
# demo experience.
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
)


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


class MockChatModel(BaseChatModel):
    """A tiny offline chat model used when no provider is configured.

    It produces context-aware canned responses and supports streaming so the
    full workflow (including the streaming endpoint) works without API keys.
    """

    @property
    def _llm_type(self) -> str:
        return "mock-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "MockChatModel":
        # The mock never emits tool calls; accept binding so create_agent works.
        return self

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
        content = self._canned_response(messages)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))]
        )

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
    has_key = any(os.getenv(key) for key in _KNOWN_PROVIDER_KEYS)
    return not has_model and not has_key


def get_llm(**overrides: Any) -> BaseChatModel:
    """Return a chat model based on environment configuration.

    Falls back to :class:`MockChatModel` when nothing is configured or when
    initialisation fails, so the template always runs.
    """
    if using_mock_llm():
        logger.info(
            "Using built-in MockChatModel (no LLM_MODEL/provider key configured). "
            "Set LLM_MODEL and a provider API key for real responses."
        )
        return MockChatModel()

    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    provider = os.getenv("LLM_PROVIDER") or None
    params: dict[str, Any] = {"temperature": float(os.getenv("LLM_TEMPERATURE", "0.7"))}
    params.update(overrides)

    try:
        return init_chat_model(model, model_provider=provider, **params)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning(
            "Failed to initialise model '%s' (%s); falling back to MockChatModel.",
            model,
            exc,
        )
        return MockChatModel()
