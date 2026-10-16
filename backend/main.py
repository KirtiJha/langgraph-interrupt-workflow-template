"""Repo Steward — FastAPI backend.

A maintainer's agent for GitHub repositories: it triages issues, reviews pull
requests, sweeps stale threads, drafts release notes and welcomes contributors,
and **asks before anything public happens**. Every mission is a LangGraph
thread that streams over SSE, pauses on per-call human-in-the-loop interrupts,
survives restarts (Postgres) and can be rewound and forked at decision points.

Endpoints:

- ``GET  /repos/inspect?repo=owner/name``     validate a repo and preview its board
- ``GET  /repos/mine``                        repositories the visitor's token can access
- ``GET  /missions``                          starter missions + the sample repo
- ``POST /missions/start``                    start a mission on a repo (SSE)
- ``POST /missions/{id}/decide``              answer approvals / questions and resume (SSE)
- ``POST /missions/{id}/continue``            a follow-up goal on the same thread (SSE)
- ``POST /missions/{id}/fork``                branch from a past decision point (SSE)
- ``POST /missions/{id}/cancel``              graceful stop (progress is saved)
- ``GET  /missions/{id}``                     current state (board, pending, report)
- ``GET  /missions/{id}/timeline``            the feed so far (for reloads)
- ``GET  /missions/{id}/history``             decision points for time travel
- ``GET  /capabilities``, ``/model/*``, ``/health``, ``/agui``

A visitor's GitHub token arrives as ``X-GitHub-Token`` and is scoped to the
request, like the ``X-LLM-*`` model settings. Without one, public repos are
read-only and actions are recorded as proposals.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

import approval_policy
import client_model
import persistence
import run_control
from agui import AGUI_AVAILABLE, AGUI_PATH, mount_agui
from agui import bind_persistence as agui_bind_persistence
from client_model import ClientModelConfigError, ClientModelConfigMiddleware, scrub
from guardrails import GuardrailMiddleware
from llm import get_llm, model_status, requests_per_second, text_of, using_mock_llm
from mcp_tools import load_mcp_tools
from memory import build_store, index_config, load_user_memory, save_user_memory
from middleware_pack import active_middleware_names
from steward import agent as M
from steward import catalog, policy
from steward.fixture import SAMPLE_REPO_NAME
from steward.github import GitHubError, GitHubTokenMiddleware, backend_for, list_user_repos, parse_repo, read_token, write_token
from steward.github import scrub as scrub_token

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def _capabilities(store, mcp_tools) -> dict:
    guardrail = GuardrailMiddleware.from_env()
    return {
        "model": {**model_status(), "requests_per_second": requests_per_second(),
                  "client_config": client_model.policy()},
        "persistence": persistence.describe(),
        "guardrails": {"enabled": guardrail is not None,
                       "redact_pii": bool(guardrail and guardrail.redact_pii),
                       "blocklist_count": len(guardrail.blocklist) if guardrail else 0},
        "semantic_memory": getattr(store, "index_config", None) is not None,
        "mcp": {"enabled": bool(mcp_tools), "tools": [getattr(t, "name", "tool") for t in mcp_tools]},
        "middleware": ["client_model", "offline_pilot", *(["guardrails"] if guardrail else []),
                       *active_middleware_names(get_llm()), "human_in_the_loop(per_call)"],
        "agui": {"enabled": AGUI_AVAILABLE, "path": AGUI_PATH if AGUI_AVAILABLE else None},
        "graceful_cancel": run_control.CANCEL_SUPPORTED,
        "hitl": {**approval_policy.describe(), **policy.describe()},
        "offline_pilot": using_mock_llm(),
        "github": {"server_token": read_token() is not None, "server_token_writes": write_token() is not None},
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_tools = await load_mcp_tools()
    async with AsyncExitStack() as stack:
        mode = persistence.persistence_mode()
        if mode == "postgres":
            saver, store = await stack.enter_async_context(
                persistence.open_postgres(persistence.database_url(), index=index_config()))
        elif mode == "sqlite":
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            saver = await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(os.getenv("CHECKPOINT_DB")))
            store = build_store()
        else:
            logger.info("Using in-memory MemorySaver (set DATABASE_URL or CHECKPOINT_DB for durability)")
            saver, store = MemorySaver(), build_store()
        app.state.store = store
        app.state.capabilities = _capabilities(store, mcp_tools)
        app.state.graph = M.build_steward_agent(checkpointer=saver, store=store, extra_tools=mcp_tools)
        agui_bind_persistence(saver, store)
        yield


app = FastAPI(title="Repo Steward", lifespan=lifespan)
mount_agui(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Model settings (X-LLM-*) and the GitHub token (X-GitHub-Token) chosen in the
# UI are scoped to each request and never stored.
app.add_middleware(ClientModelConfigMiddleware)
app.add_middleware(GitHubTokenMiddleware)


@app.exception_handler(GitHubError)
async def _github_error(_request: Request, exc: GitHubError):
    return JSONResponse(status_code=400, content={"detail": f"GitHub: {scrub_token(str(exc))}"})


@app.exception_handler(ClientModelConfigError)
async def _client_model_error(_request: Request, exc: ClientModelConfigError):
    return JSONResponse(status_code=400, content={"detail": f"Model settings: {exc}"})


# --- Request models ---------------------------------------------------------
class MissionStart(BaseModel):
    repo: str = SAMPLE_REPO_NAME  # owner/name or a github.com URL
    goal: str
    mission_id: Optional[str] = None
    user_id: Optional[str] = None
    autonomy: str = Field("careful", pattern="^(observe|careful|balanced|autopilot)$")


class Decisions(BaseModel):
    # {interrupt_id: {"type": "approve"} | {"type": "edit", "edited_action": {...}} |
    #                {"type": "reject", "message": "…"} | {"type": "respond", "message": "…"}
    #                | "<answer to a question>"}
    decisions: dict[str, Any]


class FollowUp(BaseModel):
    message: str


class Fork(BaseModel):
    checkpoint_id: str


class Cancel(BaseModel):
    reason: str = "paused by user"


# --- Helpers ----------------------------------------------------------------
def _sse(generator) -> StreamingResponse:
    async def body():
        async for chunk in generator:
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(body(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


async def _require_thread(graph, thread_id: str):
    state = await graph.aget_state(_config(thread_id))
    if state.values:
        return state
    hint = (" This server keeps state in memory, so a restart — or another serverless instance — loses "
            "missions. Set DATABASE_URL (Postgres) for durable state."
            if persistence.persistence_mode() == "memory" else "")
    raise HTTPException(status_code=404, detail=f"Mission '{thread_id}' not found.{hint}")


def _memory_key(user_id: Optional[str], repo: Optional[str]) -> Optional[str]:
    """Memories are per visitor *and* per repository."""
    return f"{user_id}@{repo}" if user_id and repo else None


async def _with_memory(request: Request, memory_key: Optional[str], stream, mission_title: str):
    """Pass events through; when the report lands, remember the outcome."""
    async for event in stream:
        if event.get("type") == "report" and memory_key:
            summary = (event["report"] or {}).get("summary", "")
            if summary:
                await save_user_memory(request.app.state.store, memory_key, f"{mission_title}: {summary}")
        yield event


# --- Meta -------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/capabilities")
async def capabilities(request: Request):
    return getattr(request.app.state, "capabilities", {})


@app.get("/model/providers")
async def model_providers():
    return {"providers": client_model.public_providers(), "policy": client_model.policy(),
            "server_default": model_status()}


@app.post("/model/test")
async def model_test():
    """Check the model in the request's X-LLM-* headers. Never returns the key."""
    override = client_model.get_override()
    label = (override or {}).get("model") or model_status().get("name")
    started = time.perf_counter()
    try:
        reply = await asyncio.wait_for(get_llm().ainvoke("Reply with the single word: OK"), timeout=30)
        sample = (text_of(getattr(reply, "content", reply)) or "").strip()[:80]
        return {"ok": True, "model": label, "latency_ms": int((time.perf_counter() - started) * 1000),
                "sample": sample}
    except asyncio.TimeoutError:
        error = "Timed out after 30s."
    except Exception as exc:
        error = scrub(f"{type(exc).__name__}: {exc}")[:500]
    return {"ok": False, "model": label, "latency_ms": int((time.perf_counter() - started) * 1000), "error": error}


# --- Missions ---------------------------------------------------------------
@app.get("/repos/inspect")
async def repo_inspect(repo: str, request: Request, user_id: Optional[str] = None):
    """Validate a repo slug/URL, load its board, and say what the visitor can do."""
    slug = parse_repo(repo)
    if not slug:
        raise HTTPException(status_code=400, detail="Enter a repository as owner/name or a github.com URL.")
    board = await asyncio.to_thread(backend_for(slug).load_board)
    memory = await load_user_memory(request.app.state.store, _memory_key(user_id, slug), limit=8)
    return {
        "repo": board["repo"], "labels": board["labels"], "issues": board["issues"], "pulls": board["pulls"],
        "mode": board["mode"], "can_write": board["can_write"], "rate": board.get("rate", {}),
        "token": "user" if request.headers.get("x-github-token") else ("server" if read_token() else None),
        "memories": [m[2:] for m in memory.splitlines() if m.startswith("- ")],
    }


@app.get("/repos/mine")
async def repos_mine():
    """Repositories the visitor's own GitHub token can access (for the picker)."""
    repos = await asyncio.to_thread(list_user_repos)
    return {"repos": repos, "count": len(repos)}


@app.get("/missions")
async def missions():
    """The gallery: starter missions and the sample repository."""
    return {"missions": catalog.MISSIONS, "sample_repo": SAMPLE_REPO_NAME, "offline_pilot": using_mock_llm()}


@app.post("/missions/start")
async def mission_start(data: MissionStart, request: Request):
    graph = request.app.state.graph
    thread_id = str(uuid.uuid4())
    goal = data.goal.strip()
    if not goal:
        raise HTTPException(status_code=400, detail="Tell me what to do.")
    slug = parse_repo(data.repo)
    if not slug:
        raise HTTPException(status_code=400, detail="Enter a repository as owner/name or a github.com URL.")
    board = await asyncio.to_thread(backend_for(slug).load_board)
    autonomy = data.autonomy
    if board["mode"] == "live" and not board["can_write"]:
        autonomy = "observe"  # nothing can execute without a write token
    mission_id = data.mission_id or catalog.mission_for_goal(goal)
    title = catalog.MISSIONS_BY_ID.get(mission_id or "", {}).get("title") or goal[:60]
    key = _memory_key(data.user_id, slug)
    memory = await load_user_memory(request.app.state.store, key, query=goal)
    inputs = M.start_input(goal, mission_id, board, autonomy, memory, user_id=key)

    async def gen():
        yield {"type": "thread", "thread_id": thread_id, "mission_id": mission_id, "title": title, "repo": slug,
               "mode": board["mode"], "can_write": board["can_write"], "autonomy": autonomy}
        async for event in _with_memory(request, key, M.stream_mission(graph, thread_id, inputs), title):
            yield event

    return _sse(gen())


@app.post("/missions/{thread_id}/decide")
async def mission_decide(thread_id: str, data: Decisions, request: Request):
    """Answer the pending approvals / question (any subset) and resume."""
    graph = request.app.state.graph
    state = await _require_thread(graph, thread_id)
    pending = {getattr(i, "id", None) for i in state.interrupts}
    unknown = [k for k in data.decisions if k not in pending]
    if unknown or not data.decisions:
        raise HTTPException(status_code=409, detail="Those decisions don't match what the mission is waiting on. "
                                                    "Reload to see its current state.")
    values = state.values or {}
    title = catalog.MISSIONS_BY_ID.get(values.get("mission_id") or "", {}).get("title") or (values.get("goal") or "")[:60]
    stream = M.stream_mission(graph, thread_id, M.resume_command(data.decisions))
    return _sse(_with_memory(request, values.get("user_id"), stream, title))  # user_id is already the memory key


@app.post("/missions/{thread_id}/continue")
async def mission_continue(thread_id: str, data: FollowUp, request: Request):
    """A follow-up goal on the same thread, with the same world."""
    graph = request.app.state.graph
    state = await _require_thread(graph, thread_id)
    if state.next:
        raise HTTPException(status_code=409, detail="The mission is still waiting on you — decide first.")
    values = state.values or {}
    title = (data.message or "")[:60]
    stream = M.stream_mission(graph, thread_id, {"messages": [HumanMessage(content=data.message)], "report": None,
                                                 "goal": data.message})
    return _sse(_with_memory(request, values.get("user_id"), stream, title))


@app.post("/missions/{thread_id}/fork")
async def mission_fork(thread_id: str, data: Fork, request: Request):
    """Rewind to a decision point and branch: the approvals come back for new answers."""
    graph = request.app.state.graph
    await _require_thread(graph, thread_id)
    try:
        new_config = await M.fork(graph, thread_id, data.checkpoint_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=scrub(f"Can't fork there: {exc}"))
    return _sse(M.stream_mission(graph, thread_id, None, new_config))


@app.post("/missions/{thread_id}/cancel")
async def mission_cancel(thread_id: str, data: Cancel):
    if not run_control.CANCEL_SUPPORTED:
        raise HTTPException(status_code=501, detail="Graceful cancel needs LangGraph >= 1.2.")
    return {"requested": run_control.request_cancel(thread_id, data.reason)}


@app.get("/missions/{thread_id}")
async def mission_state(thread_id: str, request: Request):
    graph = request.app.state.graph
    await _require_thread(graph, thread_id)
    return await M.snapshot(graph, _config(thread_id))


@app.get("/missions/{thread_id}/timeline")
async def mission_timeline(thread_id: str, request: Request):
    """The feed as events, rebuilt from the thread's messages (for reloads)."""
    graph = request.app.state.graph
    state = await _require_thread(graph, thread_id)
    events: list[dict] = []
    for m in (state.values or {}).get("messages", []):
        if isinstance(m, HumanMessage):
            events.append({"type": "goal", "content": text_of(m.content)})
        elif isinstance(m, AIMessage):
            if text_of(m.content):
                events.append({"type": "narration", "content": text_of(m.content)})
            if m.tool_calls:
                events.append({"type": "tool_calls",
                               "calls": [{"id": tc["id"], "name": tc["name"], "args": tc["args"]} for tc in m.tool_calls]})
        elif isinstance(m, ToolMessage):
            text = text_of(m.content)
            events.append({"type": "tool_result", "id": m.tool_call_id, "name": m.name, "content": text[:2000],
                           "status": M.result_status(text)})
    return {"events": events}


@app.get("/missions/{thread_id}/history")
async def mission_history(thread_id: str, request: Request):
    graph = request.app.state.graph
    await _require_thread(graph, thread_id)
    return {"decision_points": await M.decision_points(graph, thread_id)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
