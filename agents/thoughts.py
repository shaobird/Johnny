"""
Thoughts — Open Brain capture layer for Mo.

Implements the `capture_thought` API expected by the Open Brain prompt kit
(Memory Migration, Spark, Quick Capture, Weekly Review).

Smart routing:
  • category=preferences → also logged as a Mnemon pattern
  • category=decisions   → also logged as a Mnemon decision
  • all categories       → stored in storage/thoughts/thoughts.json,
                           searchable via search_thoughts() and
                           cross-referenced by Mo's search_knowledge.

Each thought is a self-contained statement that any AI can retrieve later.
"""

import json
import os
from datetime import datetime, timedelta

THOUGHTS_FILE = "storage/thoughts/thoughts.json"

VALID_CATEGORIES = {
    "people", "projects", "preferences", "decisions",
    "topics", "professional", "personal", "general",
}


# ── Storage ────────────────────────────────────────────────────────────────────

def _load() -> list:
    if os.path.exists(THOUGHTS_FILE):
        with open(THOUGHTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save(thoughts: list) -> None:
    os.makedirs(os.path.dirname(THOUGHTS_FILE), exist_ok=True)
    tmp = THOUGHTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(thoughts, f, indent=2, ensure_ascii=False)
    os.replace(tmp, THOUGHTS_FILE)


# ── Capture ────────────────────────────────────────────────────────────────────

def capture_thought(
    thought: str,
    category: str = "general",
    tags: list | None = None,
    source_ai: str = "claude",
) -> str:
    """
    Save a single self-contained thought to the Open Brain.

    category: people | projects | preferences | decisions | topics |
              professional | personal | general
    """
    if not thought or not thought.strip():
        return "No thought provided — nothing saved."

    cat = category.lower().strip()
    if cat not in VALID_CATEGORIES:
        cat = "general"

    thoughts = _load()
    entry = {
        "id":        f"t{len(thoughts) + 1:05d}",
        "ts":        datetime.now().isoformat(),
        "date":      datetime.now().strftime("%Y-%m-%d"),
        "category":  cat,
        "thought":   thought.strip(),
        "tags":      tags or [],
        "source_ai": source_ai.lower(),
    }
    thoughts.append(entry)
    _save(thoughts)

    # Smart routing: preferences and decisions also flow into Mnemon
    side_effect = ""
    try:
        if cat == "preferences":
            from agents.mnemon import log_pattern
            log_pattern("general", thought.strip(), source=f"open-brain/{source_ai}")
            side_effect = " (also logged as Mnemon pattern)"
        elif cat == "decisions":
            from agents.mnemon import log_decision
            log_decision("general", thought.strip())
            side_effect = " (also logged as Mnemon decision)"
    except Exception:
        pass

    return f"✅ Captured [{cat}] {entry['id']}: {thought.strip()[:80]}{'…' if len(thought) > 80 else ''}{side_effect}"


# ── Retrieval ──────────────────────────────────────────────────────────────────

def search_thoughts(query: str, category: str = "") -> str:
    """Keyword search across all stored thoughts."""
    thoughts = _load()
    if not thoughts:
        return "No thoughts captured yet."

    q   = query.lower()
    cat = category.lower().strip()
    results = []

    for t in thoughts:
        if cat and t.get("category") != cat:
            continue
        searchable = " ".join([
            t.get("thought", ""),
            t.get("category", ""),
            " ".join(t.get("tags", [])),
        ]).lower()
        if q in searchable:
            results.append(t)

    if not results:
        return f"No thoughts matching \"{query}\"."

    lines = [f"Found {len(results)} thought(s) matching \"{query}\":"]
    for t in results[-15:]:
        tag_str = f" [{', '.join(t['tags'])}]" if t.get("tags") else ""
        lines.append(f"  [{t['date']}] [{t['category']}]{tag_str} {t['thought'][:140]}")
    return "\n".join(lines)


def list_recent_thoughts(limit: int = 10, category: str = "") -> str:
    """Return the most recent thoughts, optionally filtered by category."""
    thoughts = _load()
    if not thoughts:
        return "No thoughts captured yet."

    cat      = category.lower().strip()
    filtered = [t for t in thoughts if not cat or t.get("category") == cat]
    recent   = filtered[-limit:]

    if not recent:
        label = f" in category \"{category}\"" if category else ""
        return f"No thoughts found{label}."

    cat_icons = {
        "people": "👥", "projects": "📋", "preferences": "⚙️",
        "decisions": "🎯", "topics": "💭", "professional": "💼",
        "personal": "🏠", "general": "•",
    }
    lines = [f"━━━ LAST {len(recent)} THOUGHTS ━━━\n"]
    for t in reversed(recent):
        icon = cat_icons.get(t.get("category", "general"), "•")
        tag_str = f" [{', '.join(t['tags'])}]" if t.get("tags") else ""
        lines.append(f"{icon} [{t['date']}] [{t['category']}]{tag_str}")
        lines.append(f"   {t['thought']}\n")
    return "\n".join(lines)


def thought_stats() -> str:
    """Summary of captured thoughts: total, per-category, recent activity."""
    thoughts = _load()
    if not thoughts:
        return "No thoughts captured yet."

    by_cat: dict = {}
    for t in thoughts:
        c = t.get("category", "general")
        by_cat[c] = by_cat.get(c, 0) + 1

    # Recent activity — last 7 days
    cutoff = datetime.now() - timedelta(days=7)
    recent_count = sum(
        1 for t in thoughts
        if datetime.fromisoformat(t["ts"]) >= cutoff
    )

    total = len(thoughts)
    lines = [f"━━━ OPEN BRAIN STATS ({total} thoughts) ━━━"]
    lines.append(f"Captured in last 7 days: {recent_count}")
    lines.append("")
    lines.append("By category:")
    for cat, count in sorted(by_cat.items(), key=lambda x: x[1], reverse=True):
        pct = round(count / total * 100)
        lines.append(f"  {cat:<14} {count:>4}  ({pct}%)")

    # By source AI
    by_src: dict = {}
    for t in thoughts:
        s = t.get("source_ai", "unknown")
        by_src[s] = by_src.get(s, 0) + 1

    lines.append("")
    lines.append("By source AI:")
    for src, count in sorted(by_src.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"  {src:<14} {count:>4}")

    return "\n".join(lines)


def get_thoughts_for_week(days: int = 7) -> list:
    """Return raw thought entries from the last N days (used by Weekly Review)."""
    thoughts = _load()
    cutoff = datetime.now() - timedelta(days=days)
    return [t for t in thoughts if datetime.fromisoformat(t["ts"]) >= cutoff]
