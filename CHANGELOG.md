# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
