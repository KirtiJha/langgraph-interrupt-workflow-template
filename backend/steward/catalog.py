"""Starter missions for Repo Steward."""

from __future__ import annotations

MISSIONS = [
    {
        "id": "triage",
        "emoji": "🏷️",
        "title": "Triage the open issues",
        "goal": "Triage the open issues: label each one (bug / enhancement / question / docs), mark duplicates, ask for a "
                "reproduction where a bug report has none, and answer questions you can answer from the README and code.",
        "blurb": "Labels, duplicates, repro requests, answers from the docs.",
        "tags": ["Labels", "Comments", "Duplicates"],
        "approvals": 6,
        "accent": "rose",
    },
    {
        "id": "stale",
        "emoji": "🧹",
        "title": "Sweep stale issues and PRs",
        "goal": "Find issues and pull requests with no activity for 60+ days. Close the ones that are resolved or abandoned "
                "with a polite note, and label the rest stale with a friendly nudge.",
        "blurb": "Closes what's done, nudges what's not — nothing without you.",
        "tags": ["Close", "Stale"],
        "approvals": 4,
        "accent": "amber",
    },
    {
        "id": "prs",
        "emoji": "🔍",
        "title": "Review the open pull requests",
        "goal": "Review each open pull request: summarise the change, flag risks, welcome first-time contributors, "
                "and recommend next steps. Request review from a maintainer where it's ready.",
        "blurb": "Summaries, risk flags, a warm welcome for first-timers.",
        "tags": ["Pull requests", "Review"],
        "approvals": 3,
        "accent": "sky",
    },
    {
        "id": "release",
        "emoji": "🚀",
        "title": "Draft the release notes",
        "goal": "Draft release notes for everything merged since the last tag, grouped by type, crediting contributors, "
                "and open a tracking issue with the draft.",
        "blurb": "Groups commits since the last tag into notes you can ship.",
        "tags": ["Release", "New issue"],
        "approvals": 1,
        "accent": "violet",
    },
    {
        "id": "welcome",
        "emoji": "👋",
        "title": "Welcome first-time contributors",
        "goal": "Find pull requests and issues from first-time contributors, thank them, point them at CONTRIBUTING.md, "
                "and label good first issues for newcomers.",
        "blurb": "Turns drive-by contributors into regulars.",
        "tags": ["Community", "Labels"],
        "approvals": 3,
        "accent": "emerald",
    },
]

MISSIONS_BY_ID = {m["id"]: m for m in MISSIONS}


def mission_for_goal(goal: str) -> str | None:
    text = (goal or "").strip().lower()
    for m in MISSIONS:
        if text == m["goal"].lower():
            return m["id"]
    return None
