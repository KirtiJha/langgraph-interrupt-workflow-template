"""Approval workflow — a second human-in-the-loop example.

A common real-world pattern: an AI drafts something (an email, a reply, a
policy snippet), then a human **approves**, **edits**, or **rejects with
feedback** before it's "sent". On reject, the draft is regenerated using the
feedback; on edit, the human's version is used verbatim.

This complements the multi-step research workflow in ``graph.py`` by showing
the three canonical HITL actions (approve / edit / reject) on a single
interrupt, mirroring what ``HumanInTheLoopMiddleware`` offers for tool calls.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from llm import get_llm

logger = logging.getLogger(__name__)

# Safety valve so a reject → redraft loop can't run forever.
MAX_REVISIONS = 3


class ApprovalState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    task: str
    draft: str
    feedback: str
    revision_count: int
    decision: str
    status: str
    final_output: str


async def drafter(state: ApprovalState) -> Dict[str, Any]:
    """Draft (or redraft) content for the task, using reviewer feedback if any."""
    logger.info("Drafting content (revision %s)", state.get("revision_count", 0))
    llm = get_llm()
    feedback = state.get("feedback", "")

    if feedback:
        system = (
            "You are revising a draft based on reviewer feedback. Produce an "
            "improved version that fully addresses the feedback."
        )
        human = (
            f"Task: {state['task']}\n\n"
            f"Previous draft:\n{state.get('draft', '')}\n\n"
            f"Reviewer feedback:\n{feedback}\n\n"
            "Rewrite the draft to address the feedback."
        )
    else:
        system = (
            "You are a helpful assistant that drafts clear, professional content "
            "for the given task. Return only the draft."
        )
        human = f"Task: {state['task']}\n\nWrite a complete draft."

    response = await llm.ainvoke(
        [SystemMessage(content=system), HumanMessage(content=human)]
    )
    return {"draft": response.content, "status": "awaiting_review"}


async def human_review(state: ApprovalState) -> Dict[str, Any]:
    """Pause for the human to approve, edit, or reject the draft."""
    logger.info("Awaiting human review")
    response = interrupt(
        {
            "type": "approval",
            "task": state["task"],
            "draft": state["draft"],
            "revision_count": state.get("revision_count", 0),
            "actions": ["approve", "edit", "reject"],
            "message": (
                "Review the draft. **Approve** to send it, **Edit** to send your "
                "own revised version, or **Reject** with feedback to request changes."
            ),
        }
    )

    # Accept either a structured response or a bare action string.
    if isinstance(response, str):
        response = {"action": response}
    action = (response.get("action") or "approve").lower()

    if action == "edit":
        return {
            "decision": "edit",
            "draft": response.get("content", state["draft"]),
            "status": "approved",
        }
    if action == "reject":
        return {
            "decision": "reject",
            "feedback": response.get("feedback", ""),
            "revision_count": state.get("revision_count", 0) + 1,
        }
    return {"decision": "approve", "status": "approved"}


def route_after_review(state: ApprovalState) -> str:
    """Loop back to redraft on reject (up to MAX_REVISIONS), else finalize."""
    if state.get("decision") == "reject" and state.get("revision_count", 0) < MAX_REVISIONS:
        return "drafter"
    return "finalize"


async def finalize(state: ApprovalState) -> Dict[str, Any]:
    """'Send' the approved (or edited) draft."""
    logger.info("Finalizing and sending")
    draft = state.get("draft", "")
    capped = (
        state.get("decision") == "reject"
        and state.get("revision_count", 0) >= MAX_REVISIONS
    )
    return {
        "messages": [AIMessage(content=draft)],
        "final_output": draft,
        "status": "sent_with_unresolved_feedback" if capped else "sent",
    }


def build_approval_graph(checkpointer: Any | None = None):
    """Build and compile the approval workflow."""
    builder = StateGraph(ApprovalState)
    builder.add_node("drafter", drafter)
    builder.add_node("human_review", human_review)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "drafter")
    builder.add_edge("drafter", "human_review")
    builder.add_conditional_edges(
        "human_review",
        route_after_review,
        {"drafter": "drafter", "finalize": "finalize"},
    )
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)


# Module-level instance for `langgraph dev` / LangGraph Studio.
approval_graph = build_approval_graph(checkpointer=MemorySaver())
