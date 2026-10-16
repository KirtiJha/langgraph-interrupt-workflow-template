"""The mission agent: ``create_agent`` + a simulated world in state + HITL.

What's wired in, outermost first:

1. ``ClientModelMiddleware`` — the model chosen in the browser, per request.
2. ``PilotMiddleware`` — when the model is the offline mock, fly the scripted
   :class:`MissionPilot` instead so the demo works with no key.
3. ``GuardrailMiddleware`` — PII redaction / blocklist before the model.
4. The power-pack (summarization, call limits, retries) from ``middleware_pack``.
5. ``HumanInTheLoopMiddleware`` with the per-call policy from :mod:`mission.policy`.

The agent's state carries ``world`` (reduced by :func:`world_reducer`), the
``autonomy`` setting, and the final ``report`` — all checkpointed, so a thread
can be paused for days, forked, or rewound.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, AsyncIterator, Optional

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import AgentMiddleware, HumanInTheLoopMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command
from typing_extensions import NotRequired

import run_control
from client_model import ClientModelMiddleware, scrub
from guardrails import GuardrailMiddleware
from llm import MockChatModel, get_llm, text_of
from middleware_pack import build_middleware_pack
from mission import policy
from mission.pilot import MissionPilot
from mission.tools import ALL_TOOLS
from mission.world import seed_world, world_reducer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Mission Control: a personal agent that gets real-life jobs done for the user \
(Alex) inside their world — inbox, calendar, wallet, contacts, subscriptions and bookings.

How to work:
- First read what you need (inbox, calendar, wallet, contacts). Call several reading tools at once.
- Compare options before acting: search tools return several candidates with prices and refund terms. \
Prefer refundable, well-rated, on-budget choices and say why in one sentence.
- Act with the acting tools (book, pay, send_email, add_calendar_event, archive_emails, cancel_subscription). \
Some actions pause for the user's approval; they may approve, edit the arguments, reject with a reason, or \
answer instead. If an action is rejected, choose the next-best alternative or move on — never retry the same call.
- Use ask_user only for a choice you genuinely can't make from their data (e.g. which of two venues).
- Keep every message to one or two short sentences before your tool calls. No markdown headers.
- When the goal is done (or blocked), call finish_mission exactly once with a summary, what was done, \
what's still open, and the total spent. Then reply with one closing sentence.
- Respect budgets and the user's remembered preferences."""


class MissionState(AgentState):
    world: NotRequired[Annotated[dict, world_reducer]]
    autonomy: NotRequired[str]  # careful | balanced | autopilot
    ask_above: NotRequired[float]
    report: NotRequired[dict]
    mission_id: NotRequired[Optional[str]]
    goal: NotRequired[str]
    user_id: NotRequired[Optional[str]]


class PilotMiddleware(AgentMiddleware):
    """Replace the offline mock model with the scripted mission pilot."""

    def _swap(self, request):
        if isinstance(request.model, MockChatModel):
            return request.override(model=MissionPilot())
        return request

    def wrap_model_call(self, request, handler):
        return handler(self._swap(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._swap(request))


def build_mission_agent(checkpointer: Any | None = None, store: Any | None = None,
                        extra_tools: Optional[list] = None):
    """``extra_tools`` (e.g. from MCP servers) are gated like any acting tool."""
    model = get_llm()
    extra_tools = list(extra_tools or [])
    hitl = HumanInTheLoopMiddleware(
        interrupt_on=policy.build_interrupt_on([t.name for t in extra_tools]),
        description_prefix="Mission Control wants to act and needs your approval",
        interrupt_mode="per_call",
    )
    middleware: list = [ClientModelMiddleware(), PilotMiddleware()]
    guardrail = GuardrailMiddleware.from_env()
    if guardrail is not None:
        middleware.append(guardrail)
    middleware.extend(build_middleware_pack(model)[0])
    middleware.append(hitl)
    return create_agent(
        model,
        tools=ALL_TOOLS + extra_tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=middleware,
        state_schema=MissionState,
        checkpointer=checkpointer,
        store=store,
    )


EDIT_NOTICE_PREFIX = "Note: a human reviewer replaced this tool call"


def result_status(text: str) -> str:
    """How a tool result came about: ran as asked, ran edited, or was rejected."""
    if text.startswith("User rejected"):
        return "rejected"
    if text.startswith(EDIT_NOTICE_PREFIX):
        return "edited"
    return "ok"


# --- Interrupts → UI ---------------------------------------------------------
def pending_from(interrupts: Any) -> dict:
    """Normalise pending interrupts: tool approvals (with risk) and questions."""
    approvals, question = [], None
    for intr in interrupts or []:
        value = getattr(intr, "value", intr)
        if not isinstance(value, dict):
            continue
        if value.get("type") == "tool_approval":
            approvals.append({
                "interrupt_id": getattr(intr, "id", None),
                "tool_call_id": value.get("tool_call_id"),
                "name": value.get("name"),
                "args": value.get("args", {}),
                "description": value.get("description", ""),
                "allowed": policy.ALLOWED,
                "response_schema": getattr(intr, "response_schema", None),
                "risk": policy.assessment_for(value.get("tool_call_id")),
            })
        elif value.get("type") == "question":
            question = {"interrupt_id": getattr(intr, "id", None), "question": value.get("question"),
                        "options": value.get("options") or []}
    return {"approvals": approvals, "question": question}


async def snapshot(graph, config: dict) -> dict:
    """The thread's state as the UI wants it."""
    state = await graph.aget_state(config)
    values = state.values or {}
    pending = pending_from(state.interrupts)
    messages = values.get("messages", [])
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage) and not m.tool_calls), None)
    status = ("awaiting_approval" if pending["approvals"] else "awaiting_answer" if pending["question"]
              else "running" if state.next else "completed" if values.get("report") else "idle")
    return {
        "type": "state",
        "status": status,
        "requires_input": bool(state.next),
        "pending": pending,
        "world": values.get("world") or seed_world(),
        "report": values.get("report"),
        "autonomy": values.get("autonomy", "careful"),
        "ask_above": values.get("ask_above", policy.DEFAULT_ASK_ABOVE),
        "goal": values.get("goal"),
        "mission_id": values.get("mission_id"),
        "closing": text_of(last_ai.content) if last_ai else "",
        "checkpoint_id": state.config.get("configurable", {}).get("checkpoint_id"),
        "step": state.metadata.get("step") if state.metadata else None,
    }


def start_input(goal: str, mission_id: Optional[str], autonomy: str, ask_above: float, memory: str,
                user_id: Optional[str] = None, today=None) -> dict:
    messages = []
    if memory:
        messages.append(SystemMessage(content=f"What you remember about the user:\n{memory}"))
    messages.append(HumanMessage(content=goal))
    return {
        "messages": messages,
        "world": {"reset": seed_world(today)},
        "autonomy": autonomy,
        "ask_above": ask_above,
        "mission_id": mission_id,
        "goal": goal,
        "user_id": user_id,
    }


def resume_command(decisions: dict[str, Any]) -> Command:
    """``{interrupt_id: decision}`` — approvals and question answers alike."""
    return Command(resume=decisions)


async def stream_mission(graph, thread_id: str, command_input, config: Optional[dict] = None) -> AsyncIterator[dict]:
    """Run or resume a mission and stream rich events, then a closing ``state``."""
    config = config or {"configurable": {"thread_id": thread_id}}
    control = run_control.new_control(thread_id)
    cancelled = False
    try:
        async for mode, data in graph.astream(command_input, config=config,
                                              stream_mode=["updates", "messages", "custom"], control=control):
            if mode == "custom":
                event = data if isinstance(data, dict) else {"message": str(data)}
                event.setdefault("type", "progress")
                yield event
            elif mode == "messages":
                chunk, meta = data
                if isinstance(chunk, ToolMessage):
                    continue
                token = text_of(getattr(chunk, "content", None))
                if token and meta.get("langgraph_node") == "model":
                    yield {"type": "token", "content": token}
            elif mode == "updates" and isinstance(data, dict):
                for node, update in data.items():
                    if node == "__interrupt__":
                        continue
                    if not isinstance(update, dict):
                        continue
                    for m in update.get("messages") or []:
                        if isinstance(m, AIMessage) and m.tool_calls:
                            yield {"type": "tool_calls", "calls": [
                                {"id": tc["id"], "name": tc["name"], "args": tc["args"]} for tc in m.tool_calls]}
                        elif isinstance(m, ToolMessage):
                            text = text_of(m.content)
                            yield {"type": "tool_result", "id": m.tool_call_id, "name": m.name,
                                   "content": text[:2000], "status": result_status(text)}
                    if (update.get("world") or {}).get("ops"):
                        yield {"type": "world_ops", "ops": update["world"]["ops"]}
                    if update.get("report"):
                        yield {"type": "report", "report": update["report"]}
    except run_control.GraphDrained:
        cancelled = True
        yield {"type": "cancelled", "message": "Mission paused — everything so far is saved."}
    except Exception as exc:  # surfaced to the UI, key scrubbed
        logger.exception("Mission stream error")
        yield {"type": "error", "content": scrub(f"{type(exc).__name__}: {exc}")}
        return
    finally:
        run_control.release(thread_id)
    # Always read the thread head: a fork's config pins an older checkpoint.
    final = await snapshot(graph, {"configurable": {"thread_id": thread_id}})
    if cancelled:
        final["status"] = "paused"
    yield final
    yield {"type": "done"}


def new_branch_config(thread_id: str, checkpoint_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": "", "checkpoint_id": checkpoint_id}}


async def fork(graph, thread_id: str, checkpoint_id: str) -> dict:
    """Branch the thread from a decision point; the pending approvals come back.

    ``aupdate_state`` at an old checkpoint creates a new child checkpoint (a
    branch) instead of overwriting history; resuming from it re-runs the gated
    tools, which raise their interrupts again — now with your new answers.
    """
    return await graph.aupdate_state(new_branch_config(thread_id, checkpoint_id), {"messages": []}, as_node="model")


async def decision_points(graph, thread_id: str) -> list[dict]:
    """Checkpoints where the mission was waiting on you — the time-travel scrubber."""
    points = []
    async for state in graph.aget_state_history({"configurable": {"thread_id": thread_id}}):
        pending = pending_from(state.interrupts)
        if not pending["approvals"] and not pending["question"]:
            continue
        world = (state.values or {}).get("world") or {}
        points.append({
            "checkpoint_id": state.config["configurable"]["checkpoint_id"],
            "step": (state.metadata or {}).get("step"),
            "created_at": state.created_at,
            "approvals": [{"name": a["name"], "args": a["args"]} for a in pending["approvals"]],
            "question": pending["question"]["question"] if pending["question"] else None,
            "balance": (world.get("wallet") or {}).get("balance"),
            "ledger_len": len(world.get("ledger") or []),
        })
    points.reverse()
    return points
