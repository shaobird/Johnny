"""
Main entry point — starts the Telegram bot and the morning briefing scheduler.

Usage:
    python main.py

The bot will run indefinitely. Press Ctrl+C to stop.
"""

import asyncio
import logging

from telegram_bot import build_app
from scheduler import setup

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


async def run() -> None:
    app = build_app()
    scheduler = setup(app)

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        scheduler.start()
        log.info("Johnny is online. Morning briefing scheduled.")

        try:
            # Block until Ctrl+C
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            log.info("Shutting down…")
        finally:
            scheduler.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()
            await app.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
