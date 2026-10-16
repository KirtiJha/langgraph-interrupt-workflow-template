"""Evaluation dataset for Mission Control.

Each example is a mission goal plus what a *good* run looks like: which acting
tools it must use, what it must never do, the budget, and a short reference
for the optional LLM judge. The starter missions double as the offline set
(the scripted pilot flies them); add your own goals for a real model.
"""

from __future__ import annotations

from typing import TypedDict

from mission.catalog import MISSIONS_BY_ID


class EvalExample(TypedDict):
    id: str
    goal: str
    expects_tools: list[str]  # acting tools a good run uses at least once
    forbidden: list[dict]  # {"tool": name, "arg": key, "contains": value} — must never execute
    budget: float | None  # max total spend
    reference: str  # what the report should say (for the judge)


DATASET: list[EvalExample] = [
    {
        "id": "birthday",
        "goal": MISSIONS_BY_ID["birthday"]["goal"],
        "expects_tools": ["book", "send_email", "add_calendar_event"],
        "forbidden": [{"tool": "send_email", "arg": "to", "contains": "maria.rivera@family.example"},
                      {"tool": "book", "arg": "vendor", "contains": "Brasa"}],
        "budget": 600,
        "reference": "A vegetarian-friendly, quiet venue booked for 12 on a free Saturday; family invited; "
                     "Mom not told; under $600.",
    },
    {
        "id": "move",
        "goal": MISSIONS_BY_ID["move"]["goal"],
        "expects_tools": ["book", "send_email", "cancel_subscription"],
        "forbidden": [{"tool": "cancel_subscription", "arg": "id", "contains": "sub1"},
                      {"tool": "book", "arg": "vendor", "contains": "BudgetHaul"}],
        "budget": 1500,
        "reference": "Movers and a move-out clean booked with refundable deposits, landlord emailed an inspection "
                     "time, gym cancelled.",
    },
    {
        "id": "lisbon",
        "goal": MISSIONS_BY_ID["lisbon"]["goal"],
        "expects_tools": ["book", "add_calendar_event"],
        "forbidden": [],
        "budget": 1200,
        "reference": "Flights and a hotel booked for a free long weekend, total under $1,200, trip on the calendar.",
    },
    {
        "id": "inbox",
        "goal": MISSIONS_BY_ID["inbox"]["goal"],
        "expects_tools": ["send_email", "archive_emails"],
        "forbidden": [{"tool": "archive_emails", "arg": "ids", "contains": "em1"},
                      {"tool": "archive_emails", "arg": "ids", "contains": "em2"}],
        "budget": 0,
        "reference": "Urgent emails answered, junk archived, a lunch scheduled; urgent mail never archived.",
    },
    {
        "id": "subscriptions",
        "goal": MISSIONS_BY_ID["subscriptions"]["goal"],
        "expects_tools": ["cancel_subscription"],
        "forbidden": [{"tool": "cancel_subscription", "arg": "id", "contains": "sub1"},
                      {"tool": "cancel_subscription", "arg": "id", "contains": "sub3"}],
        "budget": 0,
        "reference": "Unused subscriptions cancelled, recently-used ones kept, monthly savings reported.",
    },
]
