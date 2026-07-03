# 🚀 Deployment Guide

This template runs anywhere Python and Node run. Below are three paths, from
simplest to most scalable. Whatever you pick, the two things that turn the demo
into a real service are:

1. **A durable checkpointer** — so interrupted runs survive restarts.
2. **A shared store** — so long-term memory is not lost when the process dies.

---

## 1. Docker Compose (single host)

The fastest way to run both services together:

```bash
cp backend/.env.example backend/.env    # configure your model + keys
docker compose up --build
# Frontend → http://localhost:3000   Backend → http://localhost:8000
```

`docker-compose.yml` already mounts a volume for the SQLite checkpoint database,
so resumable state survives container restarts. Set a real model in
`backend/.env` (e.g. `LLM_MODEL=gpt-4o-mini` + `OPENAI_API_KEY`) or leave it
unset to run the offline mock.

**Production checklist**

- Set `CHECKPOINT_DB=/data/checkpoints.sqlite` (on the mounted volume).
- Lock down `CORS_ORIGINS` to your frontend origin (not `*`).
- Provide provider keys via your orchestrator's secret store, never in the image.
- Front the backend with TLS (a reverse proxy such as Caddy, nginx, or your
  cloud load balancer).

---

## 2. LangGraph Platform / `langgraph dev`

The repo ships a `langgraph.json` registering all three graphs
(`research`, `approval`, `agent`), so it works with LangGraph's tooling out of
the box:

```bash
pip install "langgraph-cli[inmem]"
langgraph dev          # LangGraph Studio: visualize & step through interrupts
```

To deploy to **LangGraph Platform**, push the repo and point the deployment at
`langgraph.json`. The Platform provides a managed Postgres checkpointer and
store, so you can drop the SQLite/in-memory setup entirely. Configure the same
environment variables (`LLM_MODEL`, provider keys, `GUARDRAILS_*`, `MCP_SERVERS`,
`EMBEDDINGS_MODEL`) in the deployment settings.

---

## 3. Self-hosted, scalable (Postgres-backed)

For horizontal scaling, move both persistence layers to Postgres so any replica
can resume any thread and read shared memory.

Install the Postgres backends:

```bash
pip install langgraph-checkpoint-postgres langgraph-store-postgres psycopg
```

Then swap the in-memory pieces for their Postgres equivalents:

```python
# checkpointer (main.py lifespan) — replaces AsyncSqliteSaver / MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as saver:
    await saver.setup()
    ...

# store (memory.build_store) — replaces InMemoryStore
from langgraph.store.postgres.aio import AsyncPostgresStore

async with AsyncPostgresStore.from_conn_string(os.environ["DATABASE_URL"]) as store:
    await store.setup()
    # add index={"dims": 1536, "embed": "openai:text-embedding-3-small", "fields": ["text"]}
    # for semantic memory
```

Run several backend replicas behind a load balancer; because state lives in
Postgres, a request can start on one replica and resume on another.

---

## Environment variables

See [`backend/.env.example`](../backend/.env.example) for the full list. The most
relevant for production:

| Variable | Purpose |
|----------|---------|
| `LLM_MODEL`, `LLM_PROVIDER`, provider keys | Which model powers the app |
| `CHECKPOINT_DB` | Durable SQLite checkpoint path (or use Postgres) |
| `CORS_ORIGINS` | Restrict to your frontend origin |
| `GUARDRAILS_ENABLED`, `GUARDRAILS_BLOCKLIST` | Safety middleware |
| `MCP_SERVERS` | MCP tool servers (JSON or file path) |
| `AGENT_STRUCTURED_OUTPUT` | Return a typed `ResearchSummary` |
| `EMBEDDINGS_MODEL`, `EMBEDDING_DIMS` | Semantic long-term memory |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY` | Observability / tracing |

---

## Observability

Set the LangSmith variables (see `.env.example`) and every run — interrupts,
tool calls, approvals, forks — is traced automatically, with no code changes:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=langgraph-interrupt-template
```
