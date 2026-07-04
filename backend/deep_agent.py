"""Deep Agent engine — the third selectable backend "engine".

Where ``graph.py`` is a deterministic pipeline and ``agent.py`` is a single
model-driven ``create_agent`` loop, this engine uses **Deep Agents**
(``deepagents``, built on LangGraph) for genuinely long-horizon work. A Deep
Agent gets, out of the box:

- **Planning** — a ``write_todos`` tool to decompose and track a multi-step task;
- **Subagents** — it delegates focused work to specialised subagents (here a
  ``researcher`` and a ``critic``) via a ``task`` tool, which keeps the main
  agent's context clean;
- **A virtual filesystem** — scratch space to offload large intermediate results;
- **Human-in-the-loop** — the same ``interrupt_on`` approval used by the other
  engines gates the ``web_search`` tool.

The engine runs offline with the built-in mock model (it simply returns a basic
answer), but its planning / delegation behaviour only becomes visible with a
capable provider model — set ``LLM_MODEL`` + an API key to see it plan and
delegate.

CLI demo: ``python deep_agent.py "Compare solid-state vs lithium-ion batteries"``
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from deepagents import SubAgent, create_deep_agent

from llm import get_llm, using_mock_llm
from tools import web_search

logger = logging.getLogger(__name__)

MAIN_INSTRUCTIONS = (
    "You are a research orchestrator. For any non-trivial question:\n"
    "1. Use `write_todos` to lay out a short research plan.\n"
    "2. Delegate focused fact-finding to the `researcher` subagent via the "
    "`task` tool (one delegation per sub-topic).\n"
    "3. Ask the `critic` subagent to review your synthesis for gaps or "
    "unsupported claims, and revise.\n"
    "4. Write a clear, well-structured final answer that cites what you found.\n"
    "Keep the main thread concise — push detailed work into subagents."
)

RESEARCHER = SubAgent(
    name="researcher",
    description=(
        "Researches a single focused sub-question. Delegate one sub-topic at a "
        "time; it uses web_search and returns concise, sourced findings."
    ),
    system_prompt=(
        "You are a focused researcher. Use web_search to gather current "
        "information about the given sub-question, then return 2-4 concise, "
        "well-supported findings with sources. Do not answer beyond the "
        "sub-question you were given."
    ),
    tools=[web_search],
)

CRITIC = SubAgent(
    name="critic",
    description=(
        "Reviews a draft synthesis for gaps, unsupported claims, and balance. "
        "Delegate the draft; it returns specific, actionable critique."
    ),
    system_prompt=(
        "You are a rigorous critic. Given a draft answer, identify missing "
        "angles, unsupported or overstated claims, and anything that needs a "
        "source. Return a short, specific list of improvements — do not rewrite "
        "the answer yourself."
    ),
)


def deep_agent_available() -> bool:
    """Deep Agents run offline but only *demonstrate* their value with a real model."""
    return not using_mock_llm()


def build_deep_agent(checkpointer: Any | None = None, store: Any | None = None):
    """Build the Deep Agent research orchestrator.

    ``web_search`` is gated by human approval (``interrupt_on``) — the same
    interrupt/resume mechanism the other engines use, so
    ``Command(resume={"decisions": [{"type": "approve"}]})`` drives it.
    """
    return create_deep_agent(
        model=get_llm(),
        tools=[web_search],
        system_prompt=MAIN_INSTRUCTIONS,
        subagents=[RESEARCHER, CRITIC],
        interrupt_on={"web_search": True},
        checkpointer=checkpointer,
        store=store,
    )


# Module-level instance for `langgraph dev` / LangGraph Studio.
agent = build_deep_agent()


def _demo(question: str) -> None:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command

    demo = build_deep_agent(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "deep-demo"}}
    result = demo.invoke({"messages": [{"role": "user", "content": question}]}, config)

    while "__interrupt__" in result:
        print("\n⏸  Approval requested for a tool call — auto-approving for the demo…")
        result = demo.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config)

    print("\nDeep Agent:", getattr(result["messages"][-1], "content", ""))


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    query = " ".join(sys.argv[1:]) or "Compare solid-state and lithium-ion batteries"
    _demo(query)
