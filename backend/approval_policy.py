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
  risky**, decided by a :class:`RiskClassifier` via an
  ``InterruptOnConfig.when`` predicate. This is the "approve the risky 5%, not
  every call" pattern that keeps agents usable in practice.

Risk classifiers (``HITL_RISK_CLASSIFIER``):

- ``patterns`` (default) — a regex over the arguments (``HITL_SENSITIVE_PATTERNS``).
  Deterministic, offline, free.
- ``jev`` — TypeSafe AI's **Jev**, a "System One" *decision* model: it returns a
  typed answer with **calibrated confidence** instead of text, in ~100ms. The
  gate pauses when Jev says *risky* **or when it isn't confident** — escalating
  uncertainty to a human is exactly what a decision model is for. Needs
  ``pip install langgraph-jev`` and ``TYPESAFE_API_KEY``; falls back to
  ``patterns`` if either is missing or the API errors, so the template never
  depends on it.

The default is deliberately conservative: a template should prove it pauses.
Flip to ``selective`` once you've decided what *your* risky actions are.
"""

from __future__ import annotations

import logging
import os
import re
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Protocol

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

# Below this confidence a Jev verdict is treated as "not sure" → ask a human.
DEFAULT_RISK_CONFIDENCE = 0.75


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


# --- Risk classifiers -------------------------------------------------------
@dataclass
class RiskVerdict:
    """Why a tool call was (or wasn't) escalated to a human."""

    risky: bool
    source: str  # "patterns" | "jev" | "jev→patterns" (fallback)
    confidence: Optional[float] = None
    reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class RiskClassifier(Protocol):
    name: str

    def classify(self, tool_name: str, args: Any) -> RiskVerdict: ...


class PatternRiskClassifier:
    """Deterministic, offline: risky iff an argument matches the regex."""

    name = "patterns"

    def __init__(self, pattern: re.Pattern[str] | None = None) -> None:
        self.pattern = pattern or sensitive_pattern()

    def classify(self, tool_name: str, args: Any) -> RiskVerdict:
        hit = self.pattern.search(repr(args) if not isinstance(args, str) else args)
        return RiskVerdict(
            risky=bool(hit),
            source=self.name,
            reason=f"matched /{hit.group(0)}/" if hit else "no sensitive pattern matched",
        )


class JevRiskClassifier:
    """Ask Jev a typed question and escalate when risky *or* uncertain.

    ``runnable`` is anything with ``.invoke(dict) -> JevResult`` (a
    ``langgraph_jev.JevRunnable``); it is injectable so tests need no API key.
    """

    name = "jev"

    def __init__(self, runnable: Any | None = None, threshold: float | None = None) -> None:
        self.threshold = threshold if threshold is not None else risk_confidence_threshold()
        self.fallback = PatternRiskClassifier()
        self.runnable = runnable or self._build_runnable()

    @staticmethod
    def _build_runnable() -> Any:
        # Raises JevConfigurationError without TYPESAFE_API_KEY; ImportError
        # without the package. get_risk_classifier() turns both into a fallback.
        from langgraph_jev import JevRunnable, boolean

        return JevRunnable(
            {
                "risky": boolean(
                    criteria={
                        "risky": (
                            "The tool call could cause harm if wrong: it spends money, "
                            "sends messages or data externally, modifies or deletes data, "
                            "runs code, touches credentials or personal data, or is "
                            "irreversible."
                        )
                    }
                )
            }
        )

    def classify(self, tool_name: str, args: Any) -> RiskVerdict:
        state = {"tool": tool_name, "arguments": args}
        try:
            result = self.runnable.invoke(state)
            decision = result.decisions["risky"]
        except Exception as exc:  # API/timeouts/validation → never block on the gate
            logger.warning("Jev risk check failed (%s); using pattern fallback", exc)
            verdict = self.fallback.classify(tool_name, args)
            verdict.source = "jev→patterns"
            return verdict

        confidence = decision.confidence
        says_risky = bool(decision.value)
        unsure = confidence is not None and confidence < self.threshold
        return RiskVerdict(
            risky=says_risky or unsure,
            source=self.name,
            confidence=confidence,
            reason=(
                "flagged risky"
                if says_risky
                else f"low confidence ({confidence:.2f} < {self.threshold:.2f}) — asking a human"
                if unsure
                else "looks safe"
            ),
        )


def risk_classifier_mode() -> str:
    mode = os.getenv("HITL_RISK_CLASSIFIER", "patterns").strip().lower()
    return mode if mode in ("patterns", "jev") else "patterns"


def risk_confidence_threshold() -> float:
    try:
        return float(os.getenv("HITL_RISK_CONFIDENCE", str(DEFAULT_RISK_CONFIDENCE)))
    except ValueError:
        return DEFAULT_RISK_CONFIDENCE


def get_risk_classifier(runnable: Any | None = None) -> RiskClassifier:
    """The configured classifier, degrading to patterns if Jev isn't usable."""
    if risk_classifier_mode() == "jev":
        try:
            return JevRiskClassifier(runnable=runnable)
        except ImportError:
            logger.warning("HITL_RISK_CLASSIFIER=jev but langgraph-jev isn't installed; using patterns")
        except Exception as exc:  # JevConfigurationError (no key) etc.
            logger.warning("HITL_RISK_CLASSIFIER=jev unavailable (%s); using patterns", exc)
    return PatternRiskClassifier()


# Verdicts for recently-gated tool calls, keyed by tool_call_id, so the
# interrupt sent to the UI can explain *why* it paused. Bounded; in-memory.
_VERDICTS: "OrderedDict[str, RiskVerdict]" = OrderedDict()
_VERDICT_LIMIT = 256


def _remember(tool_call_id: Optional[str], verdict: RiskVerdict) -> None:
    if not tool_call_id:
        return
    _VERDICTS[tool_call_id] = verdict
    while len(_VERDICTS) > _VERDICT_LIMIT:
        _VERDICTS.popitem(last=False)


def verdict_for(tool_call_id: Optional[str]) -> Optional[dict]:
    """The recorded verdict for a tool call (for the approval card), if any."""
    verdict = _VERDICTS.get(tool_call_id or "")
    return verdict.as_dict() if verdict else None


def _risk_when(classifier: RiskClassifier, always: bool = False):
    """``InterruptOnConfig.when``: classify the call, remember why, decide.

    With ``always=True`` the call pauses regardless (policy ``all``) but is
    still classified so the UI can show the risk assessment.
    """

    def when(request: Any) -> bool:
        call = getattr(request, "tool_call", None) or {}
        verdict = classifier.classify(call.get("name", ""), call.get("args", {}))
        _remember(call.get("id"), verdict)
        return True if always else verdict.risky

    return when


def build_interrupt_on(
    tool_names: Iterable[str], classifier: RiskClassifier | None = None
) -> Dict[str, Any]:
    """Build the ``interrupt_on`` map for the given tools under the active policy."""
    mode = policy_mode()
    never, always = never_tools(), always_tools()
    classifier = classifier or get_risk_classifier()
    # Only a model-backed classifier adds value as an annotation in `all` mode.
    annotate = classifier.name != "patterns"
    interrupt_on: Dict[str, Any] = {}

    for name in tool_names:
        if name in never:
            interrupt_on[name] = False
        elif mode == "all" or name in always:
            interrupt_on[name] = InterruptOnConfig(
                allowed_decisions=ALLOWED_DECISIONS,
                **({"when": _risk_when(classifier, always=True)} if annotate else {}),
            )
        else:
            interrupt_on[name] = InterruptOnConfig(
                allowed_decisions=ALLOWED_DECISIONS,
                when=_risk_when(classifier),
            )

    logger.info(
        "HITL policy=%s classifier=%s gating=%s",
        mode, classifier.name, {k: v is not False for k, v in interrupt_on.items()},
    )
    return interrupt_on


def describe() -> dict:
    """Summary for ``/capabilities``."""
    return {
        "policy": policy_mode(),
        "interrupt_mode": os.getenv("HITL_INTERRUPT_MODE", "per_call"),
        "always": sorted(always_tools()),
        "never": sorted(never_tools()),
        "risk_classifier": get_risk_classifier().name,
        "risk_confidence": risk_confidence_threshold(),
    }
