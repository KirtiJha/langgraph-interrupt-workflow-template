"""AG-UI protocol adapter — expose the agent to any AG-UI frontend.

[AG-UI](https://docs.ag-ui.com) (Agent–User Interaction Protocol) is an open
standard for streaming agent events to a frontend. Its flagship capability is
*pausing mid-run to ask a human for approval* — exactly this template's thesis —
so exposing the agent over AG-UI lets it plug into any AG-UI client (e.g.
[CopilotKit](https://www.copilotkit.ai), or React/Vue/Angular AG-UI widgets)
**without changing the bundled Next.js UI**, which keeps using the ``/missions/*``
SSE endpoints.

This is additive and optional: if ``ag-ui-langgraph`` isn't installed, the app
still boots and ``mount_agui`` is a no-op.
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver

from steward.agent import build_steward_agent

logger = logging.getLogger(__name__)

# The path the AG-UI endpoint is mounted at.
AGUI_PATH = "/agui"

# Set at import time; ``mount_agui`` reflects whether the adapter is available.
try:
    from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint

    AGUI_AVAILABLE = True
except Exception as exc:  # pragma: no cover - only when ag-ui-langgraph is missing
    logger.info("AG-UI adapter disabled (install 'ag-ui-langgraph'): %s", exc)
    AGUI_AVAILABLE = False


# The mounted AG-UI agent, so the app lifespan can swap in a durable graph.
_AGENT = None


def bind_persistence(checkpointer, store=None) -> None:
    """Rebuild the AG-UI agent's graph on the app's durable checkpointer.

    The endpoint must be mounted at import time (route registration), before the
    lifespan opens the database — so it starts on an in-memory checkpointer and
    is re-pointed here. Without this, AG-UI pauses wouldn't survive across
    serverless instances.
    """
    if _AGENT is None:
        return
    _AGENT.graph = build_steward_agent(checkpointer=checkpointer, store=store)


def mount_agui(app, store=None) -> bool:
    """Mount the AG-UI endpoint on ``app`` at :data:`AGUI_PATH`.

    Returns ``True`` when mounted, ``False`` when the adapter isn't installed.
    Uses a dedicated agent instance so AG-UI runs are independent of the
    ``/missions/*`` SSE endpoints; see :func:`bind_persistence`.
    """
    global _AGENT
    if not AGUI_AVAILABLE:
        return False
    try:
        graph = build_steward_agent(checkpointer=MemorySaver(), store=store)
        agent = LangGraphAgent(
            name="repo_steward",
            description="Maintainer agent for a GitHub repository — pauses for approval before anything public.",
            graph=graph,
        )
        add_langgraph_fastapi_endpoint(app, agent, path=AGUI_PATH)
        _AGENT = agent
        logger.info("AG-UI endpoint mounted at %s", AGUI_PATH)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to mount AG-UI endpoint: %s", exc)
        return False
