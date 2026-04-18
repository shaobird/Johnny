"""
Johnny's persistent memory.

Stores the user's profile, goals, and notes that Johnny learns over time.
Johnny reads this at every briefing so advice becomes increasingly personalised.

Edit memory.json directly to set your goals and preferences.
Johnny can also update it automatically via the save_note tool.
"""

import json
import os
import threading
from datetime import datetime

MEMORY_FILE = "memory.json"
PLAYBOOK_FILE = "playbook.json"

_lock = threading.Lock()

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
    with _lock:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        _save_unlocked(_DEFAULTS.copy())
        return _DEFAULTS.copy()


def save(data: dict) -> None:
    """Persist memory to disk."""
    with _lock:
        _save_unlocked(data)


def _save_unlocked(data: dict) -> None:
    data["last_updated"] = datetime.now().isoformat()
    tmp = MEMORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, MEMORY_FILE)


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

    # Strategic playbook — mental models from top thinkers
    playbook = _load_playbook()
    if playbook:
        pb_lines = []
        for key, thinker in playbook.get("thinkers", {}).items():
            pb_lines.append(f"\n  {thinker['name'].upper()}: {thinker['core_idea']}")
            for m in thinker.get("models", []):
                pb_lines.append(f"    • {m['name']}: {m['principle']}")
        rules = playbook.get("decision_rules", [])
        if rules:
            pb_lines.append("\n  DECISION RULES:")
            for r in rules:
                pb_lines.append(f"    • {r}")
        thesis = playbook.get("wealth_building_thesis", {})
        if thesis:
            pb_lines.append(f"\n  WEALTH THESIS: {thesis.get('core_belief', '')}")
            for p in thesis.get("pillars", []):
                pb_lines.append(f"    • {p}")
        sections.append("STRATEGIC PLAYBOOK (apply these frameworks to every answer)\n" + "\n".join(pb_lines))

    if not sections:
        return "No memory data yet. Edit memory.json to add your profile and goals."

    return "\n\n".join(sections)


def maintain() -> str:
    """
    Lightweight overnight maintenance — no API calls, no cost.
    - Removes exact duplicate notes
    - Keeps notes sorted by timestamp
    - Trims to last 200 notes max
    - Returns a short report of what was cleaned
    """
    data = load()
    notes: list = data.get("johnny_notes", [])
    original_count = len(notes)

    # Remove exact duplicates (same note text), keep most recent
    seen_text: set = set()
    deduped = []
    for note in reversed(notes):
        text = note.get("note", "").strip().lower()
        if text not in seen_text:
            seen_text.add(text)
            deduped.append(note)
    deduped.reverse()

    # Sort by timestamp
    deduped.sort(key=lambda n: n.get("ts", ""))

    # Trim to last 200
    deduped = deduped[-200:]

    data["johnny_notes"] = deduped
    save(data)

    removed = original_count - len(deduped)
    return f"Memory maintenance done: {original_count} notes → {len(deduped)} ({removed} duplicates removed)"


def weekly_summary() -> str:
    """
    Pull the last 7 days of notes for use in the weekly retro.
    Returns formatted text — Johnny's retro prompt uses this as input.
    """
    from datetime import timedelta
    data = load()
    notes = data.get("johnny_notes", [])
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    recent = [n for n in notes if n.get("ts", "") >= cutoff]

    if not recent:
        return "No notes recorded in the last 7 days."

    lines = [f"  [{n['ts'][:10]}] {n['note']}" for n in recent]
    return "NOTES FROM THE LAST 7 DAYS:\n" + "\n".join(lines)


def _load_playbook() -> dict:
    """Load the strategic playbook from disk."""
    if os.path.exists(PLAYBOOK_FILE):
        with open(PLAYBOOK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
