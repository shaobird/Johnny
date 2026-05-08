"""Client / CRM sub-agent — store and retrieve client records."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime

from ..config import DATA_DIR
from .. import memory as mem

CLIENTS_FILE = DATA_DIR / "clients.json"
_lock = threading.Lock()


def _load() -> list[dict]:
    if CLIENTS_FILE.exists():
        return json.loads(CLIENTS_FILE.read_text(encoding="utf-8"))
    return []


def _save(records: list[dict]) -> None:
    tmp = CLIENTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CLIENTS_FILE)


def add_client(name: str, **fields) -> str:
    with _lock:
        records = _load()
        rec = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "created": datetime.now().isoformat(),
            "interactions": [],
            **fields,
        }
        records.append(rec)
        _save(records)
    mem.remember(
        f"Client added: {name}. Details: {json.dumps(fields, ensure_ascii=False)}",
        kind="client",
    )
    return f"Client {name} saved (id {rec['id']})."


def log_interaction(client_query: str, summary: str) -> str:
    """Append an interaction note to the matching client (by name or id)."""
    with _lock:
        records = _load()
        match = _find(records, client_query)
        if not match:
            return f"No client matching {client_query!r}. Add them first."
        match.setdefault("interactions", []).append({
            "ts": datetime.now().isoformat(),
            "summary": summary,
        })
        _save(records)
    mem.remember(f"Interaction with {match['name']}: {summary}", kind="interaction")
    return f"Logged interaction for {match['name']}."


def find_client(query: str) -> str:
    records = _load()
    match = _find(records, query)
    if not match:
        return f"No client matching {query!r}."
    return json.dumps(match, indent=2, ensure_ascii=False)


def list_clients() -> str:
    records = _load()
    if not records:
        return "No clients on file yet."
    lines = []
    for r in records:
        last = r["interactions"][-1]["ts"][:10] if r.get("interactions") else "—"
        lines.append(f"  • {r['name']} (id {r['id']}, last contact: {last})")
    return f"{len(records)} clients on file:\n" + "\n".join(lines)


def _find(records: list[dict], query: str) -> dict | None:
    q = query.strip().lower()
    for r in records:
        if r["id"] == q or r["name"].lower() == q:
            return r
    for r in records:
        if q in r["name"].lower():
            return r
    return None
