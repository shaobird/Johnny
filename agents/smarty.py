"""
Smarty — Chief of Research

Smarty covers all intelligence and scheduling:
  • Calendar (Google Calendar — meetings, events)
  • News (Forex Factory — high-impact economic events)
  • Intel (Gemini 2.5 Pro + Google Search — daily briefing across
    AI, construction, forex, HYROX)

Smarty is proactive, well-read, and concise. She surfaces what matters
and ignores everything else. Signs off as "— Smarty".
"""

from agents.calendar import get_todays_events
from agents.news import get_high_impact_news
from agents.intel import get_intel_briefing


def get_full_research_brief() -> str:
    """Pull calendar + forex news + intel in one call."""
    calendar = get_todays_events()
    news = get_high_impact_news()
    intel = get_intel_briefing()

    return (
        f"━━━ SMARTY'S RESEARCH BRIEF ━━━\n\n"
        f"📅 CALENDAR\n{calendar}\n\n"
        f"🔴 FOREX NEWS\n{news}\n\n"
        f"📡 INTEL\n{intel}\n\n"
        f"— Smarty"
    )
