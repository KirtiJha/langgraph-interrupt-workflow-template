"""Approval policy — *which* tool calls pause for a human, and *when*.

LangChain's ``HumanInTheLoopMiddleware`` takes an ``interrupt_on`` map of tool
name → config. This module builds that map from a small, env-configurable
policy so the rule lives in one place and applies to every engine (agent, deep
agent, MCP tools).

Two policies:

- ``HITL_POLICY=all`` (default) — every tool that *acts* pauses for approval.
  Read-only tools (``HITL_NEVER``) are exempt so a deep agent isn't asking
  permission to ``ls`` its own scratch space.
- ``HITL_POLICY=selective`` — only tools in ``HITL_ALWAYS`` (shell, delete,
  writes …) always pause; everything else pauses **only when its arguments look
  risky**, via an ``InterruptOnConfig.when`` predicate matched against
  ``HITL_SENSITIVE_PATTERNS``. This is the "approve the risky 5%, not every
  call" pattern that keeps agents usable in practice.

The default is deliberately conservative: a template should prove it pauses.
Flip to ``selective`` once you've decided what *your* risky actions are.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Iterable, List

from langchain.agents.middleware import InterruptOnConfig

logger = logging.getLogger(__name__)

# Tools that never need approval: read-only access to the agent's own scratch
# space, planning, and delegating to a subagent (whose own tool calls are gated
# anyway).
DEFAULT_NEVER = "ls,read_file,glob,grep,task,write_todos"

# Tools that always need approval, even in `selective` mode: anything that can
# mutate, destroy, or execute. (deepagents 0.7 added `execute` and `delete`.)
DEFAULT_ALWAYS = "execute,delete,write_file,edit_file"

# In `selective` mode, other tools pause only when an argument matches one of
# these (case-insensitive) patterns.
DEFAULT_SENSITIVE_PATTERNS = (
    r"password|passwd|secret|api[_ -]?key|token|ssn|social security|"
    r"credit card|card number|bank|payment|wire|transfer|"
    r"\bdelete\b|\bdrop\b|\bwipe\b|\berase\b|\bpurge\b|\brm -rf\b"
)

ALLOWED_DECISIONS: List[str] = ["approve", "edit", "reject"]


def _csv_env(name: str, default: str) -> set[str]:
    raw = os.getenv(name)
    value = default if raw is None else raw
    return {item.strip() for item in value.split(",") if item.strip()}


def policy_mode() -> str:
    mode = os.getenv("HITL_POLICY", "all").strip().lower()
    return mode if mode in ("all", "selective") else "all"


def never_tools() -> set[str]:
    return _csv_env("HITL_NEVER", DEFAULT_NEVER)


def always_tools() -> set[str]:
    return _csv_env("HITL_ALWAYS", DEFAULT_ALWAYS)


def sensitive_pattern() -> re.Pattern[str]:
    return re.compile(os.getenv("HITL_SENSITIVE_PATTERNS", DEFAULT_SENSITIVE_PATTERNS), re.I)


def looks_sensitive(args: Any, pattern: re.Pattern[str] | None = None) -> bool:
    """True if any argument value matches the sensitive pattern."""
    pattern = pattern or sensitive_pattern()
    text = repr(args) if not isinstance(args, str) else args
    return bool(pattern.search(text))


def _sensitive_when(pattern: re.Pattern[str]):
    """``InterruptOnConfig.when`` predicate: pause only for risky arguments."""

    def when(request: Any) -> bool:
        call = getattr(request, "tool_call", None) or {}
        return looks_sensitive(call.get("args", {}), pattern)

    return when


def build_interrupt_on(tool_names: Iterable[str]) -> Dict[str, Any]:
    """Build the ``interrupt_on`` map for the given tools under the active policy."""
    mode = policy_mode()
    never, always = never_tools(), always_tools()
    pattern = sensitive_pattern()
    interrupt_on: Dict[str, Any] = {}

    for name in tool_names:
        if name in never:
            interrupt_on[name] = False
        elif mode == "all" or name in always:
            interrupt_on[name] = InterruptOnConfig(allowed_decisions=ALLOWED_DECISIONS)
        else:
            interrupt_on[name] = InterruptOnConfig(
                allowed_decisions=ALLOWED_DECISIONS,
                when=_sensitive_when(pattern),
            )

    logger.info("HITL policy=%s gating=%s", mode, {k: v is not False for k, v in interrupt_on.items()})
    return interrupt_on


def describe() -> dict:
    """Summary for ``/capabilities``."""
    return {
        "policy": policy_mode(),
        "interrupt_mode": os.getenv("HITL_INTERRUPT_MODE", "per_call"),
        "always": sorted(always_tools()),
        "never": sorted(never_tools()),
    }
