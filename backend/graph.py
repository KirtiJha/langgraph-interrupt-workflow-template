"""Research-assistant workflow built with LangGraph's ``interrupt`` primitive.

This is the heart of the template: a multi-step graph that pauses at several
points to collect human decisions (approach, research direction, output
format), preserving and resuming state via a checkpointer. It demonstrates the
human-in-the-loop pattern end to end and is intentionally easy to adapt to your
own domain.

The graph is LLM- and provider-agnostic (see ``llm.py``) and runs with zero
configuration via a built-in mock model.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, Send, interrupt

from llm import get_llm
from memory import get_active_store, load_user_memory, save_user_memory
from tools import web_search

logger = logging.getLogger(__name__)

# How many parallel sub-questions to research for each approach.
SUBQUERY_COUNT = {"simplified": 2, "focused": 2, "continue_context": 3, "proceed": 4}


def reset_or_append(existing: List[str], new: List[str]) -> List[str]:
    """Reducer: an empty write resets the list; otherwise append.

    This lets parallel sub-researchers accumulate findings within a single run
    (each appends its result) while a follow-up question can start clean by
    writing ``[]``.
    """
    if not new:
        return []
    return (existing or []) + new


class ResearchState(TypedDict):
    """State threaded through the research workflow."""

    messages: Annotated[List[AnyMessage], add_messages]
    user_query: str
    research_plan: str
    # Reducer so parallel sub-researchers (fanned out via Send) can append
    # findings concurrently; a follow-up question resets it by writing [].
    research_results: Annotated[List[str], reset_or_append]
    sub_queries: List[str]
    analysis: str
    final_response: str
    current_step: str
    requires_user_input: bool
    interrupt_data: Optional[Dict[str, Any]]
    user_choice: Optional[str]
    format_choice: Optional[str]
    research_direction: Optional[str]
    # Cross-thread long-term memory (loaded from / saved to the Store).
    user_id: Optional[str]
    user_memory: Optional[str]


class SubResearchState(TypedDict):
    """Input state for a single parallel sub-researcher (via Send)."""

    user_query: str
    sub_query: str
    sub_index: int
    sub_total: int
    user_choice: str


def _previous_exchange(messages: List[AnyMessage]) -> tuple[str, str]:
    """Return the (previous_query, previous_response) pair, if any."""
    user_messages = [m for m in messages if isinstance(m, HumanMessage)]
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]
    previous_query = user_messages[-2].content if len(user_messages) > 1 else ""
    previous_response = ai_messages[-1].content if ai_messages else ""
    return str(previous_query), str(previous_response)


# --- Node 1: Research planning (interrupt) ---------------------------------
async def research_planner_interrupt(state: ResearchState) -> Dict[str, Any]:
    """Pause to let the user choose how the research should proceed."""
    logger.info("Planning research strategy")
    messages = state.get("messages", [])
    previous_query, previous_response = _previous_exchange(
        messages + [HumanMessage(content=state["user_query"])]
    )
    is_followup = bool(previous_query and previous_response)

    if is_followup:
        interrupt_msg = f"""## Follow-up Question Analysis

**Previous Question**: {previous_query}

**Current Question**: {state['user_query']}

This looks like a follow-up to our previous conversation. How would you like me to proceed?

- **proceed**: Full comprehensive research with detailed analysis
- **simplified**: Quick overview with key points
- **focused**: Targeted research on specific aspects
- **continue_context**: Build upon our previous conversation
- **cancel**: Stop the research process"""
    else:
        interrupt_msg = f"""## Research Query Analysis

I've analyzed your question: **"{state['user_query']}"**

How would you like me to approach this research?

- **proceed**: Full comprehensive research with detailed analysis
- **simplified**: Quick overview with key points
- **focused**: Targeted research on specific aspects
- **cancel**: Stop the research process"""

    user_choice = interrupt(interrupt_msg)
    logger.info("research_planner_interrupt resumed with choice=%s", user_choice)

    return {
        "messages": [HumanMessage(content=state["user_query"])],
        "research_plan": "Comprehensive research and analysis",
        "user_choice": user_choice,
        "current_step": "information_gathering",
    }


def _emit(payload: dict) -> None:
    """Emit a custom progress event to any streaming consumer (no-op otherwise)."""
    try:
        get_stream_writer()(payload)
    except Exception:  # pragma: no cover - not in a streaming context
        pass


# --- Memory: recall (start) -------------------------------------------------
async def recall_memory(state: ResearchState) -> Dict[str, Any]:
    """Load cross-thread memory for this user before planning."""
    memory = await load_user_memory(get_active_store(), state.get("user_id"))
    if memory:
        logger.info("Recalled %d chars of long-term memory", len(memory))
    return {"user_memory": memory}


# --- Node 2a: Query planner (Send fan-out via Command) ----------------------
async def query_planner(
    state: ResearchState,
) -> Command[Literal["sub_researcher", "handle_cancel"]]:
    """Decompose the question and fan out parallel sub-researchers with ``Send``."""
    user_choice = state.get("user_choice", "proceed")
    if user_choice == "cancel":
        return Command(goto="handle_cancel")

    n = SUBQUERY_COUNT.get(user_choice, 4)
    memory = state.get("user_memory") or ""
    mem_section = f"\n\nWhat we already know about this user:\n{memory}" if memory else ""

    llm = get_llm()
    system = (
        "You are a research planner. Break the user's question into "
        f"{n} distinct, focused sub-questions that together cover it thoroughly. "
        "Return each sub-question on its own line with no numbering."
    )
    response = await llm.ainvoke(
        [
            SystemMessage(content=system),
            HumanMessage(content=f"Question: {state['user_query']}{mem_section}"),
        ]
    )
    lines = [ln.strip(" -•\t") for ln in response.content.split("\n") if ln.strip()]
    sub_queries = lines[:n] or [state["user_query"]]
    while len(sub_queries) < min(n, 2):  # ensure at least a couple of workers
        sub_queries.append(f"{state['user_query']} (aspect {len(sub_queries) + 1})")

    _emit(
        {
            "type": "progress",
            "phase": "planning",
            "message": f"Planned {len(sub_queries)} parallel research threads",
            "total": len(sub_queries),
        }
    )

    sends = [
        Send(
            "sub_researcher",
            {
                "user_query": state["user_query"],
                "sub_query": q,
                "sub_index": i,
                "sub_total": len(sub_queries),
                "user_choice": user_choice,
            },
        )
        for i, q in enumerate(sub_queries)
    ]
    return Command(
        goto=sends,
        update={
            "sub_queries": sub_queries,
            "research_plan": f"Parallel research across {len(sub_queries)} sub-questions",
            "current_step": "information_gathering",
        },
    )


# --- Node 2b: Parallel sub-researcher (one per Send) ------------------------
async def sub_researcher(state: SubResearchState) -> Dict[str, Any]:
    """Research a single sub-question; results aggregate via the reducer."""
    sub = state["sub_query"]
    logger.info("Sub-researching: %s", sub)

    search_context = ""
    try:
        search_context = web_search.invoke({"query": sub})
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("web_search failed: %s", exc)

    llm = get_llm()
    response = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "You are a focused researcher. Given a sub-question and reference "
                    "material, produce one concise, substantive finding (2-3 sentences)."
                )
            ),
            HumanMessage(content=f"Sub-question: {sub}\nReference:\n{search_context}"),
        ]
    )
    finding = f"[{sub}] {response.content.strip()}"

    _emit(
        {
            "type": "progress",
            "phase": "researching",
            "message": f"Researched: {sub}",
            "index": state.get("sub_index", 0) + 1,
            "total": state.get("sub_total", 1),
        }
    )
    return {"research_results": [finding]}


# --- Cancel branch ----------------------------------------------------------
async def handle_cancel(state: ResearchState) -> Dict[str, Any]:
    """Short-circuit when the user cancels at the planning interrupt."""
    message = "Research was cancelled at your request."
    return {
        "messages": [AIMessage(content=message)],
        "research_results": ["Research cancelled by user request"],
        "final_response": message,
        "current_step": "completed",
        "requires_user_input": False,
    }


# --- Node 3: Research direction (conditional interrupt) ---------------------
async def research_direction_interrupt(state: ResearchState) -> Dict[str, Any]:
    """For comprehensive runs, pause to refine the research direction."""
    logger.info("Checking research direction")
    user_choice = state.get("user_choice", "proceed")
    messages = state.get("messages", [])
    has_context = len(messages) > 1

    if user_choice in ("proceed", "comprehensive"):
        direction_msg = """## Research Direction Refinement

I've gathered substantial information. Would you like me to explore a specific angle further?

- **technical**: Deep dive into technical aspects and implementation details
- **practical**: Focus on real-world applications and use cases
- **recent**: Emphasize latest developments and current trends
- **comparative**: Compare different approaches or solutions
- **continue**: Proceed with general comprehensive analysis"""
        if has_context:
            direction_msg += "\n- **continue_context**: Build specifically on our previous conversation"

        direction_choice = interrupt(direction_msg)
        return {"research_direction": direction_choice, "current_step": "analysis"}

    # Non-comprehensive runs skip the interrupt.
    direction = "continue_context" if has_context else "continue"
    return {"research_direction": direction, "current_step": "analysis"}


# --- Node 4: Deep analysis --------------------------------------------------
async def deep_analyzer(state: ResearchState) -> Dict[str, Any]:
    """Synthesize the gathered findings into structured insight."""
    logger.info("Analyzing information")
    llm = get_llm()
    research_summary = "\n".join(state.get("research_results", []))
    research_direction = state.get("research_direction", "continue")
    previous_query, previous_response = _previous_exchange(state.get("messages", []))
    has_context = bool(previous_query and previous_response)

    if research_direction == "continue_context" and has_context:
        system_prompt = (
            "You are an expert analyst building on a previous conversation. "
            "Connect the current analysis to the earlier discussion, identify "
            "relationships, and synthesize insights that show progression.\n"
            f"Previous question: {previous_query}\n"
            f"Previous response: {previous_response[:400]}..."
        )
        content = (
            f"Current query: {state['user_query']}\n\n"
            f"Current research findings:\n{research_summary}"
        )
    else:
        system_prompt = (
            "You are an expert analyst. Synthesize the findings into coherent "
            "insights, identify patterns and implications, and prepare actionable "
            "conclusions while noting any limitations."
        )
        content = (
            f"User query: {state['user_query']}\n\n"
            f"Research findings to analyze:\n{research_summary}"
        )

    response = await llm.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=content)]
    )
    return {"analysis": response.content, "current_step": "format_selection"}


# --- Node 5: Format selection (interrupt) -----------------------------------
async def format_selection_interrupt(state: ResearchState) -> Dict[str, Any]:
    """Pause to let the user choose the final response format."""
    logger.info("Selecting response format")
    format_choices = (
        "comprehensive",
        "executive",
        "structured",
        "conversational",
        "bullet_points",
    )

    # If a format was already supplied (e.g. via the streaming endpoint), skip.
    user_choice = state.get("user_choice", "")
    if user_choice in format_choices:
        return {"format_choice": user_choice, "current_step": "response_formatting"}

    analysis = state.get("analysis", "")
    preview = analysis[:300] + ("..." if len(analysis) > 300 else "")
    format_msg = f"""## Research Complete — Choose Response Format

Here's a preview of the analysis:

**{preview}**

How would you like the final response presented?

- **comprehensive**: Thorough, detailed response with examples
- **executive**: Concise executive summary with key recommendations
- **structured**: Clear headings and bullet points
- **conversational**: Natural, professional tone
- **bullet_points**: Quick-reference lists and takeaways"""

    format_choice = interrupt(format_msg)
    return {"format_choice": format_choice, "current_step": "response_formatting"}


# --- Node 6: Response generation --------------------------------------------
async def response_generator(state: ResearchState) -> Dict[str, Any]:
    """Produce the final formatted response (streamed by the API)."""
    logger.info("Crafting final response")
    llm = get_llm()
    format_choice = state.get("format_choice", "comprehensive")
    research_direction = state.get("research_direction", "continue")
    previous_query, previous_response = _previous_exchange(state.get("messages", []))
    has_context = bool(previous_query and previous_response)

    format_instructions = {
        "comprehensive": "Create a thorough, detailed response with examples and clear headings.",
        "executive": "Create a concise executive summary with the most critical insights and recommendations.",
        "structured": "Format with clear sections, headings, and organized bullet points.",
        "conversational": "Write in a natural, conversational tone while staying professional.",
        "bullet_points": "Organize primarily as bullet points, lists, and key takeaways.",
    }
    style = format_instructions.get(format_choice, format_instructions["comprehensive"])

    if has_context:
        system_prompt = (
            "You are writing a follow-up response that builds on a previous "
            "conversation.\n"
            f"Previous question: {previous_query}\n"
            f"Previous response: {previous_response[:300]}...\n\n"
            f"Formatting style: {style}\n"
            "Reference the prior exchange naturally and maintain continuity."
        )
    else:
        system_prompt = (
            "You are writing the final response for the user.\n"
            f"Formatting style: {style}\n"
            "Be accurate, actionable, and directly address the question."
        )

    memory = state.get("user_memory") or ""
    if memory:
        system_prompt += f"\n\nRemembered context about this user:\n{memory}"

    context = (
        f"Original question: {state['user_query']}\n"
        f"Research findings: {'; '.join(state.get('research_results', []))}\n"
        f"Analysis insights: {state.get('analysis', 'N/A')}"
    )

    response = await llm.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=context)]
    )
    final_response = response.content

    return {
        "messages": [AIMessage(content=final_response)],
        "final_response": final_response,
        "current_step": "completed",
        "requires_user_input": False,
    }


# --- Memory: persist (end) --------------------------------------------------
async def persist_memory(state: ResearchState) -> Dict[str, Any]:
    """Save a memory note so future sessions remember this interaction."""
    note = f"Asked about: {state.get('user_query', '')[:120]}"
    if state.get("format_choice"):
        note += f" (preferred format: {state['format_choice']})"
    await save_user_memory(get_active_store(), state.get("user_id"), note)
    return {}


def build_research_graph(checkpointer: Any | None = None, store: Any | None = None):
    """Build and compile the research workflow.

    Args:
        checkpointer: A LangGraph checkpointer for durable, resumable state.
            When ``None`` (e.g. LangGraph Studio / langgraph dev), the runtime
            supplies its own persistence layer.
        store: A LangGraph ``BaseStore`` for cross-thread long-term memory.
            When ``None``, the memory nodes degrade to no-ops.
    """
    builder = StateGraph(ResearchState)
    builder.add_node("recall_memory", recall_memory)
    builder.add_node("research_planner_interrupt", research_planner_interrupt)
    builder.add_node("query_planner", query_planner)
    builder.add_node("sub_researcher", sub_researcher)
    builder.add_node("handle_cancel", handle_cancel)
    builder.add_node("research_direction_interrupt", research_direction_interrupt)
    builder.add_node("deep_analyzer", deep_analyzer)
    builder.add_node("format_selection_interrupt", format_selection_interrupt)
    builder.add_node("response_generator", response_generator)
    builder.add_node("persist_memory", persist_memory)

    builder.add_edge(START, "recall_memory")
    builder.add_edge("recall_memory", "research_planner_interrupt")
    builder.add_edge("research_planner_interrupt", "query_planner")
    # query_planner fans out to parallel sub_researchers (or cancels) via Command.
    builder.add_edge("sub_researcher", "research_direction_interrupt")
    builder.add_edge("research_direction_interrupt", "deep_analyzer")
    builder.add_edge("deep_analyzer", "format_selection_interrupt")
    builder.add_edge("format_selection_interrupt", "response_generator")
    builder.add_edge("response_generator", "persist_memory")
    builder.add_edge("persist_memory", END)
    builder.add_edge("handle_cancel", END)

    return builder.compile(checkpointer=checkpointer, store=store)


# Module-level graph for `langgraph dev` / LangGraph Studio. The FastAPI app
# builds its own instance with a durable checkpointer (see main.py).
research_graph = build_research_graph(checkpointer=MemorySaver())


# Nodes whose LLM output should be streamed to the client as the final answer.
STREAMING_NODES = {"response_generator"}


async def stream_research_response(
    graph, thread_id: str, user_choice: str, config: Optional[dict] = None
):
    """Resume the workflow and stream everything the client needs.

    Emits, as the run progresses:
    - ``progress`` events from the parallel sub-researchers (custom stream),
    - ``content`` tokens from the final-response node (messages stream),
    - a closing ``state`` event with the next interrupt / final answer.

    ``config`` can point at a past ``checkpoint_id`` to resume from there
    (time-travel / fork).
    """
    logger.info("Streaming research for thread=%s choice=%s", thread_id, user_choice)
    config = config or {"configurable": {"thread_id": thread_id}}

    try:
        interrupt_message = None
        async for mode, data in graph.astream(
            Command(resume=user_choice),
            config=config,
            stream_mode=["custom", "messages", "updates"],
        ):
            if mode == "custom":
                event = data if isinstance(data, dict) else {"message": str(data)}
                event.setdefault("type", "progress")
                yield event
            elif mode == "messages":
                chunk, meta = data
                if meta.get("langgraph_node") in STREAMING_NODES and getattr(
                    chunk, "content", None
                ):
                    yield {
                        "type": "content",
                        "content": chunk.content,
                        "done": False,
                        "node": meta.get("langgraph_node"),
                    }
            elif mode == "updates":
                if isinstance(data, dict) and "__interrupt__" in data:
                    interrupt_message = data["__interrupt__"][0].value

        state = await graph.aget_state(config)
        values = state.values or {}
        yield {
            "type": "state",
            "requires_input": bool(state.next),
            "interrupt_message": interrupt_message,
            "current_step": values.get("current_step", "unknown"),
            "final_response": values.get("final_response", ""),
            "research_results": values.get("research_results", []),
            "sub_queries": values.get("sub_queries", []),
            "next": list(state.next),
        }
        yield {"type": "done", "content": "", "done": True}
    except Exception as exc:  # pragma: no cover - surfaced to the client
        logger.exception("Streaming error")
        yield {"type": "error", "content": f"Error in streaming: {exc}", "done": True}
