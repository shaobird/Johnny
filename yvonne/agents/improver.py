"""
Improvement-proposal agent.

Looks at recent memories, profile, and what Gladys has been asking for, then
proposes new sub-agents / tools / automations that would make Yvonne more
useful. Designed to run on demand (e.g. once a day) — never auto-applied.
Each proposal is appended to data/improvement_proposals.jsonl with a status
of 'pending' until Gladys approves, rejects, or marks it built.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta

import anthropic

from ..config import ANTHROPIC_API_KEY, DATA_DIR, FOUNDER_MODEL
from .. import memory as mem

PROPOSALS_FILE = DATA_DIR / "improvement_proposals.jsonl"
_lock = threading.Lock()
_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

VALID_STATUSES = {"pending", "approved", "rejected", "built"}

_SYSTEM = """\
You are Yvonne's self-improvement agent. You analyse what Gladys (an
insurance agent) has been asking her assistant Yvonne to do, what Yvonne
has been struggling with, and what's missing from her current toolset.

You propose 1–3 concrete improvements. Each must be:
  • Specific — name a sub-agent / tool / automation, not "improve UX".
  • Grounded — tie it to actual evidence from the memory / notes provided.
  • Tractable — buildable in under a day.
  • Distinct — don't repeat anything in PRIOR PROPOSALS.

Return STRICT JSON, no prose:
{
  "proposals": [
    {
      "title": "<3-7 words>",
      "problem": "<what pain this addresses, ground in evidence>",
      "evidence": "<quote or paraphrase from memory/notes>",
      "proposal": "<what to build, named tools/files>",
      "effort": "S | M | L",
      "value": "<why Gladys will care>"
    }
  ]
}

If there's not enough signal yet, return {"proposals": []} with a single
extra field "reason": "<why nothing to propose yet>".
"""


# ── Storage ──────────────────────────────────────────────────────────────────

def _load_proposals() -> list[dict]:
    if not PROPOSALS_FILE.exists():
        return []
    out: list[dict] = []
    with PROPOSALS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _rewrite(proposals: list[dict]) -> None:
    tmp = PROPOSALS_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for p in proposals:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    tmp.replace(PROPOSALS_FILE)


def _append(proposal: dict) -> None:
    with _lock:
        with PROPOSALS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(proposal, ensure_ascii=False) + "\n")


# ── Proposal generation ─────────────────────────────────────────────────────

def _gather_evidence(days: int = 7) -> str:
    """Pull recent memory entries + founder notes for the proposer."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    profile = mem.get_context()

    recent_mem: list[str] = []
    for entry in mem._iter_entries():  # internal helper — fine within package
        if entry.get("ts", "") >= cutoff:
            recent_mem.append(f"  [{entry['ts'][:10]} · {entry.get('kind','note')}] {entry['text']}")

    return (
        f"━━ PROFILE ━━\n{profile}\n\n"
        f"━━ RECENT MEMORIES (last {days} days) ━━\n"
        + ("\n".join(recent_mem[-50:]) if recent_mem else "(none)")
    )


def _prior_titles(limit: int = 30) -> str:
    items = _load_proposals()[-limit:]
    if not items:
        return "(no prior proposals)"
    return "\n".join(
        f"  • [{p.get('status', 'pending')}] {p.get('title', '?')}" for p in items
    )


def propose(days: int = 7) -> str:
    """Run the improvement agent. Append new pending proposals; return a summary."""
    evidence = _gather_evidence(days=days)
    prior = _prior_titles()
    user_msg = (
        f"━━ EVIDENCE ━━\n{evidence}\n\n"
        f"━━ PRIOR PROPOSALS (avoid repeats) ━━\n{prior}\n\n"
        "Now produce the JSON."
    )

    resp = _client.messages.create(
        model=FOUNDER_MODEL,
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = "\n".join(b.text for b in resp.content if b.type == "text").strip()

    try:
        data = json.loads(_strip_code_fence(raw))
    except json.JSONDecodeError:
        return f"Improver returned non-JSON output:\n{raw[:500]}"

    proposals = data.get("proposals", [])
    if not proposals:
        return f"No proposals this round. {data.get('reason', '')}".strip()

    saved: list[str] = []
    for p in proposals:
        record = {
            "id": uuid.uuid4().hex[:8],
            "ts": datetime.now().isoformat(),
            "status": "pending",
            **p,
        }
        _append(record)
        saved.append(f"  • [{record['id']}] ({record.get('effort','?')}) {record['title']}")

    return (
        f"📐 Generated {len(saved)} improvement proposal(s):\n"
        + "\n".join(saved)
        + "\n\nReview them with: list_improvement_proposals\n"
        + "Then approve / reject with: mark_improvement_proposal"
    )


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        first_nl = s.find("\n")
        s = s[first_nl + 1 :] if first_nl != -1 else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


# ── Review / status management ───────────────────────────────────────────────

def list_proposals(status: str | None = None, limit: int = 20) -> str:
    items = _load_proposals()
    if status:
        items = [p for p in items if p.get("status") == status]
    items = items[-limit:]
    if not items:
        return f"No proposals{f' with status {status}' if status else ''}."

    lines = []
    for p in items:
        lines.append(
            f"[{p.get('id','?')}] [{p.get('status','pending')}] "
            f"({p.get('effort','?')}) {p.get('title','?')}\n"
            f"   problem : {p.get('problem','')}\n"
            f"   proposal: {p.get('proposal','')}\n"
            f"   evidence: {p.get('evidence','')}\n"
            f"   value   : {p.get('value','')}"
        )
    return "\n\n".join(lines)


def mark(proposal_id: str, status: str, note: str = "") -> str:
    if status not in VALID_STATUSES:
        return f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}"
    with _lock:
        proposals = _load_proposals()
        for p in proposals:
            if p.get("id") == proposal_id:
                p["status"] = status
                p["status_ts"] = datetime.now().isoformat()
                if note:
                    p["status_note"] = note
                _rewrite(proposals)
                return f"Proposal {proposal_id} marked {status}."
    return f"No proposal with id {proposal_id}."
