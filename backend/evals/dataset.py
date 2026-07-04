"""Evaluation dataset for the research agent.

Each example is a question plus lightweight expectations. ``reference`` gives
the key points a good answer should touch (used by the optional LLM-judge);
``expects_tool`` is the tool the agent should pause on for approval.

Keep this small and representative — it is meant as a starting point you extend
with the questions that matter for *your* use case.
"""

from __future__ import annotations

from typing import TypedDict


class EvalExample(TypedDict):
    id: str
    question: str
    reference: str
    expects_tool: str


DATASET: list[EvalExample] = [
    {
        "id": "solid-state-batteries",
        "question": "What are the main advantages of solid-state batteries over lithium-ion?",
        "reference": (
            "Higher energy density, improved safety (non-flammable solid "
            "electrolyte), longer cycle life, and faster charging."
        ),
        "expects_tool": "web_search",
    },
    {
        "id": "tcp-vs-udp",
        "question": "What is the difference between TCP and UDP?",
        "reference": (
            "TCP is connection-oriented, reliable, ordered, with flow/congestion "
            "control; UDP is connectionless, faster, best-effort, no guaranteed "
            "delivery — used for streaming/gaming/DNS."
        ),
        "expects_tool": "web_search",
    },
    {
        "id": "photosynthesis",
        "question": "How does photosynthesis convert sunlight into chemical energy?",
        "reference": (
            "Chlorophyll absorbs light; light-dependent reactions produce ATP and "
            "NADPH and split water (releasing O2); the Calvin cycle fixes CO2 into "
            "glucose."
        ),
        "expects_tool": "web_search",
    },
    {
        "id": "intermittent-fasting",
        "question": "What are the health benefits and risks of intermittent fasting?",
        "reference": (
            "Potential benefits: weight loss, insulin sensitivity, cellular "
            "autophagy. Risks: hunger, low energy, disordered eating, not suitable "
            "for some (pregnancy, diabetes) — evidence is mixed."
        ),
        "expects_tool": "web_search",
    },
    {
        "id": "2008-crisis",
        "question": "What were the main causes of the 2008 financial crisis?",
        "reference": (
            "Subprime mortgage lending, mortgage-backed securities and CDOs, "
            "excessive leverage, ratings-agency failures, and a housing-price "
            "collapse triggering systemic contagion."
        ),
        "expects_tool": "web_search",
    },
]
