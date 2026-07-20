# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`RESEARCH_MAX_SUBQUERIES`** — caps the number of parallel sub-researchers in
  the Workflow engine. The workflow makes one concurrent LLM call per
  sub-question, so on a rate-limited key (e.g. a free tier) setting this to 1-2
  avoids bursting past requests-per-minute limits.

### Changed
- The README demo GIF is now an **end-to-end tour on a real model** (Gemini):
  agent tool-approval (approve / edit / answer / reject) → Workflow multi-step
  human-in-the-loop with parallel research → time travel. Regenerate any time
  with `scripts/record_demo.py`.

### Fixed
- **Content-block responses** from newer models (e.g. Gemini 3.x, Claude with
  thinking) return `message.content` as a list of typed blocks rather than a
  string. Added `llm.text_of()` and applied it wherever a response was treated
  as text (workflow nodes, approval drafter, and both engines' token streaming +
  final answer), so the template works with these models instead of crashing on
  `content.split(...)` or rendering `[object Object]` in the UI.

### Added
- **Live tool progress**: the `web_search` tool now streams "🔎 Searching…" /
  "📄 Found N sources" progress via `get_stream_writer`, so the previously silent
  post-approval tool run shows activity in both the agent and workflow engines
  (flows through the existing `stream_mode="custom"` path — no UI changes).
- **Demo GIF** in the README (`docs/demo.gif`) showing the human-in-the-loop
  flow: ask → generative approval card → per-field edit → approve → streamed
  answer. Reproducible via `scripts/record_demo.py` (Playwright + Pillow), which
  captures the running app — re-run it with a real model for nicer content.
- **CopilotKit example** (`examples/copilotkit/`): a standalone, runnable
  Next.js app that drives the agent from a CopilotKit chat over the AG-UI
  protocol (`/api/copilotkit` runtime → `HttpAgent` → backend `/agui`). Its own
  `package.json`, so it doesn't touch the main `frontend/` build.
- **AG-UI protocol adapter** (`backend/agui.py`): the agent is exposed at `/agui`
  over the open [AG-UI](https://docs.ag-ui.com) protocol via `ag-ui-langgraph`, so
  any AG-UI client (e.g. CopilotKit) can drive it — human-approval pause included.
  Additive and optional: the bundled UI keeps using `/agent/*`, and the app still
  boots if `ag-ui-langgraph` is absent (endpoint just not mounted). Reported in
  `/capabilities` and shown as a header badge.
- **Generative approval card** (frontend): the agent tool-approval interrupt now
  renders as a structured card — arguments as an editable per-field form
  (generated from the tool call) plus **approve / edit / reject / answer**
  (`respond`) actions.
- **Evaluation harness** (`backend/evals/`): scores the agent on answer quality
  *and* human-in-the-loop behaviour. Deterministic evaluators — `paused_for_approval`
  (did it interrupt for approval before running its tool?), `completed`, and
  `no_pii_leak` — run offline with the mock model; an LLM-as-judge `correctness`
  metric runs with a real model. Prints a scored table locally or logs a tracked
  experiment to LangSmith (`python -m evals.run_evals [--langsmith]`). Docs in
  `docs/EVALUATION.md`.
- **Deep Agent engine** (`backend/deep_agent.py`): a third selectable engine built
  on `deepagents` that **plans** (a `write_todos` to-do list), **delegates** to
  `researcher` + `critic` **subagents** via a `task` tool, and uses a virtual
  filesystem for scratch space — with the same `web_search` human approval as the
  other engines. Added `/deep/start` + `/deep/decide` SSE endpoints and a third
  option in the UI's engine toggle (Workflow / Agent / **Deep Agent**). The
  `deepagents` import is optional: the app still boots (engine disabled) without
  it. Registered the `deep_agent` graph in `langgraph.json`.
- **Middleware power-pack** (`backend/middleware_pack.py`): the agent composes a
  curated set of prebuilt LangChain middleware alongside the custom guardrail and
  HITL middleware — `SummarizationMiddleware` (context-overflow protection on long
  threads), `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware` (runaway & cost
  guards), `ModelRetryMiddleware` (transient-error backoff), and opt-in
  `TodoListMiddleware` (a `write_todos` planning tool) / `ModelFallbackMiddleware`.
  All env-configurable with defaults that never trigger in a short chat.
- **Resilient workflow (LangGraph 1.2)**: LLM-backed graph nodes now carry a
  `retry_policy`, an optional per-node `timeout`, and `error_handler`
  **compensation** — if analysis or final generation fails, the run degrades to a
  graceful fallback (Saga pattern) instead of erroring. Configurable via
  `RETRY_MAX_ATTEMPTS` / `NODE_TIMEOUT_SECONDS`.
- `/capabilities` now reports the active `middleware` stack and `resilience`
  settings, shown as new badges in the header status strip.

- **Feature status in the UI**: a new `/capabilities` endpoint reports which
  optional features are active, and the chat header shows a status strip
  (model, guardrails, semantic memory, structured output, and an MCP tools
  count/line). The agent stream also surfaces live **guardrail** signals (a
  "redacted N PII item(s)" / "blocked" chip) and a **structured summary** card.
- **Guardrail middleware** (`backend/guardrails.py`): a custom `AgentMiddleware`
  that redacts PII (emails, phone numbers, card/SSN-like numbers) *before the
  model sees it* via `wrap_model_call`, and can refuse blocklisted input without
  calling the model. Stacks with `HumanInTheLoopMiddleware` in the agent engine —
  a demonstration of composable middleware. Configurable via `GUARDRAILS_*`
  env vars; on by default with no extra dependencies.
- **MCP tool integration** (`backend/mcp_tools.py`): optionally load tools from
  any [Model Context Protocol](https://modelcontextprotocol.io) server via
  `langchain-mcp-adapters` and expose them to the agent, gated by the same human
  approval as `web_search`. Configure with `MCP_SERVERS` (inline JSON or a file
  path); a no-op when unset.
- **Structured output** (opt-in): with `AGENT_STRUCTURED_OUTPUT=true`, the agent
  returns a validated `ResearchSummary` (`summary`, `key_findings`, `sources`,
  `confidence`) in `state["structured_response"]`, surfaced on the agent SSE
  stream.
- **Semantic long-term memory**: `memory.build_store()` builds an embeddings-
  indexed `Store` when `EMBEDDINGS_MODEL` is set, so `recall_memory` returns the
  memories most *relevant* to the current question (with graceful fallback to
  recency-based recall offline).
- **Deployment guide** (`docs/DEPLOYMENT.md`) covering Docker Compose, LangGraph
  Platform, and self-hosting with a durable checkpointer + Postgres store.

- **Second backend engine: an agentic research assistant** (`backend/agent.py`)
  built with `create_agent` + `HumanInTheLoopMiddleware`, selectable via a live
  **Workflow ↔ Agent toggle** in the UI. The model drives the loop and pauses
  for **approve / edit / reject / respond** before running a tool. Shares the
  same provider-agnostic LLM, `web_search` tool, and `Store` memory. New
  `/agent/start` and `/agent/decide` SSE endpoints.
- The offline mock model now drives a tool-calling loop, so the agent engine —
  including human-in-the-loop tool approval — works with **zero configuration**.
- **Parallel research with the `Send` API** (map-reduce): a planner decomposes
  the question and fans out concurrent sub-researchers via
  `Command(goto=[Send(...)])`, aggregated through a reset-aware reducer. Live
  progress streams to the UI via `get_stream_writer` / `stream_mode="custom"`.
- **Cross-thread long-term memory** (`backend/memory.py`) backed by a LangGraph
  `Store`: the assistant remembers a user's topics/preferences across sessions
  (new `user_id` field on `/start` and `/continue`).
- **Time travel** — `/history/{thread_id}` lists checkpoints and `/fork` rewinds
  to a past interrupt and resumes down a different path, preserving the original
  run. A "History / Rewind" panel in the UI drives it.
- Unified streaming resume: `/stream` now emits progress, tokens, and a closing
  state event for every step (one SSE path in the frontend).
- **Approve / edit / reject workflow** (`backend/approval_workflow.py`): the AI
  drafts content, a human approves it, edits it, or rejects with feedback to
  trigger a redraft (capped by `MAX_REVISIONS`). New `/approval/start` and
  `/approval/decide` endpoints and tests.
- **Approval UI** at `/approval` (`frontend/app/approval/page.tsx`) with inline
  Approve / Edit / Reject actions, plus a header link from the research assistant.
- **GitHub Codespaces / dev container** (`.devcontainer/devcontainer.json`) and an
  "Open in Codespaces" badge — one-click, fully provisioned environment.
- Registered the `approval` graph in `langgraph.json` for LangGraph Studio.

## [2.0.0] - 2026-06-01

Major modernization to the LangGraph **v1** / LangChain **v1** agent stack.

### Added
- **Provider-agnostic LLM layer** (`backend/llm.py`) via LangChain `init_chat_model` —
  OpenAI, Anthropic, Google, Groq, Mistral, IBM watsonx, Ollama, and more.
- **Zero-config offline mode**: a streaming-capable `MockChatModel` runs the full
  app (including SSE streaming) with no API keys.
- **Modern agent example** (`backend/agent.py`) using `create_agent` +
  `HumanInTheLoopMiddleware` (replaces deprecated `create_react_agent`).
- **Durable execution**: optional `AsyncSqliteSaver` checkpointer via `CHECKPOINT_DB`,
  wired through a FastAPI lifespan.
- **Example `web_search` tool** (`backend/tools.py`) with Tavily support and an
  offline fallback.
- **LangGraph Studio support** via `langgraph.json` (`research` + `agent` graphs).
- **GitHub Actions CI** for backend (pytest, Python 3.11/3.12) and frontend build.
- `/health` endpoint and configurable `CORS_ORIGINS`, `PORT`, `LOG_LEVEL`.
- Configurable frontend API base URL via `NEXT_PUBLIC_API_URL`.

### Changed
- Upgraded **LangGraph 0.2 → 1.2**, **LangChain 0.2 → 1.x**, FastAPI, Pydantic, uvicorn.
- Upgraded frontend to **Next.js 15** + **React 19**.
- `graph.py` refactored to a `build_research_graph(checkpointer)` factory and async
  state APIs; replaced `print` debugging with structured logging.
- Docker split into separate backend and frontend images; `docker-compose` now runs
  both services with a durable checkpoint volume.
- Rewrote README and `.env.example` around the provider-agnostic, zero-config workflow.

### Removed
- Dead/duplicate frontend files (`page_backup.tsx`, `page_fixed.tsx`).
- Hardcoded IBM-Watson-only configuration as the sole option.

### Security
- **Removed a hardcoded LangSmith API key** that was committed in `backend/main.py`.
  Configure all secrets via environment variables. (Rotate any previously exposed key.)

## [1.0.0] - 2025-06-13

### Added
- **Complete LangGraph interrupt workflow template**
- **Production-ready starter kit** for human-in-the-loop AI applications
- Real-time web interface for interrupt handling
- State preservation across interrupts
- Resume functionality with user choices
- FastAPI backend with RESTful endpoints
- Next.js frontend with TypeScript
- Responsive design with Tailwind CSS
- Progress bar with step visualization
- **Example workflow**: Research assistant with multiple interrupt patterns
- Markdown rendering for rich responses
- Error handling and debugging support
- **Template infrastructure**: Docker, testing, CI/CD ready
- Comprehensive README and documentation
- MIT License and contribution guidelines
- Security policy and issue templates

### Template Components
- **Modular interrupt system** - Easy to extend for different use cases
- **LLM provider abstraction** - Simple to swap between providers
- **UI component library** - Reusable interrupt interface components  
- **State management patterns** - Robust conversation and workflow state handling
- **Development workflow** - Testing, linting, and deployment configurations

### Technical Details
- LangGraph integration with `interrupt()` function
- IBM Watson ChatWatsonx LLM support
- Memory-based state persistence
- Thread-based conversation management
- ReactMarkdown for rich text rendering
- Modern UI with animations and glassmorphism effects

---

## Version History Template

Use this template for future releases:

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes in existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Security improvements
```
