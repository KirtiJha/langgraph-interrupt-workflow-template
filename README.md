# 🚀 Mission Control — a human-in-the-loop agent template

[![CI](https://github.com/KirtiJha/langgraph-interrupt-workflow-template/actions/workflows/ci.yml/badge.svg)](https://github.com/KirtiJha/langgraph-interrupt-workflow-template/actions/workflows/ci.yml)
[![LangGraph](https://img.shields.io/badge/LangGraph-v1-1C3C3C?logo=langchain&logoColor=white)](https://docs.langchain.com/oss/python/langgraph/overview)
[![LangChain](https://img.shields.io/badge/LangChain-v1-1C3C3C?logo=langchain&logoColor=white)](https://docs.langchain.com/oss/python/langchain/overview)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js%2015-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Give it a job. It asks before it acts.**

Mission Control is a personal agent that gets real-life jobs done inside a
simulated world — your inbox, calendar, wallet, contacts, subscriptions and
bookings — and **pauses for your approval** on anything that costs money, can't
be undone, or involves other people. Approve, edit, reject or reply; rewind to
any decision and try another path. It is a complete, production-shaped
reference for **human-in-the-loop agents on LangGraph v1 + LangChain v1**.

<p align="center">
  <img src="docs/demo.gif" alt="Mission Control tour: pick a mission, the agent reads your world and compares options, asks which venue, pauses for approval with a preview of the charge, you reject with a reason and it books the runner-up, you edit the deposit, invites go out, a mission report lands, and you rewind to a decision point and branch." width="100%">
</p>

> **Runs with zero configuration.** The five starter missions are flown by an
> offline *pilot*, so the whole loop — act, pause, approve, rewind — works with
> no API key. Add any model (in the UI or the env) for open-ended goals.

**Live demo:** [langgraph-hitl.vercel.app](https://langgraph-hitl.vercel.app)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/KirtiJha/langgraph-interrupt-workflow-template)

---

## ✨ What you get

| | |
|---|---|
| 🎯 **Approvals that mean something** | Every approval visibly changes the world: approve a deposit and the wallet drops, approve an invite and the calendar fills. Reject and the agent finds the runner-up. |
| 🧾 **Risk-scored, previewed actions** | Each pending action is scored against the *current* world (amount, refundable, recipients, calendar clashes, urgency) and shows exactly what will change — wallet before → after, the full email, a ghost calendar event. |
| 🎚️ **Autonomy you choose** | *Careful* asks before everything; *Balanced* asks when it matters or above your spend limit; *Autopilot* asks only for high-risk or irreversible actions. |
| ✏️ **Four decisions** | Approve · Edit the arguments (schema-driven form) · Reject with a reason · Reply instead. Hotkeys **A / E / R**, numbered options for questions. |
| ⏪ **Time travel** | Branch from any decision point; the world rewinds with it and the approvals come back for new answers. The original run is preserved. |
| 🧠 **Memory** | Missions leave memories ("Mom is vegetarian") that shape the next one. Semantic recall with embeddings, optional. |
| 🔌 **Any model, from the UI** | Pick a provider, model and key in the browser (OpenAI, Anthropic, Google, Vercel AI Gateway, OpenRouter, Groq, Together, DeepSeek, Ollama, any OpenAI-compatible URL). Sent per request, never stored. |
| 💾 **Durable** | With `DATABASE_URL`, missions live in Postgres: pause for days, resume from another instance, survive redeploys. |
| 🛡️ **Guardrails, limits, retries** | PII masking before the model, a blocklist, summarisation, call limits, retries, graceful cancel. |
| 📊 **Evals** | Scores *asked before acting*, *budget respected*, *no forbidden actions* and more — offline or as a LangSmith experiment. |
| 🔭 **Tooling** | LangGraph Studio, AG-UI endpoint for CopilotKit-style clients, MCP tools gated like any other action, Vercel one-click deploy, Docker. |

## 🧭 How it works

```
┌────────────────────┐   SSE    ┌─────────────────────────┐        ┌──────────────────────────┐
│ Next.js UI         │ ◄──────► │ FastAPI  /missions/*    │ ─────► │ LangGraph create_agent   │
│ • mission gallery  │          │ • start / decide / fork │        │ • world in state         │
│ • feed + decisions │          │ • timeline / history    │        │ • HITL middleware        │
│ • your world       │          │ • X-LLM-* model headers │        │ • Postgres checkpoints   │
└────────────────────┘          └─────────────────────────┘        └──────────────────────────┘
```

The agent is a plain `create_agent` with tools in two groups. **Reading tools**
(`read_inbox`, `read_calendar`, `check_wallet`, `search_*`, `get_quotes`…) run
freely. **Acting tools** (`book`, `pay`, `send_email`, `add_calendar_event`,
`archive_emails`, `cancel_subscription`) return `Command(update={"world":
{"ops": [...]}})` — they never mutate anything directly. A reducer applies the
operations to `state["world"]`, which is why the world is checkpointed, rewinds
with time travel, and forks cleanly.

`HumanInTheLoopMiddleware(interrupt_mode="per_call")` gates the acting tools.
Its `when` predicate is the **risk policy** (`backend/mission/policy.py`): it
reads the world and the autonomy setting from state, scores the call, records
the assessment for the UI, and decides whether to pause.

```python
InterruptOnConfig(
    allowed_decisions=["approve", "edit", "reject", "respond"],
    when=lambda req: should_ask(assess(tool, req.tool_call["args"], req.state["world"]), req.state["autonomy"]),
)
```

`ask_user` shows the *other* kind of interrupt — a raw `interrupt()` from inside
a tool — for choices only you can make ("Olive & Fig or Trattoria Nonna?").

Forking uses `aupdate_state` at an earlier checkpoint, which creates a new
branch rather than rewriting history; resuming from it re-runs the gated tools,
which raise their interrupts again.

## ⚡ Quick start (zero config)

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # works as-is on the offline pilot
python main.py                  # http://localhost:8000  (docs at /docs)

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

Open http://localhost:3000, pick **Plan Mom's 60th birthday dinner**, and
decide. Try rejecting the first venue, editing a deposit, and **Rewind →
Branch from here**.

### Starter missions

| Mission | What the agent does | Shows off |
|---|---|---|
| 🎂 Plan Mom's 60th birthday dinner | Reads Mom's email, finds quiet vegetarian venues, asks which, books one, orders a cake, invites the family (not Mom) | Questions, rejection → runner-up, group email, budget |
| 📦 Handle my apartment move | Compares mover and cleaner quotes, books with refundable deposits, emails the landlord, cancels the gym | Parallel quotes, deposits, irreversible cancel |
| ✈️ Book a long weekend in Lisbon | Finds a free long weekend, compares flights and hotels, books, blocks the calendar | Calendar reasoning, high-value payments |
| 📬 Get me to inbox zero | Replies to the urgent mail, schedules lunch, archives junk | Edit-before-send, mixed risk levels |
| 💳 Cut subscriptions I don't use | Audits spend and cancels unused plans, one approval each | Autonomy levels, savings report |

Each one is scripted for the offline pilot (`backend/mission/pilot.py`), reacts
to your decisions, and runs identically on a real model.

## 🔌 Use a real model — any provider

**From the UI (no restart):** click **Server model** in the header, pick a
provider, type or pick a model, paste your key, **Test connection**, **Save**.
The settings travel as `X-LLM-*` headers with each request and apply to that
request only; the key stays in your browser and the server never stores it.
Custom base URLs are checked against private addresses when deployed.

**From the environment:** uncomment one option in `backend/.env`:

```env
# 1) Vercel AI Gateway — one key, models from every provider
AI_GATEWAY_API_KEY=...
LLM_MODEL=anthropic/claude-sonnet-4.6        # or openai/gpt-5, google/gemini-2.5-pro, xai/grok-4…

# 2) A provider's native API ("provider:model", or set LLM_PROVIDER)
LLM_MODEL=anthropic:claude-sonnet-4-5        # + ANTHROPIC_API_KEY
LLM_MODEL=gpt-4o-mini                        # + OPENAI_API_KEY
LLM_MODEL=google_genai:gemini-2.5-flash      # + GOOGLE_API_KEY

# 3) Any OpenAI-compatible endpoint — OpenRouter, Groq, Together, DeepSeek, Ollama, vLLM, LM Studio…
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=...
LLM_MODEL=meta-llama/llama-3.3-70b-instruct
```

| Owner control | Effect | Default |
|---|---|---|
| `LLM_CLIENT_CONFIG` | `false` ignores model settings from the browser | `true` |
| `LLM_CLIENT_CAN_USE_SERVER_KEY` | Let a browser-chosen model use the server's key when none is entered | `false` |
| `LLM_CLIENT_ALLOW_PRIVATE_HOSTS` | Allow custom base URLs on private/loopback addresses (local Ollama) | `true` locally, `false` on Vercel |

## ▲ Deploy to Vercel

Two Vercel projects from this one repo: the Next.js `frontend/` and the
FastAPI `backend/` (zero-config, with SSE streaming and lifespan support).

> **A database is required on Vercel.** Serverless requests land on different
> instances, so a mission paused by one request must be resumable by another.
> Set `DATABASE_URL` and the backend switches to Postgres automatically; without
> it, resumes fail with a clear 404 explaining this.

1. **Backend** — [vercel.com/new](https://vercel.com/new) → import → **Root Directory: `backend`** → Deploy. Then **Storage → Create Database → Neon** and connect it (sets `DATABASE_URL`); optionally add a model (`AI_GATEWAY_API_KEY` + `LLM_MODEL`) and `CORS_ORIGINS`. Redeploy and check `/capabilities` → `"persistence": {"checkpointer": "postgres"}`.
2. **Frontend** — import again → **Root Directory: `frontend`** → `NEXT_PUBLIC_API_URL=https://<backend>.vercel.app` → Deploy.

[![Deploy backend](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FKirtiJha%2Flanggraph-interrupt-workflow-template%2Ftree%2Fmain%2Fbackend&project-name=mission-control-backend&repository-name=mission-control-backend&env=AI_GATEWAY_API_KEY,LLM_MODEL&envDescription=Optional%3A%20a%20default%20model.%20Then%20add%20a%20Neon%20database%20from%20the%20Storage%20tab.&envLink=https%3A%2F%2Fgithub.com%2FKirtiJha%2Flanggraph-interrupt-workflow-template%23-use-a-real-model--any-provider)
[![Deploy frontend](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FKirtiJha%2Flanggraph-interrupt-workflow-template%2Ftree%2Fmain%2Ffrontend&project-name=mission-control&repository-name=mission-control&env=NEXT_PUBLIC_API_URL&envDescription=URL%20of%20your%20deployed%20backend)

Streams run for up to 300s (`backend/vercel.json`). **Pause** is best-effort
across instances. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for Docker,
LangGraph Platform and self-hosted Postgres.

## 🛡️ Production layers

All optional, all env-configured, all degrade gracefully.

- **Guardrails** (`guardrails.py`) — an `AgentMiddleware` that masks cards, SSNs and phone numbers before the model sees them (email addresses too with `GUARDRAILS_REDACT_EMAILS=true` — off by default because an acting agent needs them) and refuses blocklisted input.
- **Middleware power-pack** (`middleware_pack.py`) — summarisation, model/tool call limits, model retry, optional fallback model and to-do planner.
- **Graceful cancel** (`run_control.py`) — **Pause** drains the run at a safe boundary; progress is checkpointed and the mission stays resumable.
- **Second-opinion risk gate** — set `HITL_RISK_CLASSIFIER=jev` and [TypeSafe AI's Jev](https://typesafe.ai) decision model also classifies each action; when it flags something the policy would have let through, the agent asks. Falls back to the regex classifier without a key.
- **MCP tools** — point `MCP_SERVERS` at any Model Context Protocol server; its tools join the agent and are treated as acting tools (medium risk, effects unknown) by the policy.
- **Rate-limit friendly** — `LLM_REQUESTS_PER_SECOND` smooths bursts on free-tier keys.

`GET /capabilities` reports what's active; the header shows the model and persistence badges.

## 🔭 LangGraph Studio & AG-UI

```bash
pip install "langgraph-cli[inmem]"
langgraph dev          # LangGraph Studio with the mission graph
```

The agent is also exposed over the open [AG-UI protocol](https://docs.ag-ui.com)
at `/agui`, so CopilotKit-style clients can drive it, approvals included — see
[`examples/copilotkit`](examples/copilotkit).

## 📡 API reference

| Endpoint | Method | Description |
|---|---|---|
| `/missions` | GET | Starter missions, the seed world, and what we remember about `user_id` |
| `/missions/start` | POST | Start a mission (`goal`, `mission_id?`, `user_id?`, `autonomy`, `ask_above`) — SSE |
| `/missions/{id}/decide` | POST | `{decisions: {interrupt_id: decision}}` — approvals (`approve` / `edit` / `reject` / `respond`) and question answers, any subset — SSE |
| `/missions/{id}/continue` | POST | A follow-up goal on the same thread and world — SSE |
| `/missions/{id}/fork` | POST | Branch from a decision point (`checkpoint_id`); the approvals come back — SSE |
| `/missions/{id}/cancel` | POST | Graceful pause; progress is saved |
| `/missions/{id}` | GET | Current state: status, pending decisions with risk + preview, world, report |
| `/missions/{id}/timeline` | GET | The feed so far (for reloads) |
| `/missions/{id}/history` | GET | Decision points for time travel |
| `/model/providers`, `/model/test` | GET, POST | Provider presets; test the model in the request's `X-LLM-*` headers |
| `/capabilities`, `/health`, `/agui` | | |

SSE events: `thread`, `token`, `tool_calls`, `tool_result`, `progress` (with option cards), `world_ops`, `report`, `guardrail`, `cancelled`, `error`, `state`, `done`.

## ⚙️ Configuration

| Variable | Description | Default |
|---|---|---|
| `LLM_MODEL` / `LLM_PROVIDER` / `AI_GATEWAY_API_KEY` / `LLM_BASE_URL` / `LLM_API_KEY` | The server's default model (see above) | offline pilot |
| `LLM_TEMPERATURE` | Sampling temperature (omit for reasoning models) | provider default |
| `LLM_CLIENT_CONFIG` / `LLM_CLIENT_CAN_USE_SERVER_KEY` / `LLM_CLIENT_ALLOW_PRIVATE_HOSTS` | Model choice from the UI | `true` / `false` / local only |
| `USE_MOCK_LLM` | Force the offline pilot | `false` |
| `DATABASE_URL` (or `POSTGRES_URL`) | Postgres checkpointer + store — **required on Vercel** | – |
| `CHECKPOINT_DB` | Durable SQLite for a single server | in-memory |
| `HITL_RISK_CLASSIFIER` / `HITL_RISK_CONFIDENCE` | `patterns` or `jev` second opinion + confidence floor | `patterns` / `0.75` |
| `GUARDRAILS_ENABLED` / `GUARDRAILS_REDACT_PII` / `GUARDRAILS_REDACT_EMAILS` / `GUARDRAILS_BLOCKLIST` | Guardrail middleware | `true` / `true` / `false` / – |
| `AGENT_MODEL_CALL_LIMIT` / `AGENT_TODO_LIST` / `AGENT_FALLBACK_MODEL` | Middleware power-pack | `25` / `false` / – |
| `EMBEDDINGS_MODEL` | Semantic memory recall | – |
| `MCP_SERVERS` | MCP server config (inline JSON or file path) | – |
| `LLM_REQUESTS_PER_SECOND` | Client-side request cap | off |
| `CORS_ORIGINS` / `PORT` | | `*` / `8000` |

## 🐳 Docker

```bash
cp backend/.env.example backend/.env
docker compose up --build       # frontend :3000, backend :8000 (SQLite volume)
```

## 🎨 Make it yours

The simulated world is the thing to swap. Everything else — approvals, risk
policy, time travel, UI — stays.

1. **Real tools.** Replace the functions in `backend/mission/tools.py` with Gmail, Google Calendar, Stripe… (or load them from MCP). Keep returning `Command(update={"world": {"ops": [...]}})` so the UI's ghosts and ledger keep working, or drop the world and just return strings.
2. **Your risk policy.** `backend/mission/policy.py:assess()` is one function: amounts, recipients, reversibility, anything your domain cares about.
3. **Your missions.** Add to `MISSIONS` in `backend/mission/catalog.py` (and a script in `pilot.py` if you want it to work offline).
4. **Your look.** Design tokens live in `frontend/app/globals.css` and `tailwind.config.js`.

## 🧪 Testing & evaluation

```bash
cd backend
USE_MOCK_LLM=true pytest -q      # API, policy, time travel, model config, guardrails — offline
python -m evals.run_evals        # asked_before_acting, budget_respected, no_forbidden_actions… (offline OK)
python -m evals.run_evals --langsmith   # tracked experiment (LANGSMITH_API_KEY)
```

See [docs/EVALUATION.md](docs/EVALUATION.md).

## 📁 Project structure

```
├── backend/
│   ├── main.py                 # FastAPI: /missions/*, /model/*, /capabilities, SSE
│   ├── mission/
│   │   ├── agent.py            # create_agent + HITL + BYO-model + guardrails; stream, fork, history
│   │   ├── policy.py           # risk assessment, autonomy, previews → InterruptOnConfig.when
│   │   ├── tools.py            # reading + acting tools (Command world updates), ask_user, remember
│   │   ├── world.py            # the simulated world: seed data + reducer
│   │   ├── catalog.py          # restaurants, flights, hotels, quotes; starter missions
│   │   └── pilot.py            # scripted offline model that flies the starter missions
│   ├── client_model.py         # model settings from the UI (X-LLM-* headers, per request)
│   ├── llm.py                  # provider-agnostic model factory + mock
│   ├── persistence.py          # Postgres / SQLite / in-memory
│   ├── approval_policy.py      # Jev / regex risk classifiers
│   ├── guardrails.py · middleware_pack.py · run_control.py · memory.py · mcp_tools.py · agui.py
│   ├── evals/                  # dataset + evaluators + runner
│   └── test_main.py · test_infra.py · test_evals.py
├── frontend/
│   ├── app/page.tsx            # header, gallery ↔ workspace
│   ├── components/             # Gallery, Workspace, Feed, ApprovalCard, QuestionCard, WorldPanel, MissionPanel, ModelSettings
│   └── lib/                    # api.ts (types, SSE, vocabulary), useMission.ts (state machine), modelSettings.ts
├── docs/ · examples/copilotkit · scripts/record_demo.py · langgraph.json · docker-compose.yml
```

## 🤝 Contributing · 📝 License

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). MIT — see [LICENSE](LICENSE).

## 🔗 Resources

- [LangGraph docs](https://docs.langchain.com/oss/python/langgraph/overview) · [Human-in-the-loop guide](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [LangGraph time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel) · [AG-UI](https://docs.ag-ui.com) · [Model Context Protocol](https://modelcontextprotocol.io)
