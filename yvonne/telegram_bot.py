"""Telegram front-end for Yvonne (Gladys's founder agent)."""

from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from . import founder
from . import memory as mem
from .agents import improver
from .config import YVONNE_TELEGRAM_BOT_TOKEN

_history: dict[int, list[dict]] = {}
_MAX_HISTORY = 30


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        "Hi Gladys — I'm Yvonne, your personal AI assistant.\n\n"
        f"Your chat ID is: {chat_id}\n\n"
        "Just talk to me normally. I'll learn how you work, keep track of "
        "your clients, your policies, your follow-ups, and draft things in "
        "your voice.\n\n"
        "Commands:\n"
        "  /today      — what's due today\n"
        "  /clients    — list clients on file\n"
        "  /improve    — propose new functionality (you approve before any build)\n"
        "  /proposals  — review pending improvement proposals\n"
        "  /reset      — clear this chat's short-term history\n"
        "  /forget     — DOES NOT delete memory; clears in-session history only"
    )


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    history = _history.get(user_id, [])
    reply = await asyncio.to_thread(
        founder.chat,
        "What's on my plate today? Check followups_due_today and tell me what matters most. "
        "If nothing's due, say so plainly.",
        history,
    )
    history.append({"role": "user", "content": "/today"})
    history.append({"role": "assistant", "content": reply})
    _history[user_id] = history[-_MAX_HISTORY:]
    await _send_long(update, reply)


async def cmd_clients(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    history = _history.get(user_id, [])
    reply = await asyncio.to_thread(
        founder.chat, "List my clients on file.", history,
    )
    await _send_long(update, reply)


async def cmd_improve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    days = 7
    if context.args:
        try:
            days = int(context.args[0])
        except ValueError:
            pass
    await update.message.reply_text(
        f"📐 Looking at the last {days} days for improvement ideas… "
        "I'll propose, you decide. Nothing gets built without your approval."
    )
    summary = await asyncio.to_thread(improver.propose, days)
    await _send_long(update, summary)


async def cmd_proposals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = context.args[0] if context.args else "pending"
    text = await asyncio.to_thread(improver.list_proposals, status)
    await _send_long(update, text)


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _history.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "Short-term chat history cleared. Long-term memory is untouched."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text
    history = _history.get(user_id, [])
    reply = await asyncio.to_thread(founder.chat, text, history)
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    _history[user_id] = history[-_MAX_HISTORY:]
    await _send_long(update, reply)


async def _send_long(update: Update, text: str) -> None:
    if not text:
        text = "(no reply)"
    limit = 4096
    for i in range(0, len(text), limit):
        await update.message.reply_text(text[i : i + limit])


def build_app() -> Application:
    if not YVONNE_TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "YVONNE_TELEGRAM_BOT_TOKEN not set — add it to .env before running."
        )
    app = Application.builder().token(YVONNE_TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("clients", cmd_clients))
    app.add_handler(CommandHandler("improve", cmd_improve))
    app.add_handler(CommandHandler("proposals", cmd_proposals))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("forget", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.post_init = _set_commands
    return app


async def _set_commands(app: Application) -> None:
    await app.bot.set_my_commands([
        ("today", "What's due today"),
        ("clients", "List clients on file"),
        ("improve", "Propose new functionality (you approve)"),
        ("proposals", "Review pending improvement proposals"),
        ("reset", "Clear short-term chat history"),
    ])
