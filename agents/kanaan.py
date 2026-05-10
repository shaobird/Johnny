"""
Kanaan — Chief of Technology & Development

Kanaan owns all things technical for Johnny Zhang:
  • Johnny's own development roadmap and backlog
  • Build vs. buy decisions for the construction business
  • AI/automation tool selection and architecture
  • Tech stack decisions — pragmatic, no hype

Kanaan speaks in trade-offs. He has strong opinions, shows his working,
and never recommends a tool he hasn't stress-tested mentally.
Signs off as "— Kanaan".
"""

import json
import os
from datetime import datetime

TECH_LOG = "storage/tech/kanaan_log.json"


# ── Storage helpers ────────────────────────────────────────────────────────────

def _load_log() -> list:
    if os.path.exists(TECH_LOG):
        with open(TECH_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_log(log: list) -> None:
    os.makedirs(os.path.dirname(TECH_LOG), exist_ok=True)
    tmp = TECH_LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    os.replace(tmp, TECH_LOG)


# ── Core operations ────────────────────────────────────────────────────────────

def log_tech_decision(decision: str, rationale: str, status: str = "decided") -> str:
    """Log a tech decision. Status: decided/pending/deferred/rejected."""
    log = _load_log()
    log.append({
        "ts": datetime.now().isoformat(),
        "type": "decision",
        "decision": decision,
        "rationale": rationale,
        "status": status,
    })
    _save_log(log)
    return f"Kanaan logged: {decision} [{status}]\n\n— Kanaan"


def log_tech_task(task: str, priority: str = "medium", notes: str = "") -> str:
    """Add a task to the dev backlog. Priority: high/medium/low."""
    log = _load_log()
    log.append({
        "ts": datetime.now().isoformat(),
        "type": "task",
        "task": task,
        "priority": priority,
        "notes": notes,
        "done": False,
    })
    _save_log(log)
    return f"Kanaan backlog [{priority.upper()}]: {task}\n\n— Kanaan"


def complete_task(task: str) -> str:
    """Mark a backlog task as done by partial name match."""
    log = _load_log()
    for entry in reversed(log):
        if entry.get("type") == "task" and not entry.get("done") and task.lower() in entry["task"].lower():
            entry["done"] = True
            entry["completed_at"] = datetime.now().isoformat()
            _save_log(log)
            return f"Kanaan marked done: {entry['task']}\n\n— Kanaan"
    return f"No open task matching \"{task}\" found.\n\n— Kanaan"


def get_dev_status() -> str:
    """Return open tasks and recent tech decisions."""
    log = _load_log()

    if not log:
        return "No tech decisions or tasks logged yet. Start by logging a decision or adding a backlog item.\n\n— Kanaan"

    open_tasks = [e for e in log if e.get("type") == "task" and not e.get("done")]
    done_count = len([e for e in log if e.get("type") == "task" and e.get("done")])
    recent_decisions = [e for e in log if e.get("type") == "decision"][-6:]

    priority_order = {"high": 0, "medium": 1, "low": 2}
    open_tasks.sort(key=lambda x: priority_order.get(x.get("priority", "medium"), 1))

    lines = ["━━━ KANAAN'S DEV STATUS ━━━\n"]

    if open_tasks:
        lines.append(f"🔧 OPEN TASKS ({len(open_tasks)} open, {done_count} done):")
        for t in open_tasks:
            pri = t.get("priority", "medium").upper()
            lines.append(f"  [{pri}] {t['task']}")
            if t.get("notes"):
                lines.append(f"         → {t['notes']}")
    else:
        lines.append(f"🔧 OPEN TASKS: None ({done_count} completed)")

    if recent_decisions:
        lines.append(f"\n📋 RECENT DECISIONS ({len(recent_decisions)}):")
        for d in recent_decisions:
            status = d.get("status", "decided").upper()
            lines.append(f"  [{d['ts'][:10]}] [{status}] {d['decision']}")
            if d.get("rationale"):
                lines.append(f"         → {d['rationale'][:80]}")

    lines.append("\n— Kanaan")
    return "\n".join(lines)
