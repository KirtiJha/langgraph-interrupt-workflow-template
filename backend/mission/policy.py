"""Risk policy for mission tools: *how risky* is this action, and *should we ask?*

Each acting tool is scored against the **current world** (state) and the
user's **autonomy setting**, producing a :class:`Assessment` that the UI shows
on the approval card:

- ``level`` — ``low`` / ``medium`` / ``high``.
- ``reasons`` — human sentences ("$300 non-refundable deposit", "emails 7 people").
- ``reversible`` — whether it can be undone.
- ``preview`` — what will change if approved: wallet before → after, a ghost
  calendar event, the full email. Approving something you can *see* is the
  whole point.

The decision to pause is an ``InterruptOnConfig.when`` predicate that reads
``request.state`` — so it rides on LangChain's HITL middleware, with the
same per-call interrupts, decisions and resume protocol as any other agent.
The optional Jev classifier (``HITL_RISK_CLASSIFIER=jev``) adds a second
opinion from TypeSafe's decision model; when it disagrees we ask.

Autonomy (``state["autonomy"]``, chosen in the UI):

- ``careful`` — every acting tool asks (the template default: prove it pauses).
- ``balanced`` — ask for medium+ risk or spend above ``ask_above`` dollars.
- ``autopilot`` — ask only for high risk or irreversible actions.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain.agents.middleware import InterruptOnConfig

import approval_policy
from mission import world as W

logger = logging.getLogger(__name__)

ACTING_TOOLS = ["send_email", "archive_emails", "add_calendar_event", "pay", "book",
                "cancel_subscription"]
READ_TOOLS = ["read_inbox", "read_calendar", "check_wallet", "list_contacts",
              "list_subscriptions", "search_restaurants", "search_flights",
              "search_hotels", "get_quotes", "ask_user", "remember", "finish_mission"]

ALLOWED = ["approve", "edit", "reject", "respond"]
DEFAULT_ASK_ABOVE = 100.0
LEVEL_RANK = {"low": 0, "medium": 1, "high": 2}


@dataclass
class Assessment:
    level: str
    reasons: list[str]
    reversible: bool
    amount: float = 0.0
    preview: dict = field(default_factory=dict)
    source: str = "policy"

    def as_dict(self) -> dict:
        return {"level": self.level, "reasons": self.reasons, "reversible": self.reversible,
                "amount": self.amount, "preview": self.preview, "source": self.source}


def _bump(level: str, to: str) -> str:
    return to if LEVEL_RANK[to] > LEVEL_RANK[level] else level


def assess(tool: str, args: dict, world: dict, ask_above: float = DEFAULT_ASK_ABOVE) -> Assessment:
    """Score a tool call against the world. Pure; also used for previews."""
    args = args or {}
    level, reasons, reversible, amount, preview = "low", [], True, 0.0, {}
    balance = float(world.get("wallet", {}).get("balance", 0))

    if tool in ("pay", "book"):
        amount = float(args.get("amount") or 0)
        refundable = bool(args.get("refundable", True))
        reversible = refundable
        payee = args.get("payee") or args.get("vendor") or "?"
        preview = {"kind": "charge", "payee": payee, "amount": amount,
                   "balance_before": balance, "balance_after": round(balance - amount, 2),
                   "refundable": refundable}
        if amount > ask_above:
            level = _bump(level, "medium")
            reasons.append(f"${amount:,.0f} is above your ${ask_above:,.0f} ask-first limit")
        if amount > 500:
            level = _bump(level, "high")
            reasons.append(f"Large payment: ${amount:,.0f}")
        if not refundable:
            level = _bump(level, "medium" if amount <= 200 else "high")
            reasons.append("Non-refundable")
        if amount > balance:
            level = "high"
            reasons.append(f"Exceeds your balance (${balance:,.0f})")
        if tool == "book":
            preview.update({"kind": "booking", "booking_kind": args.get("kind"), "date": args.get("date"),
                            "details": args.get("details")})

    elif tool == "send_email":
        to = [t for t in (args.get("to") or []) if t]
        known = W.contact_emails(world)
        strangers = [t for t in to if t.lower() not in known]
        preview = {"kind": "email", "to": to, "subject": args.get("subject", ""),
                   "body": args.get("body", "")}
        if len(to) >= 5:
            level = _bump(level, "medium")
            reasons.append(f"Group email to {len(to)} people")
        if strangers:
            level = _bump(level, "medium")
            reasons.append(f"{len(strangers)} recipient{'s' if len(strangers) != 1 else ''} not in your contacts")
        if any(w in (args.get("body", "") + args.get("subject", "")).lower()
               for w in ("resign", "lawyer", "legal", "terminate", "ssn", "password")):
            level = "high"
            reasons.append("Sensitive wording")
        reversible = False
        reasons.append("Can't unsend")

    elif tool == "add_calendar_event":
        attendees = list(args.get("attendees") or [])
        day = (args.get("start") or "")[:10]
        clashes = [e for e in W.busy_on(world, day)
                   if e.get("start") < (args.get("end") or "") and (e.get("end") or "") > (args.get("start") or "")]
        preview = {"kind": "event", "title": args.get("title"), "start": args.get("start"),
                   "end": args.get("end"), "location": args.get("location"), "attendees": attendees,
                   "clashes": [c["title"] for c in clashes]}
        if attendees:
            level = _bump(level, "medium")
            reasons.append(f"Sends invites to {len(attendees)} {'person' if len(attendees) == 1 else 'people'}")
            reversible = False
        if clashes:
            level = _bump(level, "medium")
            reasons.append(f"Clashes with “{clashes[0]['title']}”")
        if not reasons:
            reasons.append("Only your own calendar changes")

    elif tool == "archive_emails":
        ids = list(args.get("ids") or [])
        emails = [e for e in world.get("inbox", []) if e["id"] in ids]
        urgent = [e for e in emails if e.get("urgent")]
        preview = {"kind": "archive", "subjects": [e["subject"] for e in emails]}
        if urgent:
            level = "high"
            reasons.append(f"Includes {len(urgent)} urgent email{'s' if len(urgent) != 1 else ''}")
        elif len(ids) > 5:
            level = _bump(level, "medium")
            reasons.append(f"Archives {len(ids)} emails at once")
        else:
            reasons.append("Archived mail can be restored")

    elif tool == "cancel_subscription":
        sub = W.find(world.get("subscriptions", []), args.get("id", "")) or {}
        preview = {"kind": "cancel", "name": sub.get("name", args.get("id")),
                   "saves_per_month": sub.get("price", 0), "last_used_days": sub.get("last_used_days")}
        reversible = False
        level = "medium"
        reasons.append("Cancelling is permanent")
        if (sub.get("last_used_days") or 0) < 14:
            level = "high"
            reasons.append(f"Used {sub.get('last_used_days')} day(s) ago — looks active")

    elif tool not in READ_TOOLS:  # an external / MCP tool we know nothing about
        level, reversible = "medium", False
        reasons.append("External tool — effects unknown")
        preview = {"kind": "external", "args": args}

    return Assessment(level=level, reasons=reasons, reversible=reversible, amount=amount, preview=preview)


def should_ask(assessment: Assessment, autonomy: str, ask_above: float) -> bool:
    if autonomy == "autopilot":
        return assessment.level == "high" or not assessment.reversible
    if autonomy == "balanced":
        return assessment.level != "low" or assessment.amount > ask_above
    return True  # careful


# Assessments for gated calls, keyed by tool_call_id — the approval card reads
# them back (bounded, in-memory, like approval_policy's verdicts).
_ASSESSMENTS: "OrderedDict[str, dict]" = OrderedDict()


def assessment_for(tool_call_id: Optional[str]) -> Optional[dict]:
    return _ASSESSMENTS.get(tool_call_id or "")


def _remember(tool_call_id: Optional[str], data: dict) -> None:
    if not tool_call_id:
        return
    _ASSESSMENTS[tool_call_id] = data
    while len(_ASSESSMENTS) > 256:
        _ASSESSMENTS.popitem(last=False)


def _when(tool: str):
    second_opinion = approval_policy.get_risk_classifier()
    use_jev = second_opinion.name != "patterns"

    def when(request: Any) -> bool:
        call = getattr(request, "tool_call", None) or {}
        state = getattr(request, "state", None) or {}
        world = state.get("world") or W.seed_world()
        autonomy = state.get("autonomy") or "careful"
        ask_above = float(state.get("ask_above") or DEFAULT_ASK_ABOVE)
        a = assess(tool, call.get("args") or {}, world, ask_above)
        ask = should_ask(a, autonomy, ask_above)
        data = a.as_dict()
        data["autonomy"] = autonomy
        if use_jev:
            verdict = second_opinion.classify(tool, call.get("args"))
            data["jev"] = verdict.as_dict()
            if verdict.risky and not ask:
                ask = True
                data["reasons"].append(f"Jev flagged it ({verdict.reason})")
        data["asked"] = ask
        _remember(call.get("id"), data)
        return ask

    return when


def build_interrupt_on(extra_tools: Optional[list[str]] = None) -> dict:
    """``interrupt_on`` for the mission agent: acting tools gated by policy.

    Unknown extra tools (MCP) are treated as acting tools: medium risk, so
    they ask in ``careful`` and ``balanced`` modes.
    """
    cfg = {t: InterruptOnConfig(allowed_decisions=ALLOWED, when=_when(t)) for t in ACTING_TOOLS}
    cfg.update({t: InterruptOnConfig(allowed_decisions=ALLOWED, when=_when(t)) for t in (extra_tools or [])})
    cfg.update({t: False for t in READ_TOOLS})
    return cfg


def describe() -> dict:
    return {
        "acting_tools": ACTING_TOOLS,
        "autonomy_levels": ["careful", "balanced", "autopilot"],
        "default_ask_above": DEFAULT_ASK_ABOVE,
        "second_opinion": approval_policy.get_risk_classifier().name,
    }
