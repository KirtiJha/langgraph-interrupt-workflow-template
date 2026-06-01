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
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt

from llm import get_llm
from tools import web_search

logger = logging.getLogger(__name__)


class ResearchState(TypedDict):
    """State threaded through the research workflow."""

    messages: Annotated[List[AnyMessage], add_messages]
    user_query: str
    research_plan: str
    research_results: List[str]
    analysis: str
    final_response: str
    current_step: str
    requires_user_input: bool
    interrupt_data: Optional[Dict[str, Any]]
    user_choice: Optional[str]
    format_choice: Optional[str]
    research_direction: Optional[str]


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


# --- Node 2: Information gathering ------------------------------------------
async def information_gatherer(state: ResearchState) -> Dict[str, Any]:
    """Gather information for the query, optionally using a web-search tool."""
    logger.info("Gathering information")
    user_choice = state.get("user_choice", "proceed")

    if user_choice == "cancel":
        return {
            "research_results": ["Research cancelled by user request"],
            "current_step": "direct_response",
            "final_response": "Research was cancelled at your request.",
        }

    llm = get_llm()
    messages = state.get("messages", [])
    previous_query, previous_response = _previous_exchange(messages)
    has_context = bool(previous_query and previous_response)

    context_section = ""
    if has_context:
        context_section = (
            f"\n\nPrevious conversation context:\n"
            f"- Previous question: {previous_query}\n"
            f"- Previous response: {previous_response[:400]}...\n"
            "Consider this context when generating findings."
        )

    if user_choice == "simplified":
        system_prompt = (
            "You are a research assistant providing a simplified analysis. "
            "Generate 2-3 concise key findings." + context_section
        )
    elif user_choice == "focused":
        system_prompt = (
            "You are a research assistant focusing on specific aspects. "
            "Generate targeted findings on the most important aspects." + context_section
        )
    elif user_choice == "continue_context":
        system_prompt = (
            "You are a research assistant building on previous context. Provide "
            "3-4 focused findings that connect to the prior discussion." + context_section
        )
    else:
        system_prompt = (
            "You are a thorough research assistant. Provide 4-5 detailed findings "
            "covering multiple aspects of the question." + context_section
        )

    # Optionally enrich with a live web search (mock results when offline).
    search_context = ""
    try:
        search_context = web_search.invoke({"query": state["user_query"]})
    except Exception as exc:  # pragma: no cover - tool is best-effort here
        logger.warning("web_search failed: %s", exc)

    research_query = (
        f"Research query: {state['user_query']}\n"
        f"Research approach: {user_choice}\n"
        f"Reference material:\n{search_context}"
    )

    response = await llm.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=research_query)]
    )

    findings = [line.strip() for line in response.content.split("\n") if line.strip()][:5]
    research_results = [f"Finding {i + 1}: {text}" for i, text in enumerate(findings)]

    if has_context:
        research_results.append(
            f"Finding {len(research_results) + 1}: Context integration — connected to "
            f"the earlier discussion about '{previous_query[:50]}...'"
        )

    return {
        "research_results": research_results,
        "current_step": "research_direction_check",
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


def build_research_graph(checkpointer: Any | None = None):
    """Build and compile the research workflow.

    Args:
        checkpointer: A LangGraph checkpointer for durable, resumable state.
            When ``None`` (e.g. LangGraph Studio / langgraph dev), the runtime
            supplies its own persistence layer.
    """
    builder = StateGraph(ResearchState)
    builder.add_node("research_planner_interrupt", research_planner_interrupt)
    builder.add_node("information_gatherer", information_gatherer)
    builder.add_node("research_direction_interrupt", research_direction_interrupt)
    builder.add_node("deep_analyzer", deep_analyzer)
    builder.add_node("format_selection_interrupt", format_selection_interrupt)
    builder.add_node("response_generator", response_generator)

    builder.add_edge(START, "research_planner_interrupt")
    builder.add_edge("research_planner_interrupt", "information_gatherer")
    builder.add_edge("information_gatherer", "research_direction_interrupt")
    builder.add_edge("research_direction_interrupt", "deep_analyzer")
    builder.add_edge("deep_analyzer", "format_selection_interrupt")
    builder.add_edge("format_selection_interrupt", "response_generator")
    builder.add_edge("response_generator", END)

    return builder.compile(checkpointer=checkpointer)


# Module-level graph for `langgraph dev` / LangGraph Studio. The FastAPI app
# builds its own instance with a durable checkpointer (see main.py).
research_graph = build_research_graph(checkpointer=MemorySaver())


# Nodes whose LLM output should be streamed to the client.
STREAMING_NODES = {"response_generator"}


async def stream_research_response(graph, thread_id: str, user_choice: str):
    """Resume the workflow and stream tokens from the final-response node."""
    logger.info("Streaming research for thread=%s choice=%s", thread_id, user_choice)
    config = {"configurable": {"thread_id": thread_id}}

    format_choices = (
        "comprehensive",
        "executive",
        "structured",
        "conversational",
        "bullet_points",
    )

    try:
        if user_choice in format_choices:
            current_state = await graph.aget_state(config)
            if current_state.values:
                await graph.aupdate_state(
                    config,
                    {"format_choice": user_choice, "user_choice": user_choice},
                )

        async for event in graph.astream_events(
            Command(resume=user_choice), version="v2", config=config
        ):
            if event["event"] == "on_chat_model_stream":
                node = event.get("metadata", {}).get("langgraph_node")
                if node in STREAMING_NODES:
                    chunk = event["data"]["chunk"]
                    if getattr(chunk, "content", None):
                        yield {
                            "content": chunk.content,
                            "type": "content",
                            "done": False,
                            "node": node,
                        }

        yield {"content": "", "type": "content", "done": True}
    except Exception as exc:  # pragma: no cover - surfaced to the client
        logger.exception("Streaming error")
        yield {"content": f"Error in streaming: {exc}", "type": "error", "done": True}
