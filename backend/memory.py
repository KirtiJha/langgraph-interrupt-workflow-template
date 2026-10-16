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
import os
import uuid
from typing import Optional

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

logger = logging.getLogger(__name__)

# Default embedding dimensions for common models (OpenAI text-embedding-3-small).
# Override with EMBEDDING_DIMS if you use a different model.
_DEFAULT_EMBEDDING_DIMS = 1536


def _namespace(user_id: str) -> tuple[str, str]:
    return ("memories", user_id)


def index_config() -> Optional[dict]:
    """Vector-index config for semantic memory, or ``None`` when not configured."""
    embeddings_model = os.getenv("EMBEDDINGS_MODEL", "").strip()
    if not embeddings_model:
        return None
    dims = int(os.getenv("EMBEDDING_DIMS", _DEFAULT_EMBEDDING_DIMS))
    # ``embed`` accepts a provider string; LangGraph resolves it via
    # ``init_embeddings`` and only indexes the "text" field.
    return {"dims": dims, "embed": embeddings_model, "fields": ["text"]}


def build_store() -> BaseStore:
    """Create the in-memory long-term memory store, semantic when possible.

    If ``EMBEDDINGS_MODEL`` is set (e.g. ``openai:text-embedding-3-small``) and
    the matching provider credentials are available, the store is built with a
    vector index so :func:`load_user_memory` can recall the *most relevant*
    memories for the current question. Otherwise it falls back to a plain store
    (recency-ordered recall) so the zero-config demo still works offline.

    With ``DATABASE_URL`` set, ``persistence.open_postgres`` provides a
    Postgres-backed store instead (same index config).
    """
    index = index_config()
    if index:
        try:
            store = InMemoryStore(index=index)
            logger.info("Semantic memory enabled (embeddings=%s, dims=%d)", index["embed"], index["dims"])
            return store
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Could not enable semantic memory (%s); using plain store.", exc
            )
    logger.info("Using plain (non-semantic) long-term memory store.")
    return InMemoryStore()


def get_active_store() -> Optional[BaseStore]:
    """Return the store bound to the current run, or None if unavailable."""
    try:
        from langgraph.config import get_store

        return get_store()
    except Exception:
        return None


async def load_user_memory(
    store: Optional[BaseStore],
    user_id: Optional[str],
    limit: int = 5,
    query: Optional[str] = None,
) -> str:
    """Return a short bulleted summary of what we remember about the user.

    When the store has a vector index and ``query`` is provided, results are the
    memories most *semantically relevant* to the query. Otherwise the store
    returns the most recent memories.
    """
    if not store or not user_id:
        return ""
    try:
        items = await store.asearch(_namespace(user_id), query=query, limit=limit)
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
