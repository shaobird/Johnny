"""
Scheduler — fires Johnny's morning briefing at the time set in BRIEFING_TIME.
Uses APScheduler with the asyncio backend so it plays nicely with the
python-telegram-bot event loop.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from config import BRIEFING_TIME


def setup(app: Application) -> AsyncIOScheduler:
    """
    Attach a cron job to `app` that sends the daily briefing.
    Returns the scheduler (caller must call .start() and later .shutdown()).
    """
    from telegram_bot import push_briefing  # avoid circular import at module level

    hour, minute = BRIEFING_TIME.split(":")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        push_briefing,
        trigger="cron",
        hour=int(hour),
        minute=int(minute),
        args=[app],
        id="daily_briefing",
        replace_existing=True,
        misfire_grace_time=300,  # allow up to 5 min late if the process was sleeping
    )
    return scheduler
