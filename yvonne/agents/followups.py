"""Follow-up tracker sub-agent."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, date

from ..config import DATA_DIR
from .. import memory as mem

FOLLOWUPS_FILE = DATA_DIR / "followups.json"
_lock = threading.Lock()


def _load() -> list[dict]:
    if FOLLOWUPS_FILE.exists():
        return json.loads(FOLLOWUPS_FILE.read_text(encoding="utf-8"))
    return []


def _save(records: list[dict]) -> None:
    tmp = FOLLOWUPS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(FOLLOWUPS_FILE)


def add_followup(client: str, due: str, reason: str, channel: str = "call") -> str:
    """due is ISO date YYYY-MM-DD."""
    with _lock:
        records = _load()
        rec = {
            "id": uuid.uuid4().hex[:8],
            "client": client,
            "due": due,
            "reason": reason,
            "channel": channel,
            "status": "open",
            "created": datetime.now().isoformat(),
        }
        records.append(rec)
        _save(records)
    mem.remember(f"Follow-up due {due}: {client} — {reason} via {channel}", kind="followup")
    return f"Follow-up scheduled for {client} on {due}."


def complete_followup(followup_id: str, outcome: str) -> str:
    with _lock:
        records = _load()
        for r in records:
            if r["id"] == followup_id:
                r["status"] = "done"
                r["completed"] = datetime.now().isoformat()
                r["outcome"] = outcome
                _save(records)
                mem.remember(
                    f"Follow-up done: {r['client']} — {outcome}", kind="followup"
                )
                return f"Marked follow-up {followup_id} done."
    return f"No follow-up with id {followup_id}."


def due_today() -> str:
    today = date.today().isoformat()
    records = [r for r in _load() if r["status"] == "open" and r["due"] <= today]
    if not records:
        return "Nothing due today."
    return "\n".join(
        f"  • {r['client']} — {r['reason']} ({r['channel']}, id {r['id']}, due {r['due']})"
        for r in records
    )


def list_open() -> str:
    records = [r for r in _load() if r["status"] == "open"]
    if not records:
        return "No open follow-ups."
    records.sort(key=lambda r: r["due"])
    return "\n".join(
        f"  • {r['due']} — {r['client']} — {r['reason']} ({r['channel']}, id {r['id']})"
        for r in records
    )
