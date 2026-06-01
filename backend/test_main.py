"""Tests for the LangGraph interrupt workflow API.

Run with: USE_MOCK_LLM=true python -m pytest -v
The mock model keeps these tests fast and offline (no API keys required).
"""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("USE_MOCK_LLM", "true")

from main import app


@pytest.fixture()
def client():
    # `with` triggers the FastAPI lifespan so app.state.graph is built.
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_start_chat_creates_thread_and_interrupts(client):
    response = client.post("/start", json={"message": "What is quantum computing?"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["thread_id"], str) and data["thread_id"]
    assert data["requires_input"] is True
    assert data["interrupt_message"]


def test_get_state_invalid_thread(client):
    response = client.get("/get_state/invalid-thread-id")
    assert response.status_code == 404


def test_full_interrupt_flow_completes(client):
    start = client.post("/start", json={"message": "Explain interrupts"})
    thread_id = start.json()["thread_id"]

    # Resume through each interrupt until the workflow completes.
    for choice in ["proceed", "technical", "executive"]:
        resume = client.post("/resume", json={"thread_id": thread_id, "choice": choice})
        assert resume.status_code == 200

    final = client.get(f"/get_state/{thread_id}").json()
    assert final["requires_input"] is False
    assert final["state"]["final_response"]


def test_cancel_short_circuits(client):
    start = client.post("/start", json={"message": "anything"})
    thread_id = start.json()["thread_id"]
    resume = client.post("/resume", json={"thread_id": thread_id, "choice": "cancel"})
    assert resume.status_code == 200


# --- Helpers ----------------------------------------------------------------
def _sse(client, method, url, **kwargs):
    import json as _json

    events = []
    with client.stream(method, url, **kwargs) as response:
        for line in response.iter_lines():
            if line and line.startswith("data: "):
                events.append(_json.loads(line[6:]))
    return events


# --- Feature A: parallel research (Send) + progress streaming ---------------
def test_stream_resume_emits_progress(client):
    thread_id = client.post("/start", json={"message": "How do batteries work?"}).json()[
        "thread_id"
    ]
    events = _sse(client, "POST", "/stream", json={"thread_id": thread_id, "choice": "proceed"})
    types = {e.get("type") for e in events}
    assert "progress" in types  # parallel sub-researchers reported progress
    state_evt = next(e for e in events if e.get("type") == "state")
    assert len(state_evt["sub_queries"]) >= 2
    assert state_evt["requires_input"] is True  # paused at the direction interrupt


# --- Feature B: cross-thread long-term memory -------------------------------
def test_cross_session_memory(client):
    user = "memory-user"
    # Session 1: complete a full run.
    t1 = client.post("/start", json={"message": "batteries", "user_id": user}).json()["thread_id"]
    for choice in ["proceed", "technical", "executive"]:
        _sse(client, "POST", "/stream", json={"thread_id": t1, "choice": choice})
    # Session 2: a brand-new thread for the same user recalls prior memory.
    start2 = client.post("/start", json={"message": "solar panels", "user_id": user}).json()
    assert start2["state"].get("user_memory")


# --- Feature C: time travel (history + fork) --------------------------------
def test_history_and_fork(client):
    thread_id = client.post("/start", json={"message": "quantum"}).json()["thread_id"]
    _sse(client, "POST", "/stream", json={"thread_id": thread_id, "choice": "proceed"})

    history = client.get(f"/history/{thread_id}").json()["checkpoints"]
    assert len(history) > 1
    forkable = [c for c in history if c["has_interrupt"] and c["checkpoint_id"]]
    assert forkable, "expected at least one interrupt checkpoint to fork from"

    # Rewind to the earliest interrupt and choose a different path.
    checkpoint_id = forkable[-1]["checkpoint_id"]
    events = _sse(
        client,
        "POST",
        "/fork",
        json={"thread_id": thread_id, "checkpoint_id": checkpoint_id, "choice": "simplified"},
    )
    assert any(e.get("type") == "state" for e in events)


# --- Approval workflow ------------------------------------------------------
def test_approval_start_drafts_and_pauses(client):
    start = client.post("/approval/start", json={"task": "Write a welcome email"})
    assert start.status_code == 200
    data = start.json()
    assert data["thread_id"]
    assert data["requires_input"] is True
    assert data["draft"]
    assert data["status"] == "awaiting_review"


def test_approval_approve_sends(client):
    thread_id = client.post("/approval/start", json={"task": "Write a note"}).json()["thread_id"]
    decide = client.post(
        "/approval/decide", json={"thread_id": thread_id, "action": "approve"}
    )
    assert decide.status_code == 200
    data = decide.json()
    assert data["requires_input"] is False
    assert data["status"] == "sent"
    assert data["final_output"]


def test_approval_edit_uses_user_content(client):
    thread_id = client.post("/approval/start", json={"task": "Write a note"}).json()["thread_id"]
    edited = "This is my hand-edited final version."
    decide = client.post(
        "/approval/decide",
        json={"thread_id": thread_id, "action": "edit", "content": edited},
    )
    assert decide.status_code == 200
    data = decide.json()
    assert data["status"] == "sent"
    assert data["final_output"] == edited


# --- Agent engine (create_agent + HITL middleware) --------------------------
def test_agent_start_pauses_for_tool_approval(client):
    events = _sse(client, "POST", "/agent/start", json={"message": "research fuel cells"})
    assert any(e["type"] == "thread" for e in events)
    state = next(e for e in events if e["type"] == "state")
    assert state["requires_input"] is True
    assert state["tool_requests"][0]["name"] == "web_search"
    assert "approve" in state["allowed"] and "edit" in state["allowed"]


def test_agent_approve_completes(client):
    events = _sse(client, "POST", "/agent/start", json={"message": "research wind"})
    thread_id = next(e["thread_id"] for e in events if e["type"] == "thread")
    resumed = _sse(
        client,
        "POST",
        "/agent/decide",
        json={"thread_id": thread_id, "decisions": [{"type": "approve"}]},
    )
    state = next(e for e in resumed if e["type"] == "state")
    assert state["requires_input"] is False
    assert state["final_response"]


def test_agent_edit_tool_args(client):
    events = _sse(client, "POST", "/agent/start", json={"message": "research solar"})
    thread_id = next(e["thread_id"] for e in events if e["type"] == "thread")
    resumed = _sse(
        client,
        "POST",
        "/agent/decide",
        json={
            "thread_id": thread_id,
            "decisions": [
                {"type": "edit", "edited_action": {"name": "web_search", "args": {"query": "edited"}}}
            ],
        },
    )
    state = next(e for e in resumed if e["type"] == "state")
    assert state["requires_input"] is False


def test_approval_reject_redrafts_and_pauses_again(client):
    thread_id = client.post("/approval/start", json={"task": "Write a note"}).json()["thread_id"]
    decide = client.post(
        "/approval/decide",
        json={"thread_id": thread_id, "action": "reject", "feedback": "Make it shorter"},
    )
    assert decide.status_code == 200
    data = decide.json()
    # After a reject, a new draft is produced and we pause for review again.
    assert data["requires_input"] is True
    assert data["revision_count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
