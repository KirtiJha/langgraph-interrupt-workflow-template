"""
Basic tests for the LangGraph interrupt functionality.
Run with: python -m pytest
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from main import app

client = TestClient(app)


def test_root_endpoint():
    """Test that the API is running."""
    # Since we don't have a root endpoint, test the docs
    response = client.get("/docs")
    assert response.status_code == 200


def test_start_chat_endpoint():
    """Test starting a new chat conversation."""
    test_message = "What is quantum computing?"

    response = client.post("/start", json={"message": test_message})

    # Should return successfully
    assert response.status_code == 200

    data = response.json()

    # Should have required fields
    assert "thread_id" in data
    assert "state" in data
    assert "requires_input" in data

    # Thread ID should be a string
    assert isinstance(data["thread_id"], str)
    assert len(data["thread_id"]) > 0


def test_get_state_invalid_thread():
    """Test getting state for invalid thread ID."""
    response = client.get("/get_state/invalid-thread-id")
    assert response.status_code == 404


def test_resume_invalid_thread():
    """Test resuming with invalid thread ID."""
    response = client.post(
        "/resume", json={"thread_id": "invalid-thread-id", "choice": "proceed"}
    )
    assert response.status_code == 500  # Should handle gracefully


def test_conversation_history_invalid_thread():
    """Test getting conversation history for invalid thread."""
    response = client.get("/conversation_history/invalid-thread-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_interrupt_flow():
    """Test the complete interrupt flow."""
    # Start a conversation
    start_response = client.post(
        "/start", json={"message": "Test query for interrupts"}
    )

    assert start_response.status_code == 200
    start_data = start_response.json()
    thread_id = start_data["thread_id"]

    # Should have an interrupt waiting
    assert start_data["requires_input"] is True
    assert "interrupt_message" in start_data

    # Get current state
    state_response = client.get(f"/get_state/{thread_id}")
    assert state_response.status_code == 200

    # Resume with a choice
    resume_response = client.post(
        "/resume", json={"thread_id": thread_id, "choice": "proceed"}
    )

    assert resume_response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__])
