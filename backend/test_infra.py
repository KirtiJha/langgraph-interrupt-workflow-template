"""Infrastructure tests: model config, approval policy, guardrails, MCP (offline)."""

import os

import pytest

os.environ.setdefault("USE_MOCK_LLM", "true")

_LLM_ENV = (
    "LLM_MODEL", "LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY",
    "AI_GATEWAY_API_KEY", "LLM_TEMPERATURE",
)


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


def test_guardrail_unit_redaction():
    from guardrails import _redact

    cleaned, count = _redact("mail a@b.com, ssn 123-45-6789", emails=True)
    assert count == 2
    assert "[EMAIL]" in cleaned and "[SSN]" in cleaned
    # By default an acting agent keeps addresses (it needs them to send mail).
    cleaned, count = _redact("mail a@b.com, card 4111 1111 1111 1111")
    assert count == 1 and "a@b.com" in cleaned and "[CARD]" in cleaned


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


def test_mcp_tools_empty_when_unconfigured():
    import asyncio

    from mcp_tools import load_mcp_tools

    assert asyncio.run(load_mcp_tools()) == []


def test_rate_limiter_is_shared_across_calls(monkeypatch):
    import llm

    monkeypatch.setenv("LLM_REQUESTS_PER_SECOND", "2")
    assert llm._build_rate_limiter() is llm._build_rate_limiter()
