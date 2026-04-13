"""
Johnny — Personal AI Chief of Staff (Supervisor Edition)

Intelligence levers active:
  1. Adaptive thinking  — Claude reasons before every response
  2. Persistent memory  — reads user profile + notes at start of each briefing
  3. Cross-agent synthesis — explicitly instructed to connect dots across domains
  4. Supervisor prompt  — told to prioritise and advise, not just report data
"""

import anthropic
from agents.calendar import get_todays_events
from agents.fitness import get_fitness_summary
from agents.news import get_high_impact_news
from agents.intel import get_intel_briefing
import memory as mem
from config import ANTHROPIC_API_KEY

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MAX_ITERATIONS = 15


# ── System prompt (rebuilt fresh each call so memory is always current) ───────

def _build_system_prompt() -> str:
    user_context = mem.get_context()
    return f"""\
You are Johnny, a personal AI chief of staff and trusted senior advisor. \
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
• Calendar Agent   — Google Calendar: today's meetings and events
• Fitness Agent    — Strava + Hevy: last 7 days of activity, progress, advice
• News Agent       — Forex Factory: today's HIGH-IMPACT economic releases
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
]

_HANDLERS = {
    "check_calendar":    lambda _: get_todays_events(),
    "check_fitness":     lambda _: get_fitness_summary(),
    "get_forex_news":    lambda _: get_high_impact_news(),
    "get_intel_briefing": lambda _: get_intel_briefing(),
    "save_note":         lambda inp: mem.add_note(inp["note"]),
}


# ── Public API ────────────────────────────────────────────────────────────────

def chat(message: str, history: list[dict] | None = None) -> str:
    """
    Send a message to Johnny and return his reply.
    Pass the prior conversation turns as `history` to maintain context.
    """
    messages = list(history or []) + [{"role": "user", "content": message}]
    return _run_loop(messages)


def daily_briefing() -> str:
    """Trigger the full morning briefing — Johnny calls all agents and synthesises."""
    return chat(
        "Good morning. Give me my complete daily briefing. "
        "Check my calendar, review my fitness, pull the high-impact Forex events, "
        "and tell me the 2–3 things I should focus on today. "
        "Save any patterns or baselines you notice to your memory."
    )


# ── Agentic loop ──────────────────────────────────────────────────────────────

def _run_loop(messages: list[dict]) -> str:
    """
    Run the tool-use loop until Johnny reaches end_turn.
    Adaptive thinking is enabled so Claude reasons before every response.
    """
    response: anthropic.types.Message | None = None

    for _ in range(MAX_ITERATIONS):
        response = _client.messages.create(
            model="claude-opus-4-6",
            max_tokens=8096,
            thinking={"type": "adaptive"},   # ← lever 1: deep reasoning
            system=_build_system_prompt(),    # ← lever 2: memory injected fresh
            tools=_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            return _extract_text(response)

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    handler = _HANDLERS.get(block.name)
                    if handler:
                        result = handler(block.input)
                    else:
                        result = f"Unknown tool: {block.name}"
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
            continue

        break  # unexpected stop reason

    return _extract_text(response) if response else "No response."


def _extract_text(response: anthropic.types.Message) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text")
