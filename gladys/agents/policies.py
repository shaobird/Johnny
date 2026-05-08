"""Policy library sub-agent — store and look up insurance products / policies."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime

from ..config import DATA_DIR
from .. import memory as mem

POLICIES_FILE = DATA_DIR / "policies.json"
_lock = threading.Lock()


def _load() -> list[dict]:
    if POLICIES_FILE.exists():
        return json.loads(POLICIES_FILE.read_text(encoding="utf-8"))
    return []


def _save(records: list[dict]) -> None:
    tmp = POLICIES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(POLICIES_FILE)


def add_policy(name: str, provider: str, category: str, summary: str,
               details: dict | None = None) -> str:
    with _lock:
        records = _load()
        rec = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "provider": provider,
            "category": category,
            "summary": summary,
            "details": details or {},
            "added": datetime.now().isoformat(),
        }
        records.append(rec)
        _save(records)
    mem.remember(
        f"Policy added: {provider} — {name} ({category}). {summary}",
        kind="policy",
    )
    return f"Policy '{name}' from {provider} saved."


def find_policy(query: str) -> str:
    records = _load()
    q = query.strip().lower()
    matches = [
        r for r in records
        if q in r["name"].lower()
        or q in r["provider"].lower()
        or q in r["category"].lower()
        or q in r["summary"].lower()
    ]
    if not matches:
        return f"No policies matching {query!r}."
    return json.dumps(matches, indent=2, ensure_ascii=False)


def list_policies(category: str | None = None) -> str:
    records = _load()
    if category:
        records = [r for r in records if r["category"].lower() == category.lower()]
    if not records:
        return "No policies on file."
    return "\n".join(
        f"  • [{r['category']}] {r['provider']} — {r['name']} (id {r['id']})"
        for r in records
    )


def compare_policies(ids_or_names: list[str]) -> str:
    records = _load()
    by_id = {r["id"]: r for r in records}
    by_name = {r["name"].lower(): r for r in records}
    picked: list[dict] = []
    for q in ids_or_names:
        key = q.strip().lower()
        if key in by_id:
            picked.append(by_id[key])
        elif key in by_name:
            picked.append(by_name[key])
    if len(picked) < 2:
        return "Need at least 2 valid policies to compare."
    return json.dumps(picked, indent=2, ensure_ascii=False)
