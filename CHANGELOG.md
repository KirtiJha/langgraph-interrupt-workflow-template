# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **The template is now Mission Control.** The research assistant (workflow,
  agent, Deep Agent and approval-workflow engines) is replaced by one personal
  agent that acts on a simulated world — inbox, calendar, wallet, contacts,
  subscriptions, bookings — and asks before anything that matters.
  - `backend/mission/`: the world lives in graph state (checkpointed, rewinds,
    forks); acting tools return `Command` updates; a risk policy scores each
    action against the world and the user's autonomy level (careful / balanced /
    autopilot) and gives the approval card reasons and a preview; `ask_user`
    shows a raw `interrupt()`; `remember` writes long-term memory; a scripted
    offline pilot flies five starter missions and reacts to rejections, edits
    and answers.
  - `/missions/*` endpoints replace `/start`, `/agent/*`, `/deep/*` and
    `/approval/*`: start, decide (any subset of pending approvals and
    questions), continue, fork (branch from a decision point), cancel, state,
    timeline, history.
  - A new UI: mission gallery with an autonomy picker, a workspace with the
    live feed, decision tray (approve / edit / reject / reply, hotkeys), your
    world with pending actions drawn as ghosts, a live checklist, meters, and a
    time-travel scrubber. Reload resumes the open mission.
  - Evals rewritten around missions: `asked_before_acting`, `budget_respected`,
    `no_forbidden_actions`, `used_expected_tools`, plus an LLM judge.
  - Guardrails no longer mask email addresses by default
    (`GUARDRAILS_REDACT_EMAILS`); cards, SSNs and phones still are.
- `deepagents` is no longer a dependency.

### Added
- **Model settings in the UI** (`frontend/components/ModelSettings.tsx`,
  `backend/client_model.py`): choose the provider, model, key, base URL and
  temperature in the browser, test the connection and save. They are sent as
  `X-LLM-*` headers and scoped to each request with a ContextVar, so all engines
  use them, including Deep Agent subagents (through a `wrap_model_call`
  middleware), and nothing is stored server-side. Errors are scrubbed of the
  key. Custom base URLs are SSRF-checked on deployments. Owners can disable the
  feature or share their key with `LLM_CLIENT_*`. New endpoints:
  `GET /model/providers` and `POST /model/test`.
- **Any provider, any model** (`backend/llm.py`): beyond native providers
  (OpenAI, Anthropic and Google SDKs now ship by default; `provider:model`
  strings supported), `LLM_BASE_URL` + `LLM_API_KEY` target **any
  OpenAI-compatible endpoint** (OpenRouter, Groq, Together, DeepSeek, Ollama,
  vLLM, LM Studio, LiteLLM…), and `AI_GATEWAY_API_KEY` routes through **Vercel
  AI Gateway** for every provider's models with one key. `LLM_TEMPERATURE` is
  only sent when set (reasoning models reject non-default values).
- **Durable Postgres persistence** (`backend/persistence.py`): with
  `DATABASE_URL`/`POSTGRES_URL`, paused runs, history and long-term memory live
  in Postgres (one pgbouncer-safe pool; tables created idempotently; pgvector
  semantic memory when `EMBEDDINGS_MODEL` is set). The AG-UI endpoint is
  re-bound to the same durable graph. `/capabilities` reports the persistence
  mode, and the UI shows it.
- **Vercel deployment**: `backend/vercel.json` (300s SSE duration),
  `.python-version`, `.vercelignore`, `frontend/.env.example`, a README
  walkthrough + Deploy buttons, and a Vercel section in `docs/DEPLOYMENT.md`.
- **CI runs a real Postgres** and proves a run paused on one app instance is
  resumed by a fresh one.

### Changed
- A configured model that fails to load is now **surfaced** — logged as an
  error, reported by `/capabilities` (`model.error`, never the key) and shown as
  a red badge — instead of silently falling back to the mock.
- Resuming an unknown thread returns a **404 that explains the cause** (state
  is in memory; set `DATABASE_URL`) instead of an opaque 500.
- `backend/.env.example` ships with every model setting commented, so a fresh
  copy is genuinely zero-config, and documents all three model options.

### Added
- **Jev decision-model risk gate** (optional): the approval policy's "is this
  tool call risky?" check is now a pluggable `RiskClassifier`. The default is
  the existing regex; `HITL_RISK_CLASSIFIER=jev` asks TypeSafe AI's Jev (a
  "System One" model returning a typed verdict with calibrated confidence) and
  pauses when the call is risky **or** confidence is below
  `HITL_RISK_CONFIDENCE` — escalating uncertainty to a human. The verdict and
  confidence are shown on the approval card. Needs `langgraph-jev` +
  `TYPESAFE_API_KEY`; degrades to the regex otherwise or on API errors.
- **Per-call human-in-the-loop** (`HITL_INTERRUPT_MODE=per_call`, now the
  default): with langchain ≥ 1.4.6 each gated tool call raises its own
  interrupt, answered by interrupt id, and carries a JSON `response_schema` of
  the decisions it accepts. The agent stream forwards `interrupt_id`, per-request
  `allowed` decisions and the schema; the approval card now builds its edit form
  from the tool's real argument schema (typed fields, required markers,
  descriptions) and edits are validated server-side before the agent resumes.
  `/agent/decide` and `/deep/decide` accept either an id-keyed dict (per-call)
  or the ordered list (batched); `HITL_INTERRUPT_MODE=batched` restores the
  old contract.
- **Approval policy** (`backend/approval_policy.py`): one env-configurable rule
  for *which* tools pause and *when*, shared by the agent, deep agent and MCP
  tools. `HITL_POLICY=all` (default) gates every acting tool while exempting
  read-only ones (`HITL_NEVER`); `HITL_POLICY=selective` gates only
  `HITL_ALWAYS` tools unconditionally and uses an `InterruptOnConfig.when`
  predicate to pause other tools **only when their arguments look risky**
  (`HITL_SENSITIVE_PATTERNS`) — "approve the risky 5%, not every call".
- **Tool resilience middleware**: `ToolRetryMiddleware` + `ToolErrorMiddleware`
  (on by default) so a failing tool is retried and then surfaced to the model as
  a recoverable error instead of crashing the run; opt-in
  `ContextEditingMiddleware` (`AGENT_CONTEXT_EDIT_TOKENS`) clears stale tool
  outputs on long threads.

### Changed
- **UI/UX + accessibility pass** (frontend): the app shell now uses `100dvh`
  and a wrap-safe two-row header, so on phones the engine toggle, **History**
  and **New chat** stay reachable and the composer stays anchored; the feature
  status strip becomes a single scrollable row on mobile. Keyboard & screen
  readers: the engine toggle is an ARIA radiogroup, interrupt cards are labelled
  regions that **auto-focus their first action**, the message list is a live
  region, icon-only buttons have labels, **Escape** backs out of approval
  sub-modes / the history panel, and global `:focus-visible` rings +
  `prefers-reduced-motion` support were added. A **backend-unreachable banner**
  (with Retry, and the typed message restored) replaces a silent failure; a
  **Copy** button on assistant messages; HH:MM timestamps; and the misleading
  "Verified" label on every answer was removed.

### Fixed
- `LLM_REQUESTS_PER_SECOND` now actually throttles. Each `get_llm()` call
  previously created its own rate-limiter bucket.
- **deepagents 0.7 regression**: the default deep agent no longer includes the
  to-do list, so our prompt's `write_todos` step pointed at a missing tool —
  `TodoListMiddleware` is now passed explicitly. 0.7 also exposes **`execute`
  (a shell) and `delete`** by default, which were ungated; the approval policy
  now gates them. Pins bumped to langchain ≥ 1.4.6, langgraph ≥ 1.2.15,
  deepagents ≥ 0.7.
- **Graceful cancel** (`backend/run_control.py`, `POST /cancel`): stop an
  in-flight run using LangGraph 1.2's cooperative drain (`RunControl`). The run
  finishes its current superstep, **checkpoints its progress, and raises
  `GraphDrained`** — so nothing is corrupted and the thread stays **resumable**.
  Wired into both the workflow and agent/deep engines (which emit a `cancelled`
  event and a `resumable` flag), with a **Stop** button in the UI. Degrades to a
  501 on a LangGraph without `RunControl`; reported in `/capabilities`.
- **`LLM_REQUESTS_PER_SECOND`** — client-side request cap via LangChain's
  `InMemoryRateLimiter`, applied to every provider through `init_chat_model`.
  Smooths bursts (the workflow can fire several calls at once) so free/low-tier
  keys don't hit 429s and stall on SDK retries. Off by default.
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
