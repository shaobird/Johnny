"""
Yvonne's memory layer (Gladys is the human user).

Two stores:
  • profile.json — structured facts Gladys teaches Yvonne (name, products
    she sells, work style, preferences, hard rules). Read into the system
    prompt every turn.
  • vector_store.jsonl — long-tail recall. Each entry is {ts, kind, text,
    embedding}. Semantic search over past conversations, decisions, client
    interactions. Falls back to keyword search if embeddings aren't
    configured.

Yvonne (the founder agent) writes to both. Sub-agents read from both.
"""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .config import DATA_DIR, EMBEDDING_MODEL, OPENAI_API_KEY

PROFILE_FILE = DATA_DIR / "profile.json"
VECTOR_FILE = DATA_DIR / "vector_store.jsonl"

_lock = threading.Lock()

_DEFAULT_PROFILE: dict = {
    "user": {
        "name": "Gladys",
        "role": "Insurance agent",
        "company": None,
        "products_sold": [],
        "target_clients": None,
        "work_style": None,
        "preferences": [],
    },
    "rules": [],
    "founder_notes": [],
    "last_updated": None,
}


# ── Profile (structured) ──────────────────────────────────────────────────────

def load_profile() -> dict:
    with _lock:
        if PROFILE_FILE.exists():
            return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        _save_profile_unlocked(dict(_DEFAULT_PROFILE))
        return dict(_DEFAULT_PROFILE)


def save_profile(data: dict) -> None:
    with _lock:
        _save_profile_unlocked(data)


def _save_profile_unlocked(data: dict) -> None:
    data["last_updated"] = datetime.now().isoformat()
    tmp = PROFILE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PROFILE_FILE)


def update_profile(path: list[str], value) -> str:
    """Set a nested key. e.g. update_profile(['user', 'company'], 'AIA')."""
    if not path:
        return "No path provided."
    data = load_profile()
    cursor = data
    for key in path[:-1]:
        cursor = cursor.setdefault(key, {})
    cursor[path[-1]] = value
    save_profile(data)
    return f"Updated profile: {' → '.join(path)} = {value!r}"


def add_rule(rule: str) -> str:
    data = load_profile()
    rules = data.setdefault("rules", [])
    if rule not in rules:
        rules.append(rule)
        save_profile(data)
    return f"Rule recorded: {rule}"


def add_founder_note(note: str) -> str:
    data = load_profile()
    notes = data.setdefault("founder_notes", [])
    notes.append({"ts": datetime.now().isoformat(), "note": note})
    data["founder_notes"] = notes[-200:]
    save_profile(data)
    return f"Note saved."


def get_context() -> str:
    """Return a compact text summary of what Yvonne knows about Gladys."""
    data = load_profile()
    sections: list[str] = []

    user = data.get("user", {})
    if user:
        lines = []
        for k, label in [
            ("name", "Name"),
            ("role", "Role"),
            ("company", "Company"),
            ("target_clients", "Target clients"),
            ("work_style", "Work style"),
        ]:
            if user.get(k):
                lines.append(f"{label}: {user[k]}")
        if products := user.get("products_sold"):
            lines.append(f"Products sold: {', '.join(products)}")
        if prefs := user.get("preferences"):
            lines.append("Preferences:")
            for p in prefs:
                lines.append(f"  • {p}")
        if lines:
            sections.append("USER PROFILE\n" + "\n".join(lines))

    rules = data.get("rules") or []
    if rules:
        sections.append("HARD RULES (always honour)\n" + "\n".join(f"  • {r}" for r in rules))

    notes = data.get("founder_notes") or []
    if notes:
        recent = notes[-15:]
        sections.append(
            "RECENT FOUNDER NOTES\n"
            + "\n".join(f"  [{n['ts'][:10]}] {n['note']}" for n in recent)
        )

    return "\n\n".join(sections) if sections else "No profile data yet — ask Gladys about herself."


# ── Vector store (semantic recall) ────────────────────────────────────────────

@dataclass
class MemoryHit:
    ts: str
    kind: str
    text: str
    score: float


def _embed(text: str) -> list[float] | None:
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return resp.data[0].embedding
    except Exception as e:
        print(f"[yvonne.memory] embed failed: {e}")
        return None


def remember(text: str, kind: str = "note") -> str:
    """Append a memory to the vector store. Embeds if possible."""
    text = text.strip()
    if not text:
        return "Empty memory — skipped."
    entry = {
        "ts": datetime.now().isoformat(),
        "kind": kind,
        "text": text,
        "embedding": _embed(text),
    }
    with _lock:
        with VECTOR_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    mode = "embedded" if entry["embedding"] else "stored (no embedding)"
    return f"Memory {mode}: {text[:80]}"


def _iter_entries() -> Iterable[dict]:
    if not VECTOR_FILE.exists():
        return
    with VECTOR_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def recall(query: str, limit: int = 5, kind: str | None = None) -> list[MemoryHit]:
    """Semantic search over past memories. Falls back to keyword overlap."""
    entries = [e for e in _iter_entries() if not kind or e.get("kind") == kind]
    if not entries:
        return []

    q_emb = _embed(query)
    hits: list[MemoryHit] = []

    if q_emb:
        for e in entries:
            emb = e.get("embedding")
            if not emb:
                continue
            hits.append(
                MemoryHit(ts=e["ts"], kind=e.get("kind", "note"),
                          text=e["text"], score=_cosine(q_emb, emb))
            )

    if not hits:
        # keyword fallback — token overlap
        q_tokens = {t.lower() for t in query.split() if len(t) > 2}
        for e in entries:
            tokens = {t.lower() for t in e["text"].split() if len(t) > 2}
            overlap = len(q_tokens & tokens)
            if overlap:
                hits.append(
                    MemoryHit(ts=e["ts"], kind=e.get("kind", "note"),
                              text=e["text"], score=float(overlap))
                )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def recall_text(query: str, limit: int = 5, kind: str | None = None) -> str:
    hits = recall(query, limit=limit, kind=kind)
    if not hits:
        return f"No memories found for: {query!r}"
    return "\n".join(
        f"[{h.ts[:10]} · {h.kind} · score {h.score:.2f}] {h.text}" for h in hits
    )
