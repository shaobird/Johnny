"""
Peter agent — runs the family-CFO loop.

Loads the persona, the relevant skill(s), and the household data files, then
invokes Claude with web_search + web_fetch tools to ground prices, news, rates.
"""

import json
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY

_BASE = Path(__file__).parent
_SKILLS = _BASE / "skills"
_DATA = _BASE / "data"

# Mode → skill file mapping. "auto" loads all four and lets Peter choose.
AVAILABLE_MODES = {
    "portfolio": ["portfolio_review"],
    "couple":    ["couple_planning"],
    "fx":        ["fx_desk"],
    "biz":       ["construction_finance"],
    "auto":      ["portfolio_review", "couple_planning", "fx_desk", "construction_finance"],
}

_MAX_ITERATIONS = 10
_MODEL = "claude-sonnet-4-6"

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def consult_peter(question: str, mode: str = "auto") -> str:
    """
    Ask Peter a financial-services question.

    Args:
      question: The question, ideally framed with any context Johnny has gathered.
      mode:     One of portfolio | couple | fx | biz | auto. Defaults to auto.
    """
    mode = (mode or "auto").lower().strip()
    if mode not in AVAILABLE_MODES:
        return (
            f"Peter: unknown mode '{mode}'. "
            f"Use one of: {', '.join(AVAILABLE_MODES)}."
        )

    persona = (_BASE / "persona.md").read_text(encoding="utf-8")
    skills = "\n\n".join(
        (_SKILLS / f"{name}.md").read_text(encoding="utf-8")
        for name in AVAILABLE_MODES[mode]
    )

    watchlist = _load_data("watchlist")
    couple = _load_data("couple")

    system = (
        f"{persona}\n\n"
        f"━━━ ACTIVE SKILLS ━━━\n{skills}\n\n"
        f"━━━ HOUSEHOLD DATA ━━━\n"
        f"WATCHLIST:\n{watchlist}\n\n"
        f"COUPLE:\n{couple}\n"
    )

    if mode == "auto":
        instruction = (
            "Decide which of your active skills apply to this question and use them. "
            "If multiple apply, blend them. If none cleanly fit, use general financial "
            "judgment grounded in the household data."
        )
    else:
        instruction = f"Use the active skill ({mode}) to answer."

    user_msg = f"{instruction}\n\n━━━ QUESTION ━━━\n{question}"

    tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]

    messages = [{"role": "user", "content": user_msg}]
    response = None

    for _ in range(_MAX_ITERATIONS):
        response = _client.messages.create(
            model=_MODEL,
            max_tokens=8096,
            thinking={"type": "adaptive"},
            system=system,
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
        return "Peter is unavailable right now."
    return "\n".join(b.text for b in response.content if b.type == "text") or "(no reply)"


def _load_data(name: str) -> str:
    """Load a runtime data file (watchlist | couple). Falls back to template."""
    runtime = _DATA / f"{name}.json"
    template = _DATA / f"{name}.template.json"
    path = runtime if runtime.exists() else template
    try:
        return json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2)
    except Exception:
        return f"(no {name} data — populate {runtime.name} from {template.name})"
