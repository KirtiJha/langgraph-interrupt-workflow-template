"""The repo board in graph state, and the reducer that applies operations to it.

The board is a snapshot of the repository (open issues, pull requests, labels,
README) loaded at mission start. Acting tools return *operations*; on a live
repo they have already been executed on GitHub, on the sample repo they are
simply applied here. Either way the reducer updates the board and appends to
``ledger`` so the UI shows exactly what happened (or, in observe mode, what
was proposed).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find(board: dict, number: int) -> Optional[dict]:
    for item in board.get("issues", []) + board.get("pulls", []):
        if item["number"] == number:
            return item
    return None


def _apply(board: dict, op: dict) -> Optional[str]:
    kind = op.get("op")
    n = op.get("number")
    item = find(board, n) if n else None
    ref = f"#{n}"
    proposed = op.get("proposed")
    if kind == "create_label":
        if not any(l["name"] == op["name"] for l in board.get("labels", [])):
            board.setdefault("labels", []).append({"name": op["name"], "color": "ededed", "description": ""})
        return None
    if kind == "add_labels":
        if item:
            item["labels"] = sorted(set(item["labels"]) | set(op["labels"]))
            item["updated_at"] = _now()
        return f"Labelled {ref} {', '.join(op['labels'])}"
    if kind == "remove_labels":
        if item:
            item["labels"] = [l for l in item["labels"] if l not in set(op["labels"])]
        return f"Removed {', '.join(op['labels'])} from {ref}"
    if kind == "comment":
        if item:
            item["comments"] = (item.get("comments") or 0) + 1
            item.setdefault("thread", []).append({"author": "repo-steward", "body": op["body"], "created_at": _now(),
                                                  "proposed": bool(proposed)})
            item["updated_at"] = _now()
        return f"Commented on {ref}"
    if kind == "close":
        if item:
            item["state"] = "closed"
            item["state_reason"] = op.get("reason")
            item["updated_at"] = _now()
        return f"Closed {ref}" + (f" ({op['reason'].replace('_', ' ')})" if op.get("reason") else "")
    if kind == "reopen":
        if item:
            item["state"] = "open"
        return f"Reopened {ref}"
    if kind == "retitle":
        if item:
            item["title"] = op["title"]
        return f"Retitled {ref}"
    if kind == "assign":
        if item:
            item["assignees"] = sorted(set(item.get("assignees", [])) | set(op["assignees"]))
        return f"Assigned {ref} to {', '.join(op['assignees'])}"
    if kind == "request_review":
        if item:
            item["reviewers"] = sorted(set(item.get("reviewers", [])) | set(op["reviewers"]))
        return f"Requested review on {ref} from {', '.join(op['reviewers'])}"
    if kind == "create_issue":
        number = op.get("number") or (max([i["number"] for i in board["issues"] + board["pulls"]] + [0]) + 1)
        op["number"] = number
        board["issues"].insert(0, {
            "number": number, "title": op["title"], "body": op.get("body", ""), "state": "open", "author": "repo-steward",
            "author_association": "MEMBER", "labels": sorted(op.get("labels", [])), "assignees": [], "comments": 0,
            "created_at": _now(), "updated_at": _now(), "is_pr": False, "draft": False, "url": "", "milestone": None,
            "thread": [], "by_agent": True,
        })
        return f"Opened #{number} “{op['title']}”"
    if kind == "merge":
        if item:
            item["state"] = "merged"
            item["updated_at"] = _now()
        return f"Merged {ref}"
    return None


def world_reducer(current: Optional[dict], update: Optional[dict]) -> dict:
    """``{"reset": board}`` replaces; ``{"ops": [...]}`` applies in order."""
    if not update:
        return current or {}
    if "reset" in update:
        return copy.deepcopy(update["reset"])
    board = copy.deepcopy(current or {"issues": [], "pulls": [], "labels": [], "ledger": [], "repo": {}})
    board.setdefault("ledger", [])
    for op in update.get("ops") or []:
        summary = _apply(board, op)
        if summary:
            board["ledger"].append({
                "seq": len(board["ledger"]) + 1, "op": op.get("op"), "number": op.get("number"),
                "summary": summary, "proposed": bool(op.get("proposed")), "url": op.get("url", ""), "at": _now(),
            })
    return board


def open_items(board: dict, prs: bool = False) -> list[dict]:
    return [i for i in board.get("pulls" if prs else "issues", []) if i.get("state") == "open"]
