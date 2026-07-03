"""Guardrail middleware — safety controls that stack alongside HITL.

The agent engine (``agent.py``) composes middleware. ``HumanInTheLoopMiddleware``
gates *tool calls*; this module adds a *content* guardrail that runs on every
model call:

- **PII redaction** — emails, phone numbers, credit-card-like and SSN-like
  numbers in the conversation are masked *before the model sees them*, without
  mutating the persisted state. This demonstrates ``wrap_model_call``, which
  wraps the request/response around the model.
- **Input blocklist** — if a configured phrase appears in the latest user
  message, the agent short-circuits with a safe refusal instead of calling the
  model at all.

Everything is configurable via environment variables and is a no-op unless
enabled, so the zero-config demo is unaffected:

    GUARDRAILS_ENABLED=true          # turn the middleware on (default: on)
    GUARDRAILS_REDACT_PII=true       # mask PII before the model sees it
    GUARDRAILS_BLOCKLIST=hack,exploit  # comma-separated blocked phrases

This is intentionally dependency-free (stdlib ``re`` only) so it always runs.
Swap the regexes / blocklist for your own policy, or plug in a dedicated
PII/detoxification service inside ``_redact``.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.config import get_stream_writer

from langchain.agents.middleware import AgentMiddleware

logger = logging.getLogger(__name__)


# --- PII patterns (illustrative — extend for your domain) -------------------
_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("[EMAIL]", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    ("[CARD]", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("[SSN]", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("[PHONE]", re.compile(r"\b(?:\+?\d{1,2}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b")),
]


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _redact(text: str) -> tuple[str, int]:
    """Return ``(redacted_text, count)`` with recognised PII masked."""
    count = 0
    for placeholder, pattern in _PII_PATTERNS:
        text, n = pattern.subn(placeholder, text)
        count += n
    return text, count


def _emit(payload: dict) -> None:
    """Best-effort custom stream event (no-op outside a streaming run)."""
    try:
        get_stream_writer()(payload)
    except Exception:  # pragma: no cover - not in a streaming context
        pass


class GuardrailMiddleware(AgentMiddleware):
    """Redact PII and block disallowed input around every model call."""

    def __init__(
        self,
        *,
        redact_pii: bool = True,
        blocklist: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.redact_pii = redact_pii
        self.blocklist = [b.lower() for b in (blocklist or []) if b.strip()]

    @classmethod
    def from_env(cls) -> "GuardrailMiddleware | None":
        """Build from environment, or ``None`` when guardrails are disabled."""
        if not _truthy(os.getenv("GUARDRAILS_ENABLED"), default=True):
            return None
        blocklist = [
            b.strip() for b in os.getenv("GUARDRAILS_BLOCKLIST", "").split(",") if b.strip()
        ]
        return cls(
            redact_pii=_truthy(os.getenv("GUARDRAILS_REDACT_PII"), default=True),
            blocklist=blocklist,
        )

    def _blocked_phrase(self, messages: list[BaseMessage]) -> str | None:
        if not self.blocklist:
            return None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                text = str(msg.content).lower()
                return next((b for b in self.blocklist if b in text), None)
        return None

    def wrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Enforce the blocklist, then redact PII before the model runs."""
        messages: list[BaseMessage] = list(request.messages)

        # 1) Blocklist — refuse without calling the model.
        blocked = self._blocked_phrase(messages)
        if blocked:
            logger.warning("Guardrail blocked input containing %r", blocked)
            _emit({"type": "guardrail", "action": "blocked", "phrase": blocked})
            return AIMessage(
                content=(
                    "I can't help with that request. It was blocked by a safety "
                    "guardrail. Please rephrase or ask something else."
                )
            )

        # 2) PII redaction — mask before the model sees it (state is untouched).
        if self.redact_pii:
            redacted_count = 0
            new_messages: list[BaseMessage] = []
            for msg in messages:
                if isinstance(msg.content, str):
                    cleaned, n = _redact(msg.content)
                    if n:
                        redacted_count += n
                        msg = msg.model_copy(update={"content": cleaned})
                new_messages.append(msg)
            if redacted_count:
                logger.info("Guardrail redacted %d PII span(s)", redacted_count)
                _emit(
                    {
                        "type": "guardrail",
                        "action": "redacted",
                        "count": redacted_count,
                    }
                )
                request = request.override(messages=new_messages)

        return handler(request)

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Async variant that mirrors :meth:`wrap_model_call`."""
        messages: list[BaseMessage] = list(request.messages)

        blocked = self._blocked_phrase(messages)
        if blocked:
            logger.warning("Guardrail blocked input containing %r", blocked)
            _emit({"type": "guardrail", "action": "blocked", "phrase": blocked})
            return AIMessage(
                content=(
                    "I can't help with that request. It was blocked by a safety "
                    "guardrail. Please rephrase or ask something else."
                )
            )

        if self.redact_pii:
            redacted_count = 0
            new_messages: list[BaseMessage] = []
            for msg in messages:
                if isinstance(msg.content, str):
                    cleaned, n = _redact(msg.content)
                    if n:
                        redacted_count += n
                        msg = msg.model_copy(update={"content": cleaned})
                new_messages.append(msg)
            if redacted_count:
                logger.info("Guardrail redacted %d PII span(s)", redacted_count)
                _emit(
                    {"type": "guardrail", "action": "redacted", "count": redacted_count}
                )
                request = request.override(messages=new_messages)

        return await handler(request)
