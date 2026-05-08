"""
Entry point for Gladys.

    python -m gladys.main

Requires GLADYS_TELEGRAM_BOT_TOKEN and ANTHROPIC_API_KEY in .env.
"""

import asyncio
import logging

from .telegram_bot import build_app

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


async def run() -> None:
    app = build_app()
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        log.info("Gladys is online.")
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            log.info("Shutting down…")
        finally:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
