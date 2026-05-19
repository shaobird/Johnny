"""
AI Session Store — managed by Mo.

Captures Q&A / research from any AI (Claude, Gemini, ChatGPT, Perplexity, etc.)
and stores them in a unified, searchable log at storage/ai_sessions/sessions.json.

Mo uses this so every piece of research done across all AI tools is findable in one place.
"""

import json
import os
from datetime import datetime

SESSIONS_FILE = "storage/ai_sessions/sessions.json"
VALID_SOURCES = {"claude", "gemini", "chatgpt", "perplexity", "grok", "copilot", "manus", "other"}


# ── Storage ────────────────────────────────────────────────────────────────────

def _load() -> list:
    if os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save(sessions: list) -> None:
    os.makedirs(os.path.dirname(SESSIONS_FILE), exist_ok=True)
    tmp = SESSIONS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SESSIONS_FILE)


# ── Session capture ────────────────────────────────────────────────────────────

def capture_session(
    query: str,
    response: str,
    source_ai: str = "claude",
    tags: list | None = None,
    topic: str = "",
) -> str:
    """Save a Q&A exchange from any AI source."""
    sessions = _load()
    source = source_ai.lower().strip()
    if source not in VALID_SOURCES:
        source = "other"

    entry = {
        "id":        f"s{len(sessions) + 1:05d}",
        "ts":        datetime.now().isoformat(),
        "date":      datetime.now().strftime("%Y-%m-%d"),
        "source_ai": source,
        "topic":     topic or _infer_topic(query),
        "query":     query,
        "response":  response,
        "tags":      tags or [],
        "char_count": len(query) + len(response),
    }
    sessions.append(entry)
    _save(sessions)

    # Low-cost Mnemon insight so the topic surfaces in future context
    if len(response) > 200:
        try:
            from agents.mnemon import log_insight
            log_insight("research", f"[{source}] {query[:80]}", relevance="low")
        except Exception:
            pass

    tag_str = ", ".join(tags) if tags else "none"
    return (
        f"Mo saved [{source.upper()}] session: \"{query[:60]}{'…' if len(query) > 60 else ''}\"\n"
        f"Topic: {entry['topic']} | Tags: {tag_str}"
    )


def store_text_document(
    title: str,
    content: str,
    category: str = "research",
    tags: list | None = None,
    source_ai: str = "claude",
) -> str:
    """
    Store a text document directly — no source file required.
    Writes to storage/<category>/<title>.txt and indexes it in Mo's warehouse.
    """
    # Import Mo internals directly to avoid circular dependency
    from agents.mo import STORAGE_DIR, VALID_CATEGORIES, _load_index, _save_index, _summarise

    category = category.lower().strip()
    if category not in VALID_CATEGORIES:
        category = "research"

    dest_dir = os.path.join(STORAGE_DIR, category)
    os.makedirs(dest_dir, exist_ok=True)

    safe_title = "".join(c if c.isalnum() or c in " -_." else "_" for c in title)
    safe_title = safe_title.strip().replace(" ", "_")
    if not safe_title.endswith(".txt"):
        safe_title += ".txt"

    dest_path = os.path.realpath(os.path.join(dest_dir, safe_title))
    if not dest_path.startswith(os.path.realpath(dest_dir)):
        return "Mo rejected document — invalid title (path traversal blocked)."

    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)

    summary = _summarise(safe_title, content, f"[{source_ai}] {title}")

    index = _load_index()
    index = [e for e in index if e.get("filename") != safe_title]
    index.append({
        "filename":   safe_title,
        "category":   category,
        "path":       dest_path,
        "stored_at":  datetime.now().isoformat(),
        "description": title,
        "tags":        (tags or []) + [source_ai],
        "summary":     summary,
        "char_count":  len(content),
        "source_ai":   source_ai,
    })
    _save_index(index)

    return (
        f"Mo stored \"{title}\" → {category}/{safe_title} ({len(content):,} chars)\n"
        f"Summary: {summary}"
    )


# ── Search & retrieval ─────────────────────────────────────────────────────────

def search_sessions(query: str, source_ai: str = "") -> str:
    """Full-text search across all AI sessions."""
    sessions = _load()
    if not sessions:
        return "No AI sessions saved yet."

    q   = query.lower()
    src = source_ai.lower().strip()
    results = []

    for s in sessions:
        if src and s.get("source_ai") != src:
            continue
        searchable = " ".join([
            s.get("query", ""),
            s.get("response", ""),
            s.get("topic", ""),
            " ".join(s.get("tags", [])),
        ]).lower()
        if q in searchable:
            results.append(s)

    if not results:
        return f"No AI sessions matching \"{query}\"."

    lines = [f"Found {len(results)} session(s) matching \"{query}\":"]
    for s in results[-10:]:
        lines.append(
            f"\n[{s['date']}] [{s['source_ai'].upper()}] {s['query'][:80]}"
            f"{'…' if len(s['query']) > 80 else ''}"
        )
        lines.append(f"  → {s['response'][:150]}{'…' if len(s['response']) > 150 else ''}")
    return "\n".join(lines)


def get_recent_sessions(limit: int = 10, source_ai: str = "") -> str:
    """Return the most recent AI sessions, optionally filtered by source."""
    sessions = _load()
    if not sessions:
        return "No AI sessions saved yet."

    src      = source_ai.lower().strip()
    filtered = [s for s in sessions if not src or s.get("source_ai") == src]
    recent   = filtered[-limit:]

    if not recent:
        label = f" from {source_ai}" if source_ai else ""
        return f"No sessions{label} found."

    source_icons = {
        "claude": "🟠", "gemini": "🔵", "chatgpt": "🟢",
        "perplexity": "🟣", "grok": "⚫", "manus": "🔶", "other": "⚪",
    }
    lines = [f"━━━ LAST {len(recent)} AI SESSIONS ━━━\n"]
    for s in reversed(recent):
        icon = source_icons.get(s.get("source_ai", "other"), "•")
        lines.append(
            f"{icon} [{s['date']}] {s.get('source_ai', '?').upper()} | "
            f"{s.get('topic', s['query'][:40])}"
        )
        lines.append(f"   Q: {s['query'][:100]}{'…' if len(s['query']) > 100 else ''}")
        lines.append(f"   A: {s['response'][:120]}{'…' if len(s['response']) > 120 else ''}\n")
    return "\n".join(lines)


def get_session_stats() -> str:
    """Return a summary of how many sessions are stored per AI source."""
    sessions = _load()
    if not sessions:
        return "No AI sessions stored yet."

    by_source: dict = {}
    for s in sessions:
        src = s.get("source_ai", "other")
        by_source[src] = by_source.get(src, 0) + 1

    total = sum(by_source.values())
    lines = [f"━━━ AI SESSION STATS ({total} total) ━━━"]
    for src, count in sorted(by_source.items(), key=lambda x: x[1], reverse=True):
        pct = round(count / total * 100)
        lines.append(f"  {src.upper():<12} {count:>4} sessions  ({pct}%)")
    return "\n".join(lines)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _infer_topic(query: str) -> str:
    keywords = {
        "construction": ["construction", "site", "contract", "concrete", "rebar", "project", "build", "tender"],
        "finance":      ["budget", "cost", "invoice", "revenue", "expenses", "cash", "payment", "profit"],
        "trading":      ["forex", "usd", "sgd", "eur", "trade", "position", "pip", "lot", "xau", "gold"],
        "fitness":      ["hyrox", "workout", "training", "run", "gym", "exercise", "recovery", "race"],
        "ai":           ["ai", "llm", "gpt", "claude", "gemini", "model", "agent", "automation", "mcp"],
    }
    q = query.lower()
    for topic, words in keywords.items():
        if any(w in q for w in words):
            return topic
    return "general"
