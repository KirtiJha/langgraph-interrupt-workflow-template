"""The simulated world a mission acts on: inbox, calendar, wallet, bookings…

The world lives **in the graph state** (``state["world"]``), so everything
LangGraph does to state applies to it for free: it is checkpointed (Postgres in
production), it rewinds when you time-travel, and a fork gets its own copy.

Tools never mutate it directly. They return *operations* —
``{"ops": [{"op": "charge", ...}]}`` — and :func:`world_reducer` applies them.
That keeps parallel tool calls safe (two payments in the same step both land)
and gives a complete audit trail in ``world["ledger"]``.

Swap these simulated tools for real ones (Gmail, Google Calendar, Stripe — via
MCP or your own APIs) and the agent, approvals and UI stay the same.
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta
from typing import Any, Optional


# --- Seed --------------------------------------------------------------------
def _d(base: date, days: int, hour: int = 9, minute: int = 0) -> str:
    return datetime.combine(base + timedelta(days=days), datetime.min.time()).replace(
        hour=hour, minute=minute
    ).isoformat(timespec="minutes")


def _next_weekday(base: date, weekday: int) -> int:
    """Days from ``base`` to the next ``weekday`` (Mon=0), at least 1 day away."""
    delta = (weekday - base.weekday()) % 7
    return delta or 7


def seed_world(today: Optional[date] = None) -> dict:
    """A small, believable life to act on. Dates are relative to ``today``."""
    t = today or date.today()
    sat = _next_weekday(t, 5)
    return {
        "today": t.isoformat(),
        "owner": {
            "name": "Alex Rivera",
            "email": "alex@rivera.example",
            "city": "San Francisco",
        },
        "wallet": {
            "currency": "USD",
            "balance": 3240.00,
            "transactions": [
                {"id": "tx1", "date": _d(t, -2), "payee": "Blue Bottle Coffee", "amount": -6.50, "category": "food"},
                {"id": "tx2", "date": _d(t, -3), "payee": "StreamMax", "amount": -22.99, "category": "subscription"},
                {"id": "tx3", "date": _d(t, -5), "payee": "Whole Foods", "amount": -84.12, "category": "groceries"},
                {"id": "tx4", "date": _d(t, -6), "payee": "IronPeak Gym", "amount": -59.00, "category": "subscription"},
                {"id": "tx5", "date": _d(t, -9), "payee": "Payroll · Northwind", "amount": 4200.00, "category": "income"},
                {"id": "tx6", "date": _d(t, -11), "payee": "CloudVault Pro", "amount": -9.99, "category": "subscription"},
                {"id": "tx7", "date": _d(t, -12), "payee": "Lingo+ Languages", "amount": -12.99, "category": "subscription"},
            ],
        },
        "calendar": [
            {"id": "ev1", "title": "Team standup", "start": _d(t, 1, 9, 30), "end": _d(t, 1, 9, 45), "location": "Zoom", "attendees": [], "source": "you"},
            {"id": "ev2", "title": "Dentist", "start": _d(t, 3, 14), "end": _d(t, 3, 15), "location": "Mission Dental", "attendees": [], "source": "you"},
            {"id": "ev3", "title": "Sam's soccer game", "start": _d(t, sat, 10), "end": _d(t, sat, 12), "location": "Golden Gate Park", "attendees": [], "source": "you"},
            {"id": "ev4", "title": "Quarterly planning", "start": _d(t, 5, 13), "end": _d(t, 5, 15), "location": "HQ · Room 4", "attendees": ["priya@northwind.example"], "source": "you"},
            {"id": "ev5", "title": "Yoga", "start": _d(t, 8, 18), "end": _d(t, 8, 19), "location": "Studio Flow", "attendees": [], "source": "you"},
        ],
        "inbox": [
            {"id": "em1", "from": "priya@northwind.example", "from_name": "Priya Shah (manager)", "subject": "Q3 numbers before Thursday?", "date": _d(t, 0, 8, 12), "unread": True, "urgent": True,
             "body": "Hi Alex — can you send me the Q3 numbers before Thursday's planning? A rough cut is fine. Thanks!"},
            {"id": "em2", "from": "landlord@baysideapts.example", "from_name": "Bayside Apartments", "subject": "Move-out inspection", "date": _d(t, -1, 16, 40), "unread": True, "urgent": True,
             "body": "Please confirm a time for your move-out inspection. Keys must be returned by the 1st."},
            {"id": "em3", "from": "jordan@friends.example", "from_name": "Jordan Lee", "subject": "Lunch next week?", "date": _d(t, -1, 11, 5), "unread": True, "urgent": False,
             "body": "Long time! Free for lunch next Tuesday or Wednesday?"},
            {"id": "em4", "from": "deals@shopmail.example", "from_name": "ShopMail Deals", "subject": "48 hours only: 70% off everything", "date": _d(t, -1, 7, 0), "unread": True, "urgent": False,
             "body": "Don't miss out! Huge savings on things you don't need."},
            {"id": "em5", "from": "newsletter@techdigest.example", "from_name": "Tech Digest", "subject": "This week in AI agents", "date": _d(t, -2, 6, 0), "unread": False, "urgent": False,
             "body": "Human-in-the-loop is the new default for agents that act…"},
            {"id": "em6", "from": "maria.rivera@family.example", "from_name": "Mom", "subject": "Don't make a fuss for my birthday!", "date": _d(t, -3, 19, 20), "unread": False, "urgent": False,
             "body": "I know you're planning something. Something small and quiet is perfect — and remember I don't eat meat anymore!"},
        ],
        "sent": [],
        "contacts": [
            {"id": "c1", "name": "Maria Rivera", "email": "maria.rivera@family.example", "group": "family", "relation": "Mom"},
            {"id": "c2", "name": "Luis Rivera", "email": "luis.rivera@family.example", "group": "family", "relation": "Dad"},
            {"id": "c3", "name": "Sofia Rivera", "email": "sofia@family.example", "group": "family", "relation": "Sister"},
            {"id": "c4", "name": "Diego Rivera", "email": "diego@family.example", "group": "family", "relation": "Brother"},
            {"id": "c5", "name": "Elena Ortiz", "email": "elena.ortiz@family.example", "group": "family", "relation": "Aunt"},
            {"id": "c6", "name": "Carmen Ortiz", "email": "carmen@family.example", "group": "family", "relation": "Cousin"},
            {"id": "c7", "name": "Rosa Delgado", "email": "rosa.d@friends.example", "group": "family", "relation": "Mom's best friend"},
            {"id": "c8", "name": "Priya Shah", "email": "priya@northwind.example", "group": "work", "relation": "Manager"},
            {"id": "c9", "name": "Jordan Lee", "email": "jordan@friends.example", "group": "friends", "relation": "Friend"},
            {"id": "c10", "name": "Bayside Apartments", "email": "landlord@baysideapts.example", "group": "services", "relation": "Landlord"},
        ],
        "subscriptions": [
            {"id": "sub1", "name": "StreamMax", "price": 22.99, "cycle": "monthly", "last_used_days": 2, "status": "active"},
            {"id": "sub2", "name": "IronPeak Gym", "price": 59.00, "cycle": "monthly", "last_used_days": 74, "status": "active"},
            {"id": "sub3", "name": "CloudVault Pro", "price": 9.99, "cycle": "monthly", "last_used_days": 1, "status": "active"},
            {"id": "sub4", "name": "Lingo+ Languages", "price": 12.99, "cycle": "monthly", "last_used_days": 120, "status": "active"},
            {"id": "sub5", "name": "NewsDaily Premium", "price": 14.99, "cycle": "monthly", "last_used_days": 45, "status": "active"},
            {"id": "sub6", "name": "MealBox", "price": 79.96, "cycle": "monthly", "last_used_days": 33, "status": "active"},
        ],
        "bookings": [],
        "ledger": [],
    }


# --- Reducer -----------------------------------------------------------------
def _money(x: Any) -> float:
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return 0.0


def _apply(world: dict, op: dict) -> Optional[str]:
    """Apply one operation in place; return a one-line ledger summary."""
    kind = op.get("op")
    seq = len(world["ledger"]) + 1
    if kind == "charge":
        amount = _money(op.get("amount"))
        world["wallet"]["balance"] = round(world["wallet"]["balance"] - amount, 2)
        world["wallet"]["transactions"].insert(0, {
            "id": f"tx-a{seq}", "date": op.get("date") or world["today"], "payee": op.get("payee", "?"),
            "amount": -amount, "category": op.get("category", "other"), "memo": op.get("memo", ""), "by_agent": True,
        })
        return f"Paid ${amount:,.2f} to {op.get('payee')}"
    if kind == "add_event":
        ev = {k: op.get(k) for k in ("title", "start", "end", "location")}
        ev.update({"id": f"ev-a{seq}", "attendees": list(op.get("attendees") or []), "source": "agent"})
        world["calendar"].append(ev)
        world["calendar"].sort(key=lambda e: e.get("start") or "")
        who = f" with {len(ev['attendees'])} invitee(s)" if ev["attendees"] else ""
        return f"Added “{ev['title']}” to your calendar{who}"
    if kind == "send_email":
        world["sent"].insert(0, {
            "id": f"sent{seq}", "to": list(op.get("to") or []), "subject": op.get("subject", ""),
            "body": op.get("body", ""), "date": op.get("date") or world["today"],
        })
        if op.get("in_reply_to"):
            for em in world["inbox"]:
                if em["id"] == op["in_reply_to"]:
                    em["unread"] = False
                    em["replied"] = True
        n = len(op.get("to") or [])
        return f"Sent “{op.get('subject', '')}” to {n} recipient{'s' if n != 1 else ''}"
    if kind == "archive_email":
        ids = set(op.get("ids") or [])
        before = len(world["inbox"])
        world["inbox"] = [e for e in world["inbox"] if e["id"] not in ids]
        return f"Archived {before - len(world['inbox'])} email(s)"
    if kind == "mark_read":
        for em in world["inbox"]:
            if em["id"] in set(op.get("ids") or []):
                em["unread"] = False
        return None
    if kind == "cancel_subscription":
        for sub in world["subscriptions"]:
            if sub["id"] == op.get("id"):
                sub["status"] = "cancelled"
                return f"Cancelled {sub['name']} (saves ${sub['price']:,.2f}/mo)"
        return None
    if kind == "add_booking":
        booking = {k: op.get(k) for k in ("kind", "vendor", "date", "details", "amount", "refundable")}
        booking.update({"id": f"bk{seq}", "status": "confirmed",
                        "confirmation": op.get("confirmation") or f"MC-{1000 + seq}"})
        world["bookings"].append(booking)
        return f"Booked {op.get('vendor')} ({op.get('kind')})"
    return None


def apply_ops(world: dict, ops: list[dict]) -> dict:
    out = copy.deepcopy(world)
    for op in ops:
        summary = _apply(out, op)
        if summary:
            out["ledger"].append({"seq": len(out["ledger"]) + 1, "op": op.get("op"), "summary": summary})
    return out


def world_reducer(current: Optional[dict], update: Optional[dict]) -> dict:
    """State reducer: ``{"reset": world}`` replaces, ``{"ops": [...]}`` applies."""
    if not update:
        return current or {}
    if "reset" in update:
        return copy.deepcopy(update["reset"])
    return apply_ops(current or seed_world(), update.get("ops") or [])


# --- Helpers used by tools, policy and previews -----------------------------
def find(items: list[dict], item_id: str) -> Optional[dict]:
    return next((i for i in items if i.get("id") == item_id), None)


def contact_emails(world: dict) -> set[str]:
    return {c["email"].lower() for c in world.get("contacts", [])}


def busy_on(world: dict, day: str) -> list[dict]:
    """Calendar events on ``day`` (YYYY-MM-DD)."""
    return [e for e in world.get("calendar", []) if (e.get("start") or "").startswith(day)]
