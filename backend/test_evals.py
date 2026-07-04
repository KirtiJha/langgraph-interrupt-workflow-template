"""Tests for the evaluation harness (offline, mock model)."""

import os

os.environ.setdefault("USE_MOCK_LLM", "true")

from evals.dataset import DATASET
from evals.run_evals import (
    completed,
    evaluate_local,
    no_pii_leak,
    paused_for_approval,
)


# --- Evaluator unit tests (deterministic, no agent run) ---------------------
def test_paused_for_approval_scoring():
    ex = {"expects_tool": "web_search"}
    assert paused_for_approval(ex, {"paused": True, "tool": "web_search"}) == 1.0
    assert paused_for_approval(ex, {"paused": False, "tool": None}) == 0.0
    assert paused_for_approval(ex, {"paused": True, "tool": "other"}) == 0.0


def test_completed_scoring():
    assert completed({}, {"answer": "an answer", "error": None}) == 1.0
    assert completed({}, {"answer": "", "error": None}) == 0.0
    assert completed({}, {"answer": "x", "error": "boom"}) == 0.0


def test_no_pii_leak_scoring():
    assert no_pii_leak({}, {"answer": "clean answer with no PII"}) == 1.0
    assert no_pii_leak({}, {"answer": "reach me at a@b.com"}) == 0.0


# --- Integration: run the agent through the harness offline -----------------
def test_evaluate_local_offline():
    report = evaluate_local(limit=2)
    assert report["n"] == 2
    # The agent should pause for approval and complete on every example.
    assert report["summary"]["paused_for_approval"] == 1.0
    assert report["summary"]["completed"] == 1.0
    assert report["summary"]["no_pii_leak"] == 1.0
    # The LLM-judge metric is skipped on the mock model.
    assert "correctness" not in report["summary"]


def test_dataset_is_well_formed():
    for ex in DATASET:
        assert ex["question"] and ex["reference"] and ex["expects_tool"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
