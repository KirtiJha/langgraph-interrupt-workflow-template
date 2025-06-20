# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import TypedDict, Annotated, Union
import uuid
import os
import json
from datetime import datetime

from langgraph.types import Command
from graph import research_graph, ResearchState, stream_research_response

os.environ["LANGCHAIN_API_KEY"] = "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"
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_PROJECT"] = "apextestmock"


# --- FastAPI App ---
app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


# --- Pydantic Models ---
class ChatInput(BaseModel):
    message: str


class ThreadInput(BaseModel):
    thread_id: str


class ResumeInput(BaseModel):
    thread_id: str
    user_input: str
    choice: str


class ContinueInput(BaseModel):
    thread_id: str
    message: str


@app.post("/start")
async def start_chat(chat_input: ChatInput):
    """Starts a new research conversation."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Initialize the research state
    initial_state = {
        "user_query": chat_input.message,
        "research_plan": "",
        "research_results": [],
        "analysis": "",
        "final_response": "",
        "current_step": "planning",
        "requires_user_input": False,
        "interrupt_data": None,
        "conversation_history": [],
    }

    try:
        # Start the research graph with async API
        result = await research_graph.ainvoke(initial_state, config)

        # Get the current state
        state = research_graph.get_state(config)

        # Check for interrupt in the result first (this is the correct way according to LangGraph docs)
        is_interrupted = False
        interrupt_message = None

        # Check if result contains interrupt data
        if (
            isinstance(result, dict)
            and "__interrupt__" in result
            and result["__interrupt__"]
        ):
            is_interrupted = True
            # Extract the interrupt message from the first interrupt
            interrupt_obj = result["__interrupt__"][0]
            interrupt_message = interrupt_obj.value
            print(f"DEBUG: Found interrupt in result: {interrupt_message}")
        else:
            # Fallback: check if there are next nodes to execute (old method)
            is_interrupted = state.next and len(state.next) > 0
            if is_interrupted:
                next_node = state.next[0]
                interrupt_message = f"Waiting for input for {next_node}..."

        return {
            "thread_id": thread_id,
            "state": state.values,
            "next": state.next,
            "requires_input": is_interrupted,
            "interrupt_message": interrupt_message,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error starting research: {str(e)}"
        )


@app.get("/get_state/{thread_id}")
async def get_research_state(thread_id: str):
    """Gets the current state of the research conversation."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = research_graph.get_state(config)

        # Check if there are next nodes to execute (indicates an interrupt is pending)
        is_interrupted = state.next and len(state.next) > 0
        interrupt_message = None

        if is_interrupted:
            next_node = state.next[0]
            # For get_state, we provide a generic message since we don't have the result object
            # The actual interrupt message was provided when the interrupt was first triggered
            interrupt_message = f"Waiting for input for {next_node}..."

        return {
            "state": state.values,
            "next": state.next,
            "requires_input": is_interrupted,
            "interrupt_message": interrupt_message,
            "current_step": state.values.get("current_step", "unknown"),
        }
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"Thread not found or error getting state: {e}"
        )


@app.post("/resume")
async def resume_research(data: ResumeInput):
    """Resumes a research conversation with user input."""
    config = {"configurable": {"thread_id": data.thread_id}}

    try:
        # Resume the graph with the user's choice using async API
        result = await research_graph.ainvoke(Command(resume=data.choice), config)

        # Get the latest state to return
        state = research_graph.get_state(config)

        # Check for interrupt in the result first (correct way)
        is_interrupted = False
        interrupt_message = None

        # Check if result contains interrupt data
        if (
            isinstance(result, dict)
            and "__interrupt__" in result
            and result["__interrupt__"]
        ):
            is_interrupted = True
            # Extract the interrupt message from the first interrupt
            interrupt_obj = result["__interrupt__"][0]
            interrupt_message = interrupt_obj.value
            print(f"DEBUG: Found interrupt in resume result: {interrupt_message}")
        else:
            # Fallback: check if there are next nodes to execute
            is_interrupted = state.next and len(state.next) > 0
            if is_interrupted:
                next_node = state.next[0]
                interrupt_message = f"Waiting for input for {next_node}..."

        return {
            "state": state.values,
            "next": state.next,
            "requires_input": is_interrupted,
            "interrupt_message": interrupt_message,
            "current_step": state.values.get("current_step", "completed"),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error resuming research: {str(e)}"
        )


@app.post("/continue")
async def continue_conversation(data: ContinueInput):
    """Continues an existing conversation with a new follow-up question."""
    config = {"configurable": {"thread_id": data.thread_id}}

    try:
        # Get the current state to check if conversation exists
        current_state = research_graph.get_state(config)

        if not current_state.values:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Get existing messages from the current state (using LangGraph's messages pattern)
        existing_messages = current_state.values.get("messages", [])

        # Create new state for follow-up question, preserving message history
        follow_up_state = {
            "messages": existing_messages,  # Preserve conversation messages
            "user_query": data.message,  # New question
            "research_plan": "",  # Reset research fields for new query
            "research_results": [],
            "analysis": "",
            "final_response": "",
            "current_step": "planning",
            "requires_user_input": False,
            "interrupt_data": None,
            "user_choice": None,
        }

        # Start the research graph with the new question using async API
        result = await research_graph.ainvoke(follow_up_state, config)

        # Get the updated state
        state = research_graph.get_state(config)

        # Check for interrupt in the result
        is_interrupted = False
        interrupt_message = None

        if (
            isinstance(result, dict)
            and "__interrupt__" in result
            and result["__interrupt__"]
        ):
            is_interrupted = True
            interrupt_obj = result["__interrupt__"][0]
            interrupt_message = interrupt_obj.value
            print(f"DEBUG: Found interrupt in continue result: {interrupt_message}")
        else:
            is_interrupted = state.next and len(state.next) > 0
            if is_interrupted:
                next_node = state.next[0]
                interrupt_message = f"Waiting for input for {next_node}..."

        return {
            "state": state.values,
            "next": state.next,
            "requires_input": is_interrupted,
            "interrupt_message": interrupt_message,
            "current_step": state.values.get("current_step", "planning"),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error continuing conversation: {str(e)}"
        )


@app.get("/conversation_history/{thread_id}")
async def get_conversation_history(thread_id: str):
    """Gets the conversation history for a thread."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = research_graph.get_state(config)
        return {
            "conversation_history": state.values.get("conversation_history", []),
            "thread_id": thread_id,
        }
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"Thread not found or error getting history: {e}"
        )


@app.post("/stream")
async def stream_research(data: ResumeInput):
    """Streams the research response from the response_generator node."""
    config = {"configurable": {"thread_id": data.thread_id}}

    try:
        # Stream the research response using the graph's streaming capability
        async def generate_stream():
            async for chunk in stream_research_response(data.thread_id, data.choice):
                yield f"data: {json.dumps(chunk)}\n\n"
            # Send final done message
            yield f"data: {json.dumps({'type': 'done', 'content': '', 'done': True})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error streaming research: {str(e)}"
        )


@app.get("/stream")
async def stream_research_get(thread_id: str, choice: str):
    """Streams the research response from the response_generator node via GET for EventSource."""
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # Stream the research response using the graph's streaming capability
        async def generate_stream():
            async for chunk in stream_research_response(thread_id, choice):
                yield f"data: {json.dumps(chunk)}\n\n"
            # Send final done message
            yield f"data: {json.dumps({'type': 'done', 'content': '', 'done': True})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error streaming research: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
