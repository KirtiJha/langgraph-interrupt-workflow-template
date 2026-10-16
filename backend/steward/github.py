"""GitHub access for Repo Steward: a real REST backend and a fixture backend.

Both expose the same small surface. The *board* (repo, open issues, open
pull requests, labels, README) is loaded once at mission start into graph
state; tools read from state and only go back to GitHub for details (comments,
files, diffs). Writes go through :meth:`Backend.execute` with a normalised
*operation* dict, which the world reducer then applies to the board so the UI
updates the same way whether the repo is live or the fixture.

Token handling mirrors the model settings: a visitor's token arrives as the
``X-GitHub-Token`` header, is scoped to the request with a ContextVar, and is
never stored or logged. The server's own ``GITHUB_TOKEN`` (if set) is used for
reads (higher rate limits); it is used for *writes* only when
``STEWARD_SERVER_TOKEN_WRITES=true``.
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import os
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

API = "https://api.github.com"
_TOKEN: ContextVar[Optional[str]] = ContextVar("github_token", default=None)
REPO_RE = re.compile(r"^(?:https?://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git|/.*)?$")


class GitHubError(Exception):
    """A GitHub problem the user can act on (shown in the UI, token scrubbed)."""


def parse_repo(text: str) -> Optional[str]:
    """``owner/name`` from a bare slug or any github.com URL, or ``None``."""
    m = REPO_RE.match((text or "").strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def user_token() -> Optional[str]:
    return _TOKEN.get()


def server_token() -> Optional[str]:
    return (os.getenv("GITHUB_TOKEN") or "").strip() or None


def read_token() -> Optional[str]:
    return user_token() or server_token()


def write_token() -> Optional[str]:
    """The token that may *act*: the visitor's, or the server's if the owner allows."""
    if user_token():
        return user_token()
    if server_token() and _truthy("STEWARD_SERVER_TOKEN_WRITES"):
        return server_token()
    return None


def scrub(text: str) -> str:
    for tok in (user_token(), server_token()):
        if tok and len(tok) >= 8:
            text = text.replace(tok, "•••")
    return text


class GitHubTokenMiddleware:
    """Pure-ASGI: scope ``X-GitHub-Token`` to the request."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        token = None
        for k, v in scope.get("headers", []):
            if k == b"x-github-token":
                token = v.decode("latin-1").strip() or None
        ctx = _TOKEN.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            _TOKEN.reset(ctx)


# --- Helpers -----------------------------------------------------------------
def _iso(s: Optional[str]) -> Optional[str]:
    return s[:19] + "Z" if s else None


def days_ago(iso: Optional[str], now: Optional[datetime] = None) -> Optional[int]:
    if not iso:
        return None
    now = now or datetime.now(timezone.utc)
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, (now - then).days)


def slim_issue(raw: dict) -> dict:
    """The fields the board keeps for an issue or pull request."""
    is_pr = "pull_request" in raw or raw.get("is_pr")
    return {
        "number": raw["number"],
        "title": raw.get("title", ""),
        "body": (raw.get("body") or "")[:4000],
        "state": raw.get("state", "open"),
        "author": (raw.get("user") or {}).get("login") or raw.get("author", "?"),
        "author_association": raw.get("author_association", "NONE"),
        "labels": sorted(l["name"] if isinstance(l, dict) else l for l in raw.get("labels", [])),
        "assignees": [a["login"] if isinstance(a, dict) else a for a in raw.get("assignees", [])],
        "comments": raw.get("comments", 0) if isinstance(raw.get("comments"), int) else len(raw.get("comments") or []),
        "created_at": _iso(raw.get("created_at")),
        "updated_at": _iso(raw.get("updated_at")),
        "is_pr": bool(is_pr),
        "draft": bool(raw.get("draft")),
        "url": raw.get("html_url") or raw.get("url", ""),
        "milestone": (raw.get("milestone") or {}).get("title") if isinstance(raw.get("milestone"), dict) else raw.get("milestone"),
        "thread": raw.get("thread", []),  # inline comments (fixture) or fetched later
    }


# --- Real backend ---------------------------------------------------------------
class GitHub:
    """Real GitHub REST backend (httpx). Reads use any token; writes need one."""

    def __init__(self, repo: str) -> None:
        self.repo = repo
        self.rate: dict = {}

    def _headers(self, write: bool = False) -> dict:
        token = write_token() if write else read_token()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "repo-steward"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, method: str, path: str, write: bool = False, **kwargs) -> Any:
        url = path if path.startswith("http") else f"{API}{path}"
        try:
            with httpx.Client(timeout=20) as client:
                res = client.request(method, url, headers=self._headers(write), **kwargs)
        except httpx.HTTPError as exc:
            raise GitHubError(scrub(f"GitHub unreachable: {exc}")) from None
        self.rate = {"remaining": res.headers.get("x-ratelimit-remaining"), "limit": res.headers.get("x-ratelimit-limit")}
        if res.status_code == 404:
            raise GitHubError(f"Not found on GitHub: {path.split('?')[0]} (private repo? add a token).")
        if res.status_code in (401, 403):
            msg = (res.json().get("message") if res.headers.get("content-type", "").startswith("application/json") else res.text) or ""
            if "rate limit" in msg.lower():
                raise GitHubError("GitHub API rate limit hit. Add a GitHub token (Connect) for 5,000 requests/hour.")
            raise GitHubError(scrub(f"GitHub refused ({res.status_code}): {msg[:200]} — does your token have the right permissions?"))
        if res.status_code >= 400:
            raise GitHubError(scrub(f"GitHub error {res.status_code}: {res.text[:200]}"))
        if res.status_code == 204 or not res.content:
            return None
        return res.json()

    # reads
    def load_board(self, max_issues: int = 60, max_pulls: int = 25) -> dict:
        repo = self._request("GET", f"/repos/{self.repo}")
        issues_raw = self._request("GET", f"/repos/{self.repo}/issues?state=open&per_page=100&sort=updated")
        labels = self._request("GET", f"/repos/{self.repo}/labels?per_page=100")
        readme = ""
        try:
            data = self._request("GET", f"/repos/{self.repo}/readme")
            readme = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")[:6000]
        except GitHubError:
            pass
        issues = [slim_issue(i) for i in issues_raw if "pull_request" not in i][:max_issues]
        pulls = [slim_issue(i) for i in issues_raw if "pull_request" in i][:max_pulls]
        return {
            "repo": {
                "full_name": repo["full_name"], "description": repo.get("description") or "",
                "default_branch": repo.get("default_branch", "main"), "stars": repo.get("stargazers_count", 0),
                "open_issues": repo.get("open_issues_count", 0), "url": repo.get("html_url"),
                "owner": repo["owner"]["login"], "pushed_at": _iso(repo.get("pushed_at")),
                "maintainer": repo["owner"]["login"] if repo["owner"].get("type") == "User" else None,
                "has_issues": repo.get("has_issues", True),
            },
            "labels": [{"name": l["name"], "color": l.get("color", "ededed"), "description": l.get("description") or ""}
                       for l in labels],
            "issues": issues,
            "pulls": pulls,
            "readme": readme,
            "mode": "live",
            "can_write": write_token() is not None,
            "rate": self.rate,
        }

    def comments(self, number: int) -> list[dict]:
        raw = self._request("GET", f"/repos/{self.repo}/issues/{number}/comments?per_page=30")
        return [{"author": c["user"]["login"], "body": (c.get("body") or "")[:2000], "created_at": _iso(c.get("created_at"))}
                for c in raw or []]

    def file(self, path: str) -> str:
        data = self._request("GET", f"/repos/{self.repo}/contents/{path.lstrip('/')}")
        if isinstance(data, list):
            return "\n".join(f"{'📁' if d['type'] == 'dir' else '📄'} {d['path']}" for d in data)
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", "replace")[:12000]
        return data.get("content", "")[:12000]

    def pull_detail(self, number: int) -> dict:
        pr = self._request("GET", f"/repos/{self.repo}/pulls/{number}")
        files = self._request("GET", f"/repos/{self.repo}/pulls/{number}/files?per_page=50") or []
        return {
            "number": number, "title": pr["title"], "author": pr["user"]["login"], "draft": pr.get("draft", False),
            "mergeable": pr.get("mergeable"), "additions": pr.get("additions"), "deletions": pr.get("deletions"),
            "changed_files": pr.get("changed_files"), "base": pr["base"]["ref"], "head": pr["head"]["ref"],
            "files": [{"path": f["filename"], "status": f["status"], "additions": f["additions"], "deletions": f["deletions"],
                       "patch": (f.get("patch") or "")[:1500]} for f in files],
        }

    def release_context(self) -> dict:
        tags = self._request("GET", f"/repos/{self.repo}/tags?per_page=1") or []
        if tags:
            tag = tags[0]["name"]
            cmp = self._request("GET", f"/repos/{self.repo}/compare/{tag}...HEAD")
            commits = cmp.get("commits", [])
        else:
            tag = None
            commits = self._request("GET", f"/repos/{self.repo}/commits?per_page=30") or []
        return {"last_tag": tag, "commits": [
            {"sha": c["sha"][:7], "message": c["commit"]["message"].split("\n")[0][:120],
             "author": (c.get("author") or {}).get("login") or c["commit"]["author"]["name"]} for c in commits[:60]]}

    def search_issues(self, query: str) -> list[dict]:
        data = self._request("GET", f"/search/issues?q={httpx.QueryParams({'q': f'repo:{self.repo} {query}'})['q']}&per_page=8")
        return [slim_issue(i) for i in (data or {}).get("items", [])]

    # writes
    def execute(self, op: dict) -> str:
        kind, n = op.get("op"), op.get("number")
        base = f"/repos/{self.repo}"
        if kind == "create_label":
            try:
                self._request("POST", f"{base}/labels", write=True, json={"name": op["name"], "color": "ededed"})
            except GitHubError as exc:
                if "already_exists" not in str(exc) and "422" not in str(exc):
                    raise
        if kind == "add_labels":
            self._request("POST", f"{base}/issues/{n}/labels", write=True, json={"labels": op["labels"]})
        elif kind == "remove_labels":
            for label in op["labels"]:
                self._request("DELETE", f"{base}/issues/{n}/labels/{label}", write=True)
        elif kind == "comment":
            data = self._request("POST", f"{base}/issues/{n}/comments", write=True, json={"body": op["body"]})
            return data.get("html_url", "")
        elif kind == "close":
            payload = {"state": "closed"}
            reason = {"duplicate": "not_planned"}.get(op.get("reason"), op.get("reason"))
            if reason in ("completed", "not_planned"):
                payload["state_reason"] = reason
            self._request("PATCH", f"{base}/issues/{n}", write=True, json=payload)
        elif kind == "reopen":
            self._request("PATCH", f"{base}/issues/{n}", write=True, json={"state": "open"})
        elif kind == "retitle":
            self._request("PATCH", f"{base}/issues/{n}", write=True, json={"title": op["title"]})
        elif kind == "assign":
            self._request("POST", f"{base}/issues/{n}/assignees", write=True, json={"assignees": op["assignees"]})
        elif kind == "request_review":
            self._request("POST", f"{base}/pulls/{n}/requested_reviewers", write=True, json={"reviewers": op["reviewers"]})
        elif kind == "create_issue":
            data = self._request("POST", f"{base}/issues", write=True,
                                 json={"title": op["title"], "body": op.get("body", ""), "labels": op.get("labels", [])})
            op["number"] = data["number"]
            return data.get("html_url", "")
        elif kind == "merge":
            self._request("PUT", f"{base}/pulls/{n}/merge", write=True,
                          json={"merge_method": op.get("method", "squash")})
        else:
            raise GitHubError(f"Unknown operation {kind}")
        return ""


# --- Fixture backend -------------------------------------------------------------
def list_user_repos(limit: int = 300) -> list[dict]:
    """Repositories the *visitor's* token can see, most recently pushed first.

    Uses only the visitor's own token (never the server's), so one visitor can
    never browse the deployment owner's repositories. Works with classic and
    fine-grained tokens (the latter return just the repos they were granted).
    """
    token = user_token()
    if not token:
        raise GitHubError("Connect a GitHub token to list your repositories.")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "repo-steward", "Authorization": f"Bearer {token}"}
    repos: list[dict] = []
    url: Optional[str] = f"{API}/user/repos?per_page=100&sort=pushed&affiliation=owner,collaborator,organization_member"
    try:
        with httpx.Client(timeout=20) as client:
            while url and len(repos) < limit:
                res = client.get(url, headers=headers)
                if res.status_code == 401:
                    raise GitHubError("GitHub rejected the token — it may be expired or revoked.")
                if res.status_code == 403:
                    msg = (res.json().get("message") if res.headers.get("content-type", "").startswith("application/json") else "") or ""
                    raise GitHubError(scrub(f"GitHub won't list repositories for this token ({msg[:160]}). You can still type owner/name."))
                if res.status_code >= 400:
                    raise GitHubError(scrub(f"GitHub error {res.status_code}: {res.text[:200]}"))
                for r in res.json():
                    perms = r.get("permissions") or {}
                    repos.append({
                        "full_name": r["full_name"], "description": r.get("description") or "",
                        "private": bool(r.get("private")), "fork": bool(r.get("fork")), "archived": bool(r.get("archived")),
                        "open_issues": r.get("open_issues_count", 0), "stars": r.get("stargazers_count", 0),
                        "pushed_at": _iso(r.get("pushed_at")), "language": r.get("language"),
                        "can_write": bool(perms.get("push") or perms.get("maintain") or perms.get("admin")),
                        "has_issues": r.get("has_issues", True),
                    })
                url = res.links.get("next", {}).get("url")
    except httpx.HTTPError as exc:
        raise GitHubError(scrub(f"GitHub unreachable: {exc}")) from None
    return repos[:limit]


class FixtureGitHub:
    """Offline backend over a JSON snapshot: reads from it, writes are no-ops.

    The world reducer applies the operations to the board in state, so the
    demo behaves like a live repo without touching the network.
    """

    def __init__(self, repo: str, data: dict) -> None:
        self.repo = repo
        self.data = copy.deepcopy(data)
        self.rate = {}

    def load_board(self, **_) -> dict:
        d = self.data
        return {
            "repo": d["repo"], "labels": d["labels"],
            "issues": [slim_issue(i) for i in d["issues"] if not i.get("is_pr")],
            "pulls": [slim_issue(i) for i in d["issues"] if i.get("is_pr")],
            "readme": d.get("readme", ""), "mode": "fixture", "can_write": True, "rate": {},
        }

    def comments(self, number: int) -> list[dict]:
        for i in self.data["issues"]:
            if i["number"] == number:
                return list(i.get("thread", []))
        return []

    def file(self, path: str) -> str:
        files = self.data.get("files", {})
        if path in files:
            return files[path]
        prefix = path.strip("/")
        listing = [p for p in files if not prefix or p.startswith(prefix + "/") or p == prefix]
        if listing:
            return "\n".join(f"📄 {p}" for p in listing)
        raise GitHubError(f"No such file in the sample repo: {path}")

    def pull_detail(self, number: int) -> dict:
        for i in self.data["issues"]:
            if i["number"] == number and i.get("is_pr"):
                return i.get("pull", {"number": number, "files": []})
        raise GitHubError(f"#{number} is not a pull request.")

    def release_context(self) -> dict:
        return self.data.get("release", {"last_tag": None, "commits": []})

    def search_issues(self, query: str) -> list[dict]:
        words = {w.lower() for w in re.findall(r"\w{4,}", query)}
        hits = []
        for i in self.data["issues"]:
            text = f"{i['title']} {i.get('body', '')}".lower()
            score = sum(1 for w in words if w in text)
            if score:
                hits.append((score, slim_issue(i)))
        return [h for _, h in sorted(hits, key=lambda x: -x[0])[:8]]

    def execute(self, op: dict) -> str:
        return ""  # the reducer applies it to the board


def backend_for(board_or_repo: Any, fixture: Optional[dict] = None):
    """Pick the backend for a board (state) or a repo slug."""
    from steward.fixture import SAMPLE_REPO, SAMPLE_REPO_NAME

    if isinstance(board_or_repo, dict):
        repo = board_or_repo["repo"]["full_name"]
        mode = board_or_repo.get("mode", "live")
    else:
        repo = board_or_repo
        mode = "fixture" if repo == SAMPLE_REPO_NAME else "live"
    if mode == "fixture":
        return FixtureGitHub(repo, fixture or SAMPLE_REPO)
    return GitHub(repo)
