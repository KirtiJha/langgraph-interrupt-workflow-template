"""The Repo Steward agent: ``create_agent`` + the repo board in state + HITL.

Middleware, outermost first: the browser-chosen model, the offline pilot (when
the model is the mock), guardrails, the power-pack, and
``HumanInTheLoopMiddleware`` with the per-call policy from :mod:`steward.policy`.

State carries ``world`` (the board, reduced by :func:`world_reducer`), the
``autonomy`` level and the final ``report`` — all checkpointed, so a mission
can be paused for days, resumed on another instance, forked or rewound.
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
from steward import policy
from steward.pilot import StewardPilot
from steward.tools import ALL_TOOLS
from steward.world import world_reducer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Repo Steward: a maintainer's agent for a GitHub repository. You triage issues, review \
pull requests, sweep stale threads, draft release notes and welcome contributors — and you ask before anything \
public happens.

How to work:
- Start by reading what you need: list_issues / list_pulls (the board is already loaded), read_issue for threads, \
read_file for README, CONTRIBUTING and code, find_similar for duplicates, read_pull for diffs. Call several at once.
- Act with the acting tools: add_labels, comment, close_issue, retitle, create_issue, assign, request_reviewers, \
merge_pull. Only use labels that exist on the board unless a new one is clearly needed. Comments are public: be \
warm, specific and brief; cite files or lines when you answer from the code; never promise timelines.
- Some actions pause for the maintainer's approval; they may approve, edit, reject with a reason, or reply. \
If rejected, do not retry the same action — adjust or move on.
- Use ask_user only for a decision you can't make from the repository.
- Keep each message to one or two short sentences before your tool calls. No markdown headers.
- When the goal is done (or blocked), call finish_mission exactly once, then reply with one closing sentence.
- Respect what you remember about this repository's conventions."""


class StewardState(AgentState):
    world: NotRequired[Annotated[dict, world_reducer]]
    autonomy: NotRequired[str]  # observe | careful | balanced | autopilot
    report: NotRequired[dict]
    mission_id: NotRequired[Optional[str]]
    goal: NotRequired[str]
    user_id: NotRequired[Optional[str]]
    repo: NotRequired[str]


class PilotMiddleware(AgentMiddleware):
    """Replace the offline mock model with the scripted mission pilot."""

    def _swap(self, request):
        if isinstance(request.model, MockChatModel):
            board = (request.state or {}).get("world") or {}
            maintainer = (board.get("repo") or {}).get("maintainer")
            return request.override(model=StewardPilot(maintainer=maintainer))
        return request

    def wrap_model_call(self, request, handler):
        return handler(self._swap(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._swap(request))


def build_steward_agent(checkpointer: Any | None = None, store: Any | None = None,
                        extra_tools: Optional[list] = None):
    """``extra_tools`` (e.g. from MCP servers) are gated like any acting tool."""
    model = get_llm()
    extra_tools = list(extra_tools or [])
    hitl = HumanInTheLoopMiddleware(
        interrupt_on=policy.build_interrupt_on([t.name for t in extra_tools]),
        description_prefix="Repo Steward wants to act on the repository and needs your approval",
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
        state_schema=StewardState,
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
        "world": values.get("world") or {},
        "report": values.get("report"),
        "autonomy": values.get("autonomy", "careful"),
        "goal": values.get("goal"),
        "mission_id": values.get("mission_id"),
        "repo": values.get("repo"),
        "closing": text_of(last_ai.content) if last_ai else "",
        "checkpoint_id": state.config.get("configurable", {}).get("checkpoint_id"),
        "step": state.metadata.get("step") if state.metadata else None,
    }


def start_input(goal: str, mission_id: Optional[str], board: dict, autonomy: str, memory: str,
                user_id: Optional[str] = None) -> dict:
    messages = []
    repo = board.get("repo", {})
    context = (f"Repository: {repo.get('full_name')} — {repo.get('description') or ''}\n"
               f"Default branch: {repo.get('default_branch')}. Labels available: "
               f"{', '.join(l['name'] for l in board.get('labels', [])) or 'none'}.\n"
               f"Board: {len(board.get('issues', []))} open issues, {len(board.get('pulls', []))} open pull requests "
               f"({'live repository' if board.get('mode') == 'live' else 'sample repository'}; "
               f"{'write access' if board.get('can_write') else 'read-only: actions will be recorded as proposals'}).")
    if memory:
        context += f"\n\nWhat you remember about this repository:\n{memory}"
    messages.append(SystemMessage(content=context))
    messages.append(HumanMessage(content=goal))
    return {
        "messages": messages,
        "world": {"reset": {**board, "ledger": []}},
        "autonomy": autonomy,
        "mission_id": mission_id,
        "goal": goal,
        "user_id": user_id,
        "repo": repo.get("full_name"),
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
        logger.exception("Steward stream error")
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
            "ledger_len": len(world.get("ledger") or []),
        })
    points.reverse()
    return points
