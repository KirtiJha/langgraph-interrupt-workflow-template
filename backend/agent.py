"""Agent engine — the modern, model-driven counterpart to ``graph.py``.

This is the second selectable backend "engine". Where ``graph.py`` is an
explicit, deterministic pipeline (fixed interrupt points + ``Send`` fan-out),
this is a genuinely *agentic* research assistant built with ``create_agent``
(LangChain v1, which replaces the deprecated ``create_react_agent``):

- the **model drives the loop** — it decides when to call ``web_search``;
- ``HumanInTheLoopMiddleware`` pauses for **approve / edit / reject / respond**
  before a tool runs (the same interrupt/resume mechanism, with no boilerplate);
- it shares the same provider-agnostic LLM, ``web_search`` tool, and ``Store``
  long-term memory used by the workflow engine.

Toggle between the two engines live in the UI to compare the paradigms.

CLI demo: ``python agent.py "What are the latest advances in battery tech?"``
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

from llm import get_llm
from tools import web_search

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a helpful research assistant. Use the web_search tool to gather "
    "current information before answering. Cite what you find and be concise. "
    "If the user has remembered context, take it into account."
)

# Tools the agent may call. web_search is gated by human approval below.
AGENT_TOOLS = [web_search]


def build_agent(checkpointer: Any | None = None, store: Any | None = None):
    """Build a tool-using agent that requires approval before searching.

    ``HumanInTheLoopMiddleware`` interrupts before ``web_search`` runs. Resume
    with ``Command(resume={"decisions": [{"type": "approve"}]})`` (or ``edit`` /
    ``reject`` / ``respond``) to drive it.
    """
    hitl = HumanInTheLoopMiddleware(
        interrupt_on={"web_search": True},
        description_prefix="The agent wants to run a tool and needs your approval",
    )
    return create_agent(
        get_llm(),
        tools=AGENT_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        middleware=[hitl],
        checkpointer=checkpointer,
        store=store,
    )


# Module-level instance for `langgraph dev` / LangGraph Studio.
agent = build_agent()


def _pending_interrupt(value: Any) -> dict:
    """Normalize a HITLMiddleware interrupt request for the client."""
    requests = value.get("action_requests", []) if isinstance(value, dict) else []
    configs = value.get("review_configs", [{}]) if isinstance(value, dict) else [{}]
    allowed = configs[0].get("allowed_decisions", ["approve", "reject"]) if configs else [
        "approve",
        "reject",
    ]
    return {"tool_requests": requests, "allowed": allowed}


async def stream_agent_response(graph, thread_id: str, command_input, config: Optional[dict] = None):
    """Run/resume the agent and stream progress, tokens, and a closing state.

    ``command_input`` is the initial ``{"messages": [...]}`` (to start) or a
    ``Command(resume=...)`` (to resume after an approval decision).
    """
    config = config or {"configurable": {"thread_id": thread_id}}
    interrupt_value = None
    try:
        async for mode, data in graph.astream(
            command_input, config=config, stream_mode=["updates", "messages"]
        ):
            if mode == "updates" and isinstance(data, dict):
                if "__interrupt__" in data:
                    interrupt_value = data["__interrupt__"][0].value
                elif "tools" in data:
                    yield {"type": "progress", "message": "🔧 Tool executed — synthesizing…"}
            elif mode == "messages":
                chunk, _meta = data
                content = getattr(chunk, "content", None)
                if content and isinstance(content, str):
                    yield {"type": "content", "content": content, "done": False}

        state = await graph.aget_state(config)
        values = state.values or {}
        messages = values.get("messages", [])
        final = ""
        if messages and not state.next:
            final = getattr(messages[-1], "content", "") or ""

        event = {
            "type": "state",
            "requires_input": bool(state.next),
            "final_response": final,
            "current_step": "awaiting_approval" if state.next else "completed",
        }
        if interrupt_value is not None:
            event.update(_pending_interrupt(interrupt_value))
        yield event
        yield {"type": "done", "content": "", "done": True}
    except Exception as exc:  # pragma: no cover - surfaced to the client
        logger.exception("Agent streaming error")
        yield {"type": "error", "content": f"Error: {exc}", "done": True}


def _demo(question: str) -> None:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command

    demo_agent = build_agent(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "agent-demo"}}

    result = demo_agent.invoke(
        {"messages": [{"role": "user", "content": question}]}, config
    )

    if "__interrupt__" in result:
        request = result["__interrupt__"][0].value
        print("\n⏸  Human-in-the-loop pause — approval requested:")
        print(request)
        print("\n▶  Auto-approving for this demo...\n")
        result = demo_agent.invoke(
            Command(resume={"decisions": [{"type": "approve"}]}), config
        )

    final = result["messages"][-1]
    print("Agent:", getattr(final, "content", final))


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    query = " ".join(sys.argv[1:]) or "What is LangGraph and why is it useful?"
    _demo(query)
