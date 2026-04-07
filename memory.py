"""
Johnny's persistent memory.

Stores the user's profile, goals, and notes that Johnny learns over time.
Johnny reads this at every briefing so advice becomes increasingly personalised.

Edit memory.json directly to set your goals and preferences.
Johnny can also update it automatically via the save_note tool.
"""

import json
import os
from datetime import datetime

MEMORY_FILE = "memory.json"

_DEFAULTS: dict = {
    "user": {
        "name": "Boss",
        "timezone": "Asia/Singapore",
        "forex_pairs_watched": ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "NZD", "CHF"],
        "fitness_goals": {
            "cardio": "Run at least 3 times per week",
            "strength": "Progressive overload — increase weight or reps each session",
            "rest": "At least 1 full rest day per week"
        },
        "work_style": "Prefer meetings in the morning, deep work in the afternoon"
    },
    "fitness_baselines": {
        "note": "Johnny will populate this automatically as he sees your data"
    },
    "johnny_notes": [],
    "last_updated": None
}


# ── Public API ────────────────────────────────────────────────────────────────

def load() -> dict:
    """Load memory from disk. Returns defaults if file doesn't exist yet."""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # First run — seed with defaults and save
    save(_DEFAULTS.copy())
    return _DEFAULTS.copy()


def save(data: dict) -> None:
    """Persist memory to disk."""
    data["last_updated"] = datetime.now().isoformat()
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_note(note: str) -> str:
    """Append a note that Johnny wants to remember. Keeps the last 100 notes."""
    data = load()
    notes: list = data.setdefault("johnny_notes", [])
    notes.append({"ts": datetime.now().isoformat(), "note": note})
    data["johnny_notes"] = notes[-100:]
    save(data)
    return f"Note saved: {note}"


def get_context() -> str:
    """
    Return a compact text summary of everything Johnny knows about the user.
    Injected into the system prompt so Johnny always has full context.
    """
    data = load()
    sections: list[str] = []

    # User profile
    user = data.get("user", {})
    if user:
        lines = [f"Name: {user.get('name', 'Boss')}"]
        if tz := user.get("timezone"):
            lines.append(f"Timezone: {tz}")
        if pairs := user.get("forex_pairs_watched"):
            lines.append(f"Forex pairs watched: {', '.join(pairs)}")
        if goals := user.get("fitness_goals"):
            goals_str = "; ".join(f"{k} → {v}" for k, v in goals.items())
            lines.append(f"Fitness goals: {goals_str}")
        if style := user.get("work_style"):
            lines.append(f"Work style: {style}")
        sections.append("USER PROFILE\n" + "\n".join(lines))

    # Fitness baselines (populated over time)
    baselines = data.get("fitness_baselines", {})
    if baselines and "note" not in baselines:
        bl_lines = [f"  {k}: {v}" for k, v in baselines.items()]
        sections.append("FITNESS BASELINES\n" + "\n".join(bl_lines))

    # Recent notes from Johnny
    notes = data.get("johnny_notes", [])
    if notes:
        recent = notes[-10:]  # last 10 notes
        note_lines = [f"  [{n['ts'][:10]}] {n['note']}" for n in recent]
        sections.append("JOHNNY'S NOTES (what I've learned)\n" + "\n".join(note_lines))

    if not sections:
        return "No memory data yet. Edit memory.json to add your profile and goals."

    return "\n\n".join(sections)
