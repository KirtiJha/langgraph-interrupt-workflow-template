"""Risk policy for repository actions: how risky, why, and should we ask?

Scored against the *board* in state (who the issue is from, how active it is,
whether it's a pull request) and the user's autonomy level. Public comments
can't be unseen and merges can't be undone, so those weigh heaviest. The
result feeds the approval card: level, reasons, reversibility and a preview
of what will be posted or changed.

Autonomy (``state["autonomy"]``):

- ``observe``   — propose only: every action asks, and approving records a
  proposal instead of touching GitHub. The default without a write token.
- ``careful``   — every action asks (the default with a token).
- ``balanced``  — asks for medium and high risk; labels and assignments just run.
- ``autopilot`` — asks only for high risk or irreversible actions.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain.agents.middleware import InterruptOnConfig

import approval_policy
from steward import world as W
from steward.github import days_ago

logger = logging.getLogger(__name__)

ACTING_TOOLS = ["add_labels", "remove_labels", "comment", "close_issue", "reopen_issue", "retitle",
                "create_issue", "assign", "request_reviewers", "merge_pull"]
READ_TOOLS = ["list_issues", "list_pulls", "read_issue", "find_similar", "read_file", "read_pull",
              "release_context", "ask_user", "remember", "finish_mission"]
ALLOWED = ["approve", "edit", "reject", "respond"]
AUTONOMY_LEVELS = ["observe", "careful", "balanced", "autopilot"]
LEVEL_RANK = {"low": 0, "medium": 1, "high": 2}
MENTION_RE = re.compile(r"(?<![\w/])@[A-Za-z0-9-]{2,}")


@dataclass
class Assessment:
    level: str
    reasons: list[str]
    reversible: bool
    preview: dict = field(default_factory=dict)
    source: str = "policy"

    def as_dict(self) -> dict:
        return {"level": self.level, "reasons": self.reasons, "reversible": self.reversible,
                "preview": self.preview, "source": self.source}


def _bump(level: str, to: str) -> str:
    return to if LEVEL_RANK[to] > LEVEL_RANK[level] else level


def _target(board: dict, number: Any) -> dict:
    item = W.find(board, int(number)) if number else None
    if not item:
        return {"number": number, "title": f"#{number}", "labels": [], "comments": 0, "is_pr": False}
    return item


def assess(tool: str, args: dict, board: dict) -> Assessment:
    args = args or {}
    level, reasons, reversible, preview = "low", [], True, {}
    item = _target(board, args.get("number")) if args.get("number") else None
    head = {"number": item["number"], "title": item["title"], "is_pr": item.get("is_pr", False),
            "author": item.get("author"), "url": item.get("url", "")} if item else {}

    if tool in ("add_labels", "remove_labels"):
        labels = list(args.get("labels") or [])
        preview = {"kind": "labels", **head, "before": list(item["labels"]) if item else [],
                   "after": sorted(set(item["labels"]) | set(labels)) if tool == "add_labels" and item
                   else [l for l in (item["labels"] if item else []) if l not in set(labels)]}
        known = {l["name"] for l in board.get("labels", [])}
        new = [l for l in labels if l not in known]
        if new:
            level = "medium"
            reasons.append(f"Creates new label{'s' if len(new) > 1 else ''}: {', '.join(new)}")
        else:
            reasons.append("Labels can be changed back any time")

    elif tool == "comment":
        body = args.get("body") or ""
        mentions = MENTION_RE.findall(body)
        preview = {"kind": "comment", **head, "body": body}
        level, reversible = "medium", False
        reasons.append("Posts publicly on the thread")
        if len(mentions) >= 3:
            level = "high"
            reasons.append(f"Mentions {len(mentions)} people")
        if re.search(r"\b(spam|banned|lawyer|legal|refund|password|api key|secret)\b", body, re.I):
            level = "high"
            reasons.append("Sensitive wording")
        if item and item.get("author_association") in ("FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER"):
            reasons.append("First-time contributor — tone matters")

    elif tool == "close_issue":
        level = "medium"
        preview = {"kind": "close", **head, "reason": args.get("reason"), "note": args.get("note"),
                   "comments": item.get("comments", 0) if item else 0,
                   "last_activity_days": days_ago(item.get("updated_at")) if item else None,
                   "labels": item.get("labels", []) if item else []}
        reasons.append("Closes a public thread (can be reopened)")
        if item:
            if item.get("is_pr"):
                level = "high"
                reasons.append("Closes someone's pull request")
            if (item.get("comments") or 0) >= 5:
                level = "high"
                reasons.append(f"Active thread: {item['comments']} comments")
            if item.get("assignees"):
                level = "high"
                reasons.append(f"Assigned to {', '.join(item['assignees'])}")
            recent = days_ago(item.get("updated_at"))
            if recent is not None and recent <= 7:
                level = _bump(level, "medium")
                reasons.append(f"Updated {recent} day{'s' if recent != 1 else ''} ago")
        if args.get("note"):
            reversible = False
            reasons.append("Posts a closing note")

    elif tool == "reopen_issue":
        preview = {"kind": "reopen", **head}
        reasons.append("Reopens a closed thread")

    elif tool == "retitle":
        preview = {"kind": "retitle", **head, "new_title": args.get("title")}
        reasons.append("Titles can be edited back")

    elif tool == "assign":
        preview = {"kind": "assign", **head, "assignees": list(args.get("assignees") or [])}
        reasons.append("Notifies the assignee")

    elif tool == "request_reviewers":
        preview = {"kind": "review", **head, "reviewers": list(args.get("reviewers") or [])}
        reasons.append("Notifies the reviewer")

    elif tool == "create_issue":
        level = "medium"
        preview = {"kind": "new_issue", "title": args.get("title"), "body": args.get("body", ""),
                   "labels": list(args.get("labels") or [])}
        reasons.append("Opens a new public issue")

    elif tool == "merge_pull":
        level, reversible = "high", False
        preview = {"kind": "merge", **head, "method": args.get("method", "squash")}
        reasons.append("Merging can't be undone")

    elif tool not in READ_TOOLS:
        level, reversible = "medium", False
        reasons.append("External tool — effects unknown")
        preview = {"kind": "external", "args": args}

    if board.get("mode") == "live" and board.get("can_write"):
        reasons.append("This happens on the real repository")
    return Assessment(level=level, reasons=reasons, reversible=reversible, preview=preview)


def should_ask(a: Assessment, autonomy: str) -> bool:
    if autonomy == "autopilot":
        return a.level == "high" or not a.reversible
    if autonomy == "balanced":
        return a.level != "low"
    return True  # careful / observe


_ASSESSMENTS: "OrderedDict[str, dict]" = OrderedDict()


def assessment_for(tool_call_id: Optional[str]) -> Optional[dict]:
    return _ASSESSMENTS.get(tool_call_id or "")


def _remember(tool_call_id: Optional[str], data: dict) -> None:
    if not tool_call_id:
        return
    _ASSESSMENTS[tool_call_id] = data
    while len(_ASSESSMENTS) > 512:
        _ASSESSMENTS.popitem(last=False)


def _when(tool: str):
    second = approval_policy.get_risk_classifier()
    use_jev = second.name != "patterns"

    def when(request: Any) -> bool:
        call = getattr(request, "tool_call", None) or {}
        state = getattr(request, "state", None) or {}
        board = state.get("world") or {}
        autonomy = state.get("autonomy") or "careful"
        a = assess(tool, call.get("args") or {}, board)
        ask = should_ask(a, autonomy)
        data = a.as_dict()
        data["autonomy"] = autonomy
        data["observe"] = autonomy == "observe" or not board.get("can_write", True)
        if use_jev:
            v = second.classify(tool, call.get("args"))
            data["jev"] = v.as_dict()
            if v.risky and not ask:
                ask = True
                data["reasons"].append(f"Jev flagged it ({v.reason})")
        data["asked"] = ask
        _remember(call.get("id"), data)
        return ask

    return when


def build_interrupt_on(extra_tools: Optional[list[str]] = None) -> dict:
    cfg = {t: InterruptOnConfig(allowed_decisions=ALLOWED, when=_when(t)) for t in ACTING_TOOLS + list(extra_tools or [])}
    cfg.update({t: False for t in READ_TOOLS})
    return cfg


def describe() -> dict:
    return {"acting_tools": ACTING_TOOLS, "autonomy_levels": AUTONOMY_LEVELS,
            "second_opinion": approval_policy.get_risk_classifier().name}
