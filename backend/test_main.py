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


# --- Any provider / any model -----------------------------------------------
_LLM_ENV = (
    "LLM_MODEL", "LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY",
    "AI_GATEWAY_API_KEY", "LLM_TEMPERATURE",
)


def _clear_llm_env(monkeypatch):
    for key in _LLM_ENV:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(
    "env, expected",
    [
        # Native provider, inferred from the model name.
        ({"LLM_MODEL": "gpt-4o-mini"}, {"model": "gpt-4o-mini", "provider": None, "base_url": None, "via": "provider"}),
        # Explicit provider.
        ({"LLM_MODEL": "claude-sonnet-4-5", "LLM_PROVIDER": "anthropic"},
         {"model": "claude-sonnet-4-5", "provider": "anthropic", "via": "provider"}),
        # "provider:model" carries its own provider.
        ({"LLM_MODEL": "google_genai:gemini-2.5-flash"},
         {"model": "google_genai:gemini-2.5-flash", "provider": None, "via": "provider"}),
        # Any OpenAI-compatible endpoint → openai provider + that base URL.
        ({"LLM_MODEL": "meta-llama/llama-3.3-70b-instruct", "LLM_BASE_URL": "https://openrouter.ai/api/v1", "LLM_API_KEY": "k"},
         {"provider": "openai", "base_url": "https://openrouter.ai/api/v1", "api_key": "k", "via": "openai-compatible"}),
        # Vercel AI Gateway shorthand: one key, any provider's model.
        ({"AI_GATEWAY_API_KEY": "gw", "LLM_MODEL": "anthropic/claude-sonnet-4.6"},
         {"provider": "openai", "base_url": "https://ai-gateway.vercel.sh/v1", "api_key": "gw", "via": "vercel-ai-gateway"}),
        # Gateway with no model → a sensible gateway-style default.
        ({"AI_GATEWAY_API_KEY": "gw"}, {"model": "openai/gpt-4o-mini", "via": "vercel-ai-gateway"}),
        # An explicit endpoint wins over the gateway; LLM_PROVIDER can pick a non-OpenAI wire format.
        ({"AI_GATEWAY_API_KEY": "gw", "LLM_BASE_URL": "https://proxy.example/v1", "LLM_PROVIDER": "anthropic", "LLM_MODEL": "claude-x"},
         {"provider": "anthropic", "base_url": "https://proxy.example/v1", "via": "openai-compatible"}),
    ],
)
def test_resolve_model_config(monkeypatch, env, expected):
    import llm

    _clear_llm_env(monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    cfg = llm.resolve_model_config()
    for key, value in expected.items():
        assert cfg[key] == value, (key, cfg)


def test_any_provider_constructs_real_models(monkeypatch):
    """Each config path builds the right LangChain chat model (no network)."""
    import llm

    monkeypatch.delenv("USE_MOCK_LLM", raising=False)
    cases = [
        ({"LLM_MODEL": "gpt-4o-mini", "OPENAI_API_KEY": "sk-x"}, "ChatOpenAI"),
        ({"LLM_MODEL": "anthropic:claude-sonnet-4-5", "ANTHROPIC_API_KEY": "sk-x"}, "ChatAnthropic"),
        ({"LLM_MODEL": "gemini-2.5-flash", "LLM_PROVIDER": "google_genai", "GOOGLE_API_KEY": "x"}, "ChatGoogleGenerativeAI"),
        ({"LLM_MODEL": "llama3.2", "LLM_BASE_URL": "http://localhost:11434/v1", "LLM_API_KEY": "ollama"}, "ChatOpenAI"),
        ({"AI_GATEWAY_API_KEY": "gw", "LLM_MODEL": "xai/grok-4"}, "ChatOpenAI"),
    ]
    for env, cls in cases:
        _clear_llm_env(monkeypatch)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        model = llm.get_llm()
        assert type(model).__name__ == cls, (env, type(model).__name__)
        assert llm.model_status()["error"] is None


def test_temperature_only_sent_when_configured(monkeypatch):
    """Reasoning models reject non-default temperatures, so don't force one."""
    import llm

    monkeypatch.delenv("USE_MOCK_LLM", raising=False)
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    assert llm.get_llm().temperature is None
    monkeypatch.setenv("LLM_TEMPERATURE", "0.2")
    assert llm.get_llm().temperature == 0.2


def test_bad_model_config_is_surfaced_not_silent(monkeypatch):
    """A configured-but-broken model falls back to the mock *and says so*."""
    import llm

    monkeypatch.delenv("USE_MOCK_LLM", raising=False)
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "some-model")
    monkeypatch.setenv("LLM_PROVIDER", "definitely-not-a-provider")
    monkeypatch.setenv("LLM_API_KEY", "super-secret-key")
    assert isinstance(llm.get_llm(), llm.MockChatModel)
    status = llm.model_status()
    assert status["mock"] is True and status["error"]
    assert "super-secret-key" not in repr(status)  # never leak the key
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    llm.get_llm()


# --- Durable state across (serverless) instances ----------------------------
def test_resuming_unknown_thread_is_404_with_hint(client):
    resp = client.post("/agent/decide", json={"thread_id": "gone", "decisions": {"x": {"type": "approve"}}})
    assert resp.status_code == 404
    assert "DATABASE_URL" in resp.json()["detail"]  # tells you how to fix it
    resp = client.post("/resume", json={"thread_id": "gone", "choice": "proceed"})
    assert resp.status_code == 404


def test_in_memory_state_does_not_survive_a_new_instance():
    """The failure mode Postgres fixes: a fresh instance can't see the pause."""
    first = TestClient(app)
    with first:
        events = _sse(first, "POST", "/agent/start", json={"message": "research tides"})
        thread_id = next(e["thread_id"] for e in events if e["type"] == "thread")
    with TestClient(app) as second:  # new lifespan = new in-memory saver
        resp = second.post("/agent/decide", json={"thread_id": thread_id, "decisions": {"x": {"type": "approve"}}})
        assert resp.status_code == 404


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL to run")
def test_postgres_state_survives_across_instances(monkeypatch):
    """Pause on one instance, resume on another — what Vercel needs."""
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    with TestClient(app) as instance_a:
        assert instance_a.get("/capabilities").json()["persistence"]["multi_instance_safe"] is True
        events = _sse(instance_a, "POST", "/agent/start", json={"message": "research tides"})
        thread_id = next(e["thread_id"] for e in events if e["type"] == "thread")
        req = next(e for e in events if e["type"] == "state")["tool_requests"][0]
        wf_thread = instance_a.post("/start", json={"message": "compare batteries"}).json()["thread_id"]

    with TestClient(app) as instance_b:  # fresh lifespan, fresh pool — only Postgres is shared
        resumed = _sse(
            instance_b,
            "POST",
            "/agent/decide",
            json={"thread_id": thread_id, "decisions": {req["interrupt_id"]: {"type": "approve"}}},
        )
        state = [e for e in resumed if e["type"] == "state"][-1]
        assert state["requires_input"] is False and state["final_response"]
        wf = instance_b.post("/resume", json={"thread_id": wf_thread, "choice": "simplified"})
        assert wf.status_code == 200


def test_rate_limiter_off_by_default_and_configurable(monkeypatch):
    """LLM_REQUESTS_PER_SECOND builds a throttling limiter (free-tier friendly)."""
    import llm

    monkeypatch.delenv("LLM_REQUESTS_PER_SECOND", raising=False)
    assert llm.requests_per_second() is None
    assert llm._build_rate_limiter() is None

    monkeypatch.setenv("LLM_REQUESTS_PER_SECOND", "2")
    assert llm.requests_per_second() == 2.0
    limiter = llm._build_rate_limiter()
    assert limiter is not None and limiter.requests_per_second == 2.0

    # Invalid / non-positive values disable it rather than crashing.
    monkeypatch.setenv("LLM_REQUESTS_PER_SECOND", "not-a-number")
    assert llm.requests_per_second() is None
    monkeypatch.setenv("LLM_REQUESTS_PER_SECOND", "0")
    assert llm.requests_per_second() is None


def test_cancel_unknown_thread_is_a_noop(client):
    """Cancelling a thread with no in-flight run reports it cleanly (no 500)."""
    resp = client.post("/cancel", json={"thread_id": "no-such-thread"})
    assert resp.status_code == 200
    assert resp.json()["cancelled"] is False


def test_graceful_cancel_drains_run_and_keeps_it_resumable():
    """A cancelled run stops at a superstep boundary and stays resumable."""
    import asyncio

    import run_control

    if not run_control.CANCEL_SUPPORTED:  # pragma: no cover
        pytest.skip("LangGraph without RunControl")

    from langgraph.checkpoint.memory import MemorySaver

    import graph as graph_module

    async def scenario():
        # Slow the sub-researchers so the drain lands mid-run.
        original = graph_module.sub_researcher

        async def slow_sub_researcher(state):
            await asyncio.sleep(1.0)
            return await original(state)

        graph_module.sub_researcher = slow_sub_researcher
        try:
            g = graph_module.build_research_graph(checkpointer=MemorySaver())
            thread_id = "cancel-test"
            config = {"configurable": {"thread_id": thread_id}}
            await g.ainvoke(
                {"user_query": "cancel me", "messages": []}, config
            )  # runs to the first interrupt

            async def cancel_soon():
                # Land the request *during* the slow sub-researcher superstep;
                # the drain then fires once that superstep completes.
                await asyncio.sleep(0.3)
                run_control.request_cancel(thread_id, "test cancel")

            asyncio.create_task(cancel_soon())
            events = [
                e
                async for e in graph_module.stream_research_response(
                    g, thread_id, "proceed", config
                )
            ]
        finally:
            graph_module.sub_researcher = original

        assert any(e["type"] == "cancelled" for e in events), "expected a cancelled event"
        state = next(e for e in events if e["type"] == "state")
        assert state["cancelled"] is True
        assert state["resumable"] is True  # checkpointed — can be picked up later
        # The control is released so the thread isn't stuck "cancelling".
        assert run_control.is_active(thread_id) is False

    asyncio.run(scenario())


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


def test_research_subquery_cap(client, monkeypatch):
    """RESEARCH_MAX_SUBQUERIES caps parallel sub-researchers (rate-limit friendly)."""
    monkeypatch.setenv("RESEARCH_MAX_SUBQUERIES", "1")
    thread_id = client.post("/start", json={"message": "cap test"}).json()["thread_id"]
    events = _sse(client, "POST", "/stream", json={"thread_id": thread_id, "choice": "proceed"})
    state = next(e for e in events if e.get("type") == "state")
    assert len(state["sub_queries"]) == 1  # would be 4 without the cap


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
    req = state["tool_requests"][0]
    assert req["name"] == "web_search"
    # Per-call HITL (langchain >= 1.4.6): each interrupt has an id, its own
    # allowed decisions, and a JSON response_schema the UI can build a form from.
    assert state["interrupt_mode"] == "per_call"
    assert req["interrupt_id"]
    assert "approve" in req["allowed"] and "edit" in req["allowed"]
    assert "web_search" in req["response_schema"]["$defs"]  # tool arg schema for edits


def _approve_by_id(client, path, thread_id, state, decision=None):
    """Resume a per-call interrupt, keyed by its id."""
    req = state["tool_requests"][0]
    return _sse(
        client,
        "POST",
        path,
        json={"thread_id": thread_id, "decisions": {req["interrupt_id"]: decision or {"type": "approve"}}},
    )


def test_agent_approve_completes(client):
    events = _sse(client, "POST", "/agent/start", json={"message": "research wind"})
    thread_id = next(e["thread_id"] for e in events if e["type"] == "thread")
    pending = next(e for e in events if e["type"] == "state")
    resumed = _approve_by_id(client, "/agent/decide", thread_id, pending)
    state = next(e for e in resumed if e["type"] == "state")
    assert state["requires_input"] is False
    assert state["final_response"]
    # The web_search tool streams live progress once approved (get_stream_writer).
    progress = [e.get("message", "") for e in resumed if e.get("type") == "progress"]
    assert any("Searching the web" in m for m in progress)


def test_agent_edit_tool_args(client):
    """Edits are validated against the tool's own argument schema, then run."""
    events = _sse(client, "POST", "/agent/start", json={"message": "research solar"})
    thread_id = next(e["thread_id"] for e in events if e["type"] == "thread")
    pending = next(e for e in events if e["type"] == "state")
    resumed = _approve_by_id(
        client,
        "/agent/decide",
        thread_id,
        pending,
        {"type": "edit", "edited_action": {"name": "web_search", "args": {"query": "edited"}}},
    )
    state = next(e for e in resumed if e["type"] == "state")
    assert state["requires_input"] is False
    assert not [e for e in resumed if e.get("type") == "error"]


def test_agent_batched_mode_still_supported():
    """HITL_INTERRUPT_MODE=batched keeps the one-interrupt-per-turn contract."""
    import asyncio

    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command

    from agent import build_agent, stream_agent_response

    async def run():
        graph = build_agent(checkpointer=MemorySaver(), interrupt_mode="batched")
        config = {"configurable": {"thread_id": "batched-1"}}
        first = [
            e
            async for e in stream_agent_response(
                graph, "batched-1", {"messages": [{"role": "user", "content": "research x"}]}, config
            )
        ]
        state = next(e for e in first if e["type"] == "state")
        assert state["interrupt_mode"] == "batched"
        assert state["tool_requests"][0]["interrupt_id"] is None
        second = [
            e
            async for e in stream_agent_response(
                graph, "batched-1", Command(resume={"decisions": [{"type": "approve"}]}), config
            )
        ]
        assert [e for e in second if e["type"] == "state"][-1]["requires_input"] is False

    asyncio.run(run())


# --- Approval policy (which tools pause, and when) --------------------------
def test_approval_policy_default_gates_actions_not_reads(monkeypatch):
    import approval_policy as ap

    monkeypatch.delenv("HITL_POLICY", raising=False)
    rules = ap.build_interrupt_on(["web_search", "execute", "delete", "ls", "read_file", "write_todos"])
    # Read-only / planning tools never pause; anything that acts does.
    for name in ("ls", "read_file", "write_todos"):
        assert rules[name] is False
    for name in ("web_search", "execute", "delete"):
        assert rules[name] is not False
        assert rules[name].get("when") is None  # unconditional in `all` mode


def test_approval_policy_selective_pauses_only_on_risky_args(monkeypatch):
    from types import SimpleNamespace

    import approval_policy as ap

    monkeypatch.setenv("HITL_POLICY", "selective")
    rules = ap.build_interrupt_on(["web_search", "execute"])
    assert rules["execute"].get("when") is None  # always gated
    when = rules["web_search"]["when"]  # gated only when args look sensitive
    risky = SimpleNamespace(tool_call={"name": "web_search", "args": {"query": "reset my password"}})
    benign = SimpleNamespace(tool_call={"name": "web_search", "args": {"query": "tide tables"}})
    assert when(risky) is True
    assert when(benign) is False


# --- Risk classifiers (pattern default; Jev decision model, no key needed) ----
class _StubJev:
    """Stands in for langgraph_jev.JevRunnable: returns a canned JevResult."""

    def __init__(self, value: bool, confidence: float):
        self.value, self.confidence = value, confidence
        self.calls: list[dict] = []

    def invoke(self, state, config=None, **kw):
        # langgraph-jev is an optional dependency: skip these tests without it.
        lj = pytest.importorskip("langgraph_jev")

        self.calls.append(state)
        return lj.JevResult(
            model="jev",
            decisions={
                "risky": lj.JevDecision(
                    field="risky", type="boolean", value=self.value, confidence=self.confidence
                )
            },
            requires_review=False,
        )


def test_jev_classifier_pauses_when_risky_or_unsure():
    import approval_policy as ap

    risky = ap.JevRiskClassifier(runnable=_StubJev(True, 0.91), threshold=0.75)
    v = risky.classify("web_search", {"query": "wire $5000"})
    assert v.risky is True and v.source == "jev" and v.confidence == 0.91

    unsure = ap.JevRiskClassifier(runnable=_StubJev(False, 0.4), threshold=0.75)
    v = unsure.classify("web_search", {"query": "hmm"})
    assert v.risky is True and "low confidence" in v.reason  # uncertainty → human

    safe = ap.JevRiskClassifier(runnable=_StubJev(False, 0.95), threshold=0.75)
    v = safe.classify("web_search", {"query": "tide tables"})
    assert v.risky is False and v.reason == "looks safe"


def test_jev_classifier_falls_back_to_patterns_on_api_error():
    import approval_policy as ap

    class Boom:
        def invoke(self, *a, **k):
            raise RuntimeError("503 from the gate")

    clf = ap.JevRiskClassifier(runnable=Boom())
    v = clf.classify("web_search", {"query": "reset my password"})
    assert v.risky is True and v.source == "jev→patterns"  # regex still caught it


def test_jev_mode_without_key_degrades_to_patterns(monkeypatch):
    import approval_policy as ap

    monkeypatch.setenv("HITL_RISK_CLASSIFIER", "jev")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert ap.get_risk_classifier().name == "patterns"  # no crash, no key needed


def test_selective_policy_records_verdict_for_the_card(monkeypatch):
    from types import SimpleNamespace

    import approval_policy as ap

    monkeypatch.setenv("HITL_POLICY", "selective")
    stub = _StubJev(True, 0.88)
    rules = ap.build_interrupt_on(["web_search"], classifier=ap.JevRiskClassifier(runnable=stub))
    when = rules["web_search"]["when"]
    req = SimpleNamespace(tool_call={"id": "call_42", "name": "web_search", "args": {"query": "x"}})
    assert when(req) is True
    assert stub.calls[0] == {"tool": "web_search", "arguments": {"query": "x"}}
    verdict = ap.verdict_for("call_42")
    assert verdict and verdict["source"] == "jev" and verdict["confidence"] == 0.88


def test_deep_agent_restores_todos_and_gates_shell():
    """deepagents 0.7 dropped write_todos and added shell/delete tools."""
    from langgraph.checkpoint.memory import MemorySaver

    import approval_policy as ap
    from deep_agent import DEEP_TOOL_NAMES, build_deep_agent

    graph = build_deep_agent(checkpointer=MemorySaver())
    names = set(graph.nodes["tools"].bound.tools_by_name)
    assert "write_todos" in names  # planning restored explicitly
    assert {"execute", "delete"} <= names  # the new risky tools exist...
    rules = ap.build_interrupt_on(DEEP_TOOL_NAMES)
    assert rules["execute"] is not False and rules["delete"] is not False  # ...and are gated
    assert rules["ls"] is False


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


# --- Model chosen in the UI (X-LLM-* headers) --------------------------------
@pytest.fixture()
def fake_openai():
    """A tiny OpenAI-compatible server that records what it was sent."""
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append({"auth": self.headers.get("Authorization"), "model": body.get("model")})
            text = "OK from the browser-chosen model"
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for chunk in (
                    {"choices": [{"index": 0, "delta": {"role": "assistant", "content": text}}]},
                    {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                ):
                    payload = {"id": "c1", "object": "chat.completion.chunk", "created": 0,
                               "model": body.get("model"), **chunk}
                    self.wfile.write(f"data: {_json.dumps(payload)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                return
            payload = _json.dumps({
                "id": "c1", "object": "chat.completion", "created": 0, "model": body.get("model"),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }).encode()
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
    return {"X-LLM-Provider": "custom", "X-LLM-Model": model,
            "X-LLM-API-Key": key, "X-LLM-Base-URL": base_url}


def test_model_providers_lists_presets_without_secrets(client):
    data = client.get("/model/providers").json()
    ids = {p["id"] for p in data["providers"]}
    assert {"gateway", "openai", "anthropic", "google", "custom", "mock"} <= ids
    assert all("env_key" not in p and "model_provider" not in p for p in data["providers"])
    assert data["policy"]["enabled"] is True
    assert data["policy"]["server_key_shared"] is False
    assert "client_config" in client.get("/capabilities").json()["model"]


def test_model_test_uses_browser_model_and_key(client, fake_openai):
    res = client.post("/model/test", headers=_llm_headers(fake_openai["base_url"])).json()
    assert res["ok"] is True, res
    assert "OK" in res["sample"]
    assert fake_openai["seen"][-1] == {"auth": "Bearer sk-browser-secret-123", "model": "my-model"}


def test_model_test_failure_does_not_leak_key(client):
    # Nothing listens on port 9: the error must come back without the key in it.
    res = client.post("/model/test", headers=_llm_headers("http://127.0.0.1:9/v1")).json()
    assert res["ok"] is False
    assert "sk-browser-secret-123" not in str(res)


def test_browser_model_drives_the_agent(client, fake_openai):
    # Server runs on the mock; the request's headers switch this run to the
    # visitor's model. The fake model answers without calling tools.
    events = _sse(client, "POST", "/agent/start", json={"message": "hello"},
                  headers=_llm_headers(fake_openai["base_url"]))
    assert fake_openai["seen"], events
    assert all(s["model"] == "my-model" for s in fake_openai["seen"])
    state = next(e for e in events if e["type"] == "state")
    assert "browser-chosen" in state["final_response"]
    # And the server default is untouched for everyone else.
    assert client.get("/capabilities").json()["model"]["mock"] is True


def test_browser_model_drives_the_workflow(client, fake_openai):
    headers = _llm_headers(fake_openai["base_url"])
    res = client.post("/start", json={"message": "solar"}, headers=headers)
    assert res.status_code == 200
    events = _sse(client, "POST", "/stream", headers=headers,
                  json={"thread_id": res.json()["thread_id"], "choice": "proceed"})
    assert fake_openai["seen"], events
    assert not any(e.get("type") == "error" for e in events), events


@pytest.mark.parametrize(
    "headers, message",
    [
        ({"X-LLM-Provider": "nope"}, "Unknown provider"),
        ({"X-LLM-Provider": "openai"}, "Choose a model"),
        ({"X-LLM-Provider": "openai", "X-LLM-Model": "gpt-5"}, "API key"),
        ({"X-LLM-Provider": "custom", "X-LLM-Model": "m", "X-LLM-API-Key": "k"}, "base URL"),
        ({"X-LLM-Provider": "custom", "X-LLM-Model": "m", "X-LLM-API-Key": "k",
          "X-LLM-Base-URL": "file:///etc/passwd"}, "http(s)"),
        ({"X-LLM-Provider": "openai", "X-LLM-Model": "m", "X-LLM-API-Key": "k",
          "X-LLM-Temperature": "hot"}, "number"),
    ],
)
def test_bad_browser_model_settings_are_400(client, headers, message):
    res = client.post("/start", json={"message": "x"}, headers=headers)
    assert res.status_code == 400
    assert message in res.json()["detail"]


def test_deployed_blocks_private_base_urls(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    for url in ("http://example.com/v1", "https://127.0.0.1/v1", "https://169.254.169.254/v1"):
        res = client.post("/model/test", headers=_llm_headers(url))
        assert res.status_code == 400, url
    monkeypatch.setenv("LLM_CLIENT_ALLOW_PRIVATE_HOSTS", "true")
    assert client.post("/model/test", headers=_llm_headers("http://127.0.0.1:9/v1")).status_code == 200


def test_owner_can_disable_browser_model_settings(client, monkeypatch, fake_openai):
    monkeypatch.setenv("LLM_CLIENT_CONFIG", "false")
    res = client.post("/model/test", headers=_llm_headers(fake_openai["base_url"])).json()
    assert res["ok"] is True and not fake_openai["seen"]  # server model (mock) answered


def test_shared_server_key_is_opt_in(client, monkeypatch, fake_openai):
    headers = _llm_headers(fake_openai["base_url"], key="")
    assert client.post("/model/test", headers=headers).status_code == 400
    monkeypatch.setenv("LLM_CLIENT_CAN_USE_SERVER_KEY", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-server-owned-456")
    assert client.post("/model/test", headers=headers).json()["ok"] is True
    assert fake_openai["seen"][-1]["auth"] == "Bearer sk-server-owned-456"


def test_mock_provider_needs_no_key(client):
    res = client.post("/model/test", headers={"X-LLM-Provider": "mock"}).json()
    assert res["ok"] is True


def test_rate_limiter_is_shared_across_calls(monkeypatch):
    import llm

    monkeypatch.setenv("LLM_REQUESTS_PER_SECOND", "2")
    assert llm._build_rate_limiter() is llm._build_rate_limiter()


def test_browser_model_drives_the_deep_agent(client, fake_openai):
    events = _sse(client, "POST", "/deep/start", json={"message": "hello"},
                  headers=_llm_headers(fake_openai["base_url"]))
    assert fake_openai["seen"], events
    assert all(s["model"] == "my-model" for s in fake_openai["seen"])
    state = next(e for e in events if e["type"] == "state")
    assert "browser-chosen" in state["final_response"]
