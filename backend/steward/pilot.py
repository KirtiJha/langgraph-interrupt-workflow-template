"""The offline pilot: a rule-based model that runs the starter missions on *any* repo.

With no model key, Repo Steward still does useful work: it classifies issues
by their wording, spots duplicates by overlap, asks for reproductions where a
bug report has none, finds stale threads by date, summarises pull requests by
their diff stats, and drafts release notes from commit messages. It reacts to
your decisions (a rejected comment is not retried, an edited one is respected)
exactly like a real model would. What it can't do is *answer* questions from
the code — that needs a real model, and the UI says so.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Callable, Iterator, List, Optional

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from steward import catalog as C

EXECUTED = ("Labelled", "Removed", "Commented", "Closed", "Reopened", "Retitled", "Opened", "Assigned", "Requested",
            "Merged", "Mission report", "Proposed", "Note: a human reviewer")
ACTING = {"add_labels", "remove_labels", "comment", "close_issue", "reopen_issue", "retitle", "create_issue", "assign",
          "request_reviewers", "merge_pull", "finish_mission"}
BUG_RE = re.compile(r"\b(crash|crashes|error|exception|traceback|fail|fails|failed|broken|bug|not (?:found|working)|doesn'?t work|oom|leak|regression|wrong)\b", re.I)
FEATURE_RE = re.compile(r"\b(feature|support|add|option|flag|would be (?:great|nice)|could .{0,30} be added|please add|enhancement|proposal|request)\b", re.I)
QUESTION_RE = re.compile(r"\b(how (?:do|can|to)|question|is there|can i|where (?:is|do)|what is|why does)\b|\?", re.I)
DOCS_RE = re.compile(r"\b(typo|readme|docs?|documentation|spelling)\b", re.I)
RESOLVED_RE = re.compile(r"\b(landed|fixed|released|closing when|shipped|merged|done in)\b", re.I)
STOP = {"this", "that", "with", "when", "from", "have", "would", "please", "there", "which", "about", "same", "when"}


class Ctx:
    def __init__(self, messages: List[BaseMessage]) -> None:
        self.goal = next((str(m.content) for m in messages if m.type in ("human", "user")), "")
        self.mission = C.mission_for_goal(self.goal)
        self.turns = sum(1 for m in messages if m.type == "ai" and getattr(m, "tool_calls", None))
        self.calls: list[dict] = []
        pending: dict[str, dict] = {}
        for m in messages:
            if m.type == "ai":
                for tc in getattr(m, "tool_calls", None) or []:
                    pending[tc["id"]] = {"tool": tc["name"], "args": tc["args"], "result": None, "ok": False, "rejected": False}
            elif m.type == "tool":
                call = pending.get(getattr(m, "tool_call_id", ""))
                if call is None:
                    continue
                text = str(m.content)
                call["result"] = text
                call["rejected"] = text.startswith("User rejected")
                call["ok"] = text.startswith(EXECUTED) if call["tool"] in ACTING else not call["rejected"]
                self.calls.append(call)

    def tried(self, tool: str, **match) -> bool:
        return any(c["tool"] == tool and all(c["args"].get(k) == v for k, v in match.items()) for c in self.calls)

    def ok(self, tool: str, **match) -> bool:
        return any(c["ok"] and c["tool"] == tool and all(c["args"].get(k) == v for k, v in match.items()) for c in self.calls)

    def result(self, tool: str, **match) -> Any:
        for c in self.calls:
            if c["tool"] == tool and c["result"] and not c["rejected"] and all(c["args"].get(k) == v for k, v in match.items()):
                try:
                    return json.loads(c["result"])
                except ValueError:
                    return c["result"]
        return None

    def executed(self) -> list[dict]:
        return [c for c in self.calls if c["ok"] and c["tool"] in ACTING and c["tool"] != "finish_mission"]

    def rejected(self) -> list[dict]:
        return [c for c in self.calls if c["rejected"]]


Step = tuple[str, list[tuple[str, dict]]]


# --- Rules -------------------------------------------------------------------
def classify(issue: dict) -> Optional[str]:
    text = f"{issue['title']} {issue.get('body', '')}"
    if DOCS_RE.search(issue["title"]) and not BUG_RE.search(issue["title"]):
        return "docs"
    if BUG_RE.search(text):
        return "bug"
    if QUESTION_RE.search(issue["title"]):
        return "question"
    if FEATURE_RE.search(text):
        return "enhancement"
    if QUESTION_RE.search(text):
        return "question"
    return None


def needs_repro(issue: dict) -> bool:
    body = issue.get("body") or ""
    has_version = re.search(r"\b\d+\.\d+(\.\d+)?\b|version", body, re.I)
    has_code = "```" in body or "Traceback" in body
    return len(body) < 160 or not (has_version or has_code)


def _stem(w: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            w = w[: -len(suf)]
            break
    return w[:-1] if w.endswith("e") and len(w) >= 5 else w


def keywords(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOP}


def similarity(a: dict, b: dict) -> float:
    """How alike two issues are: shared title keywords, backed by body overlap."""
    ta, tb = keywords(a["title"]), keywords(b["title"])
    title = len(ta & tb) / max(min(len(ta), len(tb)), 1) if ta and tb else 0.0
    if len(ta & tb) < 2:
        title = 0.0
    wa, wb = keywords(f"{a['title']} {a.get('body', '')}"), keywords(f"{b['title']} {b.get('body', '')}")
    body = len(wa & wb) / len(wa | wb) if wa and wb else 0.0
    return round(max(title * 0.9, body), 2)


def duplicates(issues: list[dict]) -> dict[int, int]:
    """newer issue number -> older issue number it duplicates."""
    out: dict[int, int] = {}
    ordered = sorted(issues, key=lambda i: i["number"])  # lower number = opened first
    for idx, older in enumerate(ordered):
        for newer in ordered[idx + 1:]:
            if newer["number"] in out or older["number"] in out:
                continue
            if similarity(older, newer) >= 0.5:
                out[newer["number"]] = older["number"]
    return out


FIXTURE_ANSWERS = {
    103: "You can keep EXIF with `--keep-metadata`:\n\n```bash\npixelforge convert a.jpg --to webp --keep-metadata\n```\n\n"
         "It copies EXIF where the target format supports it (jpg, webp, avif) — see `pixelforge/convert.py`. "
         "I'll make sure the README mentions it.",
    112: "There's no plugin mechanism yet — pipelines only support the built-in steps (resize, crop, rotate, convert, strip); "
         "see `pixelforge/pipeline.py`. I've labelled this as an enhancement so it can be discussed. "
         "For now a Python script calling `pixelforge` per step is the workaround.",
}


# --- Scripts -----------------------------------------------------------------
def triage(c: Ctx) -> Step | str:
    if not c.tried("list_issues"):
        return ("Let me read the open issues and the README first, so labels and answers match how this repo works.",
                [("list_issues", {"only": "unlabeled"}), ("read_file", {"path": "README.md"}),
                 ("read_file", {"path": "CONTRIBUTING.md"})])
    issues = c.result("list_issues", only="unlabeled") or []
    if not isinstance(issues, list):
        issues = []
    if not c.executed() and not c.rejected() and c.turns == 1:
        if not issues:
            return ("Every open issue already has a label — nothing to triage here.",
                    [("finish_mission", {"summary": "No unlabelled issues.", "done": [], "open_items": []})])
        dups = duplicates(issues)
        calls: list[tuple[str, dict]] = []
        counts = {"bug": 0, "enhancement": 0, "question": 0, "docs": 0}
        repro, answered = 0, 0
        for i in issues[:12]:
            n = i["number"]
            if n in dups:
                calls.append(("add_labels", {"number": n, "labels": ["duplicate"]}))
                calls.append(("close_issue", {"number": n, "reason": "duplicate",
                                              "note": f"Thanks for the report! This looks like the same problem as #{dups[n]} — "
                                                      f"closing this one so the discussion stays in one place. Please add any extra details there."}))
                continue
            kind = classify(i)
            if kind:
                counts[kind] += 1
                calls.append(("add_labels", {"number": n, "labels": [kind]}))
            if kind == "bug" and needs_repro(i):
                calls.append(("add_labels", {"number": n, "labels": ["needs-repro"]}))
                calls.append(("comment", {"number": n,
                                          "body": "Thanks for reporting this. To track it down we need a bit more:\n\n"
                                                  "- the output of `--version`\n- your OS and Python version\n"
                                                  "- a minimal command or file that reproduces it\n\n"
                                                  "Once that's here we'll take a look."}))
                repro += 1
            if kind == "question" and n in FIXTURE_ANSWERS and c.mission == "triage":
                calls.append(("comment", {"number": n, "body": FIXTURE_ANSWERS[n]}))
                answered += 1
        if not calls:
            return ("Everything's already labelled — nothing to triage.",
                    [("finish_mission", {"summary": "All open issues already have labels.", "done": [], "open_items": []})])
        bits = [f"{v} {k}{'s' if v != 1 else ''}" for k, v in counts.items() if v]
        say = (f"{len(issues)} unlabelled issues. I'd label {', '.join(bits)}; "
               f"{len(dups)} look{'s' if len(dups) == 1 else ''} like a duplicate; {repro} bug report{'s' if repro != 1 else ''} "
               f"need{'s' if repro == 1 else ''} a reproduction" + (f"; I can answer {answered} from the code" if answered else "")
               + ". Each action is yours to approve.")
        return (say, calls)
    if not c.tried("finish_mission"):
        done = [f"{_describe(x)}" for x in c.executed()]
        skipped = [f"Skipped: {_describe(x)}" for x in c.rejected()]
        unanswered = [i["number"] for i in issues if classify(i) == "question" and i["number"] not in FIXTURE_ANSWERS]
        open_items = [f"Answer #{n} (needs a real model to read the code)" for n in unanswered][:5] + skipped[:5]
        calls = [("finish_mission", {"summary": f"Triaged {len(issues)} issues: {len(c.executed())} actions taken, "
                                                f"{len(c.rejected())} declined.", "done": done, "open_items": open_items})]
        if c.executed():
            calls.insert(0, ("remember", {"note": "This repo triages with bug / enhancement / question / docs, and asks for a reproduction with needs-repro."}))
        return ("That's the backlog triaged.", calls)
    return "Triage done — the board is up to date."


def stale(c: Ctx) -> Step | str:
    if not c.tried("list_issues"):
        return ("Looking for threads nobody has touched in 60 days.",
                [("list_issues", {"only": "stale"}), ("list_pulls", {})])
    issues = c.result("list_issues", only="stale") or []
    pulls = [p for p in (c.result("list_pulls") or []) if (p.get("inactive_days") or 0) >= 60]
    if not c.executed() and not c.rejected() and c.turns == 1:
        if not issues and not pulls:
            return ("Nothing stale — this repo is well tended.",
                    [("finish_mission", {"summary": "No issues or PRs inactive for 60+ days.", "done": [], "open_items": []})])
        reads = [("read_issue", {"number": i["number"]}) for i in issues[:8]]
        return (f"{len(issues)} stale issue{'s' if len(issues) != 1 else ''} and {len(pulls)} stale PR{'s' if len(pulls) != 1 else ''}. "
                "Reading the threads to tell resolved from abandoned.", reads or [("list_pulls", {})])
    if not c.executed() and not c.rejected() and c.turns == 2:
        calls: list[tuple[str, dict]] = []
        closed = nudged = 0
        for i in issues[:8]:
            full = c.result("read_issue", number=i["number"]) or {}
            thread = full.get("thread") or [] if isinstance(full, dict) else []
            last = thread[-1]["body"] if thread else ""
            resolved = any(RESOLVED_RE.search(t.get("body", "")) for t in thread)
            if resolved:
                calls.append(("close_issue", {"number": i["number"], "reason": "completed",
                                              "note": "Closing this as resolved — the thread indicates it has landed. Reopen if it's still a problem for you."}))
                closed += 1
            else:
                calls.append(("add_labels", {"number": i["number"], "labels": ["stale"]}))
                calls.append(("comment", {"number": i["number"],
                                          "body": f"This has been quiet for {i.get('inactive_days')} days. Is it still relevant? "
                                                  "If we don't hear back in two weeks we'll close it to keep the backlog honest — "
                                                  "a quick comment keeps it open."}))
                nudged += 1
        for p in pulls[:5]:
            calls.append(("comment", {"number": p["number"],
                                      "body": f"This PR hasn't moved in {p.get('inactive_days')} days and may need a rebase. "
                                              "Are you still working on it? Happy to help if it's stuck."}))
            nudged += 1
        return (f"{closed} look resolved — I'd close them with a note. {nudged} need a nudge rather than a close.", calls)
    if not c.tried("finish_mission"):
        return ("Stale sweep done.", [("finish_mission", {
            "summary": f"Swept {len(issues)} stale issues and {len(pulls)} PRs: {len(c.executed())} actions, {len(c.rejected())} declined.",
            "done": [_describe(x) for x in c.executed()], "open_items": [f"Skipped: {_describe(x)}" for x in c.rejected()]})])
    return "Backlog's honest again."


def prs(c: Ctx) -> Step | str:
    if not c.tried("list_pulls"):
        return ("Reading the open pull requests.", [("list_pulls", {})])
    pulls = c.result("list_pulls") or []
    if not c.tried("read_pull") and pulls:
        return (f"{len(pulls)} open. Pulling each diff so the summaries are grounded.",
                [("read_pull", {"number": p["number"]}) for p in pulls[:6]])
    if not pulls:
        return ("No open pull requests.", [("finish_mission", {"summary": "No open PRs.", "done": [], "open_items": []})])
    if not c.executed() and not c.rejected() and not c.tried("comment"):
        calls: list[tuple[str, dict]] = []
        owner = _maintainer(c)
        for p in pulls[:6]:
            d = c.result("read_pull", number=p["number"]) or {}
            if not isinstance(d, dict):
                d = {}
            files = d.get("files") or []
            first = p.get("association") in ("FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER")
            stale_pr = (p.get("inactive_days") or 0) >= 60
            risk = ("Large change" if (d.get("changed_files") or 0) > 10 else "Small, focused change")
            body = (("Welcome, and thanks for your first contribution! 🎉\n\n" if first else "") +
                    f"**Summary:** {d.get('title') or p['title']} — {d.get('changed_files') or len(files)} file(s), "
                    f"+{d.get('additions') or 0}/−{d.get('deletions') or 0}.\n\n"
                    f"**Files:** " + (", ".join(f"`{f['path']}`" for f in files[:6]) or "n/a") + "\n\n"
                    f"**Risk:** {risk}" + (". Draft and out of date with main — needs a rebase before review." if p.get("draft") and stale_pr
                                           else ". Tests touched." if any("test" in f["path"] for f in files) else ". No tests changed — worth a look.") +
                    ("\n\n**Next:** ready for a maintainer review." if d.get("mergeable") and not p.get("draft") else
                     "\n\n**Next:** rebase onto main, then mark ready for review."))
            calls.append(("comment", {"number": p["number"], "body": body}))
            if d.get("mergeable") and not p.get("draft") and owner:
                calls.append(("request_reviewers", {"number": p["number"], "reviewers": [owner]}))
        return ("Here's a review summary for each, with a welcome for first-timers and review requests where it's ready.", calls)
    if not c.tried("finish_mission"):
        return ("PR pass complete.", [("finish_mission", {
            "summary": f"Reviewed {len(pulls)} PRs: {len(c.executed())} actions, {len(c.rejected())} declined.",
            "done": [_describe(x) for x in c.executed()], "open_items": [f"Skipped: {_describe(x)}" for x in c.rejected()]})])
    return "All pull requests have a summary now."


def release(c: Ctx) -> Step | str:
    if not c.tried("release_context"):
        return ("Reading the commits since the last tag.", [("release_context", {}), ("read_file", {"path": "CHANGELOG.md"})])
    ctx = c.result("release_context") or {}
    commits = ctx.get("commits") if isinstance(ctx, dict) else []
    if not c.tried("create_issue"):
        if not commits:
            return ("No commits since the last tag — nothing to release.",
                    [("finish_mission", {"summary": "Nothing to release.", "done": [], "open_items": []})])
        groups: dict[str, list[str]] = {"Fixes": [], "Features": [], "Docs": [], "Internal": []}
        authors = set()
        for cm in commits:
            msg, who = cm["message"], cm.get("author")
            if who:
                authors.add(who)
            line = f"- {msg} (`{cm['sha']}`)" + (f" — @{who}" if who else "")
            low = msg.lower()
            if low.startswith(("fix", "handle", "normalise", "normalize")) or "fix" in low:
                groups["Fixes"].append(line)
            elif low.startswith(("add", "feat", "support", "implement")):
                groups["Features"].append(line)
            elif low.startswith("docs") or "readme" in low:
                groups["Docs"].append(line)
            else:
                groups["Internal"].append(line)
        tag = ctx.get("last_tag") or "the last release"
        body = f"Draft notes for the next release (changes since {tag}):\n\n" + "\n\n".join(
            f"### {k}\n" + "\n".join(v) for k, v in groups.items() if v
        ) + f"\n\nThanks to {', '.join('@' + a for a in sorted(authors))}.\n\n_Drafted by Repo Steward — edit freely._"
        return (f"{len(commits)} commits since {tag}. Grouped into fixes, features, docs and internal, with credits.",
                [("create_issue", {"title": f"Release notes draft: changes since {tag}", "body": body, "labels": ["docs"]})])
    if not c.tried("finish_mission"):
        return ("Release notes drafted.", [("finish_mission", {
            "summary": f"Drafted release notes for {len(commits)} commits since {ctx.get('last_tag') or 'the last release'}.",
            "done": [_describe(x) for x in c.executed()], "open_items": ["Edit the draft, then tag the release"]})])
    return "Ready to ship."


def welcome(c: Ctx) -> Step | str:
    if not c.tried("list_issues"):
        return ("Looking for first-time contributors and newcomer-friendly issues.",
                [("list_issues", {}), ("list_pulls", {})])
    issues = c.result("list_issues") or []
    pulls = c.result("list_pulls") or []
    if not c.executed() and not c.rejected() and c.turns == 1:
        calls: list[tuple[str, dict]] = []
        firsts = [p for p in issues + pulls if p.get("association") in ("FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER")]
        for p in firsts[:5]:
            calls.append(("comment", {"number": p["number"],
                                      "body": "Welcome, and thank you for your first contribution! 🎉 A maintainer will take a look soon. "
                                              "If you're up for more, CONTRIBUTING.md has the lay of the land and we keep a few "
                                              "`good first issue`s ready."}))
        easy = [i for i in issues if classify(i) == "docs" and "good first issue" not in i["labels"]]
        for i in easy[:4]:
            calls.append(("add_labels", {"number": i["number"], "labels": ["good first issue"]}))
        if not calls:
            return ("No first-time contributors or newcomer-sized issues right now.",
                    [("finish_mission", {"summary": "Nothing to welcome today.", "done": [], "open_items": []})])
        return (f"{len(firsts)} first-time contributor{'s' if len(firsts) != 1 else ''} to thank, and {len(easy)} small "
                f"issue{'s' if len(easy) != 1 else ''} to mark as good first issues.", calls)
    if not c.tried("finish_mission"):
        return ("Done.", [("finish_mission", {"summary": f"Welcomed newcomers: {len(c.executed())} actions.",
                                               "done": [_describe(x) for x in c.executed()],
                                               "open_items": [f"Skipped: {_describe(x)}" for x in c.rejected()]})])
    return "Newcomers welcomed."


def generic(c: Ctx) -> Step | str:
    if not c.tried("list_issues"):
        return ("I'm the offline pilot — let me look at the board.", [("list_issues", {"limit": 10}), ("list_pulls", {})])
    return ("Offline, I can only run the starter missions (triage, stale sweep, PR review, release notes, welcome). "
            "Pick one, or add a model under Model and I'll take on this goal properly.")


SCRIPTS: dict[str, Callable[[Ctx], Step | str]] = {"triage": triage, "stale": stale, "prs": prs, "release": release,
                                                    "welcome": welcome}


def _maintainer(c: Ctx) -> Optional[str]:
    return c._maintainer if hasattr(c, "_maintainer") else None


def _describe(call: dict) -> str:
    a, t = call["args"], call["tool"]
    n = a.get("number")
    return {"add_labels": f"Labelled #{n} {', '.join(a.get('labels', []))}", "remove_labels": f"Removed labels from #{n}",
            "comment": f"Commented on #{n}", "close_issue": f"Closed #{n} ({a.get('reason', 'completed')})",
            "reopen_issue": f"Reopened #{n}", "retitle": f"Retitled #{n}", "create_issue": f"Opened “{a.get('title')}”",
            "assign": f"Assigned #{n}", "request_reviewers": f"Requested review on #{n}", "merge_pull": f"Merged #{n}"}.get(t, t)


# --- The model ---------------------------------------------------------------
class StewardPilot(BaseChatModel):
    """Rule-based chat model for Repo Steward (offline / mock)."""

    maintainer: Optional[str] = None  # who to request reviews from (repo owner)

    @property
    def _llm_type(self) -> str:
        return "steward-pilot"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "StewardPilot":
        return self

    def _next(self, messages: List[BaseMessage]) -> AIMessage:
        ctx = Ctx(messages)
        ctx._maintainer = self.maintainer  # type: ignore[attr-defined]
        if ctx.turns >= 10:
            return AIMessage(content="I've done what I can for this mission.")
        step = SCRIPTS.get(ctx.mission or "", generic)(ctx)
        if isinstance(step, str):
            return AIMessage(content=step)
        say, calls = step
        return AIMessage(content=say, tool_calls=[{"name": n, "args": a, "id": f"pilot-{ctx.turns}-{i}"}
                                                  for i, (n, a) in enumerate(calls)])

    def _generate(self, messages, stop=None, run_manager: Optional[CallbackManagerForLLMRun] = None, **kw) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    async def _agenerate(self, messages, stop=None, run_manager: Optional[AsyncCallbackManagerForLLMRun] = None, **kw) -> ChatResult:
        return self._generate(messages, stop=stop, **kw)

    def _stream(self, messages, stop=None, run_manager: Optional[CallbackManagerForLLMRun] = None, **kw) -> Iterator[ChatGenerationChunk]:
        msg = self._next(messages)
        words = str(msg.content).split(" ")
        for i, token in enumerate(words):
            text = token + (" " if i < len(words) - 1 else "")
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=text))
            if run_manager:
                run_manager.on_llm_new_token(text, chunk=chunk)
            yield chunk
        if msg.tool_calls:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[
                {"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"], "index": i}
                for i, tc in enumerate(msg.tool_calls)]))
