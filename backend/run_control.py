"""Cooperative cancellation for in-flight graph runs (LangGraph graceful drain).

LangGraph 1.2 added *graceful shutdown*: pass a ``RunControl`` into a run and
call :meth:`RunControl.request_drain` from anywhere to stop it **after the
current superstep completes**. The run raises ``GraphDrained``, and — crucially —
its progress is checkpointed, so the thread can be resumed later instead of
being lost.

That is exactly the behaviour a "Stop" button should have: cancel *now*, but
cleanly, and keep the work done so far. This module keeps a registry of the
controls for currently-streaming threads so an HTTP endpoint can cancel them.

Degrades gracefully: on a LangGraph without ``RunControl``, runs simply aren't
cancellable and :func:`request_cancel` reports that.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from langgraph.errors import GraphDrained
    from langgraph.runtime import RunControl

    CANCEL_SUPPORTED = True
except Exception:  # pragma: no cover - older LangGraph
    RunControl = None  # type: ignore[assignment]

    class GraphDrained(Exception):  # type: ignore[no-redef]
        """Fallback so ``except GraphDrained`` is always valid."""

    CANCEL_SUPPORTED = False


# thread_id -> RunControl for runs currently streaming.
_ACTIVE: Dict[str, Any] = {}


def new_control(thread_id: str) -> Optional[Any]:
    """Create and register a fresh control for ``thread_id``.

    A control is single-use (once drained it stays drained), so each run gets a
    new one. Returns ``None`` when the installed LangGraph has no ``RunControl``.
    """
    if not CANCEL_SUPPORTED:
        return None
    control = RunControl()
    _ACTIVE[thread_id] = control
    return control


def release(thread_id: str) -> None:
    """Forget the control for ``thread_id`` (run finished, drained, or failed)."""
    _ACTIVE.pop(thread_id, None)


def request_cancel(thread_id: str, reason: str = "cancelled by user") -> bool:
    """Ask the in-flight run for ``thread_id`` to drain. ``True`` if requested."""
    control = _ACTIVE.get(thread_id)
    if control is None:
        return False
    control.request_drain(reason)
    logger.info("Drain requested for thread=%s (%s)", thread_id, reason)
    return True


def is_active(thread_id: str) -> bool:
    """Whether a cancellable run is currently registered for ``thread_id``."""
    return thread_id in _ACTIVE
