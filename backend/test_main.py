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


def test_text_of_normalizes_block_content():
    """Newer models (Gemini 3.x, Claude thinking) return content as blocks."""
    from llm import text_of

    assert text_of("plain string") == "plain string"
    assert text_of(None) == ""
    # Gemini-style content blocks -> flattened text (non-text blocks dropped).
    blocks = [
        {"type": "text", "text": "Hello "},
        {"type": "thinking", "thinking": "ignore me"},
        {"type": "text", "text": "world"},
    ]
    assert text_of(blocks) == "Hello world"
    assert text_of(["a", "b"]) == "ab"


def test_capabilities_reports_active_features(client):
    caps = client.get("/capabilities").json()
    # Offline defaults: mock model, guardrails on, no MCP, no semantic memory.
    assert caps["model"]["mock"] is True
    assert caps["guardrails"]["enabled"] is True
    assert caps["guardrails"]["redact_pii"] is True
    assert caps["structured_output"] is False
    assert caps["semantic_memory"] is False
    assert caps["mcp"]["enabled"] is False
    assert caps["mcp"]["tools"] == []
    # Deep Agent engine is reported (installed, but "unavailable" on the mock model).
    assert "deep_agent" in caps
    assert caps["deep_agent"]["available"] is False  # mock model
    assert caps["deep_agent"]["reason"]
    # Middleware power-pack + resilience are reported for the UI status strip.
    assert "human_in_the_loop" in caps["middleware"]
    assert any("model_call_limit" in m for m in caps["middleware"])
    assert caps["resilience"]["retry_max_attempts"] >= 1
    assert caps["resilience"]["compensation"] is True


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


# --- Guardrail middleware (PII redaction + blocklist) -----------------------
def test_guardrail_redacts_pii_before_model(client):
    """The agent's tool call should only ever see masked PII."""
    events = _sse(
        client,
        "POST",
        "/agent/start",
        json={"message": "research fuel cells, email me at jane@acme.com or 415-555-2671"},
    )
    state = next(e for e in events if e["type"] == "state")
    query = state["tool_requests"][0]["args"]["query"]
    assert "jane@acme.com" not in query
    assert "[EMAIL]" in query
    assert "[PHONE]" in query


def test_guardrail_unit_redaction():
    from guardrails import _redact

    cleaned, count = _redact("mail a@b.com, ssn 123-45-6789")
    assert count == 2
    assert "[EMAIL]" in cleaned and "[SSN]" in cleaned


def test_guardrail_unit_blocklist():
    from langchain_core.messages import HumanMessage

    from guardrails import GuardrailMiddleware

    mw = GuardrailMiddleware(blocklist=["forbidden"])
    assert mw._blocked_phrase([HumanMessage(content="this is FORBIDDEN")]) == "forbidden"
    assert mw._blocked_phrase([HumanMessage(content="all good")]) is None


def test_guardrail_from_env_disabled(monkeypatch):
    from guardrails import GuardrailMiddleware

    monkeypatch.setenv("GUARDRAILS_ENABLED", "false")
    assert GuardrailMiddleware.from_env() is None


# --- MCP tools (optional, off by default) -----------------------------------
def test_mcp_tools_empty_when_unconfigured():
    import asyncio

    from mcp_tools import load_mcp_tools

    assert asyncio.run(load_mcp_tools()) == []


# --- Semantic memory store --------------------------------------------------
def test_build_store_plain_offline():
    from langgraph.store.memory import InMemoryStore

    from memory import build_store

    store = build_store()
    assert isinstance(store, InMemoryStore)
    # No embeddings configured → no vector index (plain, recency-based recall).
    assert getattr(store, "index_config", None) is None


# --- Structured output (opt-in) ---------------------------------------------
def test_structured_agent_builds():
    from agent import ResearchSummary, build_agent

    agent = build_agent(structured=True)
    assert agent is not None
    assert set(ResearchSummary.model_fields) == {
        "summary",
        "key_findings",
        "sources",
        "confidence",
    }


# --- Middleware power-pack --------------------------------------------------
def test_middleware_pack_defaults():
    from llm import get_llm
    from middleware_pack import build_middleware_pack

    middleware, names = build_middleware_pack(get_llm())
    assert len(middleware) == len(names)
    assert any("summarization" in n for n in names)
    assert any("model_call_limit" in n for n in names)
    assert any("model_retry" in n for n in names)


def test_tool_call_limit_opt_in(monkeypatch):
    from llm import get_llm
    from middleware_pack import build_middleware_pack

    monkeypatch.setenv("AGENT_TOOL_CALL_LIMIT", "5")
    _, names = build_middleware_pack(get_llm())
    assert any("tool_call_limit(5)" in n for n in names)


# --- Resilience layer (LangGraph 1.2) ---------------------------------------
def test_compensation_handlers_unit():
    import asyncio

    from graph import _analysis_fallback, _response_fallback

    cmd = asyncio.run(_analysis_fallback({"research_results": ["f1", "f2"]}))
    assert cmd.goto == "format_selection_interrupt"
    assert "(Automatic fallback)" in cmd.update["analysis"]

    cmd2 = asyncio.run(_response_fallback({"analysis": "A"}))
    assert cmd2.goto == "persist_memory"
    assert cmd2.update["final_response"]


def test_resilience_analysis_compensation(client, monkeypatch):
    """If the analysis node fails, the run degrades gracefully instead of 500ing."""
    import graph as g
    from llm import MockChatModel

    class FailAnalyst(MockChatModel):
        async def _agenerate(self, messages, stop=None, run_manager=None, **kw):
            if any("expert analyst" in str(getattr(m, "content", "")) for m in messages):
                raise ValueError("simulated analysis failure")
            return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kw)

    monkeypatch.setattr(g, "get_llm", lambda **k: FailAnalyst())

    thread_id = client.post("/start", json={"message": "resilience"}).json()["thread_id"]
    for choice in ["proceed", "technical", "executive"]:
        assert client.post("/resume", json={"thread_id": thread_id, "choice": choice}).status_code == 200

    final = client.get(f"/get_state/{thread_id}").json()
    assert final["requires_input"] is False
    assert final["state"]["final_response"]  # completed despite the failure
    assert "(Automatic fallback)" in final["state"]["analysis"]  # compensation ran


# --- Deep Agent engine (planning + subagents) -------------------------------
def test_deep_agent_builds_offline():
    from langgraph.checkpoint.memory import MemorySaver

    from deep_agent import build_deep_agent

    agent = build_deep_agent(checkpointer=MemorySaver())
    assert agent is not None  # compiles with subagents + HITL on the mock model


def test_deep_start_streams_and_completes(client):
    events = _sse(client, "POST", "/deep/start", json={"message": "compare batteries"})
    assert any(e["type"] == "thread" for e in events)
    state = next(e for e in events if e["type"] == "state")
    # On the mock model the deep agent completes with a basic answer.
    assert state["requires_input"] is False
    assert state["final_response"]


# --- AG-UI protocol adapter -------------------------------------------------
def test_agui_capability_and_endpoint(client):
    caps = client.get("/capabilities").json()
    assert "agui" in caps
    if caps["agui"]["enabled"]:
        # Endpoint is mounted and healthy; GET on the run path is 405 (POST-only).
        assert client.get(caps["agui"]["path"] + "/health").status_code == 200
        assert client.get(caps["agui"]["path"]).status_code == 405


def test_agui_graceful_without_package(monkeypatch):
    """The app boots and legacy endpoints work even if ag-ui-langgraph is absent."""
    import builtins
    import importlib
    import sys

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("ag_ui"):
            raise ImportError("simulated missing ag-ui-langgraph")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    for mod in ("agui", "main"):
        sys.modules.pop(mod, None)
    agui = importlib.import_module("agui")
    assert agui.AGUI_AVAILABLE is False
    from fastapi import FastAPI

    app = FastAPI()
    assert agui.mount_agui(app) is False  # no-op, no crash

    # Restore for the rest of the session.
    for mod in ("agui", "main"):
        sys.modules.pop(mod, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
