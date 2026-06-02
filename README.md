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

### 🔀 Two engines, one UI

The chat app ships with a live **Workflow ↔ Agent** toggle so you can compare the two control paradigms on the same screen:

| Engine | Control flow | Human-in-the-loop |
|--------|--------------|-------------------|
| **Workflow** (`graph.py`) | Deterministic StateGraph — fixed interrupt points + parallel `Send` research | Structured choices at each step |
| **Agent** (`agent.py`) | Model-driven `create_agent` loop — the LLM decides when to call tools | Approve / edit / reject the tool call before it runs |

Both share the same provider-agnostic LLM, `web_search` tool, and long-term memory.

## 🚀 Features

- **🧩 Human-in-the-loop, done right** — multiple interrupt points, resume with approve/edit/redirect.
- **🔀 Parallel research (`Send`)** — a planner fans out concurrent sub-researchers (map-reduce) via `Command(goto=[Send(...)])`, with **live progress streaming**.
- **🧠 Long-term memory** — a LangGraph `Store` remembers a user's topics & preferences **across sessions**, not just within a thread.
- **⏪ Time travel** — rewind to any past checkpoint and **fork** a different path; the original run is preserved.
- **🔌 Provider-agnostic** — OpenAI, Anthropic, Google, Groq, Mistral, IBM watsonx, Ollama… via LangChain's `init_chat_model`. One env var to switch.
- **🆓 Zero-config demo** — a streaming-capable mock model runs the whole app with **no API keys**.
- **💾 Durable execution** — optional `AsyncSqliteSaver` checkpointer; workflows survive server restarts.
- **🤖 Latest agent stack** — LangGraph **v1.2** + LangChain **v1**, `create_agent`, and `HumanInTheLoopMiddleware`.
- **📡 Streaming** — Server-Sent Events stream progress *and* the final answer to the UI.
- **🔭 LangGraph Studio ready** — `langgraph.json` registers all graphs for `langgraph dev`.
- **🎨 Modern UI** — Next.js 15 + React 19 chat interface with live progress and a rewind panel.
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

## 🔭 Visualize with LangGraph Studio

```bash
pip install "langgraph-cli[inmem]"
langgraph dev          # opens LangGraph Studio with the research, approval, and agent graphs
```

`langgraph.json` registers all three graphs so you can step through interrupts visually.

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
| `/approval/start` | POST | Draft content for a task and pause for review |
| `/approval/decide` | POST | Resume with `approve` / `edit` / `reject` |
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

## 📁 Project structure

```
langgraph-interrupt-workflow-template/
├── backend/
│   ├── main.py                # FastAPI app (lifespan-managed graphs, SSE streaming)
│   ├── graph.py               # Multi-step human-in-the-loop research workflow
│   ├── approval_workflow.py   # Approve / edit / reject workflow
│   ├── agent.py               # create_agent + HumanInTheLoopMiddleware example
│   ├── memory.py              # Cross-thread long-term memory (Store)
│   ├── llm.py                 # Provider-agnostic LLM factory + offline mock model
│   ├── tools.py               # Example web_search tool (Tavily / mock)
│   ├── test_main.py           # Pytest suite
│   ├── requirements.txt
│   └── .env.example
├── frontend/                  # Next.js 15 + React 19 UI
│   ├── app/page.tsx           # Research assistant chat
│   ├── app/approval/page.tsx  # Approve / edit / reject UI
│   └── Dockerfile
├── .devcontainer/             # GitHub Codespaces / VS Code dev container
├── langgraph.json             # LangGraph Studio config (research + approval + agent)
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
