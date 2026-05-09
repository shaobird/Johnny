"""
Mo — Chief Warehouse Manager

Mo is the central storage and retrieval agent for all files.
He ingests documents, auto-summarises them, indexes them by category and tags,
and provides context to Johnny, Val, and other agents on demand.

Storage layout:
  storage/
    index.json          — master manifest
    construction/       — contracts, quotes, site docs
    finance/            — budgets, invoices, cost sheets
    newsletters/        — past newsletters
    research/           — supplier info, market data
    personal/           — misc

Mo is referenced by other agents via get_context() or search().
"""

import json
import os
import shutil
from datetime import datetime

from agents.files import parse_file
from config import GEMINI_API_KEY, ANTHROPIC_API_KEY

STORAGE_DIR = "storage"
INDEX_FILE = os.path.join(STORAGE_DIR, "index.json")

VALID_CATEGORIES = {"construction", "finance", "newsletters", "research", "personal", "other"}


# ── Index helpers ─────────────────────────────────────────────────────────────

def _load_index() -> list:
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_index(index: list) -> None:
    os.makedirs(STORAGE_DIR, exist_ok=True)
    tmp = INDEX_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    os.replace(tmp, INDEX_FILE)


# ── Core operations ───────────────────────────────────────────────────────────

def store_file(
    src_path: str,
    filename: str,
    category: str = "other",
    description: str = "",
    tags: list | None = None,
) -> str:
    """
    Ingest a file into Mo's warehouse.
    Parses the file, auto-summarises, and stores permanently.
    Returns a confirmation with the storage path.
    """
    category = category.lower().strip()
    if category not in VALID_CATEGORIES:
        category = "other"

    dest_dir = os.path.join(STORAGE_DIR, category)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)

    # Copy file to permanent storage
    shutil.copy2(src_path, dest_path)

    # Parse content for summary generation
    parsed = parse_file(dest_path)

    # Auto-generate summary
    summary = _summarise(filename, parsed, description)

    # Update index
    index = _load_index()
    # Remove old entry if re-storing same filename
    index = [e for e in index if e.get("filename") != filename]
    index.append({
        "filename": filename,
        "category": category,
        "path": dest_path,
        "stored_at": datetime.now().isoformat(),
        "description": description,
        "tags": tags or [],
        "summary": summary,
        "char_count": len(parsed),
    })
    _save_index(index)

    return (
        f"Mo stored \"{filename}\" in {category}/\n"
        f"Summary: {summary}"
    )


def search(query: str, category: str = "") -> str:
    """Search Mo's index by keyword. Optionally filter by category."""
    index = _load_index()
    if not index:
        return "Mo's warehouse is empty — no files stored yet."

    q = query.lower()
    cat = category.lower().strip()
    results = []

    for entry in index:
        if cat and entry.get("category") != cat:
            continue
        searchable = " ".join([
            entry.get("filename", ""),
            entry.get("description", ""),
            entry.get("summary", ""),
            " ".join(entry.get("tags", [])),
        ]).lower()
        if q in searchable:
            results.append(entry)

    if not results:
        return f"Mo found nothing matching \"{query}\"."

    lines = [f"Mo found {len(results)} file(s) matching \"{query}\":"]
    for e in results:
        lines.append(
            f"  • [{e['category']}] {e['filename']} ({e['stored_at'][:10]})\n"
            f"    {e['summary'][:120]}{'…' if len(e['summary']) > 120 else ''}"
        )
    return "\n".join(lines)


def get_context(topic: str, max_files: int = 3) -> str:
    """
    Return the most relevant file summaries for a given topic.
    Used by other agents (newsletter, Val, Johnny) to get background context.
    """
    index = _load_index()
    if not index:
        return "Mo has no stored files yet."

    t = topic.lower()
    scored = []
    for entry in index:
        score = 0
        searchable = " ".join([
            entry.get("filename", ""),
            entry.get("description", ""),
            entry.get("summary", ""),
            entry.get("category", ""),
            " ".join(entry.get("tags", [])),
        ]).lower()
        for word in t.split():
            if word in searchable:
                score += 1
        if score > 0:
            scored.append((score, entry))

    if not scored:
        return f"Mo has no files relevant to \"{topic}\"."

    scored.sort(reverse=True)
    top = scored[:max_files]

    lines = [f"Mo's context for \"{topic}\":"]
    for _, e in top:
        lines.append(
            f"\n━━━ {e['filename']} [{e['category']}] ({e['stored_at'][:10]}) ━━━\n"
            f"{e['summary']}"
        )
    return "\n".join(lines)


def get_file_content(filename: str) -> str:
    """Return the full parsed content of a stored file."""
    index = _load_index()
    entry = next((e for e in index if e["filename"] == filename), None)
    if not entry:
        return f"Mo can't find \"{filename}\" in the warehouse."
    return parse_file(entry["path"])


def list_files(category: str = "") -> str:
    """List all files Mo has stored, optionally filtered by category."""
    index = _load_index()
    if not index:
        return "Mo's warehouse is empty."

    cat = category.lower().strip()
    filtered = [e for e in index if not cat or e.get("category") == cat]

    if not filtered:
        return f"No files stored in category \"{cat}\"."

    by_cat: dict = {}
    for e in filtered:
        by_cat.setdefault(e["category"], []).append(e)

    lines = ["Mo's warehouse:"]
    for cat_name, entries in sorted(by_cat.items()):
        lines.append(f"\n📁 {cat_name.upper()} ({len(entries)} files)")
        for e in entries:
            lines.append(f"  • {e['filename']} — {e['summary'][:80]}…")
    return "\n".join(lines)


# ── Auto-summariser ───────────────────────────────────────────────────────────

def _summarise(filename: str, content: str, description: str) -> str:
    """Generate a 1-2 sentence summary using Gemini (free) or Anthropic fallback."""
    prompt = (
        f"File: {filename}\n"
        f"Description: {description or 'none provided'}\n\n"
        f"Content (first 3000 chars):\n{content[:3000]}\n\n"
        "Write a 1-2 sentence summary of what this file contains and what it's useful for. "
        "Be specific — mention key figures, dates, or topics if present."
    )

    if GEMINI_API_KEY:
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            return response.text.strip()
        except Exception:
            pass

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception:
        return description or f"{filename} — no summary available."
