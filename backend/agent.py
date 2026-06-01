"""Modern prebuilt agent with human-in-the-loop middleware (LangChain/LangGraph v1).

This module showcases the *latest* agent pattern: ``create_agent`` from
LangChain v1 (which replaces the deprecated ``create_react_agent``) combined
with ``HumanInTheLoopMiddleware``. The middleware pauses the agent for human
approval whenever it tries to call a sensitive tool — the same interrupt /
resume mechanism used by the custom graph in ``graph.py``, but with almost no
boilerplate.

Run a quick CLI demo:

    python agent.py "What are the latest advances in battery technology?"
"""

from __future__ import annotations

import logging

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

from llm import get_llm
from tools import web_search

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a helpful research assistant. Use the web_search tool to gather "
    "current information before answering. Cite what you find and be concise."
)


def build_agent(checkpointer=None):
    """Build a tool-using agent that requires approval before searching.

    The ``HumanInTheLoopMiddleware`` interrupts execution before the
    ``web_search`` tool runs. Resume with ``Command(resume=...)`` to approve,
    edit, or reject the tool call — exactly the human-in-the-loop pattern this
    template is about.
    """
    hitl = HumanInTheLoopMiddleware(
        interrupt_on={"web_search": True},
        description_prefix="The agent wants to run a tool and needs your approval",
    )
    return create_agent(
        get_llm(),
        tools=[web_search],
        system_prompt=SYSTEM_PROMPT,
        middleware=[hitl],
        checkpointer=checkpointer,
    )


# Module-level instance for `langgraph dev` / LangGraph Studio.
agent = build_agent()


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
        # Approve all pending tool calls. Shape depends on the middleware version;
        # `{"type": "accept"}` is the common approval payload.
        result = demo_agent.invoke(Command(resume=[{"type": "accept"}]), config)

    final = result["messages"][-1]
    print("Agent:", getattr(final, "content", final))


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    query = " ".join(sys.argv[1:]) or "What is LangGraph and why is it useful?"
    _demo(query)
