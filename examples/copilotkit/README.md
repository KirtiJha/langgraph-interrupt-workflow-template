# CopilotKit × AG-UI example

A minimal [CopilotKit](https://copilotkit.ai) chat that drives **this template's
human-in-the-loop agent** over the open **[AG-UI protocol](https://docs.ag-ui.com)** —
approval pause included. It talks to the backend's `/agui` endpoint (see
`backend/agui.py`); the model and all agent logic stay in the Python backend.

This is a **standalone** app with its own `package.json`, so it doesn't affect the
main `frontend/` build.

```
┌─────────────┐   /api/copilotkit    ┌──────────────┐    AG-UI (/agui)   ┌──────────────┐
│ CopilotChat │ ───────────────────► │ CopilotKit   │ ─────────────────► │  FastAPI     │
│  (page.tsx) │ ◄─────────────────── │ runtime      │ ◄───────────────── │  agent       │
└─────────────┘                      │ (route.ts)   │                    │ (agui.py)    │
                                     └──────────────┘                    └──────────────┘
```

## Run it

**1. Start the template backend** (from the repo root) so `/agui` is live:

```bash
cd backend
pip install -r requirements.txt     # includes ag-ui-langgraph
python main.py                      # http://localhost:8000  (AG-UI at /agui)
```

> Works with the zero-config mock model. For a real agent that actually plans and
> searches, set `LLM_MODEL` + a provider key in `backend/.env`.

**2. Start this example** (in a new terminal):

```bash
cd examples/copilotkit
cp .env.example .env                # AGUI_URL defaults to http://127.0.0.1:8000/agui
npm install
npm run dev                         # http://localhost:3001
```

Open http://localhost:3001 and ask it to research something — the agent pauses
for approval before it searches, surfaced right in the CopilotKit chat.

## How it's wired

- **`app/api/copilotkit/route.ts`** — a `CopilotRuntime` that registers the
  backend as an AG-UI `HttpAgent` (`@ag-ui/client`) pointed at `AGUI_URL`, exposed
  at `/api/copilotkit`.
- **`app/page.tsx`** — `<CopilotKit runtimeUrl="/api/copilotkit" agent="research_agent">`
  wrapping `<CopilotChat/>`.

To point at a deployed backend, set `AGUI_URL` in `.env`.

## Notes

- No LLM key is needed in *this* app — the model lives in the Python backend.
- The bundled `frontend/` UI still uses the `/agent/*` SSE endpoints directly;
  this example is an alternative front end over the standard protocol, showing the
  same agent is portable across UIs.
