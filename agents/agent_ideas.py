"""
Daily AI agent idea — Smarty researches, Kanaan evaluates.

Runs once daily at 09:00 SGT via the scheduler.
Smarty pulls current AI trends via Gemini Search (research layer).
Kanaan evaluates technical feasibility and fit for Johnny's stack (Haiku — cheap).
Output is stored in Mnemon and pushed to Telegram.

Get past ideas: get_past_ideas(limit)
"""

import json
import os
from datetime import datetime

from config import GEMINI_API_KEY, ANTHROPIC_API_KEY

IDEAS_LOG = "storage/research/agent_ideas.json"


# ── Storage ────────────────────────────────────────────────────────────────────

def _load_ideas() -> list:
    if os.path.exists(IDEAS_LOG):
        with open(IDEAS_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_ideas(ideas: list) -> None:
    os.makedirs(os.path.dirname(IDEAS_LOG), exist_ok=True)
    tmp = IDEAS_LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ideas, f, indent=2, ensure_ascii=False)
    os.replace(tmp, IDEAS_LOG)


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_daily_idea() -> str:
    """
    Smarty researches AI agent trends via Gemini Search.
    Kanaan evaluates technical fit using Haiku (cheap).
    Result stored in Mnemon + returned for Telegram push.
    """
    past = _load_ideas()
    avoid = ", ".join(i.get("name", "") for i in past[-30:]) or "none"

    research = _smarty_research(avoid)
    evaluation = _kanaan_evaluate(research)

    entry = {
        "ts":         datetime.now().isoformat(),
        "date":       datetime.now().strftime("%Y-%m-%d"),
        "name":       _extract_name(research),
        "research":   research,
        "evaluation": evaluation,
    }
    past.append(entry)
    _save_ideas(past)

    # Log in Mnemon as a low-relevance insight (keeps memory lean)
    try:
        from agents.mnemon import log_insight
        log_insight("tech", f"Agent idea {entry['date']}: {entry['name']}", relevance="low")
    except Exception:
        pass

    return (
        f"━━━ 💡 TODAY'S AI AGENT IDEA ({entry['date']}) ━━━\n\n"
        f"🔍 SMARTY'S RESEARCH:\n{research}\n\n"
        f"⚙️  KANAAN'S VERDICT:\n{evaluation}\n\n"
        f"— Smarty + Kanaan"
    )


def get_past_ideas(limit: int = 7) -> str:
    """Return the last N daily agent ideas."""
    ideas = _load_ideas()
    if not ideas:
        return "No agent ideas generated yet. The daily job runs at 09:00."
    recent = ideas[-limit:]
    lines = [f"━━━ LAST {len(recent)} AGENT IDEAS ━━━\n"]
    for idea in reversed(recent):
        lines.append(f"[{idea['date']}] {idea.get('name', 'Unnamed')}")
        lines.append(f"{idea['research'][:220]}…")
        lines.append(f"Kanaan: {idea['evaluation'][:120]}…\n")
    return "\n".join(lines)


# ── Smarty: research layer (Gemini with Search grounding) ─────────────────────

def _smarty_research(avoid: str) -> str:
    prompt = (
        "You are Smarty, Chief of Research. Today's task: identify ONE novel, practical AI agent idea "
        "that is underexplored or hasn't been built well yet.\n\n"
        "Context: For Johnny Zhang — Singapore construction business owner, forex trader, HYROX athlete. "
        "His AI stack: Claude Opus (reasoning), Gemini (research), LLaMA local (Ollama), "
        "Python agents on Mac Mini, Telegram interface.\n\n"
        f"Already proposed — do NOT repeat: {avoid}\n\n"
        "Search recent AI agent developments, open problems, and emerging tools. Propose ONE agent:\n"
        "• Name: [2-3 word name]\n"
        "• Problem it solves: [1 sentence]\n"
        "• How it works: [2-3 sentences]\n"
        "• Why now: [what recent development makes this possible today]\n"
        "• Fit for Johnny: [how it slots into his current setup]\n\n"
        "Be specific. No generic 'AI assistant' ideas. Think niche, high-value, buildable."
    )

    if GEMINI_API_KEY:
        try:
            from google import genai
            from google.genai import types as gt
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt,
                config=gt.GenerateContentConfig(
                    tools=[gt.Tool(google_search=gt.GoogleSearch())],
                ),
            )
            if response.text:
                return response.text
        except Exception as e:
            print(f"[Smarty/agent_ideas] Gemini failed: {e}")

    # Fallback: Haiku without search
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        r = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.content[0].text
    except Exception as e:
        return f"Research unavailable: {e}"


# ── Kanaan: technical evaluation (Haiku — fast and cheap) ─────────────────────

def _kanaan_evaluate(research: str) -> str:
    prompt = (
        "You are Kanaan, Chief of Tech & Dev. Smarty proposed this AI agent idea:\n\n"
        f"{research}\n\n"
        "Evaluate it for Johnny's stack (Python, Claude API, Gemini API, Ollama/LLaMA, Mac Mini, Telegram).\n\n"
        "Sharp technical assessment — under 120 words:\n"
        "• Build complexity: Easy / Medium / Hard\n"
        "• New dependencies needed\n"
        "• How it fits current agents\n"
        "• Verdict: Build now / Backlog / Skip — one clear reason\n\n"
        "No padding. Be direct."
    )
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        r = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.content[0].text
    except Exception as e:
        return f"Kanaan evaluation unavailable: {e}"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_name(research: str) -> str:
    """Best-effort extraction of the agent name from Smarty's research output."""
    for line in research.splitlines():
        if line.strip().lower().startswith("• name:") or line.strip().lower().startswith("name:"):
            return line.split(":", 1)[-1].strip()[:60]
    return research[:40].strip()
