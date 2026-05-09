"""
Telegram Bot — Johnny's front-end interface.

Commands:
  /start    — welcome message
  /briefing — trigger the full daily briefing on demand
  /calendar — today's meetings only
  /fitness  — fitness summary only
  /news     — Forex Factory high-impact events only
  /intel    — daily intelligence briefing (AI, construction, forex, HYROX)
  /research — deep-dive on a sector / theme / ticker (e.g. /research NVDA)
  /macro    — FX + central-bank + scheduled-data brief
  /earnings — earnings review for a ticker (e.g. /earnings MSFT)
  /thesis   — weekly AI / automation thesis tracker (or pass your own thesis)
  /peter    — consult Peter, the family CFO (Boss + Yvonne both authorized)
  /journal  — save a journal entry (e.g. /journal Today was tough but productive)
  /reflect  — Johnny reflects on your last 7 days of journal entries

Any other text is forwarded to Johnny as a freeform message.
"""

import asyncio
import os
import tempfile

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import johnny
import memory as mem
from agents.calendar import get_todays_events
from agents.fitness import get_fitness_summary
from agents.news import get_high_impact_news
from agents.intel import get_intel_briefing
from agents.research import research_topic, macro_brief, earnings_brief, thesis_update
from agents.peter import consult_peter, suggest_mode, format_suggestion
from agents.mrktedge import check_new_items, format_item
from agents.gmail import get_new_emails, format_email
from agents.files import parse_file
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_CHAT_ID_YVONNE, OPENAI_API_KEY


def _asker_for(chat_id: int | str | None) -> str | None:
    """Map a Telegram chat_id to 'boss' / 'yvonne' / None (unauthorized)."""
    if chat_id is None:
        return None
    cid = str(chat_id)
    if TELEGRAM_CHAT_ID and cid == str(TELEGRAM_CHAT_ID):
        return "boss"
    if TELEGRAM_CHAT_ID_YVONNE and cid == str(TELEGRAM_CHAT_ID_YVONNE):
        return "yvonne"
    return None

# In-memory conversation history per user (last 20 messages = 10 turns)
_history: dict[int, list[dict]] = {}
_MAX_HISTORY = 20


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"👋 Hey, I'm Johnny — your personal AI chief of staff.\n\n"
        f"Your chat ID is: {chat_id}\n\n"
        "📋 COMMANDS\n"
        "  /briefing — full daily briefing\n"
        "  /calendar — today's meetings\n"
        "  /fitness  — workout summary\n"
        "  /news     — Forex high-impact events\n"
        "  /intel    — AI, construction & macro briefing\n"
        "  /research — sector/ticker deep dive (e.g. /research NVDA)\n"
        "  /macro    — FX + central-bank + data brief\n"
        "  /earnings — earnings review (e.g. /earnings MSFT)\n"
        "  /thesis   — AI thesis tracker (or pass your own)\n"
        "  /peter    — ask Peter (family CFO) — portfolio / couple / fx / biz\n"
        "  /journal  — log a journal entry\n"
        "              e.g. /journal Good Push session today\n"
        "  /reflect  — Johnny reflects on your last 7 days\n\n"
        "Or just talk to me normally — I'll remember the conversation."
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


async def cmd_intel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📡 Running intel search across AI, construction, forex & HYROX…\n"
        "This takes 1–2 minutes ⏳"
    )
    await _send_long(update, get_intel_briefing())


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🔴 Scraping Forex Factory…")
    await _send_long(update, get_high_impact_news())


# ── Research handlers ─────────────────────────────────────────────────────────

async def cmd_research(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text(
            "Usage: /research <topic>\n"
            "Examples:\n"
            "  /research datacenter power demand\n"
            "  /research NVDA\n"
            "  /research Singapore construction tech"
        )
        return
    await update.message.reply_text(
        f"🔍 Researching *{topic}* — comps, catalysts, risks, ideas…\n"
        "Takes 1–2 min ⏳",
        parse_mode="Markdown",
    )
    reply = await asyncio.to_thread(research_topic, topic)
    await _send_long(update, reply)


async def cmd_macro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("💱 Building macro brief — USD bias, central banks, week-ahead data…")
    reply = await asyncio.to_thread(macro_brief)
    await _send_long(update, reply)


async def cmd_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ticker = (context.args[0] if context.args else "").strip().upper()
    if not ticker:
        await update.message.reply_text("Usage: /earnings <TICKER>\nExample: /earnings NVDA")
        return
    await update.message.reply_text(
        f"📊 Reviewing *{ticker}* — last print, guide, call takeaways…",
        parse_mode="Markdown",
    )
    reply = await asyncio.to_thread(earnings_brief, ticker)
    await _send_long(update, reply)


async def cmd_peter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Direct line to Peter (family CFO). Usage: /peter [mode] <question>.

    Mode is optional and one of: portfolio | couple | fx | biz | auto (default).
    Example: /peter portfolio how is our AI exposure looking?
    Example: /peter how much do we need monthly to hit BTO downpayment by 2027?
    """
    asker = _asker_for(update.effective_chat.id)
    if asker is None:
        await update.message.reply_text("Peter is private — your chat isn't authorized.")
        return

    args = list(context.args or [])
    explicit_mode = None
    if args and args[0].lower() in ("portfolio", "couple", "fx", "biz", "auto"):
        explicit_mode = args.pop(0).lower()
    question = " ".join(args).strip()

    if not question:
        await update.message.reply_text(
            "Usage: /peter [mode] <question>\n"
            "Modes: portfolio | couple | fx | biz | auto\n"
            "(omit the mode and Peter picks the best fit himself)\n\n"
            "Examples:\n"
            "  /peter how is our AI exposure looking?\n"
            "  /peter couple what's our progress on the BTO downpayment?\n"
            "  /peter fx what's the setup for tonight's NY session?\n\n"
            "Tip: /whichpeter <question> tells you the suggested mode without running Peter."
        )
        return

    if explicit_mode and explicit_mode != "auto":
        mode = explicit_mode
        suggestion_line = f"📍 Peter mode: *{mode}* (you set it)"
    else:
        suggested, reason = suggest_mode(question)
        mode = suggested
        suggestion_line = format_suggestion(suggested, reason)

    label = asker.title()
    await update.message.reply_text(
        f"📒 Peter is on it for *{label}*\n{suggestion_line}\n"
        "Takes ~30–60s ⏳",
        parse_mode="Markdown",
    )
    reply = await asyncio.to_thread(consult_peter, question, mode, asker)
    await _send_long(update, reply)


async def cmd_whichpeter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tell the user which Peter mode fits their question, without running Peter."""
    asker = _asker_for(update.effective_chat.id)
    if asker is None:
        await update.message.reply_text("Peter is private — your chat isn't authorized.")
        return

    question = " ".join(context.args or []).strip()
    if not question:
        await update.message.reply_text(
            "Usage: /whichpeter <question>\n"
            "Returns the recommended Peter mode (portfolio | couple | fx | biz)\n"
            "and the reasoning, without spending the API call to actually run Peter.\n\n"
            "Example: /whichpeter should we add to NVDA before earnings?"
        )
        return

    mode, reason = suggest_mode(question)
    if mode == "auto":
        msg = (
            f"🤔 No clear single best fit — {reason}.\n"
            "You can either run `/peter <question>` and let Peter pick across all four,\n"
            "or specify a mode: `/peter portfolio|couple|fx|biz <question>`."
        )
    else:
        msg = (
            f"📍 Best fit: *{mode}* — {reason}.\n\n"
            f"Run it with: `/peter {mode} {question}`\n"
            f"Or just `/peter {question}` and Peter will route the same way."
        )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_thesis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    thesis = " ".join(context.args) if context.args else ""
    label = thesis or "AI + automation"
    await update.message.reply_text(
        f"🧠 Tracking thesis: *{label}* — last 7 days…",
        parse_mode="Markdown",
    )
    reply = await asyncio.to_thread(thesis_update, thesis)
    await _send_long(update, reply)


# ── Free-text handler ─────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text

    # Yvonne's chat: route free-text straight to Peter (Johnny is Boss's persona).
    asker = _asker_for(update.effective_chat.id)
    if asker == "yvonne":
        mode, reason = suggest_mode(text)
        await update.message.reply_text(
            f"📒 Forwarding to Peter for you, Yvonne\n{format_suggestion(mode, reason)}\n"
            "Takes ~30–60s ⏳",
            parse_mode="Markdown",
        )
        reply = await asyncio.to_thread(consult_peter, text, mode, "yvonne")
        await _send_long(update, reply)
        return

    history = _history.get(user_id, [])
    reply = johnny.chat(text, history)

    # Update rolling history
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    _history[user_id] = history[-_MAX_HISTORY:]

    await _send_long(update, reply)


# ── Journal handlers ──────────────────────────────────────────────────────────

async def cmd_journal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    entry = " ".join(context.args) if context.args else ""
    if not entry:
        await update.message.reply_text(
            "Usage: /journal <your entry>\n"
            "Example: /journal Had a solid Push session. Feeling focused today."
        )
        return
    mem.add_journal(entry)
    reply = johnny.chat(
        f"The user just journalled: \"{entry}\"\n\n"
        "Acknowledge it briefly (1-2 sentences max). If there's a pattern or insight worth noting, "
        "mention it. Otherwise just confirm it's saved. No filler."
    )
    await _send_long(update, reply)


async def cmd_newsletter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a newsletter research brief — intel + topic gap + top performers."""
    angle = " ".join(context.args) if context.args else ""
    await update.message.reply_text(
        "📰 Preparing newsletter brief — pulling intel + topic history…\n"
        "Takes 1-2 min ⏳"
    )
    reply = johnny.chat(
        f"Run prepare_newsletter_brief with angle: \"{angle}\". "
        "Then synthesise into 3 newsletter angle suggestions, each with: "
        "headline, 1-line hook, key points to cover, why it'll resonate. "
        "Avoid topics from the last 6 weeks."
    )
    await _send_long(update, reply)


async def cmd_reflect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📔 Reading your journal...")
    entries = mem.get_recent_journal(days=7)
    reply = johnny.chat(
        f"Here are the user's journal entries from the last 7 days:\n\n{entries}\n\n"
        "Give a sharp reflection (max 150 words):\n"
        "• What patterns do you notice?\n"
        "• What's going well?\n"
        "• What needs attention?\n"
        "• One clear recommendation for the week ahead.\n"
        "Be direct. No filler."
    )
    await _send_long(update, reply)


# ── Voice handler ─────────────────────────────────────────────────────────────

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not OPENAI_API_KEY:
        await update.message.reply_text("Voice not configured — add OPENAI_API_KEY to .env")
        return

    await update.message.reply_text("🎙️ Transcribing...")

    try:
        from openai import OpenAI
        oai = OpenAI(api_key=OPENAI_API_KEY)

        voice_file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await voice_file.download_to_drive(tmp_path)

        with open(tmp_path, "rb") as f:
            transcript = oai.audio.transcriptions.create(model="whisper-1", file=f)
        os.unlink(tmp_path)

        text = transcript.text
        await update.message.reply_text(f'_{text}_', parse_mode="Markdown")

        user_id = update.effective_user.id
        history = _history.get(user_id, [])
        reply = johnny.chat(text, history)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})
        _history[user_id] = history[-_MAX_HISTORY:]
        await _send_long(update, reply)

    except Exception as e:
        await update.message.reply_text(f"Voice transcription failed: {e}")


# ── Document handler ──────────────────────────────────────────────────────────

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive a file (Excel/CSV/PDF/text), parse it, send to Johnny for analysis."""
    doc = update.message.document
    if not doc:
        return

    caption = (update.message.caption or "").strip()
    filename = doc.file_name or "uploaded_file"

    await update.message.reply_text(f"📎 Got `{filename}`. Reading…", parse_mode="Markdown")

    try:
        # Download to temp file
        tg_file = await doc.get_file()
        suffix = os.path.splitext(filename)[1] or ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
        await tg_file.download_to_drive(tmp_path)

        # Parse it
        parsed = await asyncio.to_thread(parse_file, tmp_path)
        os.unlink(tmp_path)

        # Build the message for Johnny
        instruction = caption or (
            "Analyse this file. Give me the key insights, anomalies, and what I should "
            "act on. Use tables where useful. Be concise."
        )

        prompt = (
            f"The user uploaded a file named `{filename}`. Their request: {instruction}\n\n"
            f"━━━ FILE CONTENTS ━━━\n{parsed}\n━━━━━━━━━━━━━━━━━━━━"
        )

        user_id = update.effective_user.id
        history = _history.get(user_id, [])
        reply = await asyncio.to_thread(johnny.chat, prompt, history)

        history.append({"role": "user", "content": f"[Uploaded {filename}] {instruction}"})
        history.append({"role": "assistant", "content": reply})
        _history[user_id] = history[-_MAX_HISTORY:]

        await _send_long(update, reply)

    except Exception as e:
        await update.message.reply_text(f"Failed to process file: {e}")


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
    await _push(app, text)


async def push_intel(app: Application) -> None:
    """Called by the scheduler to send the daily intel briefing."""
    if not TELEGRAM_CHAT_ID:
        print("TELEGRAM_CHAT_ID not set — skipping intel briefing.")
        return
    text = get_intel_briefing()
    await _push(app, text)


async def push_macro(app: Application) -> None:
    """Called by the scheduler to send the morning macro / FX brief."""
    if not TELEGRAM_CHAT_ID:
        print("TELEGRAM_CHAT_ID not set — skipping macro brief.")
        return
    try:
        text = await asyncio.to_thread(macro_brief)
        await _push(app, f"💱 *Macro Brief*\n\n{text}")
    except Exception as exc:
        print(f"[Macro] Push failed: {exc}")


async def push_email_alerts(app: Application) -> None:
    """Called every 30 min — pushes new relevant emails instantly."""
    if not TELEGRAM_CHAT_ID:
        return
    try:
        new_emails = await asyncio.to_thread(get_new_emails)
        for email in new_emails:
            await app.bot.send_message(
                chat_id=int(TELEGRAM_CHAT_ID),
                text=format_email(email),
                parse_mode="Markdown",
            )
    except Exception as e:
        print(f"[Gmail] Push failed: {e}")


async def push_maintenance_report(app: Application) -> None:
    """Runs at 02:00 nightly — cleans memory, no API cost."""
    if not TELEGRAM_CHAT_ID:
        return
    try:
        report = await asyncio.to_thread(mem.maintain)
        print(f"[Memory] {report}")
        # Only notify if something was actually cleaned
        if "0 duplicates" not in report:
            await app.bot.send_message(
                chat_id=int(TELEGRAM_CHAT_ID),
                text=f"🧹 Memory maintenance: {report}",
            )
    except Exception as e:
        print(f"[Memory] Maintenance failed: {e}")


async def push_weekly_retro(app: Application) -> None:
    """Runs Sunday 08:00 — one Claude call, weekly pattern summary."""
    if not TELEGRAM_CHAT_ID:
        return
    try:
        summary = await asyncio.to_thread(mem.weekly_summary)
        retro = await asyncio.to_thread(
            johnny.chat,
            f"Give me a concise weekly retro. Here are the notes you saved this week:\n\n{summary}\n\n"
            "What patterns do you notice? What should I focus on or change next week? "
            "Keep it under 200 words, plain text, no headers.",
            None,
        )
        await _push(app, f"📊 *Weekly Retro*\n\n{retro}")
    except Exception as e:
        print(f"[Retro] Weekly retro failed: {e}")


async def push_mrktedge_alerts(app: Application) -> None:
    """Called every 10 min — pushes any new HIGH IMPACT items instantly."""
    if not TELEGRAM_CHAT_ID:
        return
    try:
        new_items = await asyncio.to_thread(check_new_items)
        for item in new_items:
            await app.bot.send_message(
                chat_id=int(TELEGRAM_CHAT_ID),
                text=format_item(item),
                parse_mode="Markdown",
            )
    except Exception as e:
        print(f"[MrktEdge] Push failed: {e}")


async def _push(app: Application, text: str) -> None:
    """Send a (potentially long) message to the owner's chat."""
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
    app.add_handler(CommandHandler("intel", cmd_intel))
    app.add_handler(CommandHandler("research", cmd_research))
    app.add_handler(CommandHandler("macro", cmd_macro))
    app.add_handler(CommandHandler("earnings", cmd_earnings))
    app.add_handler(CommandHandler("thesis", cmd_thesis))
    app.add_handler(CommandHandler("peter", cmd_peter))
    app.add_handler(CommandHandler("whichpeter", cmd_whichpeter))
    app.add_handler(CommandHandler("journal", cmd_journal))
    app.add_handler(CommandHandler("reflect", cmd_reflect))
    app.add_handler(CommandHandler("newsletter", cmd_newsletter))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Register command menu so they appear when user taps "/"
    app.post_init = _set_commands
    return app


async def _set_commands(app: Application) -> None:
    await app.bot.set_my_commands([
        ("briefing", "Full daily briefing"),
        ("calendar", "Today's meetings"),
        ("fitness",  "Workout summary"),
        ("news",     "Forex high-impact events"),
        ("intel",    "AI, construction & macro briefing"),
        ("research", "Sector / ticker deep dive"),
        ("macro",    "FX + central-bank brief"),
        ("earnings", "Earnings review for a ticker"),
        ("thesis",   "AI thesis tracker"),
        ("peter",    "Ask Peter (family CFO) — auto-routes to best mode"),
        ("whichpeter","Suggest the best Peter mode without running it"),
        ("journal",  "Log a journal entry"),
        ("reflect",  "Reflect on last 7 days"),
        ("newsletter", "Newsletter research brief"),
    ])
