"""
Telegram Bot — Johnny's front-end interface.

Commands:
  /start    — welcome message
  /briefing — trigger the full daily briefing on demand
  /calendar — today's meetings only
  /fitness  — fitness summary only
  /news     — Forex Factory high-impact events only

Any other text is forwarded to Johnny as a freeform message.

Setup:
  1. Message @BotFather on Telegram → /newbot → copy the token
  2. Add TELEGRAM_BOT_TOKEN to .env
  3. Start the bot, then message it once — Johnny will reply with your chat ID.
     Copy that ID into TELEGRAM_CHAT_ID in .env so the scheduler can DM you.
"""

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import johnny
from agents.calendar import get_todays_events
from agents.fitness import get_fitness_summary
from agents.news import get_high_impact_news
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# In-memory conversation history per user (last 20 messages = 10 turns)
_history: dict[int, list[dict]] = {}
_MAX_HISTORY = 20


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"👋 Hey, I'm Johnny — your personal AI chief of staff.\n\n"
        f"Your chat ID is: {chat_id}\n"
        f"(Add this as TELEGRAM_CHAT_ID in .env for morning briefings)\n\n"
        "Commands:\n"
        "  /briefing — full daily briefing\n"
        "  /calendar — today's meetings\n"
        "  /fitness  — workout summary\n"
        "  /news     — Forex high-impact events\n\n"
        "Or just talk to me normally."
    )


async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Preparing your briefing… ⏳")
    reply = johnny.daily_briefing()
    await _send_long(update, reply)


async def cmd_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📅 Checking your calendar…")
    await _send_long(update, get_todays_events())


async def cmd_fitness(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("💪 Fetching fitness data…")
    await _send_long(update, get_fitness_summary())


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🔴 Scraping Forex Factory…")
    await _send_long(update, get_high_impact_news())


# ── Free-text handler ─────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text

    history = _history.get(user_id, [])
    reply = johnny.chat(text, history)

    # Update rolling history
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    _history[user_id] = history[-_MAX_HISTORY:]

    await _send_long(update, reply)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _send_long(update: Update, text: str) -> None:
    """Telegram caps messages at 4096 chars — split if needed."""
    limit = 4096
    for i in range(0, len(text), limit):
        await update.message.reply_text(text[i : i + limit])


async def push_briefing(app: Application) -> None:
    """Called by the scheduler to send the morning briefing to the owner."""
    if not TELEGRAM_CHAT_ID:
        print("TELEGRAM_CHAT_ID not set — skipping scheduled briefing.")
        return
    text = johnny.daily_briefing()
    limit = 4096
    for i in range(0, len(text), limit):
        await app.bot.send_message(chat_id=int(TELEGRAM_CHAT_ID), text=text[i : i + limit])


# ── App builder ───────────────────────────────────────────────────────────────

def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    app.add_handler(CommandHandler("fitness", cmd_fitness))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
