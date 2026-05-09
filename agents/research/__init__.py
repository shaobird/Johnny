"""
Research Agent — structured market research for Johnny.

Modes (inspired by anthropics/financial-services agent patterns):
  • research_topic(topic)   — sector / theme / ticker deep dive (Market Researcher)
  • macro_brief()           — FX + central-bank + scheduled-data brief
  • earnings_brief(ticker)  — earnings release + call summary (Earnings Reviewer)
  • thesis_update(thesis)   — weekly tracker for a multi-year thesis (default: AI)

Each mode loads a markdown skill prompt from agents/research/skills/ and runs it
through the shared search runner (Gemini grounding, with Claude web_search fallback).
"""

from .runner import load_skill, run_search


def research_topic(topic: str) -> str:
    """Deep-dive research on a sector, theme, ticker, or company."""
    topic = (topic or "").strip()
    if not topic:
        return (
            "Usage: /research <topic>\n"
            "Examples:\n"
            "  /research datacenter power demand\n"
            "  /research NVDA\n"
            "  /research Singapore construction tech\n"
        )
    prompt = load_skill("market_research", TOPIC=topic)
    return run_search(prompt)


def macro_brief() -> str:
    """Macro / FX brief: USD bias, central-bank stance, scheduled high-impact data."""
    prompt = load_skill("macro_frame")
    return run_search(prompt)


def earnings_brief(ticker: str) -> str:
    """Summarise the latest earnings release + call for a public company."""
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return (
            "Usage: /earnings <TICKER>\n"
            "Example: /earnings NVDA"
        )
    prompt = load_skill("earnings_review", TICKER=ticker)
    return run_search(prompt)


def thesis_update(thesis: str = "") -> str:
    """Weekly tracker for a multi-year investment thesis (default: AI + automation)."""
    thesis = (thesis or "").strip() or "AI + automation infrastructure and applications"
    prompt = load_skill("thesis_tracker", THESIS=thesis)
    return run_search(prompt)


__all__ = ["research_topic", "macro_brief", "earnings_brief", "thesis_update"]
