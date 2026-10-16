"""The offline pilot: a scripted model that flies the starter missions.

When no real model is configured (or the visitor picks "Mock" in the UI), the
mission agent still has to *do* things — read the inbox, compare venues, book,
pay, email — and react to what you decide: a rejected booking leads to the
runner-up, an edited amount is respected, an ``ask_user`` answer is honoured.

This is a tiny deterministic "model": it looks at the conversation so far
(which tool calls succeeded, which were rejected, what you answered) and emits
the next tool calls, with a line of narration. It only knows the starter
missions; for anything else it explains that a real model is needed.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterator, List, Optional

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from mission import catalog as C

FAMILY = ["maria.rivera@family.example", "luis.rivera@family.example", "sofia@family.example",
          "diego@family.example", "elena.ortiz@family.example", "carmen@family.example",
          "rosa.d@friends.example"]
GUESTS = [e for e in FAMILY if e != "maria.rivera@family.example"]

EXECUTED_PREFIXES = ("Booked", "Paid", "Email", "Added", "Archived", "Cancelled", "Mission report",
                     "Note: a human reviewer replaced")


# --- Reading the conversation -----------------------------------------------
class Ctx:
    """What has happened so far, from the pilot's point of view."""

    def __init__(self, messages: List[BaseMessage]) -> None:
        self.goal = next((str(m.content) for m in messages if m.type in ("human", "user")), "")
        self.mission = C.mission_for_goal(self.goal)
        self.turns = sum(1 for m in messages if m.type == "ai" and getattr(m, "tool_calls", None))
        self.calls: list[dict] = []  # {"tool", "args", "result", "ok", "rejected"}
        pending: dict[str, dict] = {}
        for m in messages:
            if m.type == "ai":
                for tc in getattr(m, "tool_calls", None) or []:
                    pending[tc["id"]] = {"tool": tc["name"], "args": tc["args"], "result": None,
                                         "ok": False, "rejected": False}
            elif m.type == "tool":
                call = pending.get(getattr(m, "tool_call_id", ""))
                if call is None:
                    continue
                text = str(m.content)
                call["result"] = text
                # A reviewer may have edited the call: what *ran* is in the notice.
                marker = "Executed instead: "
                if text.startswith("Note: a human reviewer") and marker in text:
                    try:
                        after = text[text.index(marker) + len(marker):]
                        name, _, rest = after.partition(" with arguments ")
                        call["args"] = json.JSONDecoder().raw_decode(rest)[0]
                        call["tool"] = name.strip()
                    except (ValueError, IndexError):
                        pass
                call["rejected"] = text.startswith("User rejected")
                acting = call["tool"] in ("send_email", "archive_emails", "add_calendar_event", "pay", "book",
                                          "cancel_subscription", "finish_mission")
                call["ok"] = (text.startswith(EXECUTED_PREFIXES) if acting else not call["rejected"])
                self.calls.append(call)

    def ok(self, tool: str, **match) -> bool:
        return any(c["ok"] and c["tool"] == tool and all(c["args"].get(k) == v for k, v in match.items())
                   for c in self.calls)

    def rejected(self, tool: str, **match) -> int:
        return sum(1 for c in self.calls if c["rejected"] and c["tool"] == tool
                   and all(c["args"].get(k) == v for k, v in match.items()))

    def tried(self, tool: str, **match) -> bool:
        return any(c["tool"] == tool and all(c["args"].get(k) == v for k, v in match.items())
                   for c in self.calls)

    def result(self, tool: str) -> Any:
        for c in self.calls:
            if c["tool"] == tool and c["result"] and not c["rejected"]:
                try:
                    return json.loads(c["result"])
                except ValueError:
                    return c["result"]
        return None

    def answer(self, tool: str = "ask_user") -> Optional[str]:
        for c in reversed(self.calls):
            if c["tool"] == tool and c["result"]:
                return c["result"].replace("The user answered:", "").strip()
        return None

    def spent(self) -> float:
        total = 0.0
        for c in self.calls:
            if c["ok"] and c["tool"] in ("pay", "book"):
                total += float(c["args"].get("amount") or 0)
        return round(total, 2)

    def today(self) -> date:
        cal = self.result("read_calendar")
        if isinstance(cal, dict) and cal.get("today"):
            return date.fromisoformat(cal["today"])
        return date.today()

    def free_weekend(self) -> tuple[date, date]:
        cal = self.result("read_calendar")
        if isinstance(cal, dict) and cal.get("free_long_weekends"):
            start = date.fromisoformat(cal["free_long_weekends"][0][:10])
            return start, start + timedelta(days=3)
        t = self.today() + timedelta(days=14)
        return t, t + timedelta(days=3)

    def next_free_saturday(self, min_days: int = 14) -> date:
        cal = self.result("read_calendar")
        busy = {e["start"][:10] for e in (cal or {}).get("events", [])} if isinstance(cal, dict) else set()
        d = self.today() + timedelta(days=min_days)
        while d.weekday() != 5 or d.isoformat() in busy:
            d += timedelta(days=1)
        return d


def _dt(d: date, h: int, m: int = 0) -> str:
    return datetime.combine(d, datetime.min.time()).replace(hour=h, minute=m).isoformat(timespec="minutes")


Step = tuple[str, list[tuple[str, dict]]]  # narration, tool calls


# --- Scripts -----------------------------------------------------------------
def birthday(c: Ctx) -> Step | str:
    if not c.tried("read_inbox"):
        return ("Let me start with who's family, what Mom said, and what you can spend.",
                [("read_inbox", {}), ("list_contacts", {"group": "family"}), ("check_wallet", {})])
    if not c.tried("search_restaurants"):
        return ("Mom asked for something small and quiet — and she's vegetarian now. "
                "Looking for quiet, veggie-friendly places that seat 12, and a free Saturday.",
                [("search_restaurants", {"party_size": 12, "vegetarian": True, "max_price_per_person": 55}),
                 ("read_calendar", {"days": 45}),
                 ("remember", {"note": "Mom (Maria) is vegetarian and prefers small, quiet celebrations."})])
    if not c.tried("ask_user"):
        return ("Two good fits. Which would she prefer?",
                [("ask_user", {"question": "Olive & Fig has a quiet private garden room ($45/person, refundable $120 "
                                           "deposit). Trattoria Nonna is candlelit with handmade pasta ($52/person, "
                                           "$150 deposit). Which should I book?",
                               "options": ["Olive & Fig", "Trattoria Nonna"]})])
    choice = "Trattoria Nonna" if "nonna" in (c.answer() or "").lower() else "Olive & Fig"
    other = "Olive & Fig" if choice == "Trattoria Nonna" else "Trattoria Nonna"
    sat = c.next_free_saturday()
    if not c.ok("book", kind="restaurant"):
        if c.rejected("book", kind="restaurant") == 0:
            venue = next(r for r in C.RESTAURANTS if r["name"] == choice)
        elif c.rejected("book", kind="restaurant") == 1:
            venue = next(r for r in C.RESTAURANTS if r["name"] == other)
        else:
            return ("No problem — I'll leave the venue to you.", [("finish_mission", {
                "summary": "Venue not booked — both options were declined.", "done": [],
                "open_items": ["Pick a venue", "Order the cake", "Invite the family"], "spent": c.spent()})])
        narration = (f"Booking {venue['name']} for {sat.strftime('%A %b %-d')} at 7pm, and a vegetarian cake."
                     if not c.rejected("book", kind="restaurant")
                     else f"Understood. Trying {venue['name']} instead.")
        calls = [("book", {"kind": "restaurant", "vendor": venue["name"], "date": _dt(sat, 19),
                           "amount": venue["deposit"], "refundable": venue["refundable"],
                           "details": f"Private room for 12 · vegetarian menu · {venue['highlight']}"})]
        if not c.tried("pay", payee="Golden Crumb"):
            calls.append(("pay", {"payee": "Golden Crumb", "amount": 64, "category": "food",
                                  "memo": "Tres leches birthday cake (serves 16)"}))
        return (narration, calls)
    venue = next((cl["args"] for cl in c.calls if cl["ok"] and cl["tool"] == "book"), {})
    if not c.tried("send_email") and not c.tried("add_calendar_event"):
        return ("Venue's locked in. Putting it on the calendar and inviting the family (not Mom — it's a surprise).",
                [("add_calendar_event", {"title": "Mom's 60th birthday dinner 🎂", "start": _dt(sat, 19),
                                         "end": _dt(sat, 21, 30), "location": venue.get("vendor", choice),
                                         "attendees": GUESTS}),
                 ("send_email", {"to": GUESTS, "subject": "Mom's 60th — save the date 🎉",
                                 "body": f"Hi all,\n\nWe're celebrating Mom's 60th with a dinner at "
                                         f"{venue.get('vendor', choice)} on {sat.strftime('%A, %B %-d')} at 7pm. "
                                         "Vegetarian menu (her request!). Please keep it a surprise.\n\n"
                                         "Reply if you can make it.\n\n— Alex"})])
    if not c.tried("finish_mission"):
        done = [f"Booked {venue.get('vendor', choice)} for {sat.strftime('%b %-d')} (12 people, refundable deposit)"]
        if c.ok("pay", payee="Golden Crumb"):
            done.append("Ordered a tres leches cake from Golden Crumb")
        if c.ok("add_calendar_event"):
            done.append("Added the dinner to your calendar")
        if c.ok("send_email"):
            done.append(f"Invited {len(GUESTS)} family members")
        open_items = [x for x, ok in (("Invite the family", not c.ok("send_email")),
                                      ("Order a cake", not c.ok("pay", payee="Golden Crumb"))) if ok]
        total = 12 * next((r["price_per_person"] for r in C.RESTAURANTS if r["name"] == venue.get("vendor")), 45)
        budget_line = (f"about ${total:,} for 12, under your $600" if total <= 600
                       else f"about ${total:,} for 12 — ${total - 600} over your $600; the deposit is refundable if you'd rather switch")
        return (f"All set. Dinner will run {budget_line}.",
                [("finish_mission", {"summary": f"Mom's 60th is on {sat.strftime('%A, %B %-d')} at "
                                                f"{venue.get('vendor', choice)} — quiet, vegetarian, "
                                                f"{'under budget' if total <= 600 else f'about ${total - 600} over budget'}.",
                                     "done": done, "open_items": open_items, "spent": c.spent()})])
    return "Mission complete — I'll be here when the RSVPs come in."


def move(c: Ctx) -> Step | str:
    if not c.tried("read_inbox"):
        return ("Checking your inbox, subscriptions, calendar and balance before I book anything.",
                [("read_inbox", {}), ("list_subscriptions", {}), ("check_wallet", {}),
                 ("read_calendar", {"days": 30})])
    if not c.tried("get_quotes"):
        return ("Your landlord wants an inspection time by the 1st. Getting mover and cleaner quotes in parallel.",
                [("get_quotes", {"service": "movers"}), ("get_quotes", {"service": "cleaners"})])
    first = (c.today().replace(day=1) + timedelta(days=32)).replace(day=1)
    if not c.ok("book", kind="movers"):
        n = c.rejected("book", kind="movers")
        if n >= 2:
            return ("I'll leave the movers to you then.",
                    [("finish_mission", {"summary": "Movers not booked.", "done": [],
                                         "open_items": ["Book movers"], "spent": c.spent()})])
        mover = C.SERVICES["movers"][1 if n else 0]
        calls = [("book", {"kind": "movers", "vendor": mover["vendor"], "date": _dt(first, 8),
                           "amount": mover["deposit"], "refundable": mover["refundable"],
                           "details": f"{mover['crew']}-person crew · ${mover['price']} total · {mover['note']}"})]
        say = (f"SwiftMove is the best value with a refundable deposit (BudgetHaul wants full prepayment, no "
               f"insurance). Booking them and SparkleSquad for the move-out clean." if not n
               else f"OK — {mover['vendor']} is the top-rated alternative. Trying them.")
        if not c.tried("book", kind="cleaners"):
            cl = C.SERVICES["cleaners"][0]
            calls.append(("book", {"kind": "cleaners", "vendor": cl["vendor"], "date": _dt(first - timedelta(days=1), 9),
                                   "amount": cl["deposit"], "refundable": True, "details": cl["note"]}))
        return (say, calls)
    inspect = first - timedelta(days=1)
    if not c.tried("send_email"):
        return ("Movers booked. Telling the landlord, blocking the inspection, and cancelling the gym you haven't "
                "used in 74 days.",
                [("send_email", {"to": ["landlord@baysideapts.example"], "in_reply_to": "em2",
                                 "subject": "Re: Move-out inspection",
                                 "body": f"Hello,\n\nI'd like to schedule the move-out inspection for "
                                         f"{inspect.strftime('%A, %B %-d')} at 3pm. Keys will be returned the same "
                                         "day.\n\nThanks,\nAlex Rivera"}),
                 ("add_calendar_event", {"title": "Move-out inspection", "start": _dt(inspect, 15),
                                         "end": _dt(inspect, 15, 45), "location": "Bayside Apartments"}),
                 ("cancel_subscription", {"id": "sub2"})])
    if not c.tried("finish_mission"):
        done = [d for d, ok in (("Booked movers (refundable deposit)", c.ok("book", kind="movers")),
                                ("Booked a move-out clean", c.ok("book", kind="cleaners")),
                                ("Emailed the landlord to schedule the inspection", c.ok("send_email")),
                                ("Added the inspection to your calendar", c.ok("add_calendar_event")),
                                ("Cancelled IronPeak Gym (saves $59/mo)", c.ok("cancel_subscription"))) if ok]
        open_items = [d for d, ok in (("Confirm the inspection time with the landlord", True),
                                      ("Cancel the gym", not c.ok("cancel_subscription"))) if ok]
        return ("Move is organised.", [("finish_mission", {
            "summary": f"Movers on {first.strftime('%B %-d')}, cleaners the day before, landlord notified.",
            "done": done, "open_items": open_items, "spent": c.spent()})])
    return "That's everything for the move. Good luck with the boxes!"


def lisbon(c: Ctx) -> Step | str:
    if not c.tried("read_calendar"):
        return ("Finding a long weekend you're actually free, and checking the budget.",
                [("read_calendar", {"days": 45}), ("check_wallet", {})])
    start, end = c.free_weekend()
    if not c.tried("search_flights"):
        return (f"{start.strftime('%b %-d')}–{end.strftime('%-d')} is wide open. Comparing flights and hotels.",
                [("search_flights", {"destination": "Lisbon", "depart": start.isoformat(),
                                     "return_date": end.isoformat()}),
                 ("search_hotels", {"city": "Lisbon", "checkin": start.isoformat(), "nights": 3})])
    if not c.ok("book", kind="flight"):
        n = c.rejected("book", kind="flight")
        if n >= 2:
            return ("I'll stop here — pick a flight and I'll take it from there.",
                    [("finish_mission", {"summary": "Flights not booked.", "done": [],
                                         "open_items": ["Choose a flight"], "spent": c.spent()})])
        fl = C.FLIGHTS[1 if n == 0 else 2]
        calls = [("book", {"kind": "flight", "vendor": fl["airline"], "date": start.isoformat(),
                           "amount": fl["price"], "refundable": fl["refundable"],
                           "details": f"{fl['route']} round trip · {fl['stops']} stop · departs {fl['depart_time']}"})]
        say = ("United+Lufthansa is refundable and only $77 more than the cheapest — worth it. "
               "Casa do Bairro has rooftop river views and free cancellation. Total $1,043, under your $1,200."
               if n == 0 else f"Got it — the Azores Airlines fare is cheaper (${fl['price']}) but non-refundable.")
        if not c.tried("book", kind="hotel"):
            h = C.HOTELS[0]
            calls.append(("book", {"kind": "hotel", "vendor": h["name"], "date": start.isoformat(),
                                   "amount": h["price_per_night"] * 3, "refundable": h["refundable"],
                                   "details": f"{h['area']} · 3 nights · {h['highlight']}"}))
        return (say, calls)
    if not c.tried("add_calendar_event"):
        return ("Booked. Blocking the trip on your calendar.",
                [("add_calendar_event", {"title": "Lisbon ✈️", "start": _dt(start, 13, 40), "end": _dt(end, 22),
                                         "location": "Lisbon, Portugal"}),
                 ("remember", {"note": "Prefers refundable fares and hotels with free cancellation."})])
    if not c.tried("finish_mission"):
        done = [d for d, ok in (("Booked refundable flights SFO → LIS", c.ok("book", kind="flight")),
                                ("Booked 3 nights at Casa do Bairro (free cancellation)", c.ok("book", kind="hotel")),
                                ("Blocked the trip on your calendar", c.ok("add_calendar_event"))) if ok]
        return ("Lisbon's on.", [("finish_mission", {
            "summary": f"Long weekend in Lisbon {start.strftime('%b %-d')}–{end.strftime('%-d')}, "
                       f"${c.spent():,.0f} of your $1,200.",
            "done": done, "open_items": ["Pack"] if done else ["Choose flights and a hotel"], "spent": c.spent()})])
    return "Boa viagem! Everything's booked and on your calendar."


def inbox(c: Ctx) -> Step | str:
    if not c.tried("read_inbox"):
        return ("Reading everything and checking next week's calendar.",
                [("read_inbox", {}), ("read_calendar", {"days": 14})])
    tue = c.today() + timedelta(days=(1 - c.today().weekday()) % 7 or 7)
    if not c.tried("send_email"):
        return ("Two urgent threads (your manager and your landlord), a lunch invite, and junk. Drafting replies — "
                "edit anything before it goes out.",
                [("send_email", {"to": ["priya@northwind.example"], "in_reply_to": "em1",
                                 "subject": "Re: Q3 numbers before Thursday?",
                                 "body": "Hi Priya,\n\nYes — I'll send a rough cut of the Q3 numbers by Wednesday "
                                         "EOD so you have them before planning.\n\nAlex"}),
                 ("send_email", {"to": ["jordan@friends.example"], "in_reply_to": "em3",
                                 "subject": "Re: Lunch next week?",
                                 "body": f"Would love to! Tuesday {tue.strftime('%b %-d')} at 12:30 works for me — "
                                         "I'll send an invite.\n\nAlex"}),
                 ("archive_emails", {"ids": ["em4", "em5"]})])
    if not c.tried("add_calendar_event"):
        return ("Putting lunch on the calendar.",
                [("add_calendar_event", {"title": "Lunch with Jordan", "start": _dt(tue, 12, 30), "end": _dt(tue, 13, 30),
                                         "location": "TBD", "attendees": ["jordan@friends.example"]})])
    if not c.tried("finish_mission"):
        done = [d for d, ok in (("Replied to Priya about the Q3 numbers", c.ok("send_email", in_reply_to="em1")),
                                ("Replied to Jordan about lunch", c.ok("send_email", in_reply_to="em3")),
                                ("Archived 2 junk emails", c.ok("archive_emails")),
                                ("Scheduled lunch with Jordan", c.ok("add_calendar_event"))) if ok]
        return ("Inbox handled.", [("finish_mission", {
            "summary": "Urgent mail answered, lunch scheduled, junk gone. The landlord's inspection still needs a date "
                       "from you.",
            "done": done, "open_items": ["Reply to Bayside Apartments with an inspection time",
                                         "Send Priya the Q3 numbers by Wednesday"], "spent": 0})])
    return "You're at inbox zero (well, one — the landlord needs a date from you)."


def subscriptions(c: Ctx) -> Step | str:
    if not c.tried("list_subscriptions"):
        return ("Pulling your subscriptions and recent charges.", [("list_subscriptions", {}), ("check_wallet", {})])
    if not c.tried("cancel_subscription"):
        return ("Three haven't been used in over a month: Lingo+ (120 days), IronPeak Gym (74), NewsDaily (45). "
                "MealBox is borderline at 33 days, so I'm leaving it. Each cancellation needs your OK.",
                [("cancel_subscription", {"id": "sub4"}), ("cancel_subscription", {"id": "sub2"}),
                 ("cancel_subscription", {"id": "sub5"})])
    if not c.tried("finish_mission"):
        prices = {"sub4": 12.99, "sub2": 59.00, "sub5": 14.99}
        saved = round(sum(p for sid, p in prices.items() if c.ok("cancel_subscription", id=sid)), 2)
        names = {"sub4": "Lingo+", "sub2": "IronPeak Gym", "sub5": "NewsDaily"}
        done = [f"Cancelled {names[s]}" for s in prices if c.ok("cancel_subscription", id=s)]
        kept = [names[s] for s in prices if not c.ok("cancel_subscription", id=s)]
        return (f"That saves ${saved:,.2f} a month — ${saved * 12:,.0f} a year.", [("finish_mission", {
            "summary": f"Cancelled {len(done)} unused subscription(s), saving ${saved:,.2f}/month.",
            "done": done, "open_items": [f"Decide on {k}" for k in kept] + ["Re-check MealBox next month"],
            "spent": 0})])
    return "Done — your statement will be lighter next month."


def generic(c: Ctx) -> Step | str:
    if not c.tried("read_inbox"):
        return ("I'm the offline pilot, so I'll take a look around first.",
                [("read_inbox", {"unread_only": True}), ("read_calendar", {"days": 14}), ("check_wallet", {})])
    return ("I can only fly the starter missions offline. Pick one from the gallery, or choose a real model "
            "under the Model button and I'll plan this goal properly.")


SCRIPTS: dict[str, Callable[[Ctx], Step | str]] = {
    "birthday": birthday, "move": move, "lisbon": lisbon, "inbox": inbox, "subscriptions": subscriptions,
}


# --- The model ---------------------------------------------------------------
class MissionPilot(BaseChatModel):
    """Scripted chat model for the mission agent (offline / mock)."""

    @property
    def _llm_type(self) -> str:
        return "mission-pilot"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "MissionPilot":
        return self

    def _next(self, messages: List[BaseMessage]) -> AIMessage:
        ctx = Ctx(messages)
        if ctx.turns >= 12:  # safety: never loop forever
            return AIMessage(content="I've done what I can for this mission.")
        step = SCRIPTS.get(ctx.mission or "", generic)(ctx)
        if isinstance(step, str):
            return AIMessage(content=step)
        say, calls = step
        tool_calls = [{"name": name, "args": args, "id": f"pilot-{ctx.turns}-{i}"} for i, (name, args) in enumerate(calls)]
        return AIMessage(content=say, tool_calls=tool_calls)

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                  run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    async def _agenerate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                         run_manager: Optional[AsyncCallbackManagerForLLMRun] = None, **kwargs: Any) -> ChatResult:
        return self._generate(messages, stop=stop, **kwargs)

    def _stream(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        msg = self._next(messages)
        words = str(msg.content).split(" ")
        for i, token in enumerate(words):
            text = token + (" " if i < len(words) - 1 else "")
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=text))
            if run_manager:
                run_manager.on_llm_new_token(text, chunk=chunk)
            yield chunk
        if msg.tool_calls:
            yield ChatGenerationChunk(message=AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"], "index": i}
                                  for i, tc in enumerate(msg.tool_calls)],
            ))
