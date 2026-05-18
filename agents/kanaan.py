"""
Kanaan — Chief of Technology & Development

Kanaan owns all things technical for Johnny Zhang:
  • Johnny's own development roadmap and backlog
  • Build vs. buy decisions for the construction business
  • AI/automation tool selection and architecture
  • Tech stack decisions — pragmatic, no hype
  • Code implementation via Claude API (proposes changes, user approves)

Kanaan speaks in trade-offs. He has strong opinions, shows his working,
and never recommends a tool he hasn't stress-tested mentally.
Signs off as "— Kanaan".
"""

import json
import os
from datetime import datetime

from config import ANTHROPIC_API_KEY

TECH_LOG    = "storage/tech/kanaan_log.json"
JOHNNY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


# ── Dashboard alerts ───────────────────────────────────────────────────────────

def check_alerts() -> list:
    """Return tech/dev alerts for the shared dashboard."""
    alerts = []
    log = _load_log()

    high_tasks = [
        e for e in log
        if e.get("type") == "task" and not e.get("done") and e.get("priority") == "high"
    ]
    if high_tasks:
        tasks_str = " | ".join(t["task"][:35] for t in high_tasks[:3])
        alerts.append({
            "agent": "Kanaan",
            "priority": "medium",
            "category": "tech",
            "message": f"{len(high_tasks)} high-priority task(s) open: {tasks_str}",
        })

    pending_decisions = [
        e for e in log
        if e.get("type") == "decision" and e.get("status") == "pending"
    ]
    if pending_decisions:
        alerts.append({
            "agent": "Kanaan",
            "priority": "low",
            "category": "tech",
            "message": f"{len(pending_decisions)} tech decision(s) pending sign-off",
        })

    return alerts


# ── Code implementation (Claude Code capability) ───────────────────────────────

def code_task(task: str, files: list | None = None) -> str:
    """
    Kanaan uses Claude Sonnet to implement a coding task within the Johnny codebase.

    Workflow:
      1. Reads the relevant files (scoped to JOHNNY_ROOT only)
      2. Generates a full implementation plan + code
      3. Returns the proposed changes — does NOT commit automatically
      4. User must approve before anything is applied

    Args:
        task:  What to build or fix (plain English)
        files: Optional list of specific files to focus on (relative to Johnny root)
    """
    import anthropic

    # Build context from requested files (safety: only within JOHNNY_ROOT)
    file_context = ""
    if files:
        for rel_path in files[:6]:  # cap at 6 files to keep context manageable
            abs_path = os.path.realpath(os.path.join(JOHNNY_ROOT, rel_path))
            if not abs_path.startswith(os.path.realpath(JOHNNY_ROOT)):
                continue  # path traversal guard
            if os.path.isfile(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8") as f:
                        content = f.read(8000)  # cap per-file at 8K chars
                    file_context += f"\n\n━━━ {rel_path} ━━━\n{content}"
                except Exception:
                    pass

    prompt = (
        "You are Kanaan, Chief of Technology & Development for the Johnny AI system.\n"
        "Johnny is a personal AI chief-of-staff built in Python, running on a Mac Mini.\n"
        "Stack: Claude API (Opus/Sonnet/Haiku), Gemini API, Ollama/LLaMA, Telegram bot.\n\n"
        f"TASK:\n{task}\n"
        + (f"\nRELEVANT FILES:{file_context}" if file_context else "") +
        "\n\nProvide:\n"
        "1. Brief implementation plan (3-5 bullet points)\n"
        "2. Complete, working code for each file that needs to change\n"
        "3. Any new files to create (full content)\n"
        "4. Required pip installs (if any)\n"
        "5. One-line summary of what to test after applying\n\n"
        "Format each file as:\n"
        "FILE: <path>\n```python\n<full file content>\n```\n\n"
        "Be precise. No placeholders. Production-ready code only.\n\n— Kanaan"
    )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.content[0].text

        # Log as a pending tech task so it shows up in dev status
        log_tech_task(f"[code_task] {task[:60]}", priority="high",
                      notes="Pending user review and approval before applying.")

        return (
            f"━━━ KANAAN'S CODE PROPOSAL ━━━\n\n"
            f"{result}\n\n"
            f"━━━ REVIEW BEFORE APPLYING ━━━\n"
            f"• Changes above are PROPOSED only — not yet written to disk\n"
            f"• Tell Johnny 'apply Kanaan's changes' to implement\n"
            f"• Or 'reject Kanaan's proposal' to discard\n\n"
            f"— Kanaan"
        )
    except Exception as e:
        return f"Kanaan code task failed: {e}\n\n— Kanaan"


def apply_code_proposal(file_path: str, content: str) -> str:
    """
    Apply a specific file change from Kanaan's proposal.
    Only writes files within JOHNNY_ROOT. User must call this explicitly.
    """
    abs_path = os.path.realpath(os.path.join(JOHNNY_ROOT, file_path))
    if not abs_path.startswith(os.path.realpath(JOHNNY_ROOT)):
        return f"Kanaan blocked: {file_path} is outside the Johnny directory.\n\n— Kanaan"

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)

    log_tech_decision(
        f"Applied code change: {file_path}",
        rationale="User approved Kanaan's code proposal.",
        status="decided",
    )
    return f"Kanaan applied changes to {file_path}. Review with git diff before committing.\n\n— Kanaan"
