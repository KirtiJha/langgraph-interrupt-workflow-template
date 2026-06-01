"""Cross-thread long-term memory via a LangGraph ``Store``.

The *checkpointer* persists state **within** a thread (so an interrupted run can
resume). A *Store* persists facts **across** threads and sessions, keyed here by
``user_id`` — so the assistant can remember a returning user's topics and
preferences even in a brand-new conversation.

All helpers degrade gracefully to no-ops when no store or user_id is available,
so the graph still runs in LangGraph Studio / tests without a configured store.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from langgraph.store.base import BaseStore

logger = logging.getLogger(__name__)


def _namespace(user_id: str) -> tuple[str, str]:
    return ("memories", user_id)


def get_active_store() -> Optional[BaseStore]:
    """Return the store bound to the current run, or None if unavailable."""
    try:
        from langgraph.config import get_store

        return get_store()
    except Exception:
        return None


async def load_user_memory(
    store: Optional[BaseStore], user_id: Optional[str], limit: int = 5
) -> str:
    """Return a short bulleted summary of what we remember about the user."""
    if not store or not user_id:
        return ""
    try:
        items = await store.asearch(_namespace(user_id), limit=limit)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Memory load failed: %s", exc)
        return ""
    notes = [i.value.get("text", "") for i in items if i.value.get("text")]
    return "\n".join(f"- {n}" for n in notes)


async def save_user_memory(
    store: Optional[BaseStore], user_id: Optional[str], text: str
) -> None:
    """Persist a single memory note for the user."""
    if not store or not user_id or not text:
        return
    try:
        await store.aput(_namespace(user_id), str(uuid.uuid4()), {"text": text})
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Memory save failed: %s", exc)
