# 🧩 LangGraph Interrupt Workflow Template

[![CI](https://github.com/KirtiJha/langgraph-interrupt-workflow-template/actions/workflows/ci.yml/badge.svg)](https://github.com/KirtiJha/langgraph-interrupt-workflow-template/actions/workflows/ci.yml)
[![LangGraph](https://img.shields.io/badge/LangGraph-v1-1C3C3C?logo=langchain&logoColor=white)](https://docs.langchain.com/oss/python/langgraph/overview)
[![LangChain](https://img.shields.io/badge/LangChain-v1-1C3C3C?logo=langchain&logoColor=white)](https://docs.langchain.com/oss/python/langchain/overview)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js%2015-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

⚡ A **production-ready, provider-agnostic template** for building **human-in-the-loop AI workflows** with **LangGraph v1**. Pause an agent mid-execution, ask a human to approve / edit / redirect, then resume exactly where it left off — with a polished Next.js chat UI on top.

> **Runs with zero configuration.** Clone it and go — a built-in mock model lets you explore the full interrupt flow without any API keys. Add a provider when you're ready.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/KirtiJha/langgraph-interrupt-workflow-template)

> One click → a ready-to-run dev container with Python, Node, and all dependencies installed.

---

## ✨ Why this template?

Most "agent" demos run start-to-finish with no human control. Real-world systems — approvals, content review, high-stakes tool calls — need a human in the loop. This template shows **three complementary ways** to do that with the latest LangGraph:

| Pattern | File | Best for |
|---------|------|----------|
| 🛠️ **Custom multi-step interrupt graph** | `backend/graph.py` | Workflows with several explicit decision points (approve plan → pick direction → choose format). |
| ✅ **Approve / edit / reject workflow** | `backend/approval_workflow.py` | Draft-then-review flows: the AI drafts, a human approves, edits, or rejects with feedback (redrafts on reject). |
| 🤖 **Prebuilt agent + HITL middleware** | `backend/agent.py` | Tool-using agents where you want approval *only* before sensitive actions, with minimal code (`create_agent` + `HumanInTheLoopMiddleware`). |

All three use the same primitive: `interrupt()` pauses the graph, **persists state**, and waits for `Command(resume=...)`.

### 🔀 Three engines, one UI

The chat app ships with a live **Workflow ↔ Agent ↔ Deep Agent** toggle so you can compare the control paradigms on the same screen:

| Engine | Control flow | Human-in-the-loop |
|--------|--------------|-------------------|
| **Workflow** (`graph.py`) | Deterministic StateGraph — fixed interrupt points + parallel `Send` research | Structured choices at each step |
| **Agent** (`agent.py`) | Model-driven `create_agent` loop — the LLM decides when to call tools | Approve / edit / reject the tool call before it runs |
| **Deep Agent** (`deep_agent.py`) | Plans with a to-do list, spawns **researcher + critic subagents**, uses a virtual filesystem for scratch space | Same tool approval, now inside a planning/delegation loop |

All three share the same provider-agnostic LLM, `web_search` tool, and long-term memory. *(The Deep Agent runs offline too, but its planning/delegation only becomes visible with a real provider model.)*

## 🚀 Features

- **🧩 Human-in-the-loop, done right** — multiple interrupt points, resume with approve/edit/redirect.
- **🔀 Parallel research (`Send`)** — a planner fans out concurrent sub-researchers (map-reduce) via `Command(goto=[Send(...)])`, with **live progress streaming**.
- **🧠 Long-term memory** — a LangGraph `Store` remembers a user's topics & preferences **across sessions**, not just within a thread. Optional **semantic recall** with embeddings.
- **⏪ Time travel** — rewind to any past checkpoint and **fork** a different path; the original run is preserved.
- **🛡️ Guardrail middleware** — composable safety layer that **redacts PII** before the model sees it and can block disallowed input, stacked with the HITL middleware.
- **🔗 MCP tools** — optionally load tools from any **Model Context Protocol** server and expose them to the agent, gated by the same human approval.
- **📦 Structured output** — opt in to a validated `ResearchSummary` object (`summary`, `key_findings`, `sources`, `confidence`).
- **🧠 Deep Agent engine** — a third engine (`deepagents`) that **plans**, spawns **researcher + critic subagents**, and uses a virtual filesystem — with the same tool-approval HITL.
- **🧱 Middleware power-pack** — prebuilt **summarization**, **call/tool-call limits**, **model retry**, **fallback**, and a **TodoList planner**, composed with the custom guardrail + HITL middleware.
- **♻️ Resilient workflow (LangGraph 1.2)** — per-node **retries**, **timeouts**, and **compensation** (`error_handler`) so failures degrade gracefully instead of 500ing.
- **🔌 Provider-agnostic** — OpenAI, Anthropic, Google, Groq, Mistral, IBM watsonx, Ollama… via LangChain's `init_chat_model`. One env var to switch.
- **🆓 Zero-config demo** — a streaming-capable mock model runs the whole app with **no API keys**.
- **💾 Durable execution** — optional `AsyncSqliteSaver` checkpointer; workflows survive server restarts.
- **🤖 Latest agent stack** — LangGraph **v1.2** + LangChain **v1**, `create_agent`, and `HumanInTheLoopMiddleware`.
- **📡 Streaming** — Server-Sent Events stream progress *and* the final answer to the UI.
- **🔭 LangGraph Studio ready** — `langgraph.json` registers all graphs for `langgraph dev`.
- **🎨 Modern UI** — Next.js 15 + React 19 chat interface with live progress and a rewind panel.
- **📊 Evaluation harness** — score the agent on answer **correctness** *and* whether it **paused for approval** (`backend/evals`), offline or as a tracked LangSmith experiment.
- **✅ Tested & CI'd** — pytest suite + GitHub Actions for backend and frontend.

## 🏗️ Architecture

```
┌──────────────────┐     HTTP / SSE      ┌──────────────────┐         ┌────────────────────┐
│   Frontend       │ ──────────────────► │   Backend        │ ──────► │   LangGraph        │
│   Next.js 15     │ ◄────────────────── │   FastAPI        │ ◄────── │   workflow         │
│ • Chat UI        │                     │ • /start /resume │         │ • interrupt()      │
│ • Interrupt cards│                     │ • /stream (SSE)  │         │ • checkpointer     │
│ • Live progress  │                     │ • lifespan graph │         │ • resume via Command│
└──────────────────┘                     └──────────────────┘         └────────────────────┘
```

## ⚡ Quick Start (zero config)

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # works as-is with the built-in mock model
python main.py                  # http://localhost:8000  (docs at /docs)

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

Open http://localhost:3000, ask a question, and watch the workflow pause for your input at each interrupt.

### Use a real LLM

Edit `backend/.env` and set a model + matching API key:

```env
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
# or: LLM_MODEL=claude-sonnet-4-5  LLM_PROVIDER=anthropic  ANTHROPIC_API_KEY=...
```

That's it — the workflow and agent automatically use it.

## 🧠 How interrupts work

```python
from langgraph.types import interrupt, Command

async def format_selection_interrupt(state):
    # Pause and ask the human. State is persisted automatically.
    choice = interrupt("How should I format the final answer?")
    return {"format_choice": choice}

# Later, from your API:
await graph.ainvoke(Command(resume="executive"), config)   # resumes exactly here
```

1. A node calls `interrupt(payload)` → execution pauses, state is checkpointed.
2. The API returns the interrupt payload to the UI (`requires_input: true`).
3. The user picks an option; the API calls `ainvoke(Command(resume=choice))`.
4. The graph continues from the interrupted node with the user's input.

### The modern agent pattern (HITL middleware)

```python
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

agent = create_agent(
    model,
    tools=[web_search],
    middleware=[HumanInTheLoopMiddleware(interrupt_on={"web_search": True})],
    checkpointer=checkpointer,
)
```

Try it from the CLI:

```bash
cd backend && python agent.py "What are the latest advances in solid-state batteries?"
```

### Approve / edit / reject workflow

A second example (`backend/approval_workflow.py`, UI at **`/approval`**) shows the
three canonical human actions on a single interrupt:

- **Approve** → send the draft as-is
- **Edit** → send the human's revised version
- **Reject + feedback** → the AI redrafts using the feedback, then pauses again

```python
response = interrupt({"type": "approval", "draft": draft, "actions": ["approve", "edit", "reject"]})
# resume with: Command(resume={"action": "reject", "feedback": "Make it shorter"})
```

## 🧪 Advanced LangGraph features

The research workflow is also a tour of LangGraph's more powerful primitives:

**Parallel research with `Send` (map-reduce).** A planner node splits the
question into sub-questions and fans them out to concurrent workers, combining
`Command` (state update + dynamic routing) with `Send` (one task per item):

```python
return Command(
    goto=[Send("sub_researcher", {"sub_query": q}) for q in sub_queries],
    update={"sub_queries": sub_queries},
)
```

Each worker streams a progress event (`get_stream_writer`) so the UI shows
*"Researched: …"* live; results aggregate through a reset-aware reducer.

**Cross-thread long-term memory (`Store`).** Pass a `user_id` and the assistant
remembers across sessions — a brand-new thread recalls prior topics/preferences:

```python
graph = build_research_graph(checkpointer=saver, store=InMemoryStore())
# in a node:  await store.aput(("memories", user_id), key, {"text": note})
```

**Time travel (rewind & fork).** List checkpoints and resume from any past one
down a different path — without losing the original run:

```python
async for snap in graph.aget_state_history(config): ...   # GET /history/{thread_id}
# resume from a past checkpoint -> POST /fork
graph.astream(Command(resume=new_choice),
              config={"configurable": {"thread_id": tid, "checkpoint_id": cid}})
```

## 🛡️ Production hardening

Four optional layers turn the demo into something you'd ship. All degrade
gracefully — the zero-config app is unaffected until you enable them.

**Guardrail middleware (`backend/guardrails.py`).** A custom `AgentMiddleware`
that runs on every model call, composed *alongside* the HITL middleware. It
redacts PII before the model sees it (state is never mutated) and can refuse
blocklisted input without calling the model at all:

```python
# middleware stack in build_agent():  guardrails wrap the model, HITL gates tools
middleware = [GuardrailMiddleware.from_env(), HumanInTheLoopMiddleware(...)]
```

```env
GUARDRAILS_ENABLED=true          # on by default, no extra deps
GUARDRAILS_REDACT_PII=true       # mask emails / phones / cards / SSNs
GUARDRAILS_BLOCKLIST=exploit,malware
```

**MCP tools (`backend/mcp_tools.py`).** Point `MCP_SERVERS` at any
[Model Context Protocol](https://modelcontextprotocol.io) servers (inline JSON or
a file path) and their tools are loaded and exposed to the agent — each gated by
the same human approval as `web_search`:

```env
MCP_SERVERS='{"math": {"command": "python", "args": ["server.py"], "transport": "stdio"}}'
# requires: pip install langchain-mcp-adapters
```

**Structured output (opt-in).** Set `AGENT_STRUCTURED_OUTPUT=true` (with a real
model) and the agent returns a validated `ResearchSummary` in
`state["structured_response"]`, surfaced on the agent SSE stream.

**Semantic long-term memory.** Set `EMBEDDINGS_MODEL` and memories are recalled
by *relevance* to the current question rather than recency:

```env
EMBEDDINGS_MODEL=openai:text-embedding-3-small
EMBEDDING_DIMS=1536
```

**Middleware power-pack (prebuilt LangChain middleware).** The agent composes a
curated stack of production middleware alongside the custom guardrail and HITL
middleware — all env-configurable, with defaults that never trigger in a short
chat:

- `SummarizationMiddleware` — compresses old messages so long threads don't
  overflow the context window
- `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware` — runaway & cost guards
- `ModelRetryMiddleware` — retries transient endpoint errors with backoff
- `TodoListMiddleware` *(opt-in)* — a `write_todos` planning tool for the agent
- `ModelFallbackMiddleware` *(opt-in)* — fall back to another model on failure

```env
AGENT_MODEL_CALL_LIMIT=25        # cap model calls per run
AGENT_TODO_LIST=true             # add the planning tool
AGENT_FALLBACK_MODEL=gpt-4o-mini # resilience across providers
```

**Resilient workflow (LangGraph 1.2).** The LLM-backed graph nodes are hardened
with the newest LangGraph durability primitives: a `retry_policy` (retries
transient failures with backoff), an optional per-node `timeout`, and
`error_handler` **compensation** — if analysis or final generation fails, the run
degrades to a graceful fallback (Saga pattern) instead of returning a 500:

```python
builder.add_node("response_generator", response_generator,
                 retry_policy=RetryPolicy(max_attempts=3),
                 error_handler=_response_fallback,        # graceful degrade
                 destinations=("persist_memory",))
```

```env
RETRY_MAX_ATTEMPTS=3
NODE_TIMEOUT_SECONDS=30          # per-node wall-clock cap (empty = off)
```

The active feature set is reported by `GET /capabilities` and shown as a status
strip in the chat header.

See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** for Docker, LangGraph Platform,
and Postgres-backed self-hosting.

## 🔭 Visualize with LangGraph Studio

```bash
pip install "langgraph-cli[inmem]"
langgraph dev          # opens LangGraph Studio with the research, approval, agent, and deep_agent graphs
```

`langgraph.json` registers all four graphs so you can step through interrupts visually.

## 📡 API reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/start` | POST | Start a research thread (`user_id` enables memory) |
| `/resume` | POST | Resume an interrupted workflow with a choice |
| `/stream` | GET/POST | Resume and stream progress + the final answer (SSE) |
| `/continue` | POST | Ask a follow-up on an existing thread (keeps memory) |
| `/history/{thread_id}` | GET | List checkpoints for time travel |
| `/fork` | POST | Rewind to a checkpoint and resume a different path |
| `/get_state/{thread_id}` | GET | Inspect current workflow state |
| `/agent/start` | POST | Start/continue the agent engine (SSE) |
| `/agent/decide` | POST | Resume the agent with `approve`/`edit`/`reject`/`respond` (SSE) |
| `/deep/start` | POST | Start/continue the Deep Agent engine (planning + subagents, SSE) |
| `/deep/decide` | POST | Resume the Deep Agent with a tool-approval decision (SSE) |
| `/approval/start` | POST | Draft content for a task and pause for review |
| `/approval/decide` | POST | Resume with `approve` / `edit` / `reject` |
| `/capabilities` | GET | Which optional features are active (guardrails, MCP tools, structured output, semantic memory) — drives the UI status strip |
| `/health` | GET | Liveness probe |

## ⚙️ Configuration

All configuration is via environment variables (see [`backend/.env.example`](backend/.env.example)).

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_MODEL` | Model id (e.g. `gpt-4o-mini`) | mock model |
| `LLM_PROVIDER` | Provider override (`openai`, `anthropic`, `ibm`, …) | inferred |
| `LLM_TEMPERATURE` | Sampling temperature | `0.7` |
| `USE_MOCK_LLM` | Force the offline mock model | `false` |
| `TAVILY_API_KEY` | Enables live web search in `tools.py` | – |
| `CHECKPOINT_DB` | Path to enable durable SQLite persistence | in-memory |
| `GUARDRAILS_ENABLED` | Enable the PII-redaction / blocklist middleware | `true` |
| `GUARDRAILS_BLOCKLIST` | Comma-separated phrases the agent refuses | – |
| `MCP_SERVERS` | MCP server config (inline JSON or file path) | – |
| `AGENT_STRUCTURED_OUTPUT` | Return a typed `ResearchSummary` from the agent | `false` |
| `EMBEDDINGS_MODEL` | Embeddings model for semantic memory recall | – |
| `AGENT_MODEL_CALL_LIMIT` | Cap model calls per agent run (runaway/cost guard) | `25` |
| `AGENT_TODO_LIST` | Add a `write_todos` planning tool to the agent | `false` |
| `AGENT_FALLBACK_MODEL` | Fall back to this model on failure | – |
| `RETRY_MAX_ATTEMPTS` | Per-node retry attempts in the workflow | `3` |
| `NODE_TIMEOUT_SECONDS` | Per-node wall-clock timeout | off |
| `CORS_ORIGINS` | Comma-separated allowed origins | `*` |
| `PORT` | Backend port | `8000` |

## 🐳 Docker

```bash
cp backend/.env.example backend/.env   # configure as needed
docker compose up --build
# Frontend → http://localhost:3000   Backend → http://localhost:8000
```

Compose runs the backend (with a durable SQLite checkpoint volume) and the Next.js frontend as separate services.

## 🎨 Customizing for your use case

This template ships a **research assistant** example to demonstrate the patterns. To adapt it:

1. **Define your state** in `backend/graph.py` (`ResearchState`).
2. **Add nodes**, calling `interrupt(...)` wherever you need a human decision.
3. **Wire edges** in `build_research_graph()`.
4. **Add tools** in `backend/tools.py` and expose them to the agent.
5. **Swap the LLM** by changing env vars — no code changes needed.

Great fits: content review & approval, data-processing pipelines, quality control, configuration wizards, customer-support escalation, and any workflow needing human oversight.

## 🧪 Testing

```bash
cd backend
USE_MOCK_LLM=true pytest -v     # fast, offline, no API keys
```

## 📊 Evaluation

A human-in-the-loop agent must be judged on answer quality **and** on whether it
**pauses for approval before acting**. The harness in [`backend/evals/`](backend/evals)
scores both — deterministic metrics (`paused_for_approval`, `completed`,
`no_pii_leak`) run offline with no keys, and an LLM-as-judge `correctness` metric
kicks in with a real model:

```bash
cd backend
python -m evals.run_evals               # prints a scored table (offline OK)
python -m evals.run_evals --langsmith   # tracked experiment (needs LANGSMITH_API_KEY)
```

See **[docs/EVALUATION.md](docs/EVALUATION.md)** to add your own examples and
evaluators, or gate CI on `paused_for_approval == 1.0`.

## 📁 Project structure

```
langgraph-interrupt-workflow-template/
├── backend/
│   ├── main.py                # FastAPI app (lifespan-managed graphs, SSE streaming)
│   ├── graph.py               # Multi-step human-in-the-loop research workflow
│   ├── approval_workflow.py   # Approve / edit / reject workflow
│   ├── agent.py               # create_agent + HITL + guardrails + structured output
│   ├── deep_agent.py          # Deep Agent engine (planning + researcher/critic subagents)
│   ├── guardrails.py          # PII-redaction / blocklist middleware
│   ├── middleware_pack.py     # Prebuilt middleware (summarization, limits, retry, todos)
│   ├── mcp_tools.py           # Optional Model Context Protocol tool loader
│   ├── memory.py              # Cross-thread long-term memory (Store, semantic-ready)
│   ├── llm.py                 # Provider-agnostic LLM factory + offline mock model
│   ├── tools.py               # Example web_search tool (Tavily / mock)
│   ├── evals/                 # Evaluation harness (dataset + evaluators + runner)
│   ├── test_main.py           # Pytest suite
│   ├── requirements.txt
│   └── .env.example
├── frontend/                  # Next.js 15 + React 19 UI
│   ├── app/page.tsx           # Research assistant chat
│   ├── app/approval/page.tsx  # Approve / edit / reject UI
│   └── Dockerfile
├── docs/DEPLOYMENT.md         # Docker / LangGraph Platform / Postgres deploy guide
├── .devcontainer/             # GitHub Codespaces / VS Code dev container
├── langgraph.json             # LangGraph Studio config (research + approval + agent + deep_agent)
├── .github/workflows/ci.yml
├── Dockerfile                 # Backend image
├── docker-compose.yml         # Backend + frontend services
└── README.md
```

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md). Fork → branch → PR.

## 📝 License

MIT — see [LICENSE](LICENSE).

## 🔗 Resources

- [LangGraph docs](https://docs.langchain.com/oss/python/langgraph/overview) · [What's new in v1](https://docs.langchain.com/oss/python/releases/langgraph-v1)
- [Human-in-the-loop guide](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [`create_agent`](https://docs.langchain.com/oss/python/langchain/agents) · [FastAPI](https://fastapi.tiangolo.com/) · [Next.js](https://nextjs.org/docs)
