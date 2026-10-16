"""Durable persistence — where interrupted runs and long-term memory live.

A human-in-the-loop app *must* keep a paused run's state somewhere both the
"pause" request and the later "resume" request can reach. Three options, picked
automatically from the environment:

- **Postgres** (``DATABASE_URL`` or ``POSTGRES_URL``) — required for serverless
  hosts like Vercel, where consecutive requests can land on different
  instances. Checkpoints *and* the long-term memory store share one connection
  pool. Works with Neon / Supabase / any Postgres, including pgbouncer-pooled
  URLs (``prepare_threshold=0``).
- **SQLite** (``CHECKPOINT_DB``) — durable on a single long-running server.
- **In-memory** (default) — zero config for local dev; lost on restart and not
  shared between instances.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional, Tuple

logger = logging.getLogger(__name__)


def database_url() -> Optional[str]:
    """The Postgres URL, if configured (Vercel/Neon sets both names)."""
    return (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip() or None


def persistence_mode() -> str:
    if database_url():
        return "postgres"
    if os.getenv("CHECKPOINT_DB"):
        return "sqlite"
    return "memory"


def describe() -> dict:
    """Summary for ``/capabilities`` (never includes credentials)."""
    mode = persistence_mode()
    return {
        "checkpointer": mode,
        "durable": mode != "memory",
        # Only Postgres is shared across serverless instances.
        "multi_instance_safe": mode == "postgres",
    }


@asynccontextmanager
async def open_postgres(url: str, index: Optional[dict] = None) -> AsyncIterator[Tuple[Any, Any]]:
    """Yield ``(checkpointer, store)`` backed by one Postgres connection pool.

    Tables are created on startup (idempotent; set ``DB_AUTO_SETUP=false`` to
    manage migrations yourself). ``index`` enables semantic memory via pgvector.
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.store.postgres.aio import AsyncPostgresStore
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    pool = AsyncConnectionPool(
        conninfo=url,
        min_size=1,
        max_size=int(os.getenv("DB_POOL_MAX", "5")),
        open=False,
        # autocommit + dict rows are what the LangGraph savers expect;
        # prepare_threshold=0 keeps pgbouncer (transaction pooling) happy.
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)
        store = AsyncPostgresStore(pool, index=index) if index else AsyncPostgresStore(pool)
        if os.getenv("DB_AUTO_SETUP", "true").strip().lower() not in ("0", "false", "no"):
            try:
                await saver.setup()
                await store.setup()
            except Exception as exc:  # e.g. two cold starts racing the same migration
                logger.warning("Postgres setup reported %s — continuing (tables likely exist)", exc)
        logger.info("Using durable Postgres checkpointer + store")
        yield saver, store
    finally:
        await pool.close()
