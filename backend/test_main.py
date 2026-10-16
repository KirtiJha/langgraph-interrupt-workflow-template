"""API tests for Repo Steward (offline, on the sample repository and the rule-based pilot).

Run with: USE_MOCK_LLM=true python -m pytest -q
Set TEST_GITHUB_LIVE=1 to also read a real public repository.
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("USE_MOCK_LLM", "true")

from main import app  # noqa: E402
from steward.catalog import MISSIONS_BY_ID  # noqa: E402
from steward.fixture import SAMPLE_REPO_NAME  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def _sse(client, method, url, **kwargs):
    events = []
    with client.stream(method, url, **kwargs) as response:
        assert response.status_code == 200, response.read()
        for line in response.iter_lines():
            if line and line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def _start(client, mission_id, repo=SAMPLE_REPO_NAME, **extra):
    events = _sse(client, "POST", "/missions/start",
                  json={"repo": repo, "goal": MISSIONS_BY_ID[mission_id]["goal"], "mission_id": mission_id, **extra})
    thread = next(e for e in events if e["type"] == "thread")["thread_id"]
    return thread, events


def _state(events):
    return [e for e in events if e["type"] == "state"][-1]


def _decide(client, thread, decisions):
    return _sse(client, "POST", f"/missions/{thread}/decide", json={"decisions": decisions})


def _approve_all(client, thread, state, decide=None):
    for _ in range(12):
        if not state["requires_input"]:
            return state
        decisions = {}
        if state["pending"]["question"]:
            q = state["pending"]["question"]
            decisions[q["interrupt_id"]] = (q["options"] or ["ok"])[0]
        for a in state["pending"]["approvals"]:
            decisions[a["interrupt_id"]] = (decide(a) if decide else None) or {"type": "approve"}
        state = _state(_decide(client, thread, decisions))
    return state


def _issue(state, number):
    return next(i for i in state["world"]["issues"] + state["world"]["pulls"] if i["number"] == number)


# --- Meta -------------------------------------------------------------------------
def test_health_and_capabilities(client):
    assert client.get("/health").json()["status"] == "ok"
    caps = client.get("/capabilities").json()
    assert caps["offline_pilot"] is True
    assert caps["hitl"]["autonomy_levels"] == ["observe", "careful", "balanced", "autopilot"]
    assert "merge_pull" in caps["hitl"]["acting_tools"]
    assert "human_in_the_loop(per_call)" in caps["middleware"]


def test_gallery_and_sample_repo(client):
    data = client.get("/missions").json()
    assert {m["id"] for m in data["missions"]} == {"triage", "stale", "prs", "release", "welcome"}
    assert data["sample_repo"] == SAMPLE_REPO_NAME
    board = client.get("/repos/inspect", params={"repo": SAMPLE_REPO_NAME}).json()
    assert board["mode"] == "fixture" and board["can_write"] is True
    assert len(board["issues"]) == 12 and len(board["pulls"]) == 3
    assert any(l["name"] == "needs-repro" for l in board["labels"])


def test_inspect_rejects_bad_slugs(client):
    assert client.get("/repos/inspect", params={"repo": "not a repo"}).status_code == 400
    assert client.get("/repos/inspect", params={"repo": "https://github.com/acme/pixelforge/issues"}).json()["mode"] == "fixture"


# --- Triage: the core loop ----------------------------------------------------------
def test_triage_pauses_with_risk_and_previews(client):
    thread, events = _start(client, "triage")
    state = _state(events)
    assert state["status"] == "awaiting_approval"
    approvals = state["pending"]["approvals"]
    names = {a["name"] for a in approvals}
    assert {"add_labels", "comment", "close_issue"} <= names
    label = next(a for a in approvals if a["name"] == "add_labels" and a["args"]["number"] == 101)
    assert label["risk"]["level"] == "low" and label["risk"]["preview"]["after"] == ["bug"]
    comment = next(a for a in approvals if a["name"] == "comment" and a["args"]["number"] == 102)
    assert comment["risk"]["level"] == "medium" and comment["risk"]["reversible"] is False
    assert "--version" in comment["risk"]["preview"]["body"]
    dup = next(a for a in approvals if a["name"] == "close_issue")
    assert dup["args"]["number"] == 105 and dup["args"]["reason"] == "duplicate" and "#101" in dup["args"]["note"]
    answer = next(a for a in approvals if a["name"] == "comment" and a["args"]["number"] == 103)
    assert "--keep-metadata" in answer["args"]["body"]  # answered from the code
    # Nothing has changed yet.
    assert _issue(state, 101)["labels"] == []


def test_approve_updates_the_board_and_reports(client):
    thread, events = _start(client, "triage", user_id="u-1")
    state = _approve_all(client, thread, _state(events))
    assert state["status"] == "completed"
    assert _issue(state, 101)["labels"] == ["bug"]
    assert _issue(state, 102)["labels"] == ["bug", "needs-repro"] and _issue(state, 102)["comments"] == 1
    assert _issue(state, 105)["state"] == "closed"
    assert state["report"]["summary"].startswith("Triaged")
    assert len(state["world"]["ledger"]) >= 12
    memories = client.get("/repos/inspect", params={"repo": SAMPLE_REPO_NAME, "user_id": "u-1"}).json()["memories"]
    assert any("needs-repro" in m for m in memories)


def test_reject_and_edit_are_respected(client):
    thread, events = _start(client, "triage")
    state = _state(events)
    decisions = {}
    for a in state["pending"]["approvals"]:
        if a["name"] == "comment" and a["args"]["number"] == 102:
            decisions[a["interrupt_id"]] = {"type": "reject", "message": "Too formal"}
        elif a["name"] == "comment" and a["args"]["number"] == 111:
            decisions[a["interrupt_id"]] = {"type": "edit", "edited_action": {"name": "comment", "args": {**a["args"], "body": "Edited body"}}}
        else:
            decisions[a["interrupt_id"]] = {"type": "approve"}
    events = _decide(client, thread, decisions)
    assert any(e["type"] == "tool_result" and e["status"] == "rejected" for e in events)
    assert any(e["type"] == "tool_result" and e["status"] == "edited" for e in events)
    state = _approve_all(client, thread, _state(events))
    assert _issue(state, 102)["comments"] == 0  # rejected comment never posted
    assert _issue(state, 111)["thread"][-1]["body"] == "Edited body"
    assert any("Skipped: Commented on #102" in x for x in state["report"]["open_items"])


def test_partial_decisions_keep_the_rest_pending(client):
    thread, events = _start(client, "welcome")
    state = _state(events)
    assert len(state["pending"]["approvals"]) == 2
    first = state["pending"]["approvals"][0]
    state = _state(_decide(client, thread, {first["interrupt_id"]: {"type": "approve"}}))
    assert state["status"] == "awaiting_approval" and len(state["pending"]["approvals"]) == 1


# --- Other missions ---------------------------------------------------------------
def test_stale_sweep_closes_resolved_and_nudges_the_rest(client):
    thread, events = _start(client, "stale")
    state = _state(events)
    approvals = state["pending"]["approvals"]
    close = next(a for a in approvals if a["name"] == "close_issue")
    assert close["args"]["number"] == 107 and close["risk"]["preview"]["last_activity_days"] >= 60
    nudges = [a for a in approvals if a["name"] == "comment"]
    assert {a["args"]["number"] for a in nudges} == {110, 111, 115}
    state = _approve_all(client, thread, state)
    assert _issue(state, 107)["state"] == "closed" and "stale" in _issue(state, 110)["labels"]


def test_pr_review_welcomes_first_timers_and_requests_review(client):
    thread, events = _start(client, "prs")
    state = _state(events)
    approvals = state["pending"]["approvals"]
    welcome = next(a for a in approvals if a["name"] == "comment" and a["args"]["number"] == 113)
    assert "first contribution" in welcome["args"]["body"]
    assert any("First-time contributor" in r for r in welcome["risk"]["reasons"])
    review = [a for a in approvals if a["name"] == "request_reviewers"]
    assert {a["args"]["number"] for a in review} == {113, 114} and review[0]["args"]["reviewers"] == ["maintainer-ana"]
    assert all(a["args"]["number"] != 115 or "rebase" in a["args"]["body"] for a in approvals if a["name"] == "comment")


def test_release_notes_open_a_tracking_issue(client):
    thread, events = _start(client, "release")
    state = _state(events)
    a = state["pending"]["approvals"][0]
    assert a["name"] == "create_issue" and "### Fixes" in a["args"]["body"] and "@ops-sam" in a["args"]["body"]
    state = _approve_all(client, thread, state)
    assert state["world"]["issues"][0]["by_agent"] is True and state["world"]["issues"][0]["labels"] == ["docs"]


# --- Autonomy & observe mode ---------------------------------------------------------
def test_balanced_runs_labels_without_asking(client):
    thread, events = _start(client, "triage", autonomy="balanced")
    state = _state(events)
    names = {a["name"] for a in state["pending"]["approvals"]}
    assert "add_labels" not in names and "comment" in names
    assert _issue(state, 101)["labels"] == ["bug"]  # already applied


def test_autopilot_asks_only_for_irreversible_or_high(client):
    thread, events = _start(client, "stale", autonomy="autopilot")
    state = _state(events)
    names = [a["name"] for a in state["pending"]["approvals"]]
    assert "add_labels" not in names and set(names) == {"close_issue", "comment"}


def test_observe_mode_records_proposals_instead_of_acting(client):
    thread, events = _start(client, "welcome", autonomy="observe")
    state = _approve_all(client, thread, _state(events))
    assert state["status"] == "completed"
    assert all(l["proposed"] for l in state["world"]["ledger"]) and state["report"]["proposals"] == 2
    assert state["world"]["ledger"][0]["summary"].startswith("Commented")


# --- Time travel, reload, follow-up ---------------------------------------------------
def test_fork_rewinds_the_board_and_reasks(client):
    thread, events = _start(client, "welcome")
    state = _approve_all(client, thread, _state(events))
    assert len(state["world"]["ledger"]) == 2
    points = client.get(f"/missions/{thread}/history").json()["decision_points"]
    assert len(points) == 1
    state = _state(_sse(client, "POST", f"/missions/{thread}/fork", json={"checkpoint_id": points[0]["checkpoint_id"]}))
    assert state["status"] == "awaiting_approval" and state["world"]["ledger"] == []
    decisions = {a["interrupt_id"]: ({"type": "reject", "message": "not yet"} if a["name"] == "comment" else {"type": "approve"})
                 for a in state["pending"]["approvals"]}
    state = _approve_all(client, thread, _state(_decide(client, thread, decisions)))
    assert state["status"] == "completed" and len(state["world"]["ledger"]) == 1


def test_timeline_state_and_follow_up(client):
    thread, events = _start(client, "release")
    state = client.get(f"/missions/{thread}").json()
    assert state["repo"] == SAMPLE_REPO_NAME and state["status"] == "awaiting_approval"
    timeline = client.get(f"/missions/{thread}/timeline").json()["events"]
    assert timeline[0]["type"] == "goal" and any(e["type"] == "tool_calls" for e in timeline)
    assert client.post(f"/missions/{thread}/continue", json={"message": "also"}).status_code == 409
    state = _approve_all(client, thread, state)
    assert client.post(f"/missions/{thread}/continue", json={"message": "also"}).status_code == 200
    assert client.post("/missions/nope/cancel", json={}).json() == {"requested": False}
    assert client.post(f"/missions/{thread}/decide", json={"decisions": {"x": {"type": "approve"}}}).status_code == 409


# --- GitHub token handling -------------------------------------------------------------
def test_github_token_is_scoped_and_scrubbed(client, monkeypatch):
    from steward import github as gh

    assert gh.user_token() is None
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert gh.write_token() is None
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_serverside_secret_123456")
    assert gh.read_token() == "ghp_serverside_secret_123456" and gh.write_token() is None
    monkeypatch.setenv("STEWARD_SERVER_TOKEN_WRITES", "true")
    assert gh.write_token() == "ghp_serverside_secret_123456"
    assert "ghp_serverside" not in gh.scrub("boom ghp_serverside_secret_123456 boom")
    assert gh.parse_repo("https://github.com/acme/pixelforge.git") == "acme/pixelforge"
    assert gh.parse_repo("acme/pixelforge") == "acme/pixelforge" and gh.parse_repo("nope") is None


def test_repos_mine_needs_the_visitors_token(client, monkeypatch):
    # The server's own token must never be used to list repos for a visitor.
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_server_owned_token_1234")
    res = client.get("/repos/mine")
    assert res.status_code == 400 and "Connect a GitHub token" in res.json()["detail"]


def test_repos_mine_lists_and_paginates(client, monkeypatch):
    import httpx

    pages = {
        "https://api.github.com/user/repos?per_page=100&sort=pushed&affiliation=owner,collaborator,organization_member":
            ([{"full_name": "me/a", "private": True, "open_issues_count": 3, "permissions": {"push": True}, "pushed_at": "2026-10-01T00:00:00Z"}],
             '<https://api.github.com/page2>; rel="next"'),
        "https://api.github.com/page2": ([{"full_name": "org/b", "permissions": {"pull": True}}], None),
    }
    seen = {}

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, headers):
            seen["auth"] = headers["Authorization"]
            body, link = pages[url]
            return httpx.Response(200, json=body, headers={"link": link} if link else {}, request=httpx.Request("GET", url))

    monkeypatch.setattr("steward.github.httpx.Client", FakeClient)
    data = client.get("/repos/mine", headers={"X-GitHub-Token": "github_pat_visitor_9876"}).json()
    assert [r["full_name"] for r in data["repos"]] == ["me/a", "org/b"]
    assert data["repos"][0]["can_write"] is True and data["repos"][0]["private"] is True
    assert data["repos"][1]["can_write"] is False
    assert seen["auth"] == "Bearer github_pat_visitor_9876"


@pytest.mark.skipif(not os.getenv("TEST_GITHUB_LIVE"), reason="set TEST_GITHUB_LIVE=1 to hit api.github.com")
def test_live_public_repo_is_read_only_without_a_token(client):
    board = client.get("/repos/inspect", params={"repo": "KirtiJha/langgraph-interrupt-workflow-template"}).json()
    assert board["mode"] == "live" and board["repo"]["default_branch"]
    thread, events = _start(client, "triage", repo="KirtiJha/langgraph-interrupt-workflow-template")
    head = next(e for e in events if e["type"] == "thread")
    assert head["autonomy"] == "observe"
    state = _approve_all(client, thread, _state(events))
    assert state["status"] == "completed" and all(l["proposed"] for l in state["world"]["ledger"])


def test_in_memory_state_does_not_survive_a_new_instance():
    with TestClient(app) as first:
        thread, _ = _start(first, "release")
    with TestClient(app) as second:
        assert second.get(f"/missions/{thread}").status_code == 404


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL to run")
def test_postgres_state_survives_across_instances(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    with TestClient(app) as a:
        thread, events = _start(a, "release")
        state = _state(events)
    with TestClient(app) as b:
        assert _approve_all(b, thread, state)["status"] == "completed"


# --- Model chosen in the UI (unchanged contract) ----------------------------------------
def _llm_headers(base_url, key="sk-browser-secret-123", model="my-model"):
    return {"X-LLM-Provider": "custom", "X-LLM-Model": model, "X-LLM-API-Key": key, "X-LLM-Base-URL": base_url}


def test_model_providers_and_test_endpoint(client):
    data = client.get("/model/providers").json()
    assert {"gateway", "openai", "anthropic", "custom", "mock"} <= {p["id"] for p in data["providers"]}
    assert client.post("/model/test", headers={"X-LLM-Provider": "mock"}).json()["ok"] is True
    res = client.post("/model/test", headers=_llm_headers("http://127.0.0.1:9/v1")).json()
    assert res["ok"] is False and "sk-browser-secret-123" not in str(res)


@pytest.mark.parametrize("headers, message", [
    ({"X-LLM-Provider": "nope"}, "Unknown provider"),
    ({"X-LLM-Provider": "openai", "X-LLM-Model": "gpt-5"}, "API key"),
    ({"X-LLM-Provider": "custom", "X-LLM-Model": "m", "X-LLM-API-Key": "k", "X-LLM-Base-URL": "file:///x"}, "http(s)"),
])
def test_bad_browser_model_settings_are_400(client, headers, message):
    res = client.post("/missions/start", json={"goal": "x"}, headers=headers)
    assert res.status_code == 400 and message in res.json()["detail"]
