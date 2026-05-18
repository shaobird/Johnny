"""
Mnemon — Memory & Learning Agent (sub-agent under Mo)

Where Mo stores files, Mnemon stores what's been *learned* — behavioural
patterns, key decisions and their outcomes, and persistent insights about
the user, the business, and the market.

Mnemon feeds context into:
  • Mo's get_context() — any agent that calls Mo also gets Mnemon's learnings
  • Johnny's system prompt — top patterns are always visible to Johnny

Three memory types:
  • patterns  — observed behavioural regularities ("skips Monday workouts")
  • decisions — choices made + outcomes logged when known
  • insights  — one-line truths about the business/user/market

Signs off as "— Mnemon".
"""

import json
import os
from datetime import datetime

MNEMON_FILE = "storage/memory/mnemon.json"


# ── Storage helpers ────────────────────────────────────────────────────────────

def _load() -> dict:
    if os.path.exists(MNEMON_FILE):
        with open(MNEMON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"patterns": [], "decisions": [], "insights": []}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(MNEMON_FILE), exist_ok=True)
    tmp = MNEMON_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, MNEMON_FILE)


def _next_id(entries: list, prefix: str) -> str:
    return f"{prefix}{len(entries) + 1:04d}"


# ── Pattern memory ─────────────────────────────────────────────────────────────

def log_pattern(category: str, pattern: str, source: str = "johnny") -> str:
    """
    Record an observed behavioural pattern.
    Category: fitness / finance / trading / construction / work / general
    Each time the same pattern is reinforced, increment its observation count.
    """
    data = _load()
    patterns = data["patterns"]

    # Check if a similar pattern already exists
    for p in patterns:
        if p["category"] == category.lower() and pattern.lower()[:40] in p["pattern"].lower():
            p["observations"] = p.get("observations", 1) + 1
            p["last_seen"] = datetime.now().isoformat()[:10]
            p["confidence"] = min(round(p["observations"] / 5, 1), 1.0)
            _save(data)
            return (
                f"Mnemon reinforced pattern [{category}]: \"{p['pattern']}\" "
                f"({p['observations']} observations, confidence {p['confidence']})\n\n— Mnemon"
            )

    # New pattern
    entry = {
        "id": _next_id(patterns, "p"),
        "ts": datetime.now().isoformat(),
        "category": category.lower(),
        "pattern": pattern,
        "confidence": 0.3,
        "observations": 1,
        "last_seen": datetime.now().isoformat()[:10],
        "source": source,
    }
    patterns.append(entry)
    data["patterns"] = patterns
    _save(data)
    return f"Mnemon logged pattern [{category}]: \"{pattern}\"\n\n— Mnemon"


# ── Decision memory ────────────────────────────────────────────────────────────

def log_decision(
    domain: str,
    decision: str,
    outcome: str = "pending",
    lesson: str = "",
) -> str:
    """
    Record a decision and its outcome.
    Domain: construction / finance / trading / tech / personal / general
    Outcome: positive / negative / neutral / pending
    """
    data = _load()
    entry = {
        "id": _next_id(data["decisions"], "d"),
        "ts": datetime.now().isoformat(),
        "domain": domain.lower(),
        "decision": decision,
        "outcome": outcome.lower(),
        "lesson": lesson,
    }
    data["decisions"].append(entry)
    _save(data)
    outcome_str = f" [{outcome}]" if outcome != "pending" else " [pending outcome]"
    return f"Mnemon logged decision [{domain}]: \"{decision}\"{outcome_str}\n\n— Mnemon"


def update_decision_outcome(decision_fragment: str, outcome: str, lesson: str = "") -> str:
    """Update the outcome of a previously logged decision."""
    data = _load()
    for d in reversed(data["decisions"]):
        if decision_fragment.lower() in d["decision"].lower() and d["outcome"] == "pending":
            d["outcome"] = outcome.lower()
            d["lesson"] = lesson
            d["resolved_at"] = datetime.now().isoformat()
            _save(data)
            return (
                f"Mnemon updated decision: \"{d['decision'][:60]}\" → {outcome}"
                f"{f' | Lesson: {lesson}' if lesson else ''}\n\n— Mnemon"
            )
    return f"No pending decision found matching \"{decision_fragment}\".\n\n— Mnemon"


# ── Insight memory ─────────────────────────────────────────────────────────────

def log_insight(category: str, insight: str, relevance: str = "medium") -> str:
    """
    Save a key insight — a one-line truth about the business, user, or market.
    Category: finance / construction / trading / fitness / general
    Relevance: high / medium / low
    """
    data = _load()
    entry = {
        "id": _next_id(data["insights"], "i"),
        "ts": datetime.now().isoformat(),
        "category": category.lower(),
        "insight": insight,
        "relevance": relevance.lower(),
    }
    data["insights"].append(entry)
    _save(data)
    return f"Mnemon saved insight [{category}, {relevance}]: \"{insight}\"\n\n— Mnemon"


# ── Context retrieval ──────────────────────────────────────────────────────────

def get_context(topic: str = "") -> str:
    """
    Return relevant patterns, decisions, and insights for a given topic.
    Called by Mo on every get_context() call so agents always see learnings.
    Pass empty topic to get top patterns across all categories.
    """
    data = _load()
    t = topic.lower()

    def _matches(entry: dict) -> bool:
        if not t:
            return True
        searchable = " ".join([
            entry.get("category", ""),
            entry.get("pattern", ""),
            entry.get("decision", ""),
            entry.get("insight", ""),
            entry.get("domain", ""),
            entry.get("lesson", ""),
        ]).lower()
        return any(word in searchable for word in t.split() if len(word) > 2)

    patterns  = [p for p in data["patterns"]  if _matches(p)]
    decisions = [d for d in data["decisions"] if _matches(d)]
    insights  = [i for i in data["insights"]  if _matches(i)]

    if not patterns and not decisions and not insights:
        return ""  # return empty — Mo will skip silently

    lines = ["🧠 MNEMON'S LEARNINGS:"]

    if patterns:
        # Sort by confidence desc, take top 5
        top = sorted(patterns, key=lambda x: x.get("confidence", 0), reverse=True)[:5]
        lines.append("  Patterns:")
        for p in top:
            conf = f"{int(p.get('confidence', 0) * 100)}% confidence"
            lines.append(f"    • [{p['category']}] {p['pattern']} ({conf})")

    if decisions:
        resolved = [d for d in decisions if d["outcome"] != "pending"][-4:]
        if resolved:
            lines.append("  Past decisions:")
            for d in resolved:
                lesson = f" → {d['lesson']}" if d.get("lesson") else ""
                lines.append(f"    • [{d['domain']}] {d['decision'][:60]} [{d['outcome']}]{lesson}")

    if insights:
        top_i = sorted(insights, key=lambda x: {"high": 2, "medium": 1, "low": 0}.get(x.get("relevance", "low"), 0), reverse=True)[:4]
        lines.append("  Insights:")
        for i in top_i:
            lines.append(f"    • [{i['category']}] {i['insight']}")

    return "\n".join(lines)


def get_all_patterns(category: str = "") -> str:
    """List all logged patterns, optionally filtered by category."""
    data = _load()
    patterns = data["patterns"]
    if category:
        patterns = [p for p in patterns if p["category"] == category.lower()]

    if not patterns:
        label = f"in category \"{category}\"" if category else "yet"
        return f"No patterns logged {label}.\n\n— Mnemon"

    by_cat: dict = {}
    for p in patterns:
        by_cat.setdefault(p["category"], []).append(p)

    cat_icons = {
        "fitness": "🏃", "finance": "💰", "trading": "📈",
        "construction": "🏗️", "work": "💼", "general": "🔍",
    }
    lines = ["━━━ MNEMON'S PATTERN LIBRARY ━━━\n"]
    for cat, entries in sorted(by_cat.items()):
        icon = cat_icons.get(cat, "•")
        lines.append(f"{icon} {cat.upper()}:")
        for p in sorted(entries, key=lambda x: x.get("confidence", 0), reverse=True):
            conf = int(p.get("confidence", 0) * 100)
            obs = p.get("observations", 1)
            lines.append(f"  • {p['pattern']}  ({conf}% conf, {obs} obs)")
    lines.append("\n— Mnemon")
    return "\n".join(lines)


def get_decisions(domain: str = "") -> str:
    """List logged decisions and outcomes, optionally filtered by domain."""
    data = _load()
    decisions = data["decisions"]
    if domain:
        decisions = [d for d in decisions if d["domain"] == domain.lower()]

    if not decisions:
        label = f"in domain \"{domain}\"" if domain else "yet"
        return f"No decisions logged {label}.\n\n— Mnemon"

    lines = ["━━━ MNEMON'S DECISION LOG ━━━\n"]
    for d in reversed(decisions[-20:]):
        outcome_icon = {"positive": "✅", "negative": "❌", "neutral": "⚪", "pending": "⏳"}.get(d["outcome"], "•")
        lines.append(f"{outcome_icon} [{d['ts'][:10]}] [{d['domain']}] {d['decision']}")
        if d.get("lesson"):
            lines.append(f"   → Lesson: {d['lesson']}")
    lines.append("\n— Mnemon")
    return "\n".join(lines)
