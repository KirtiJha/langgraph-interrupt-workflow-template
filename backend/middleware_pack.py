"""Prebuilt middleware "power-pack" for the agent engine.

LangChain v1 ships a catalog of production-ready middleware. This module wires a
curated, env-configurable subset onto the agent (composed *alongside* the custom
guardrail and human-in-the-loop middleware in ``agent.py``):

- **SummarizationMiddleware** — compresses old messages as the conversation
  grows, so long-running threads never overflow the context window.
- **ModelCallLimitMiddleware** — caps model calls per run (a runaway / cost
  guardrail).
- **ToolCallLimitMiddleware** — caps tool calls per run (opt-in).
- **ModelRetryMiddleware** — retries transient model/endpoint errors with
  exponential backoff.
- **TodoListMiddleware** — gives the agent a ``write_todos`` planning tool so it
  can decompose and track multi-step work (opt-in — adds a tool).
- **ModelFallbackMiddleware** — falls back to another model on failure (opt-in;
  needs a second model configured).

Everything has a sensible default and is controlled by environment variables, so
the zero-config demo is unaffected. Defaults are conservative enough that they
never trigger during a short conversation.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
)

logger = logging.getLogger(__name__)


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int | None) -> int | None:
    raw = os.getenv(name, "").strip()
    if raw == "":
        return default
    try:
        value = int(raw)
        return value if value > 0 else None
    except ValueError:
        return default


def build_middleware_pack(model: Any) -> tuple[list, list[str]]:
    """Return ``(middleware, active_names)`` for the configured power-pack.

    ``model`` is the chat model the summarization middleware uses to condense
    history. The returned middleware are meant to sit between the guardrail and
    the human-in-the-loop middleware in ``build_agent``.
    """
    middleware: list = []
    active: list[str] = []

    # 1) Summarization — protect against context overflow on long threads.
    if _truthy(os.getenv("AGENT_SUMMARIZATION"), default=True):
        trigger_messages = _int_env("AGENT_SUMMARIZATION_TRIGGER_MESSAGES", 40) or 40
        keep_messages = _int_env("AGENT_SUMMARIZATION_KEEP_MESSAGES", 20) or 20
        middleware.append(
            SummarizationMiddleware(
                model=model,
                trigger=("messages", trigger_messages),
                keep=("messages", keep_messages),
            )
        )
        active.append(f"summarization(>{trigger_messages} msgs)")

    # 2) Model-call limit — runaway / cost guardrail.
    model_call_limit = _int_env("AGENT_MODEL_CALL_LIMIT", 25)
    if model_call_limit:
        middleware.append(
            ModelCallLimitMiddleware(run_limit=model_call_limit, exit_behavior="end")
        )
        active.append(f"model_call_limit({model_call_limit})")

    # 3) Tool-call limit — opt-in cap on tool invocations per run.
    tool_call_limit = _int_env("AGENT_TOOL_CALL_LIMIT", None)
    if tool_call_limit:
        middleware.append(
            ToolCallLimitMiddleware(run_limit=tool_call_limit, exit_behavior="continue")
        )
        active.append(f"tool_call_limit({tool_call_limit})")

    # 4) Model retry — recover from transient endpoint errors.
    if _truthy(os.getenv("AGENT_MODEL_RETRY"), default=True):
        retries = _int_env("AGENT_MODEL_RETRIES", 2) or 2
        middleware.append(ModelRetryMiddleware(max_retries=retries))
        active.append(f"model_retry({retries})")

    # 5) TodoList planning tool — opt-in (adds a `write_todos` tool).
    if _truthy(os.getenv("AGENT_TODO_LIST"), default=False):
        from langchain.agents.middleware import TodoListMiddleware

        middleware.append(TodoListMiddleware())
        active.append("todo_list")

    # 6) Model fallback — opt-in; needs a second model id.
    fallback_model = os.getenv("AGENT_FALLBACK_MODEL", "").strip()
    if fallback_model:
        try:
            from langchain.agents.middleware import ModelFallbackMiddleware

            middleware.append(ModelFallbackMiddleware(fallback_model))
            active.append(f"model_fallback({fallback_model})")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not enable model fallback: %s", exc)

    return middleware, active


def active_middleware_names(model: Any) -> list[str]:
    """Just the active-name list (for reporting in /capabilities)."""
    return build_middleware_pack(model)[1]
