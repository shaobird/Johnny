"""
Johnny — Personal AI Chief of Staff
Orchestrates Calendar, Fitness, and News agents.
Responds to freeform chat and generates the daily morning briefing.
"""

import anthropic
from agents.calendar import get_todays_events
from agents.fitness import get_fitness_summary
from agents.news import get_high_impact_news
from config import ANTHROPIC_API_KEY

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """\
You are Johnny, the user's personal AI chief of staff. You are professional, \
concise, and proactive. You address the user directly.

You coordinate three specialist agents:
  • Calendar Agent  — checks today's Google Calendar meetings
  • Fitness Agent   — reviews Strava + Hevy workout data and tracks progress
  • News Agent      — fetches high-impact Forex Factory economic events

When the user asks for their daily briefing (or good morning), call all three \
agents and present a clean, structured summary. For other questions, call only \
the relevant agent(s) or answer from your own knowledge.

Format rules:
  - Use plain text with emoji section headers (📅 💪 🔴)
  - Keep each section tight — no filler
  - If an agent returns an error, note it briefly and move on\
"""

_TOOLS = [
    {
        "name": "check_calendar",
        "description": "Get today's meetings and scheduled events from Google Calendar.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_fitness",
        "description": (
            "Get the last 7 days of Strava and Hevy activity, "
            "with a progress summary and recommendation."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_forex_news",
        "description": (
            "Fetch today's high-impact economic events from Forex Factory "
            "(time, currency, event name, forecast, previous)."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

_TOOL_HANDLERS = {
    "check_calendar": get_todays_events,
    "check_fitness": get_fitness_summary,
    "get_forex_news": get_high_impact_news,
}

MAX_ITERATIONS = 10


def chat(message: str, history: list[dict] | None = None) -> str:
    """
    Send a message to Johnny and return his reply.
    `history` is the prior turns as [{"role": ..., "content": ...}, ...].
    The caller is responsible for maintaining and passing history each turn.
    """
    messages = list(history or []) + [{"role": "user", "content": message}]
    return _run_loop(messages)


def daily_briefing() -> str:
    """Trigger the morning briefing — calls all three agents."""
    return chat(
        "Good morning. Give me my full daily briefing: "
        "check my calendar, review my fitness, and pull the high-impact Forex events."
    )


# ── Internal agentic loop ─────────────────────────────────────────────────────

def _run_loop(messages: list[dict]) -> str:
    for _ in range(MAX_ITERATIONS):
        response = _client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
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
                    handler = _TOOL_HANDLERS.get(block.name)
                    result = handler() if handler else f"Unknown tool: {block.name}"
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason — return whatever text we have
        break

    return _extract_text(response)


def _extract_text(response: anthropic.types.Message) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text")
