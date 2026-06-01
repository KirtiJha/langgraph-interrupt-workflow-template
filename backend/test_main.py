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
