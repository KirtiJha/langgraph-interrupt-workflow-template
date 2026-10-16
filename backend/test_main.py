"""API tests for Mission Control (offline, on the scripted pilot).

Run with: USE_MOCK_LLM=true python -m pytest -q
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("USE_MOCK_LLM", "true")

from main import app  # noqa: E402
from mission.catalog import MISSIONS_BY_ID  # noqa: E402


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


def _start(client, mission_id, **extra):
    events = _sse(client, "POST", "/missions/start",
                  json={"goal": MISSIONS_BY_ID[mission_id]["goal"], "mission_id": mission_id, **extra})
    thread = next(e for e in events if e["type"] == "thread")["thread_id"]
    return thread, events


def _state(events):
    return [e for e in events if e["type"] == "state"][-1]


def _decide(client, thread, decisions):
    return _sse(client, "POST", f"/missions/{thread}/decide", json={"decisions": decisions})


def _approve_all(client, thread, state, decide=None):
    """Drive a mission to the end, approving everything (or per ``decide``)."""
    for _ in range(12):
        if not state["requires_input"]:
            return state
        decisions = {}
        if state["pending"]["question"]:
            q = state["pending"]["question"]
            decisions[q["interrupt_id"]] = q["options"][0]
        for a in state["pending"]["approvals"]:
            decisions[a["interrupt_id"]] = (decide(a) if decide else None) or {"type": "approve"}
        state = _state(_decide(client, thread, decisions))
    return state


# --- Meta ---------------------------------------------------------------------
def test_health_and_capabilities(client):
    assert client.get("/health").json()["status"] == "ok"
    caps = client.get("/capabilities").json()
    assert caps["model"]["mock"] is True and caps["offline_pilot"] is True
    assert caps["hitl"]["acting_tools"] and caps["hitl"]["autonomy_levels"] == ["careful", "balanced", "autopilot"]
    assert "human_in_the_loop(per_call)" in caps["middleware"] and "guardrails" in caps["middleware"]
    assert caps["guardrails"]["enabled"] is True


def test_gallery_lists_missions_and_world(client):
    data = client.get("/missions").json()
    assert {m["id"] for m in data["missions"]} == {"birthday", "move", "lisbon", "inbox", "subscriptions"}
    assert data["world"]["wallet"]["balance"] == 3240.0 and len(data["world"]["inbox"]) == 6
    assert data["memories"] == []


# --- The core loop: act → pause → decide → world changes ---------------------
def test_mission_pauses_before_acting_and_shows_a_preview(client):
    thread, events = _start(client, "subscriptions")
    assert any(e["type"] == "tool_calls" for e in events)
    assert any(e["type"] == "token" for e in events)  # narration streams
    state = _state(events)
    assert state["status"] == "awaiting_approval"
    approvals = state["pending"]["approvals"]
    assert [a["name"] for a in approvals] == ["cancel_subscription"] * 3
    risk = approvals[0]["risk"]
    assert risk["level"] == "medium" and risk["reversible"] is False and risk["asked"] is True
    assert risk["preview"]["kind"] == "cancel" and risk["preview"]["saves_per_month"] == 12.99
    assert approvals[0]["response_schema"]["$defs"]  # schema-driven edit form
    # Nothing has changed yet.
    assert all(s["status"] == "active" for s in state["world"]["subscriptions"])


def test_approve_changes_the_world_and_finishes_with_a_report(client):
    thread, events = _start(client, "subscriptions", user_id="u-1")
    state = _approve_all(client, thread, _state(events))
    assert state["status"] == "completed" and state["requires_input"] is False
    cancelled = {s["name"] for s in state["world"]["subscriptions"] if s["status"] == "cancelled"}
    assert cancelled == {"Lingo+ Languages", "IronPeak Gym", "NewsDaily Premium"}
    assert state["report"]["summary"].startswith("Cancelled 3")
    assert len(state["world"]["ledger"]) == 3
    # …and the outcome is remembered for next time.
    assert any("Cut subscriptions" in m for m in client.get("/missions", params={"user_id": "u-1"}).json()["memories"])


def test_reject_sends_the_agent_to_the_runner_up(client):
    thread, events = _start(client, "birthday")
    state = _state(events)
    assert state["status"] == "awaiting_answer"
    q = state["pending"]["question"]
    assert "Olive & Fig" in q["options"]
    state = _state(_decide(client, thread, {q["interrupt_id"]: "Olive & Fig"}))
    booking = next(a for a in state["pending"]["approvals"] if a["name"] == "book")
    assert booking["args"]["vendor"] == "Olive & Fig"
    assert booking["risk"]["preview"]["balance_after"] == booking["risk"]["preview"]["balance_before"] - 120
    others = {a["interrupt_id"]: {"type": "approve"} for a in state["pending"]["approvals"] if a is not booking}
    state = _state(_decide(client, thread, {booking["interrupt_id"]: {"type": "reject", "message": "Too far away"},
                                             **others}))
    retry = next(a for a in state["pending"]["approvals"] if a["name"] == "book")
    assert retry["args"]["vendor"] == "Trattoria Nonna"
    events = _decide(client, thread, {retry["interrupt_id"]: {"type": "approve"}})
    assert any(e["type"] == "tool_result" and e["status"] == "rejected" for e in events) is False
    state = _approve_all(client, thread, _state(events))
    assert state["status"] == "completed"
    assert state["world"]["bookings"][0]["vendor"] == "Trattoria Nonna"
    assert "maria.rivera@family.example" not in state["world"]["sent"][0]["to"]  # Mom isn't told
    assert state["world"]["calendar"][-1]["attendees"] or any(e["source"] == "agent" for e in state["world"]["calendar"])


def test_edit_changes_what_runs(client):
    thread, events = _start(client, "lisbon")
    state = _state(events)
    flight = next(a for a in state["pending"]["approvals"] if a["args"]["kind"] == "flight")
    hotel = next(a for a in state["pending"]["approvals"] if a["args"]["kind"] == "hotel")
    edited = {**flight["args"], "amount": 500, "details": "negotiated"}
    events = _decide(client, thread, {
        flight["interrupt_id"]: {"type": "edit", "edited_action": {"name": "book", "args": edited}},
        hotel["interrupt_id"]: {"type": "approve"},
    })
    assert any(e["type"] == "tool_result" and e["status"] == "edited" for e in events)
    state = _approve_all(client, thread, _state(events))
    charge = next(t for t in state["world"]["wallet"]["transactions"] if t["payee"] == "United + Lufthansa")
    assert charge["amount"] == -500
    assert state["report"]["spent"] == 500 + 495  # the pilot reads what *ran*, not what it asked


def test_partial_decisions_and_respond(client):
    thread, events = _start(client, "inbox")
    state = _state(events)
    pending = state["pending"]["approvals"]
    assert len(pending) == 3
    first = pending[0]
    # Decide one of three; the other two stay pending.
    state = _state(_decide(client, thread, {first["interrupt_id"]: {"type": "approve"}}))
    assert state["status"] == "awaiting_approval" and len(state["pending"]["approvals"]) == 2
    # "respond" answers instead of running the tool.
    rest = {a["interrupt_id"]: {"type": "respond", "message": "I'll reply to this one myself."}
            if a["name"] == "send_email" else {"type": "approve"} for a in state["pending"]["approvals"]}
    state = _approve_all(client, thread, _state(_decide(client, thread, rest)))
    assert state["status"] == "completed"
    assert len(state["world"]["sent"]) == 1  # only the first email went out


def test_stale_decisions_are_409(client):
    thread, events = _start(client, "subscriptions")
    resp = client.post(f"/missions/{thread}/decide", json={"decisions": {"nope": {"type": "approve"}}})
    assert resp.status_code == 409
    assert client.post("/missions/unknown/decide", json={"decisions": {"x": {}}}).status_code == 404


# --- Autonomy -----------------------------------------------------------------
def test_balanced_autonomy_only_asks_when_it_matters(client):
    thread, events = _start(client, "birthday", autonomy="balanced", ask_above=100)
    state = _state(events)
    q = state["pending"]["question"]
    state = _state(_decide(client, thread, {q["interrupt_id"]: "Olive & Fig"}))
    names = [a["name"] for a in state["pending"]["approvals"]]
    assert names == ["book"]  # the $64 cake was paid without asking; the $120 deposit asks
    assert state["world"]["wallet"]["balance"] == 3240 - 64


def test_autopilot_still_asks_for_irreversible_actions(client):
    thread, events = _start(client, "subscriptions", autonomy="autopilot")
    state = _state(events)
    assert state["status"] == "awaiting_approval"  # cancellations can't be undone
    thread, events = _start(client, "inbox", autonomy="autopilot")
    state = _state(events)
    assert [a["name"] for a in state["pending"]["approvals"]] == ["send_email", "send_email"]  # archive just ran
    assert len(state["world"]["inbox"]) == 4


# --- Time travel ----------------------------------------------------------------
def test_fork_rewinds_the_world_and_reasks(client):
    thread, events = _start(client, "subscriptions")
    state = _approve_all(client, thread, _state(events))
    assert state["status"] == "completed" and len(state["world"]["ledger"]) == 3
    points = client.get(f"/missions/{thread}/history").json()["decision_points"]
    assert len(points) == 1 and [a["name"] for a in points[0]["approvals"]] == ["cancel_subscription"] * 3
    events = _sse(client, "POST", f"/missions/{thread}/fork", json={"checkpoint_id": points[0]["checkpoint_id"]})
    state = _state(events)
    assert state["status"] == "awaiting_approval" and len(state["pending"]["approvals"]) == 3
    assert state["world"]["ledger"] == []  # rewound
    # Decide differently on the branch: keep the gym.
    decisions = {a["interrupt_id"]: ({"type": "reject", "message": "keep it"} if a["args"]["id"] == "sub2"
                                     else {"type": "approve"}) for a in state["pending"]["approvals"]}
    state = _approve_all(client, thread, _state(_decide(client, thread, decisions)))
    assert state["status"] == "completed"
    assert next(s for s in state["world"]["subscriptions"] if s["id"] == "sub2")["status"] == "active"
    assert len(client.get(f"/missions/{thread}/history").json()["decision_points"]) == 2


def test_timeline_and_state_reload(client):
    thread, events = _start(client, "move")
    state = client.get(f"/missions/{thread}").json()
    assert state["status"] == "awaiting_approval" and state["goal"].startswith("I'm moving")
    timeline = client.get(f"/missions/{thread}/timeline").json()["events"]
    assert timeline[0]["type"] == "goal"
    assert any(e["type"] == "tool_calls" and e["calls"][0]["name"] == "get_quotes" for e in timeline)


def test_follow_up_on_a_finished_mission(client):
    thread, events = _start(client, "subscriptions")
    state = _approve_all(client, thread, _state(events))
    assert client.post(f"/missions/{thread}/continue", json={"message": "also"}).status_code == 200
    thread2, events2 = _start(client, "move")
    assert client.post(f"/missions/{thread2}/continue", json={"message": "also"}).status_code == 409


def test_cancel_unknown_is_a_noop(client):
    assert client.post("/missions/nope/cancel", json={}).json() == {"requested": False}


# --- Memory + guardrails + durability ------------------------------------------
def test_memory_is_recalled_in_the_next_mission(client):
    thread, events = _start(client, "birthday", user_id="u-mem")
    _approve_all(client, thread, _state(events))
    memories = client.get("/missions", params={"user_id": "u-mem"}).json()["memories"]
    assert any("vegetarian" in m for m in memories)


def test_guardrail_redacts_pii_in_goals(client):
    events = _sse(client, "POST", "/missions/start",
                  json={"goal": "Email jo@x.com about my card 4111 1111 1111 1111", "autonomy": "careful"})
    assert any(e.get("type") == "guardrail" and e.get("action") == "redacted" for e in events)


def test_in_memory_state_does_not_survive_a_new_instance():
    with TestClient(app) as first:
        thread, _ = _start(first, "subscriptions")
    with TestClient(app) as second:
        assert second.get(f"/missions/{thread}").status_code == 404


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL to run")
def test_postgres_state_survives_across_instances(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    with TestClient(app) as a:
        assert a.get("/capabilities").json()["persistence"]["multi_instance_safe"] is True
        thread, events = _start(a, "subscriptions")
        state = _state(events)
    with TestClient(app) as b:
        state = _approve_all(b, thread, state)
        assert state["status"] == "completed"


# --- Model chosen in the UI ----------------------------------------------------
@pytest.fixture()
def fake_openai():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append({"auth": self.headers.get("Authorization"), "model": body.get("model")})
            text = "OK from the browser-chosen model"
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for chunk in ({"choices": [{"index": 0, "delta": {"role": "assistant", "content": text}}]},
                              {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}):
                    payload = {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": body.get("model"),
                               **chunk}
                    self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                return
            payload = json.dumps({"id": "c1", "object": "chat.completion", "created": 0, "model": body.get("model"),
                                  "choices": [{"index": 0, "finish_reason": "stop",
                                               "message": {"role": "assistant", "content": text}}],
                                  "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield {"base_url": f"http://127.0.0.1:{server.server_port}/v1", "seen": seen}
    server.shutdown()


def _llm_headers(base_url, key="sk-browser-secret-123", model="my-model"):
    return {"X-LLM-Provider": "custom", "X-LLM-Model": model, "X-LLM-API-Key": key, "X-LLM-Base-URL": base_url}


def test_model_providers_lists_presets_without_secrets(client):
    data = client.get("/model/providers").json()
    assert {"gateway", "openai", "anthropic", "google", "custom", "mock"} <= {p["id"] for p in data["providers"]}
    assert all("env_key" not in p and "model_provider" not in p for p in data["providers"])
    assert data["policy"]["enabled"] is True and data["policy"]["server_key_shared"] is False


def test_model_test_uses_browser_model_and_key(client, fake_openai):
    res = client.post("/model/test", headers=_llm_headers(fake_openai["base_url"])).json()
    assert res["ok"] is True and "OK" in res["sample"]
    assert fake_openai["seen"][-1] == {"auth": "Bearer sk-browser-secret-123", "model": "my-model"}


def test_model_test_failure_does_not_leak_key(client):
    res = client.post("/model/test", headers=_llm_headers("http://127.0.0.1:9/v1")).json()
    assert res["ok"] is False and "sk-browser-secret-123" not in str(res)


def test_browser_model_drives_the_mission(client, fake_openai):
    events = _sse(client, "POST", "/missions/start", json={"goal": "say hi"},
                  headers=_llm_headers(fake_openai["base_url"]))
    assert fake_openai["seen"] and all(s["model"] == "my-model" for s in fake_openai["seen"])
    assert "browser-chosen" in _state(events)["closing"]
    assert client.get("/capabilities").json()["model"]["mock"] is True  # server default untouched


@pytest.mark.parametrize("headers, message", [
    ({"X-LLM-Provider": "nope"}, "Unknown provider"),
    ({"X-LLM-Provider": "openai"}, "Choose a model"),
    ({"X-LLM-Provider": "openai", "X-LLM-Model": "gpt-5"}, "API key"),
    ({"X-LLM-Provider": "custom", "X-LLM-Model": "m", "X-LLM-API-Key": "k"}, "base URL"),
    ({"X-LLM-Provider": "custom", "X-LLM-Model": "m", "X-LLM-API-Key": "k", "X-LLM-Base-URL": "file:///etc/passwd"},
     "http(s)"),
    ({"X-LLM-Provider": "openai", "X-LLM-Model": "m", "X-LLM-API-Key": "k", "X-LLM-Temperature": "hot"}, "number"),
])
def test_bad_browser_model_settings_are_400(client, headers, message):
    res = client.post("/missions/start", json={"goal": "x"}, headers=headers)
    assert res.status_code == 400 and message in res.json()["detail"]


def test_deployed_blocks_private_base_urls(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    for url in ("http://example.com/v1", "https://127.0.0.1/v1", "https://169.254.169.254/v1"):
        assert client.post("/model/test", headers=_llm_headers(url)).status_code == 400, url
    monkeypatch.setenv("LLM_CLIENT_ALLOW_PRIVATE_HOSTS", "true")
    assert client.post("/model/test", headers=_llm_headers("http://127.0.0.1:9/v1")).status_code == 200


def test_owner_can_disable_browser_model_settings(client, monkeypatch, fake_openai):
    monkeypatch.setenv("LLM_CLIENT_CONFIG", "false")
    res = client.post("/model/test", headers=_llm_headers(fake_openai["base_url"])).json()
    assert res["ok"] is True and not fake_openai["seen"]


def test_shared_server_key_is_opt_in(client, monkeypatch, fake_openai):
    headers = _llm_headers(fake_openai["base_url"], key="")
    assert client.post("/model/test", headers=headers).status_code == 400
    monkeypatch.setenv("LLM_CLIENT_CAN_USE_SERVER_KEY", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-server-owned-456")
    assert client.post("/model/test", headers=headers).json()["ok"] is True
    assert fake_openai["seen"][-1]["auth"] == "Bearer sk-server-owned-456"


def test_mock_provider_needs_no_key(client):
    assert client.post("/model/test", headers={"X-LLM-Provider": "mock"}).json()["ok"] is True
