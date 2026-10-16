"""Repo Steward tools: read the board and the repo, then act on GitHub.

Reading tools run freely. Acting tools are gated by :mod:`steward.policy`;
when approved they execute on GitHub (live repo with a write token), record a
*proposal* (observe mode, or no write token), or simply update the board
(sample repo). Either way they return a ``Command`` with the operation so the
world reducer keeps the board — and the UI — in sync.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command, interrupt

from steward import world as W
from steward.github import GitHubError, backend_for, days_ago, scrub, write_token


def _emit(message: str, **extra) -> None:
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()({"type": "progress", "message": message, **extra})
    except Exception:  # pragma: no cover
        pass


def _board(runtime: ToolRuntime) -> dict:
    return (runtime.state or {}).get("world") or {}


def _slim(i: dict, body_chars: int = 300) -> dict:
    return {"number": i["number"], "title": i["title"], "author": i["author"], "association": i.get("author_association"),
            "labels": i["labels"], "assignees": i.get("assignees", []), "comments": i.get("comments", 0),
            "age_days": days_ago(i.get("created_at")), "inactive_days": days_ago(i.get("updated_at")),
            "draft": i.get("draft", False), "body": (i.get("body") or "")[:body_chars]}


def _act(runtime: ToolRuntime, ops: list[dict], result: str, extra: Optional[dict] = None) -> Command:
    """Execute (live + token), propose (observe / no token) or just apply (fixture)."""
    board = _board(runtime)
    autonomy = (runtime.state or {}).get("autonomy") or "careful"
    live = board.get("mode") == "live"
    observe = autonomy == "observe" or (live and not write_token())
    if live and not observe:
        backend = backend_for(board)
        for op in ops:
            try:
                url = backend.execute(op)
            except GitHubError as exc:
                return Command(update={"messages": [ToolMessage(f"GitHub refused: {scrub(str(exc))}",
                                                                tool_call_id=runtime.tool_call_id, status="error")]})
            if url:
                op["url"] = url
    elif observe:
        for op in ops:
            op["proposed"] = True
        result = f"Proposed (not executed{'' if autonomy == 'observe' else ' — no GitHub token with write access'}): {result}"
    update = {"world": {"ops": ops}, "messages": [ToolMessage(result, tool_call_id=runtime.tool_call_id)]}
    if extra:
        update.update(extra)
    return Command(update=update)


# --- Reading -----------------------------------------------------------------
@tool
def list_issues(runtime: ToolRuntime, only: str = "all", limit: int = 40) -> str:
    """Open issues on the board. ``only``: all | unlabeled | stale | bugs | questions | enhancements."""
    _emit("📋 Listing open issues…")
    items = W.open_items(_board(runtime))
    if only == "unlabeled":
        items = [i for i in items if not i["labels"]]
    elif only == "stale":
        items = [i for i in items if (days_ago(i.get("updated_at")) or 0) >= 60]
    elif only in ("bugs", "questions", "enhancements"):
        want = {"bugs": "bug", "questions": "question", "enhancements": "enhancement"}[only]
        items = [i for i in items if want in i["labels"]]
    _emit(f"📋 {len(items)} issue{'s' if len(items) != 1 else ''}")
    return json.dumps([_slim(i) for i in items[:limit]])


@tool
def list_pulls(runtime: ToolRuntime) -> str:
    """Open pull requests on the board."""
    _emit("🔀 Listing open pull requests…")
    items = W.open_items(_board(runtime), prs=True)
    return json.dumps([_slim(i) for i in items])


@tool
def read_issue(runtime: ToolRuntime, number: int) -> str:
    """Full body and comment thread of an issue or pull request."""
    _emit(f"📖 Reading #{number}…")
    board = _board(runtime)
    item = W.find(board, number)
    if not item:
        return f"#{number} is not on the board (only open items were loaded)."
    thread = item.get("thread") or []
    if board.get("mode") == "live" and item.get("comments") and not thread:
        try:
            thread = backend_for(board).comments(number)
        except GitHubError as exc:
            thread = [{"author": "system", "body": f"(couldn't load comments: {exc})"}]
    return json.dumps({**_slim(item, body_chars=4000), "thread": thread, "url": item.get("url")})


@tool
def find_similar(runtime: ToolRuntime, number: int) -> str:
    """Open issues that look like duplicates of ``number`` (by title and body overlap), most similar first."""
    _emit(f"🔎 Looking for duplicates of #{number}…")
    board = _board(runtime)
    item = W.find(board, number)
    if not item:
        return "[]"

    from steward.pilot import similarity

    hits = []
    for other in W.open_items(board):
        if other["number"] == number:
            continue
        score = similarity(item, other)
        if score >= 0.3:
            hits.append({"number": other["number"], "title": other["title"], "similarity": score,
                         "older": other["number"] < number})
    hits.sort(key=lambda h: -h["similarity"])
    return json.dumps(hits[:5])


@tool
def read_file(runtime: ToolRuntime, path: str = "README.md") -> str:
    """Read a file from the default branch (a directory path lists its entries)."""
    _emit(f"📄 Reading {path}…")
    board = _board(runtime)
    if path in ("README.md", "README") and board.get("readme"):
        return board["readme"]
    try:
        return backend_for(board).file(path)
    except GitHubError as exc:
        return f"Couldn't read {path}: {exc}"


@tool
def read_pull(runtime: ToolRuntime, number: int) -> str:
    """Files changed, additions/deletions, mergeability and patch excerpts for a pull request."""
    _emit(f"🧩 Reading the diff of #{number}…")
    try:
        return json.dumps(backend_for(_board(runtime)).pull_detail(number))
    except GitHubError as exc:
        return f"Couldn't read PR #{number}: {exc}"


@tool
def release_context(runtime: ToolRuntime) -> str:
    """The last tag and the commits merged since it."""
    _emit("🏷️ Reading commits since the last release…")
    try:
        return json.dumps(backend_for(_board(runtime)).release_context())
    except GitHubError as exc:
        return f"Couldn't read release context: {exc}"


@tool
async def remember(runtime: ToolRuntime, note: str) -> str:
    """Save a lasting fact about this repository's conventions for future missions."""
    from memory import save_user_memory

    await save_user_memory(runtime.store, (runtime.state or {}).get("user_id"), note)
    _emit(f"Remembered for next time: {note}", kind="memory")
    return f"Remembered: {note}"


@tool
def ask_user(question: str, options: Optional[list[str]] = None) -> str:
    """Ask the maintainer a question you can't answer from the repository (pauses the mission)."""
    answer = interrupt({"type": "question", "question": question, "options": options or []})
    return f"The user answered: {answer}"


# --- Acting (gated by the policy) -------------------------------------------
@tool
def add_labels(runtime: ToolRuntime, number: int, labels: list[str]) -> Command:
    """Add labels to an issue or pull request (unknown labels are created)."""
    board = _board(runtime)
    known = {l["name"] for l in board.get("labels", [])}
    ops: list[dict] = []
    for label in labels:
        if label not in known:
            ops.append({"op": "create_label", "name": label})
    ops.append({"op": "add_labels", "number": number, "labels": list(labels)})
    _emit(f"🏷️ Labelling #{number}: {', '.join(labels)}")
    return _act(runtime, ops, f"Labelled #{number}: {', '.join(labels)}.")


@tool
def remove_labels(runtime: ToolRuntime, number: int, labels: list[str]) -> Command:
    """Remove labels from an issue or pull request."""
    _emit(f"🏷️ Removing {', '.join(labels)} from #{number}")
    return _act(runtime, [{"op": "remove_labels", "number": number, "labels": list(labels)}],
                f"Removed {', '.join(labels)} from #{number}.")


@tool
def comment(runtime: ToolRuntime, number: int, body: str) -> Command:
    """Post a comment on an issue or pull request (Markdown)."""
    _emit(f"💬 Commenting on #{number}")
    return _act(runtime, [{"op": "comment", "number": number, "body": body}], f"Commented on #{number}.")


@tool
def close_issue(runtime: ToolRuntime, number: int, reason: str = "completed", note: Optional[str] = None) -> Command:
    """Close an issue or PR. ``reason``: completed | not_planned | duplicate. ``note`` posts a closing comment first."""
    ops: list[dict] = []
    if note:
        ops.append({"op": "comment", "number": number, "body": note})
    ops.append({"op": "close", "number": number, "reason": "not_planned" if reason == "duplicate" else reason})
    _emit(f"✅ Closing #{number} ({reason})")
    return _act(runtime, ops, f"Closed #{number} as {reason}.")


@tool
def reopen_issue(runtime: ToolRuntime, number: int) -> Command:
    """Reopen a closed issue or PR."""
    return _act(runtime, [{"op": "reopen", "number": number}], f"Reopened #{number}.")


@tool
def retitle(runtime: ToolRuntime, number: int, title: str) -> Command:
    """Give an issue or PR a clearer title."""
    _emit(f"✏️ Retitling #{number}")
    return _act(runtime, [{"op": "retitle", "number": number, "title": title}], f"Retitled #{number} to “{title}”.")


@tool
def create_issue(runtime: ToolRuntime, title: str, body: str = "", labels: Optional[list[str]] = None) -> Command:
    """Open a new issue."""
    _emit(f"🆕 Opening issue “{title}”")
    return _act(runtime, [{"op": "create_issue", "title": title, "body": body, "labels": list(labels or [])}],
                f"Opened a new issue “{title}”.")


@tool
def assign(runtime: ToolRuntime, number: int, assignees: list[str]) -> Command:
    """Assign people to an issue or PR."""
    return _act(runtime, [{"op": "assign", "number": number, "assignees": list(assignees)}],
                f"Assigned #{number} to {', '.join(assignees)}.")


@tool
def request_reviewers(runtime: ToolRuntime, number: int, reviewers: list[str]) -> Command:
    """Request a review on a pull request."""
    _emit(f"👀 Requesting review on #{number}")
    return _act(runtime, [{"op": "request_review", "number": number, "reviewers": list(reviewers)}],
                f"Requested review on #{number} from {', '.join(reviewers)}.")


@tool
def merge_pull(runtime: ToolRuntime, number: int, method: str = "squash") -> Command:
    """Merge a pull request. ``method``: squash | merge | rebase. Irreversible."""
    _emit(f"🔀 Merging #{number}")
    return _act(runtime, [{"op": "merge", "number": number, "method": method}], f"Merged #{number} ({method}).")


@tool
def finish_mission(runtime: ToolRuntime, summary: str, done: list[str], open_items: Optional[list[str]] = None) -> Command:
    """Call once at the end: a short summary, what was done (or proposed), and what still needs a human."""
    board = _board(runtime)
    proposals = [l for l in board.get("ledger", []) if l.get("proposed")]
    report = {"summary": summary, "done": done, "open_items": open_items or [], "proposals": len(proposals)}
    return _act(runtime, [], "Mission report recorded.", {"report": report})


READ_TOOLS = [list_issues, list_pulls, read_issue, find_similar, read_file, read_pull, release_context, remember, ask_user]
ACT_TOOLS = [add_labels, remove_labels, comment, close_issue, reopen_issue, retitle, create_issue, assign,
             request_reviewers, merge_pull]
ALL_TOOLS = READ_TOOLS + ACT_TOOLS + [finish_mission]
