"""FastAPI server exposing the LangGraph human-in-the-loop research workflow.

The graph is compiled at startup with a checkpointer chosen from the
environment:

- ``CHECKPOINT_DB=checkpoints.sqlite`` → durable, resumable state via
  ``AsyncSqliteSaver`` (survives server restarts — LangGraph's durable
  execution feature).
- unset → in-memory state via ``MemorySaver`` (great for local dev).

No secrets are hardcoded here; configure everything through environment
variables (see ``.env.example``).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from agent import build_agent, stream_agent_response
from approval_workflow import build_approval_graph
from graph import build_research_graph, stream_research_response
from memory import load_user_memory, save_user_memory

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Compile the graphs with a checkpointer (+ store for long-term memory)."""
    # Cross-thread long-term memory. Swap for a Postgres-backed store in prod.
    store = InMemoryStore()
    app.state.store = store

    checkpoint_db = os.getenv("CHECKPOINT_DB")
    if checkpoint_db:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        logger.info("Using durable AsyncSqliteSaver at %s", checkpoint_db)
        async with AsyncSqliteSaver.from_conn_string(checkpoint_db) as saver:
            app.state.graph = build_research_graph(checkpointer=saver, store=store)
            app.state.approval_graph = build_approval_graph(checkpointer=saver)
            app.state.agent_graph = build_agent(checkpointer=saver, store=store)
            yield
    else:
        logger.info("Using in-memory MemorySaver (set CHECKPOINT_DB for durability)")
        saver = MemorySaver()
        app.state.graph = build_research_graph(checkpointer=saver, store=store)
        app.state.approval_graph = build_approval_graph(checkpointer=saver)
        app.state.agent_graph = build_agent(checkpointer=saver, store=store)
        yield


app = FastAPI(title="LangGraph Interrupt Workflow Template", lifespan=lifespan)

_allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request models ---------------------------------------------------------
class ChatInput(BaseModel):
    message: str
    user_id: str | None = None  # enables cross-session long-term memory


class ResumeInput(BaseModel):
    thread_id: str
    choice: str
    user_input: str | None = None


class ContinueInput(BaseModel):
    thread_id: str
    message: str
    user_id: str | None = None


class ForkInput(BaseModel):
    thread_id: str
    checkpoint_id: str
    choice: str  # the (possibly different) decision to apply at that checkpoint


class AgentStart(BaseModel):
    message: str
    user_id: str | None = None
    thread_id: str | None = None  # provide to continue an existing agent thread


class AgentDecision(BaseModel):
    thread_id: str
    # One decision per pending tool call, e.g.
    #   {"type": "approve"}
    #   {"type": "edit", "edited_action": {"name": "web_search", "args": {...}}}
    #   {"type": "reject", "message": "..."}  /  {"type": "respond", "message": "..."}
    decisions: list[dict]


class ApprovalStart(BaseModel):
    task: str


class ApprovalDecision(BaseModel):
    thread_id: str
    action: str  # "approve" | "edit" | "reject"
    content: str | None = None  # edited draft, when action == "edit"
    feedback: str | None = None  # change request, when action == "reject"


# --- Helpers ----------------------------------------------------------------
def _interrupt_info(result) -> tuple[bool, str | None]:
    """Extract interrupt status and message from an ainvoke result."""
    if isinstance(result, dict) and result.get("__interrupt__"):
        return True, result["__interrupt__"][0].value
    return False, None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/start")
async def start_chat(chat_input: ChatInput, request: Request):
    """Start a new research conversation."""
    graph = request.app.state.graph
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "messages": [],
        "user_query": chat_input.message,
        "research_plan": "",
        "research_results": [],
        "sub_queries": [],
        "analysis": "",
        "final_response": "",
        "current_step": "planning",
        "requires_user_input": False,
        "interrupt_data": None,
        "user_choice": None,
        "user_id": chat_input.user_id,
        "user_memory": None,
    }

    try:
        result = await graph.ainvoke(initial_state, config)
        state = await graph.aget_state(config)
        is_interrupted, interrupt_message = _interrupt_info(result)
        return {
            "thread_id": thread_id,
            "state": state.values,
            "next": state.next,
            "requires_input": is_interrupted,
            "interrupt_message": interrupt_message,
        }
    except Exception as exc:
        logger.exception("Error starting research")
        raise HTTPException(status_code=500, detail=f"Error starting research: {exc}")


@app.get("/get_state/{thread_id}")
async def get_research_state(thread_id: str, request: Request):
    """Get the current state of a conversation."""
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await graph.aget_state(config)
        if not state.values:
            raise HTTPException(status_code=404, detail="Thread not found")
        is_interrupted = bool(state.next)
        message = f"Waiting for input for {state.next[0]}..." if is_interrupted else None
        return {
            "state": state.values,
            "next": state.next,
            "requires_input": is_interrupted,
            "interrupt_message": message,
            "current_step": state.values.get("current_step", "unknown"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Error getting state: {exc}")


@app.post("/resume")
async def resume_research(data: ResumeInput, request: Request):
    """Resume an interrupted conversation with the user's choice."""
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": data.thread_id}}
    try:
        result = await graph.ainvoke(Command(resume=data.choice), config)
        state = await graph.aget_state(config)
        is_interrupted, interrupt_message = _interrupt_info(result)
        return {
            "state": state.values,
            "next": state.next,
            "requires_input": is_interrupted,
            "interrupt_message": interrupt_message,
            "current_step": state.values.get("current_step", "completed"),
        }
    except Exception as exc:
        logger.exception("Error resuming research")
        raise HTTPException(status_code=500, detail=f"Error resuming research: {exc}")


@app.post("/continue")
async def continue_conversation(data: ContinueInput, request: Request):
    """Continue a finished conversation with a follow-up question."""
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": data.thread_id}}
    try:
        current_state = await graph.aget_state(config)
        if not current_state.values:
            raise HTTPException(status_code=404, detail="Thread not found")

        follow_up_state = {
            "user_query": data.message,
            "research_plan": "",
            "research_results": [],  # reset prior findings (reset_or_append reducer)
            "sub_queries": [],
            "analysis": "",
            "final_response": "",
            "current_step": "planning",
            "requires_user_input": False,
            "interrupt_data": None,
            "user_choice": None,
            "user_id": data.user_id or current_state.values.get("user_id"),
            "user_memory": None,
        }

        result = await graph.ainvoke(follow_up_state, config)
        state = await graph.aget_state(config)
        is_interrupted, interrupt_message = _interrupt_info(result)
        return {
            "state": state.values,
            "next": state.next,
            "requires_input": is_interrupted,
            "interrupt_message": interrupt_message,
            "current_step": state.values.get("current_step", "planning"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error continuing conversation")
        raise HTTPException(status_code=500, detail=f"Error continuing conversation: {exc}")


# --- Approval workflow (draft → approve / edit / reject → send) -------------
def _approval_payload(state, result) -> dict:
    """Build a response describing the current approval state."""
    is_interrupted, interrupt_message = _interrupt_info(result)
    return {
        "state": state.values,
        "next": state.next,
        "requires_input": is_interrupted,
        "interrupt": interrupt_message,
        "draft": state.values.get("draft", ""),
        "status": state.values.get("status", "unknown"),
        "final_output": state.values.get("final_output", ""),
        "revision_count": state.values.get("revision_count", 0),
    }


@app.post("/approval/start")
async def approval_start(data: ApprovalStart, request: Request):
    """Draft content for a task and pause for human review."""
    graph = request.app.state.approval_graph
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "messages": [],
        "task": data.task,
        "draft": "",
        "feedback": "",
        "revision_count": 0,
        "decision": "",
        "status": "drafting",
        "final_output": "",
    }
    try:
        result = await graph.ainvoke(initial_state, config)
        state = await graph.aget_state(config)
        return {"thread_id": thread_id, **_approval_payload(state, result)}
    except Exception as exc:
        logger.exception("Error starting approval workflow")
        raise HTTPException(status_code=500, detail=f"Error starting approval: {exc}")


@app.post("/approval/decide")
async def approval_decide(data: ApprovalDecision, request: Request):
    """Resume the approval workflow with approve / edit / reject."""
    graph = request.app.state.approval_graph
    config = {"configurable": {"thread_id": data.thread_id}}

    action = data.action.lower()
    resume_value: dict = {"action": action}
    if action == "edit":
        resume_value["content"] = data.content or ""
    elif action == "reject":
        resume_value["feedback"] = data.feedback or ""

    try:
        result = await graph.ainvoke(Command(resume=resume_value), config)
        state = await graph.aget_state(config)
        return _approval_payload(state, result)
    except Exception as exc:
        logger.exception("Error deciding approval workflow")
        raise HTTPException(status_code=500, detail=f"Error in approval decision: {exc}")


def _stream_response(
    graph, thread_id: str, choice: str, config: dict | None = None
) -> StreamingResponse:
    async def generate_stream():
        async for chunk in stream_research_response(graph, thread_id, choice, config):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'content': '', 'done': True})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/stream")
async def stream_research(data: ResumeInput, request: Request):
    """Resume and stream progress + the final response (SSE)."""
    return _stream_response(request.app.state.graph, data.thread_id, data.choice)


@app.get("/stream")
async def stream_research_get(thread_id: str, choice: str, request: Request):
    """Resume and stream via GET (for EventSource)."""
    return _stream_response(request.app.state.graph, thread_id, choice)


# --- Agent engine (create_agent + HITL middleware) --------------------------
def _sse(generator) -> StreamingResponse:
    async def body():
        async for chunk in generator:
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/agent/start")
async def agent_start(data: AgentStart, request: Request):
    """Start (or continue) an agentic run; streams progress, tokens, approvals."""
    graph = request.app.state.agent_graph
    store = request.app.state.store
    is_new = not data.thread_id
    thread_id = data.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    from langchain_core.messages import HumanMessage, SystemMessage

    messages = []
    if is_new:
        # Inject cross-session memory as a leading system message (first turn only).
        memory = await load_user_memory(store, data.user_id)
        if memory:
            messages.append(SystemMessage(content=f"Remembered context:\n{memory}"))
    messages.append(HumanMessage(content=data.message))

    async def gen():
        yield {"type": "thread", "thread_id": thread_id}
        final_seen = ""
        async for ev in stream_agent_response(graph, thread_id, {"messages": messages}, config):
            if ev.get("type") == "state" and not ev.get("requires_input"):
                final_seen = ev.get("final_response", "")
            yield ev
        if final_seen:
            await save_user_memory(store, data.user_id, f"Asked the agent about: {data.message[:120]}")

    return _sse(gen())


@app.post("/agent/decide")
async def agent_decide(data: AgentDecision, request: Request):
    """Resume the agent with approve / edit / reject / respond decisions."""
    graph = request.app.state.agent_graph
    config = {"configurable": {"thread_id": data.thread_id}}
    command = Command(resume={"decisions": data.decisions})
    return _sse(stream_agent_response(graph, data.thread_id, command, config))


# --- Time travel (checkpoint history + fork) --------------------------------
@app.get("/history/{thread_id}")
async def get_history(thread_id: str, request: Request):
    """List the checkpoints for a thread so a user can rewind / fork."""
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    try:
        checkpoints = []
        async for snap in graph.aget_state_history(config):
            nxt = list(snap.next)
            checkpoints.append(
                {
                    "checkpoint_id": snap.config.get("configurable", {}).get("checkpoint_id"),
                    "step": (snap.metadata or {}).get("step"),
                    "next": nxt,
                    "has_interrupt": bool(nxt),
                    "current_step": (snap.values or {}).get("current_step"),
                    "user_query": (snap.values or {}).get("user_query", ""),
                    "created_at": str(snap.created_at) if snap.created_at else None,
                }
            )
        return {"thread_id": thread_id, "checkpoints": checkpoints}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Error reading history: {exc}")


@app.post("/fork")
async def fork_from_checkpoint(data: ForkInput, request: Request):
    """Rewind to a past checkpoint and resume with a (possibly different) choice.

    Streams the forked run just like ``/stream``. The new run branches off the
    chosen checkpoint without losing the original history.
    """
    config = {
        "configurable": {
            "thread_id": data.thread_id,
            "checkpoint_id": data.checkpoint_id,
        }
    }
    return _stream_response(request.app.state.graph, data.thread_id, data.choice, config)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
