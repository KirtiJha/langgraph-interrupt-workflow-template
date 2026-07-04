# 📊 Evaluating the agent

A human-in-the-loop agent has to be judged on two things: **is the answer good**,
and **did it pause for approval before acting**? The harness in
[`backend/evals/`](../backend/evals) scores both.

## Quick start (offline, no API keys)

```bash
cd backend
python -m evals.run_evals
```

This runs every example in [`evals/dataset.py`](../backend/evals/dataset.py)
through the agent (auto-approving tool calls) and prints a scored table:

```
=== Eval results ===
  solid-state-batteries    paused_for_approval=1.00  completed=1.00  no_pii_leak=1.00
  tcp-vs-udp               paused_for_approval=1.00  completed=1.00  no_pii_leak=1.00
  ...

=== Summary (mean) ===
  completed              1.000
  no_pii_leak            1.000
  paused_for_approval    1.000
```

## The evaluators

**Deterministic** (run offline with the mock model — no keys):

| Metric | What it checks |
|--------|----------------|
| `paused_for_approval` | The agent **interrupted for human approval** on the expected tool before running it — the behaviour this template exists to enforce. |
| `completed` | It produced a non-empty final answer without erroring. |
| `no_pii_leak` | The final answer contains no recognisable raw PII (pairs with the guardrail middleware). |

**Model-graded** (needs a real model):

| Metric | What it checks |
|--------|----------------|
| `correctness` | An **LLM-as-judge** score (0–1) comparing the answer to a reference. Automatically **skipped on the mock model**. |

Set a real model to include the judge:

```bash
LLM_MODEL=gpt-4o-mini OPENAI_API_KEY=sk-... python -m evals.run_evals
```

## Tracked experiments with LangSmith

To log results as a comparable experiment over time, set `LANGSMITH_API_KEY`
and run:

```bash
LANGSMITH_API_KEY=... LLM_MODEL=gpt-4o-mini OPENAI_API_KEY=sk-... \
  python -m evals.run_evals --langsmith
```

This creates (once) a `hitl-research-agent` dataset in your LangSmith workspace
and runs [`evaluate`](https://docs.smith.langchain.com/evaluation) against it, so
each run shows up as an experiment you can diff.

## Extending it

- **Add examples** — append to `DATASET` in `evals/dataset.py` with the
  questions that matter for your domain and the tool you expect the agent to
  pause on.
- **Add evaluators** — write a `fn(example, result) -> float` and register it in
  `DETERMINISTIC_EVALUATORS` (or add another model-graded one alongside
  `correctness`). Ideas: citation presence, answer length bounds, refusal on
  out-of-scope questions, latency budgets.
- **Wire into CI** — the deterministic metrics run offline, so you can gate a PR
  on, e.g., `paused_for_approval == 1.0` for every example.
