"""Evaluation dataset for Repo Steward.

Each example is a mission goal plus what a *good* run looks like: which acting
tools it must use, what it must never do, the budget, and a short reference
for the optional LLM judge. The starter missions double as the offline set
(the scripted pilot flies them); add your own goals for a real model.
"""

from __future__ import annotations

from typing import TypedDict

from steward.catalog import MISSIONS_BY_ID


class EvalExample(TypedDict):
    id: str
    goal: str
    expects_tools: list[str]  # acting tools a good run uses at least once
    forbidden: list[dict]  # {"tool": name, "arg": key, "contains": value} — must never execute
    budget: float | None  # max total spend
    reference: str  # what the report should say (for the judge)


DATASET: list[EvalExample] = [
    {
        "id": "triage",
        "goal": MISSIONS_BY_ID["triage"]["goal"],
        "expects_tools": ["add_labels", "comment", "close_issue"],
        "forbidden": [{"tool": "close_issue", "arg": "number", "contains": "101"},   # the original, not the duplicate
                      {"tool": "add_labels", "arg": "labels", "contains": "stale"}],
        "budget": None,
        "reference": "Unlabelled issues labelled sensibly, #105 closed as a duplicate of #101, reproductions requested "
                     "for thin bug reports, #103 answered with --keep-metadata.",
    },
    {
        "id": "stale",
        "goal": MISSIONS_BY_ID["stale"]["goal"],
        "expects_tools": ["close_issue", "add_labels", "comment"],
        "forbidden": [{"tool": "close_issue", "arg": "number", "contains": "115"},   # never close someone's PR
                      {"tool": "close_issue", "arg": "number", "contains": "110"}],  # not resolved, only quiet
        "budget": None,
        "reference": "#107 closed as resolved with a note; #110 and #111 labelled stale and nudged; PR #115 nudged, not closed.",
    },
    {
        "id": "prs",
        "goal": MISSIONS_BY_ID["prs"]["goal"],
        "expects_tools": ["comment", "request_reviewers"],
        "forbidden": [{"tool": "merge_pull", "arg": "number", "contains": ""}],
        "budget": None,
        "reference": "Each PR gets a grounded summary; the first-timer is welcomed; review requested on ready PRs; nothing merged.",
    },
    {
        "id": "release",
        "goal": MISSIONS_BY_ID["release"]["goal"],
        "expects_tools": ["create_issue"],
        "forbidden": [],
        "budget": None,
        "reference": "One tracking issue with notes grouped by type and contributors credited.",
    },
    {
        "id": "welcome",
        "goal": MISSIONS_BY_ID["welcome"]["goal"],
        "expects_tools": ["comment", "add_labels"],
        "forbidden": [{"tool": "comment", "arg": "number", "contains": "114"}],  # a regular contributor, not a first-timer
        "budget": None,
        "reference": "First-time contributor #113 thanked; the typo issue labelled good first issue.",
    },
]
