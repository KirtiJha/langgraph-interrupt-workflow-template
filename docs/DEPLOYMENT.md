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

For horizontal scaling, keep both persistence layers in Postgres so any replica
can resume any thread and read shared memory. This is **built in** — no code
changes — just set a connection string:

```env
DATABASE_URL=postgresql://user:pass@host:5432/db     # POSTGRES_URL also works
```

On startup `backend/persistence.py` opens one connection pool and builds a
Postgres **checkpointer** (paused runs, history/time travel) and **store**
(long-term memory; semantic search via pgvector when `EMBEDDINGS_MODEL` is set),
creating the tables idempotently (`DB_AUTO_SETUP=false` to manage migrations
yourself). The pool uses `prepare_threshold=0`, so pgbouncer / Neon pooled URLs
work. `GET /capabilities` reports `"persistence": {"checkpointer": "postgres",
"multi_instance_safe": true}`.

Run several backend replicas behind a load balancer; because state lives in
Postgres, a request can start on one replica and resume on another — CI proves
this on every PR by pausing a run on one app instance and resuming it on a
fresh one against a real Postgres.

## 4. Vercel (serverless)

Two projects from one repo — `frontend/` (Next.js) and `backend/` (FastAPI,
detected zero-config from `main.py`). Step-by-step instructions and Deploy
buttons are in the [README](../README.md#-deploy-to-vercel). The essentials:

| Project | Root Directory | Required env |
|---|---|---|
| Backend | `backend` | `DATABASE_URL` (Storage → Neon), a model (`AI_GATEWAY_API_KEY` + `LLM_MODEL`, or any option in `.env.example`), `CORS_ORIGINS` |
| Frontend | `frontend` | `NEXT_PUBLIC_API_URL` = backend URL |

- **Postgres is mandatory** on Vercel: requests may hit different instances, and
  in-memory state would make every resume fail (with a 404 that says so).
- `backend/vercel.json` raises the function `maxDuration` to 300s for long SSE
  runs (800s max on Pro); `backend/.vercelignore` keeps tests/evals out of the
  bundle (~230 MB, under Vercel's 500 MB Python limit).
- `backend/.python-version` pins Python 3.12.
- Cancel (Stop) is per-instance best-effort; runs that aren't drained still
  complete and remain resumable.

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
