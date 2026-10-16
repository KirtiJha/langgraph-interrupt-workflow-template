"""Mission tools: read the world, search the catalog, and *act* on the world.

Reading tools run freely. Acting tools (``send_email``, ``pay``, ``book`` …)
are gated by :mod:`mission.policy` and return ``Command(update={"world":
{"ops": [...]}})`` so the world reducer applies the change — nothing is mutated
in place, which keeps time travel and forks honest.

``ask_user`` shows the *other* kind of interrupt: a plain ``interrupt()`` from
inside a tool, used when the agent needs a decision only you can make.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command, interrupt

from mission import catalog as C
from mission import world as W


def _emit(message: str, **extra) -> None:
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()({"type": "progress", "message": message, **extra})
    except Exception:  # pragma: no cover - outside a streaming run
        pass


def _world(runtime: ToolRuntime) -> dict:
    return (runtime.state or {}).get("world") or W.seed_world()


def _act(runtime: ToolRuntime, ops: list[dict], result: str, extra: Optional[dict] = None) -> Command:
    update = {"world": {"ops": ops}, "messages": [ToolMessage(result, tool_call_id=runtime.tool_call_id)]}
    if extra:
        update.update(extra)
    return Command(update=update)


# --- Reading -----------------------------------------------------------------
@tool
def read_inbox(runtime: ToolRuntime, unread_only: bool = False) -> str:
    """Read the user's inbox: sender, subject, date, urgency and body of each email."""
    _emit("📬 Reading your inbox…")
    world = _world(runtime)
    emails = [e for e in world["inbox"] if e["unread"] or not unread_only]
    return json.dumps([{k: e[k] for k in ("id", "from", "from_name", "subject", "date", "unread", "urgent", "body")}
                       for e in emails])


@tool
def read_calendar(runtime: ToolRuntime, days: int = 45) -> str:
    """List the user's calendar events for the next ``days`` days, and free weekends."""
    _emit("📅 Checking your calendar…")
    world = _world(runtime)
    today = datetime.fromisoformat(world["today"])
    horizon = today + timedelta(days=days)
    events = [e for e in world["calendar"] if today.isoformat() <= e["start"] <= horizon.isoformat()]
    busy_days = {e["start"][:10] for e in events}
    free_weekends = []
    d = today
    while d <= horizon:
        if d.weekday() == 4:  # Friday
            days3 = [(d + timedelta(days=i)).date().isoformat() for i in range(3)]
            if not any(x in busy_days for x in days3):
                free_weekends.append(f"{days3[0]} → {days3[2]}")
        d += timedelta(days=1)
    return json.dumps({"today": world["today"], "events": events, "free_long_weekends": free_weekends})


@tool
def check_wallet(runtime: ToolRuntime) -> str:
    """Current balance and recent transactions."""
    _emit("💳 Checking your wallet…")
    w = _world(runtime)["wallet"]
    return json.dumps({"balance": w["balance"], "currency": w["currency"], "recent": w["transactions"][:8]})


@tool
def list_contacts(runtime: ToolRuntime, group: Optional[str] = None) -> str:
    """Contacts, optionally filtered by group: family, friends, work, services."""
    _emit("👥 Looking up contacts…")
    contacts = _world(runtime)["contacts"]
    return json.dumps([c for c in contacts if not group or c["group"] == group])


@tool
def list_subscriptions(runtime: ToolRuntime) -> str:
    """Active subscriptions with price and days since last use."""
    _emit("🔎 Auditing subscriptions…")
    return json.dumps(_world(runtime)["subscriptions"])


@tool
def search_restaurants(party_size: int, vegetarian: bool = False, max_price_per_person: Optional[int] = None) -> str:
    """Find restaurants that can host a party, with price, rating, deposit and refund terms."""
    _emit(f"🍽️ Searching restaurants for {party_size}…")
    hits = [r for r in C.RESTAURANTS if r["max_party"] >= party_size
            and (not vegetarian or r["vegetarian_friendly"])
            and (max_price_per_person is None or r["price_per_person"] <= max_price_per_person)]
    _emit(f"🍽️ {len(hits)} restaurant{'s' if len(hits) != 1 else ''} match", options=hits, kind="restaurants")
    return json.dumps({"restaurants": hits, "bakeries": C.BAKERIES})


@tool
def search_flights(destination: str, depart: str, return_date: str) -> str:
    """Search round-trip flights (dates YYYY-MM-DD). Prices are per person, round trip."""
    _emit(f"✈️ Searching flights to {destination}…")
    _emit(f"✈️ {len(C.FLIGHTS)} flight options", options=C.FLIGHTS, kind="flights")
    return json.dumps({"depart": depart, "return": return_date, "flights": C.FLIGHTS})


@tool
def search_hotels(city: str, checkin: str, nights: int) -> str:
    """Search hotels for a stay; price is per night."""
    _emit(f"🏨 Searching hotels in {city}…")
    _emit(f"🏨 {len(C.HOTELS)} hotels found", options=C.HOTELS, kind="hotels")
    return json.dumps({"city": city, "checkin": checkin, "nights": nights, "hotels": C.HOTELS})


@tool
def get_quotes(service: str) -> str:
    """Get quotes from local vendors. ``service``: movers | cleaners."""
    _emit(f"📋 Getting {service} quotes…")
    quotes = C.SERVICES.get(service, [])
    _emit(f"📋 {len(quotes)} quotes for {service}", options=quotes, kind=service)
    return json.dumps(quotes)


@tool
async def remember(runtime: ToolRuntime, note: str) -> str:
    """Save a lasting fact or preference about the user for future missions (e.g. 'Mom is vegetarian')."""
    from memory import save_user_memory

    user_id = (runtime.state or {}).get("user_id")
    await save_user_memory(runtime.store, user_id, note)
    _emit(f"🧠 Remembered: {note}", kind="memory")
    return f"Remembered: {note}"


@tool
def ask_user(question: str, options: Optional[list[str]] = None) -> str:
    """Ask the user a question you can't answer from their data (pauses the mission)."""
    answer = interrupt({"type": "question", "question": question, "options": options or []})
    return f"The user answered: {answer}"


# --- Acting (gated by the policy) -------------------------------------------
@tool
def send_email(runtime: ToolRuntime, to: list[str], subject: str, body: str, in_reply_to: Optional[str] = None) -> Command:
    """Send an email from the user. ``in_reply_to`` is the inbox email id when replying."""
    _emit(f"✉️ Sending “{subject}” to {len(to)} recipient(s)")
    ops = [{"op": "send_email", "to": to, "subject": subject, "body": body, "in_reply_to": in_reply_to,
            "date": _world(runtime)["today"]}]
    return _act(runtime, ops, f"Email “{subject}” sent to {', '.join(to)}.")


@tool
def archive_emails(runtime: ToolRuntime, ids: list[str]) -> Command:
    """Archive emails by id (removes them from the inbox)."""
    _emit(f"🗂️ Archiving {len(ids)} email(s)")
    return _act(runtime, [{"op": "archive_email", "ids": ids}], f"Archived {len(ids)} email(s).")


@tool
def add_calendar_event(runtime: ToolRuntime, title: str, start: str, end: str, location: str = "",
                       attendees: Optional[list[str]] = None) -> Command:
    """Add a calendar event (ISO datetimes). Attendees receive invitations."""
    _emit(f"📅 Adding “{title}”")
    ops = [{"op": "add_event", "title": title, "start": start, "end": end, "location": location,
            "attendees": attendees or []}]
    return _act(runtime, ops, f"Added “{title}” on {start[:10]} ({len(attendees or [])} invited).")


@tool
def pay(runtime: ToolRuntime, payee: str, amount: float, memo: str = "", category: str = "other",
        refundable: bool = True) -> Command:
    """Pay a vendor from the user's wallet."""
    _emit(f"💸 Paying ${amount:,.2f} to {payee}")
    ops = [{"op": "charge", "payee": payee, "amount": amount, "memo": memo, "category": category,
            "date": _world(runtime)["today"]}]
    return _act(runtime, ops, f"Paid ${amount:,.2f} to {payee}.")


@tool
def book(runtime: ToolRuntime, kind: str, vendor: str, date: str, amount: float, details: str = "",
         refundable: bool = True) -> Command:
    """Make a booking (restaurant, flight, hotel, movers, cleaners…) and pay its amount/deposit."""
    _emit(f"🧾 Booking {vendor} ({kind})")
    world = _world(runtime)
    ops = [{"op": "add_booking", "kind": kind, "vendor": vendor, "date": date, "details": details,
            "amount": amount, "refundable": refundable}]
    if amount:
        ops.append({"op": "charge", "payee": vendor, "amount": amount, "memo": f"{kind} booking", "category": kind,
                    "date": world["today"]})
    confirmation = f"MC-{abs(hash(runtime.tool_call_id)) % 9000 + 1000}"
    ops[0]["confirmation"] = confirmation
    return _act(runtime, ops, f"Booked {vendor} for {date}. Confirmation {confirmation}. Charged ${amount:,.2f}.")


@tool
def cancel_subscription(runtime: ToolRuntime, id: str) -> Command:
    """Cancel a subscription by id. This cannot be undone."""
    sub = W.find(_world(runtime)["subscriptions"], id) or {"name": id, "price": 0}
    _emit(f"🚫 Cancelling {sub['name']}")
    return _act(runtime, [{"op": "cancel_subscription", "id": id}],
                f"Cancelled {sub['name']} — saves ${sub['price']:,.2f}/month.")


@tool
def finish_mission(runtime: ToolRuntime, summary: str, done: list[str], open_items: Optional[list[str]] = None,
                   spent: float = 0.0) -> Command:
    """Call once at the end with a short summary, what was done, what's still open, and total spent."""
    report = {"summary": summary, "done": done, "open_items": open_items or [], "spent": spent}
    return _act(runtime, [], "Mission report recorded.", {"report": report})


READ_TOOLS = [read_inbox, read_calendar, check_wallet, list_contacts, list_subscriptions,
              search_restaurants, search_flights, search_hotels, get_quotes, ask_user, remember]
ACT_TOOLS = [send_email, archive_emails, add_calendar_event, pay, book, cancel_subscription]
ALL_TOOLS = READ_TOOLS + ACT_TOOLS + [finish_mission]
