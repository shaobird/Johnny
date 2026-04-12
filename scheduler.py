"""
Scheduler — fires Johnny's daily jobs.

Jobs:
  1. Morning briefing (BRIEFING_TIME)       — calendar + fitness + forex events
  2. Intel briefing   (INTEL_BRIEFING_TIME) — AI + construction + macro + HYROX news
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from config import BRIEFING_TIME, INTEL_BRIEFING_TIME


def setup(app: Application) -> AsyncIOScheduler:
    """
    Register all scheduled jobs and return the scheduler.
    Caller must call scheduler.start() and later scheduler.shutdown().
    """
    # Avoid circular imports — telegram_bot imports johnny which imports agents
    from telegram_bot import push_briefing, push_intel

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

    return scheduler
