"""Model Context Protocol (MCP) tool integration — optional.

MCP is an open standard for exposing tools/data to LLM apps. This module lets
the agent load tools from any number of MCP servers and use them like native
tools — each one gated by the same human-in-the-loop approval as ``web_search``.

It is entirely optional and degrades to a no-op when unconfigured, so the
zero-config demo is unaffected. To enable it:

1. Install the adapter:  ``pip install langchain-mcp-adapters``
2. Point ``MCP_SERVERS`` at a JSON config, either inline or a file path:

    # inline JSON
    MCP_SERVERS='{"math": {"command": "python", "args": ["math_server.py"], "transport": "stdio"}}'

    # or a path to a JSON file with the same shape
    MCP_SERVERS=./mcp_servers.json

   Each entry follows ``langchain-mcp-adapters``' connection schema:

    {
      "math":    {"command": "python", "args": ["server.py"], "transport": "stdio"},
      "weather": {"url": "http://localhost:8000/mcp", "transport": "streamable_http"}
    }

The loaded tools are passed to ``build_agent(extra_tools=...)`` in ``main.py``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, List

logger = logging.getLogger(__name__)


def _load_config() -> dict[str, Any] | None:
    """Parse ``MCP_SERVERS`` as inline JSON or a path to a JSON file."""
    raw = os.getenv("MCP_SERVERS", "").strip()
    if not raw:
        return None
    # A path to a JSON file?
    if not raw.startswith("{") and os.path.exists(raw):
        try:
            with open(raw, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not read MCP config file %s: %s", raw, exc)
            return None
    # Otherwise treat it as inline JSON.
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("MCP_SERVERS is not valid JSON: %s", exc)
        return None


async def load_mcp_tools() -> List[Any]:
    """Return tools discovered from configured MCP servers (``[]`` if none).

    Never raises: any misconfiguration or connection failure is logged and
    yields an empty list so the agent still starts.
    """
    config = _load_config()
    if not config:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        logger.warning(
            "MCP_SERVERS is set but 'langchain-mcp-adapters' is not installed. "
            "Run: pip install langchain-mcp-adapters"
        )
        return []

    try:
        client = MultiServerMCPClient(config)
        tools = await client.get_tools()
        logger.info(
            "Loaded %d MCP tool(s) from %d server(s): %s",
            len(tools),
            len(config),
            ", ".join(sorted(config)),
        )
        return list(tools)
    except Exception as exc:  # pragma: no cover - network/subprocess issues
        logger.warning("Failed to load MCP tools: %s", exc)
        return []
