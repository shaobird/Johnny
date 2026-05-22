"""
Johnny — Personal AI Chief of Staff (Supervisor Edition)

Intelligence levers active:
  1. Adaptive thinking  — Claude reasons before every response
  2. Persistent memory  — reads user profile + notes at start of each briefing
  3. Cross-agent synthesis — explicitly instructed to connect dots across domains
  4. Supervisor prompt  — told to prioritise and advise, not just report data
"""

import concurrent.futures
import json
import os
from datetime import datetime
import anthropic
from agents.calendar import get_todays_events
from agents.fitness import get_fitness_summary
from agents.news import get_high_impact_news
from agents.intel import get_intel_briefing
from agents.construction import get_construction_briefing
from agents.training_loop import get_training_analysis, log_proposal, record_outcome
from agents.gmail import get_email_summary
import memory as mem
from config import ANTHROPIC_API_KEY

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MAX_ITERATIONS = 15


# ── System prompt (rebuilt fresh each call so memory is always current) ───────

def _build_system_prompt() -> str:
    user_context = mem.get_context()
    return f"""\
You are Johnny Zhang — Zhang Zhi Yi — personal AI chief of staff and trusted senior advisor. \
Your English name is Johnny. Your Chinese name is Zhang Zhi Yi (张智义). \
You have a strong, distinct personality — sharp, direct, honest, and collaborative. \
You address the user as "Boss" unless their name is in the profile below.

━━━ YOUR PERSONALITY ━━━
• Direct — get to the point immediately. No preamble, no "Great question!", no filler.
• Concise — say more with less. One clear sentence beats three vague ones.
• Technically deep — don't just say what, explain why. The reasoning matters.
• Brutally honest — if something won't work, say so clearly and explain why.
  Never just agree to avoid conflict. Push back when you see a flaw.
• Collaborative — work through problems together. Ask sharp questions.
  Think out loud when useful. Say "I'm not sure, let me think..." when you're not.
• Confident but not arrogant — you have strong views, held loosely.
  When new evidence arrives, update immediately without ego.
• Dry wit — occasional, never forced. Never use emojis in casual conversation
  (section headers in briefings are fine).
• No sycophancy — never start with praise or validation. Just answer.
━━━━━━━━━━━━━━━━━━━━━━

━━━ WHAT YOU KNOW ABOUT THE USER ━━━
{user_context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ YOUR SPECIALIST AGENTS ━━━
• Calendar Agent     — Google Calendar: today's meetings and events
• Fitness Agent      — Strava + Hevy: last 7 days of activity, progress, advice
• News Agent         — Forex Factory: today's HIGH-IMPACT economic releases
• Intel Agent        — Live web search: AI, construction, forex, HYROX news
• Construction Agent — Weekly construction-business newsletter (CR13 / CR09 /
                       CW01 scope): tech, safety, tender pipeline, regulatory
• Gmail Agent        — Inbox monitor: urgent + action-needed + construction mail
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ STRATEGIC PLAYBOOK ━━━
You have a playbook of mental models from Munger, Buffett, Dalio, Hormozi, and Naval. \
Apply these frameworks proactively — don't wait to be asked. \
When giving advice: invert the problem (Munger), check for moats (Buffett), \
look for systems to build (Dalio), find leverage (Naval), and maximise value delivery (Hormozi). \
Reference specific models by name when relevant so the user learns them over time.
━━━━━━━━━━━━━━━━━━━━━━━━

━━━ SUPERVISOR MINDSET ━━━
You are NOT a data reporter. You are a synthesiser and advisor.

Step 1 — GATHER: Call all relevant agents before forming any opinion.
Step 2 — SYNTHESISE: Look for connections across the three domains:
  • Does a high-impact forex release overlap with a calendar meeting? Flag it.
  • Are there forex events for the pairs the user watches? Highlight those first.
  • Has the user been overtraining (consecutive hard sessions, no rest)? Warn them.
  • Is today's calendar light — a good opportunity to train?
  • Is the user behind on their weekly fitness goals based on their targets?
  • Are there patterns worth noting (always skips Mondays, pace improving, etc.)?
Step 3 — PRIORITISE: Lead with the 2–3 things that matter MOST today.
Step 4 — ADVISE: End with one clear action recommendation.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ MEMORY ━━━
You can save notes to your memory using the save_note tool. Use it when you:
  • Notice a pattern (e.g. "skips workouts when 3+ meetings")
  • Learn a preference the user states explicitly
  • Want to track a baseline (e.g. "avg run pace as of Apr 7: 5:45/km")

━━━ FORMATTING ━━━
  • Plain text with emoji section headers (📅 💪 🔴 🧠) in briefings only
  • Bullet points for lists
  • Bold key insights using *asterisks* (Telegram renders these as bold)
  • Keep each section tight — no filler, no padding
  • If an agent fails, note it in one line and move on\
"""


# ── Tools ─────────────────────────────────────────────────────────────────────

_TOOLS = [
    {
        "name": "check_calendar",
        "description": "Fetch today's meetings and events from Google Calendar.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_fitness",
        "description": (
            "Fetch the last 7 days of Strava and Hevy activity. "
            "Returns a progress summary and a Claude-generated fitness recommendation."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_forex_news",
        "description": (
            "Scrape today's HIGH-IMPACT economic events from Forex Factory. "
            "Returns time, currency, event name, forecast, and previous values."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_intel_briefing",
        "description": (
            "Run a live web search and generate a daily intelligence briefing "
            "across 4 domains: AI & automation, construction industry, "
            "forex & macro markets, and HYROX / endurance sport. "
            "Each item includes a 'why it matters for you' analysis. "
            "Ends with 3 actionable signals for today. Takes 1–2 minutes to run."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_construction_briefing",
        "description": (
            "Generate the weekly construction-business newsletter for the user's "
            "Singapore contractor (CR13-L1 Waterproofing, CR09-L4 Repair & Redec, "
            "CW01-C1 General Building). Returns construction tech top 5, safety "
            "reminders, tender pipeline + portal watchlist + 3 weekly actions, "
            "and rolling regulatory deadlines. Live web search; takes 1–2 minutes."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "save_note",
        "description": (
            "Save a note to Johnny's persistent memory. Use this to record patterns, "
            "preferences, baselines, or anything worth remembering for future briefings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "The note to save. Be specific and concise.",
                }
            },
            "required": ["note"],
        },
    },
    {
        "name": "check_emails",
        "description": (
            "Check Johnny's Gmail inbox for new relevant emails. "
            "Filters out promotions and low-signal mail. "
            "Returns urgent, action-needed, market, and construction emails only."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "analyze_training",
        "description": (
            "Analyze the last 4 weeks of training data (Strava + Hevy). "
            "Identifies trends in run volume, pace, gym compliance. "
            "Proposes one specific adjustment for next week using the Karpathy Loop pattern. "
            "Returns winning/losing patterns detected over time."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "log_training_proposal",
        "description": (
            "Log a proposed training adjustment so Johnny can track whether it worked next week."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal": {"type": "string", "description": "The specific change proposed."},
                "variable":  {"type": "string", "description": "What training variable is being changed."},
                "hypothesis": {"type": "string", "description": "Why this change should help."},
            },
            "required": ["proposal", "variable", "hypothesis"],
        },
    },
    {
        "name": "record_training_outcome",
        "description": (
            "Record whether last week's proposed training adjustment worked. "
            "Updates the winning/losing patterns log."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "outcome":          {"type": "string", "description": "What happened."},
                "metric_improved":  {"type": "boolean", "description": "True if the target metric improved."},
            },
            "required": ["outcome", "metric_improved"],
        },
    },
]

_HANDLERS = {
    "check_emails":            lambda _:   get_email_summary(),
    "check_calendar":          lambda _:   get_todays_events(),
    "check_fitness":           lambda _:   get_fitness_summary(),
    "get_forex_news":          lambda _:   get_high_impact_news(),
    "get_intel_briefing":      lambda _:   get_intel_briefing(),
    "get_construction_briefing": lambda _: get_construction_briefing(),
    "save_note":               lambda inp: mem.add_note(inp["note"]),
    "analyze_training":        lambda _:   get_training_analysis(),
    "log_training_proposal":   lambda inp: log_proposal(inp["proposal"], inp["variable"], inp["hypothesis"]),
    "record_training_outcome": lambda inp: record_outcome(inp["outcome"], inp["metric_improved"]),
}


# ── Public API ────────────────────────────────────────────────────────────────

def chat(message: str, history: list[dict] | None = None, use_opus: bool = False) -> str:
    """
    Send a message to Johnny and return his reply.
    Pass the prior conversation turns as `history` to maintain context.
    """
    messages = list(history or []) + [{"role": "user", "content": message}]
    return _run_loop(messages, use_opus=use_opus)


def daily_briefing() -> str:
    """Trigger the full morning briefing — Johnny calls all agents and synthesises."""
    return chat(
        "Good morning. Give me my complete daily briefing. "
        "Call check_calendar, check_fitness, and get_forex_news first, "
        "then structure your reply exactly like this:\n\n"
        "📅 CALENDAR\n"
        "List today's meetings with times. If none, say so.\n\n"
        "💪 FITNESS\n"
        "Last 7 days summary. Am I on track? Any warning signs?\n\n"
        "🔴 FOREX\n"
        "Today's high-impact events with times (SGT) and currencies. If none, say so.\n\n"
        "⚡ PRIORITIES\n"
        "The 2–3 things that matter most today. Be specific, not generic.\n\n"
        "✅ ONE ACTION\n"
        "Single most important thing I should do right now.\n\n"
        "Save any patterns or baselines you notice to memory.",
        use_opus=True,
    )


# ── Usage tracking ───────────────────────────────────────────────────────────

USAGE_LOG = "usage_log.json"

def _log_usage(response: anthropic.types.Message) -> None:
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    log = []
    if os.path.exists(USAGE_LOG):
        with open(USAGE_LOG, "r") as f:
            log = json.load(f)
    log.append(entry)
    with open(USAGE_LOG, "w") as f:
        json.dump(log, f, indent=2)


# ── Agentic loop ──────────────────────────────────────────────────────────────

def _run_loop(messages: list[dict], use_opus: bool = False) -> str:
    """
    Run the tool-use loop until Johnny reaches end_turn.
    Opus is used for briefings; Sonnet for freeform chat (80% cheaper).
    """
    model = "claude-opus-4-6" if use_opus else "claude-sonnet-4-6"
    response: anthropic.types.Message | None = None

    for _ in range(MAX_ITERATIONS):
        response = _client.messages.create(
            model=model,
            max_tokens=8096,
            thinking={"type": "adaptive"},
            system=_build_system_prompt(),
            tools=_TOOLS,
            messages=messages,
        )
        _log_usage(response)

        if response.stop_reason == "end_turn":
            return _extract_text(response)

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_blocks = [b for b in response.content if b.type == "tool_use"]

            def _call(block):
                try:
                    handler = _HANDLERS.get(block.name)
                    result = handler(block.input) if handler else f"Unknown tool: {block.name}"
                except Exception as e:
                    result = f"Tool error: {e}"
                return {"type": "tool_result", "tool_use_id": block.id, "content": str(result)}

            with concurrent.futures.ThreadPoolExecutor() as executor:
                tool_results = list(executor.map(_call, tool_blocks))

            messages.append({"role": "user", "content": tool_results})
            continue

        break  # unexpected stop reason

    return _extract_text(response) if response else "No response."


def _extract_text(response: anthropic.types.Message) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text")
