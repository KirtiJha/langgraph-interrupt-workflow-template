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
from langgraph.types import Command

from graph import build_research_graph, stream_research_response

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Compile the graph with a durable checkpointer when configured."""
    checkpoint_db = os.getenv("CHECKPOINT_DB")
    if checkpoint_db:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        logger.info("Using durable AsyncSqliteSaver at %s", checkpoint_db)
        async with AsyncSqliteSaver.from_conn_string(checkpoint_db) as saver:
            app.state.graph = build_research_graph(checkpointer=saver)
            yield
    else:
        logger.info("Using in-memory MemorySaver (set CHECKPOINT_DB for durability)")
        app.state.graph = build_research_graph(checkpointer=MemorySaver())
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


class ResumeInput(BaseModel):
    thread_id: str
    choice: str
    user_input: str | None = None


class ContinueInput(BaseModel):
    thread_id: str
    message: str


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
        "analysis": "",
        "final_response": "",
        "current_step": "planning",
        "requires_user_input": False,
        "interrupt_data": None,
        "user_choice": None,
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
            "messages": current_state.values.get("messages", []),
            "user_query": data.message,
            "research_plan": "",
            "research_results": [],
            "analysis": "",
            "final_response": "",
            "current_step": "planning",
            "requires_user_input": False,
            "interrupt_data": None,
            "user_choice": None,
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


def _stream_response(graph, thread_id: str, choice: str) -> StreamingResponse:
    async def generate_stream():
        async for chunk in stream_research_response(graph, thread_id, choice):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'content': '', 'done': True})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/stream")
async def stream_research(data: ResumeInput, request: Request):
    """Stream the final response from the response_generator node."""
    return _stream_response(request.app.state.graph, data.thread_id, data.choice)


@app.get("/stream")
async def stream_research_get(thread_id: str, choice: str, request: Request):
    """Stream the final response via GET (for EventSource)."""
    return _stream_response(request.app.state.graph, thread_id, choice)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
