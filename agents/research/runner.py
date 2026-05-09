"""
Shared web-search runner for the research agent.

Primary: Gemini 2.5 Pro with Google Search grounding (free tier, real-time).
Fallback: Claude with native web_search + web_fetch tools.

Skill prompts live in agents/research/skills/*.md and are loaded on demand.
"""

from pathlib import Path

from config import ANTHROPIC_API_KEY, GEMINI_API_KEY

_SKILLS_DIR = Path(__file__).parent / "skills"


def load_skill(name: str, **substitutions: str) -> str:
    """Load a skill prompt by stem (e.g. 'market_research') and substitute {PLACEHOLDERS}."""
    path = _SKILLS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    for key, value in substitutions.items():
        text = text.replace("{" + key + "}", value)
    return text


def run_search(prompt: str) -> str:
    """Execute a grounded search. Tries Gemini first, falls back to Claude web_search."""
    if GEMINI_API_KEY:
        try:
            return _gemini_search(prompt)
        except Exception as exc:
            print(f"[Research] Gemini failed ({exc}); falling back to Claude.")
    return _claude_search(prompt)


def _gemini_search(prompt: str) -> str:
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
        ),
    )
    return response.text


def _claude_search(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]

    messages = [{"role": "user", "content": prompt}]
    response = None
    for _ in range(25):
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=8096,
            thinking={"type": "adaptive"},
            tools=tools,
            messages=messages,
        )
        if response.stop_reason == "end_turn":
            break
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        break

    if not response:
        return "Research unavailable."
    return "\n".join(b.text for b in response.content if b.type == "text")
