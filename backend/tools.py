"""Tools available to the agent.

The example ``web_search`` tool uses Tavily when ``TAVILY_API_KEY`` is set and
``langchain-tavily`` is installed; otherwise it returns deterministic mock
results so the template still runs offline. Add your own tools here.
"""

from __future__ import annotations

import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def web_search(query: str) -> str:
    """Search the web for current information about a topic.

    Args:
        query: A focused natural-language search query.

    Returns:
        A formatted string of search results (title, snippet, url).
    """
    if os.getenv("TAVILY_API_KEY"):
        try:
            from langchain_tavily import TavilySearch

            response = TavilySearch(max_results=5).invoke({"query": query})
            results = response.get("results", []) if isinstance(response, dict) else []
            if results:
                return "\n\n".join(
                    f"- {item.get('title', 'Result')}\n  {item.get('content', '')}\n  {item.get('url', '')}"
                    for item in results
                )
        except Exception as exc:  # pragma: no cover - network/credential issues
            logger.warning("Tavily search failed (%s); using mock results.", exc)

    return (
        f"[mock search results for '{query}']\n"
        "- Overview: a concise, relevant summary of the topic.\n"
        "- Key points: the most important facts a reader should know.\n"
        "- Note: install 'langchain-tavily' and set TAVILY_API_KEY for live web search."
    )


# Convenience list to pass to agents/graphs.
TOOLS = [web_search]
