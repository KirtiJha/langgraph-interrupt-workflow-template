"""Tests for the evaluation harness (offline, scripted pilot)."""

import os

os.environ.setdefault("USE_MOCK_LLM", "true")

from evals.dataset import DATASET
from evals.run_evals import (
    asked_before_acting,
    budget_respected,
    completed,
    evaluate_local,
    no_forbidden_actions,
    no_pii_leak,
)


def test_evaluator_scoring():
    ex = {"expects_tools": ["book"], "forbidden": [{"tool": "book", "arg": "vendor", "contains": "Brasa"}],
          "budget": 100}
    ok = {"asked": ["c1"], "executed": [{"id": "c1", "name": "book", "args": {"vendor": "Olive"}}],
          "report": {"summary": "done"}, "spent": 50, "closing": "clean"}
    assert asked_before_acting(ex, ok) == 1.0
    assert asked_before_acting(ex, {**ok, "asked": []}) == 0.0
    assert completed(ex, ok) == 1.0 and completed(ex, {**ok, "report": None}) == 0.0
    assert no_forbidden_actions(ex, ok) == 1.0
    assert no_forbidden_actions(ex, {**ok, "executed": [{"id": "c1", "name": "book", "args": {"vendor": "Brasa"}}]}) == 0.0
    assert budget_respected(ex, ok) == 1.0 and budget_respected(ex, {**ok, "spent": 150}) == 0.0
    assert no_pii_leak(ex, ok) == 1.0 and no_pii_leak(ex, {**ok, "closing": "card 4111 1111 1111 1111"}) == 0.0


def test_every_starter_mission_scores_perfectly_offline():
    report = evaluate_local()
    assert report["n"] == len(DATASET)
    for metric, value in report["summary"].items():
        assert value == 1.0, (metric, report["results"])
    assert "report_quality" not in report["summary"]  # judge skipped on the pilot


def test_dataset_is_well_formed():
    for ex in DATASET:
        assert ex["goal"] and ex["reference"] and ex["expects_tools"]
