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

import concurrent.futures

from agents.calendar import get_todays_events
from agents.news import get_high_impact_news
from agents.intel import get_intel_briefing


def get_full_research_brief() -> str:
    """Pull calendar + forex news + intel in parallel, with per-source error handling."""
    def _safe(fn, label):
        try:
            return fn()
        except Exception as e:
            return f"{label} unavailable: {e}"

    with concurrent.futures.ThreadPoolExecutor() as ex:
        f_cal   = ex.submit(_safe, get_todays_events,    "Calendar")
        f_news  = ex.submit(_safe, get_high_impact_news, "Forex news")
        f_intel = ex.submit(_safe, get_intel_briefing,   "Intel")
        calendar = f_cal.result(timeout=120)
        news     = f_news.result(timeout=120)
        intel    = f_intel.result(timeout=120)

    return (
        f"━━━ SMARTY'S RESEARCH BRIEF ━━━\n\n"
        f"📅 CALENDAR\n{calendar}\n\n"
        f"🔴 FOREX NEWS\n{news}\n\n"
        f"📡 INTEL\n{intel}\n\n"
        f"— Smarty"
    )
