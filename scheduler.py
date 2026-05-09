"""
Scheduler — fires Johnny's daily jobs.

Jobs:
  1. Morning briefing  (BRIEFING_TIME)       — calendar + fitness + forex events
  2. Intel briefing    (INTEL_BRIEFING_TIME) — AI + construction + macro + HYROX news
  3. Macro brief       (MACRO_BRIEF_TIME)    — FX + central-bank + week-ahead data
  4. MrktEdge monitor  (every 10 min)        — HIGH IMPACT news alerts, instant push
  5. Memory maintenance (02:00 nightly)      — dedupe + sort notes, no API cost
  6. Weekly retro       (Sunday 08:00)       — one-week pattern summary via Claude
  7. Gmail monitor      (every 30 min)       — new relevant emails, instant push
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from config import BRIEFING_TIME, INTEL_BRIEFING_TIME, MACRO_BRIEF_TIME


def setup(app: Application) -> AsyncIOScheduler:
    """
    Register all scheduled jobs and return the scheduler.
    Caller must call scheduler.start() and later scheduler.shutdown().
    """
    from telegram_bot import (
        push_briefing,
        push_intel,
        push_macro,
        push_mrktedge_alerts,
        push_maintenance_report,
        push_weekly_retro,
        push_email_alerts,
    )

    scheduler = AsyncIOScheduler()

    # ── Job 1: Morning briefing (calendar + fitness + forex) ──────────────────
    b_hour, b_min = BRIEFING_TIME.split(":")
    scheduler.add_job(
        push_briefing,
        trigger="cron",
        hour=int(b_hour),
        minute=int(b_min),
        args=[app],
        id="daily_briefing",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── Job 2: Intel briefing (AI + construction + macro + HYROX) ─────────────
    i_hour, i_min = INTEL_BRIEFING_TIME.split(":")
    scheduler.add_job(
        push_intel,
        trigger="cron",
        hour=int(i_hour),
        minute=int(i_min),
        args=[app],
        id="daily_intel",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── Job 2b: Macro brief (FX + central banks + week-ahead data) ────────────
    m_hour, m_min = MACRO_BRIEF_TIME.split(":")
    scheduler.add_job(
        push_macro,
        trigger="cron",
        hour=int(m_hour),
        minute=int(m_min),
        args=[app],
        id="daily_macro",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── Job 3: MrktEdge HIGH IMPACT monitor (every 10 minutes) ────────────────
    scheduler.add_job(
        push_mrktedge_alerts,
        trigger="interval",
        minutes=10,
        args=[app],
        id="mrktedge_monitor",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # ── Job 4: Overnight memory maintenance (02:00 daily) — no API cost ───────
    scheduler.add_job(
        push_maintenance_report,
        trigger="cron",
        hour=2,
        minute=0,
        args=[app],
        id="memory_maintenance",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── Job 5: Weekly retro (Sunday 08:00) — one Claude call per week ─────────
    scheduler.add_job(
        push_weekly_retro,
        trigger="cron",
        day_of_week="sun",
        hour=8,
        minute=0,
        args=[app],
        id="weekly_retro",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── Job 6: Gmail monitor (every 30 minutes) ───────────────────────────────
    scheduler.add_job(
        push_email_alerts,
        trigger="interval",
        minutes=30,
        args=[app],
        id="gmail_monitor",
        replace_existing=True,
        misfire_grace_time=300,
    )

    return scheduler
