"""
Sally — Chief of Marketing & Communications. The newsletter sub-agent.

Sally owns the newsletter domain end-to-end:
  - performance tracking (opens / clicks per issue)
  - topic memory (what we've covered, when)
  - research brief (intel + topic gaps + top performers)
  - drafting (full publishable text in the brand voice)
  - polishing (tighten, punchier, shorter, clarify, headline)
  - shipping (archive to the library + log for performance tracking)

She is not a Telegram bot. She's an internal specialist that Johnny
delegates to. Voice + content themes come from memory.json (alter_ego.*)
and she queries the library agent for term-trends so she doesn't repeat
saturated topics.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, date
from typing import Any

import anthropic

import memory as mem
from agents.library import for_persona
from agents.intel import get_intel_briefing
from config import ANTHROPIC_API_KEY

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
_MODEL = "claude-sonnet-4-6"


# ── Performance tracking & topic memory ─────────────────────────────────────

def log_newsletter(title: str, topic: str, key_points: str = "") -> str:
    """Record a newsletter that was sent. Performance metrics added later."""
    data = mem.load()
    newsletters = data.setdefault("newsletters", [])
    newsletters.append({
        "ts": datetime.now().isoformat(),
        "title": title,
        "topic": topic,
        "key_points": key_points,
        "metrics": None,
    })
    data["newsletters"] = newsletters[-200:]
    mem.save(data)
    return f"Newsletter logged: \"{title}\" (topic: {topic})"


def record_metrics(title: str, opens: int, clicks: int, sent_to: int = 0) -> str:
    """Attach performance metrics to a previously logged newsletter."""
    data = mem.load()
    newsletters = data.get("newsletters", [])

    target = None
    for nl in reversed(newsletters):
        if nl["title"].lower().strip() == title.lower().strip():
            target = nl
            break

    if not target:
        return f"No newsletter found with title \"{title}\". Log it first."

    open_rate = round(opens / sent_to * 100, 1) if sent_to else None
    click_rate = round(clicks / sent_to * 100, 1) if sent_to else None

    target["metrics"] = {
        "opens": opens,
        "clicks": clicks,
        "sent_to": sent_to,
        "open_rate_pct": open_rate,
        "click_rate_pct": click_rate,
        "recorded_at": datetime.now().isoformat(),
    }
    mem.save(data)
    return (
        f"Metrics saved for \"{target['title']}\": "
        f"{opens} opens ({open_rate}%), {clicks} clicks ({click_rate}%)"
    )


def get_recent_topics(weeks: int = 8) -> str:
    """Return topics covered in the last N weeks so we don't repeat."""
    data = mem.load()
    newsletters = data.get("newsletters", [])
    cutoff = (datetime.now() - timedelta(weeks=weeks)).isoformat()
    recent = [nl for nl in newsletters if nl.get("ts", "") >= cutoff]

    if not recent:
        return f"No newsletters logged in the last {weeks} weeks."

    lines = []
    for nl in recent:
        d = nl["ts"][:10]
        metrics = nl.get("metrics") or {}
        perf = ""
        if metrics.get("open_rate_pct") is not None:
            perf = f" · {metrics['open_rate_pct']}% open / {metrics['click_rate_pct']}% click"
        lines.append(f"  [{d}] {nl['title']} — topic: {nl['topic']}{perf}")
    return f"NEWSLETTERS LAST {weeks} WEEKS:\n" + "\n".join(lines)


def get_top_performers(limit: int = 5) -> str:
    """Return best-performing newsletters by open rate."""
    data = mem.load()
    newsletters = data.get("newsletters", [])
    with_metrics = [
        nl for nl in newsletters
        if nl.get("metrics") and nl["metrics"].get("open_rate_pct") is not None
    ]

    if not with_metrics:
        return "No newsletters have performance metrics recorded yet."

    sorted_nls = sorted(
        with_metrics,
        key=lambda n: n["metrics"]["open_rate_pct"],
        reverse=True,
    )[:limit]

    lines = []
    for nl in sorted_nls:
        m = nl["metrics"]
        lines.append(
            f"  • {nl['title']} — {m['open_rate_pct']}% open, {m['click_rate_pct']}% click "
            f"(topic: {nl['topic']})"
        )
    return f"TOP {limit} NEWSLETTERS BY OPEN RATE:\n" + "\n".join(lines)


# ── Research brief ──────────────────────────────────────────────────────────

def prepare_research_brief(angle: str = "") -> str:
    """
    Generate a research brief for the next newsletter.
    Combines intel briefing + recent topic gap analysis + top performers.
    """
    recent = get_recent_topics(weeks=6)
    top = get_top_performers(limit=5)

    print("[Sally] Pulling intel briefing — this may take 1-2 min...")
    intel = get_intel_briefing()

    angle_note = f"REQUESTED ANGLE: {angle}\n\n" if angle else ""

    return f"""━━━ NEWSLETTER RESEARCH BRIEF ━━━
{angle_note}{recent}

{top}

━━━ FRESH INTEL (from today's intel briefing) ━━━
{intel}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Use the intel above as raw input. Avoid repeating topics from the last 6 weeks.
Reference what's worked (top performers) when picking angles.
"""

LENGTH_TARGETS = {
    "short":  "150-250 words",
    "medium": "350-500 words",
    "long":   "700-900 words",
}


def _voice_block() -> str:
    data = mem.load()
    alter = (data.get("agent") or {}).get("alter_ego") or {}
    voice = alter.get("voice", "High-signal, concise, no motivational fluff.")
    themes = alter.get("content_themes") or []
    handle = alter.get("instagram", "")
    return (
        f"VOICE: {voice}\n"
        f"CONTENT THEMES: {', '.join(themes) if themes else '(none set)'}\n"
        f"PUBLIC PERSONA: {handle}"
    )


_SYSTEM = """You are Sally — Chief of Marketing & Communications for Johnny Zhang \
(public alias: Zhang Zhi Yi). You are an editorial specialist, not a chatbot.

Editorial rules — non-negotiable:
- Every sentence earns its place. Cut ruthlessly.
- No motivational fluff, no filler transitions ("In today's fast-paced world…"), no hedging.
- Concrete > abstract. Numbers, names, specific moves.
- One clear idea per piece. State it plainly, defend it, end.
- No emojis unless the user explicitly asks. No exclamation marks unless quoting someone.
- Active voice. Short sentences mixed with the occasional longer one for rhythm.
- If you don't have a sharp angle, say so — do not pad.

Output discipline:
- When asked to draft, return clean publishable text — no meta-commentary, no
  "Here's your draft:" preamble.
- When asked to polish, return only the polished text. No explanations unless
  the user explicitly asks for them.
"""


def _llm(prompt: str, *, max_tokens: int = 1500, system_extra: str = "") -> str:
    voice = _voice_block()
    system = f"{_SYSTEM}\n\n{voice}"
    if system_extra:
        system = f"{system}\n\n{system_extra}"
    resp = _client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if hasattr(b, "text")).strip()


# ── drafting ────────────────────────────────────────────────────────────────

def draft_newsletter(
    angle: str,
    brief: str | None = None,
    length: str = "medium",
) -> dict[str, Any]:
    """
    Produce a full newsletter draft for the given angle.

    Pulls recent topics + top performers + recent library trends so Sally
    knows what's been covered and which terms are dominating coverage.

    Returns: {"title", "hook", "body", "key_points"}
    """
    target = LENGTH_TARGETS.get(length, LENGTH_TARGETS["medium"])
    recent = get_recent_topics(weeks=6)
    top = get_top_performers(limit=5)

    lib = for_persona("johnny")
    try:
        trend = lib.trends(weeks=12, top=10)
        trend_lines = "\n".join(
            f"  - {t['term']}: total={t['total']} across {t['issues']} issues"
            for t in trend["terms"]
        ) or "  (no archived issues yet)"
    except Exception:
        trend_lines = "  (library unavailable)"

    brief_block = f"\nBRIEF / RESEARCH NOTES:\n{brief}\n" if brief else ""

    prompt = f"""Draft a newsletter on this angle:

ANGLE: {angle}

LENGTH TARGET: {target}
{brief_block}
{recent}

{top}

TERM TRENDS IN PAST 12 ISSUES (avoid leaning on what's already saturated):
{trend_lines}

Return a JSON object with exactly these keys:
{{
  "title":       "<subject-line / headline, max 70 chars>",
  "hook":        "<one-sentence opener that earns the read>",
  "body":        "<the full newsletter body in markdown, hitting the length target>",
  "key_points":  "<2-3 bullet summary of the takeaways, semicolon-separated>"
}}

Return ONLY the JSON object. No prose around it."""

    raw = _llm(prompt, max_tokens=2200)
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        return json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return {
            "title": angle[:70],
            "hook": "",
            "body": raw,
            "key_points": "",
        }


# ── polishing ───────────────────────────────────────────────────────────────

POLISH_INTENTS = {
    "tighten":  "Tighten this. Cut filler, sharpen verbs, keep the meaning. Same voice.",
    "punchier": "Make this punchier. Stronger hooks, harder verbs. Don't lose nuance.",
    "shorter":  "Cut to roughly half the length. Keep the core point. Drop everything else.",
    "clarify":  "Clarify. If something is vague or hand-wavy, make it concrete or remove it.",
    "headline": "Rewrite as a single subject-line / headline (max 70 chars). Return only the line.",
}


def polish(text: str, intent: str = "tighten") -> str:
    """Polish a piece of text. Returns only the polished version."""
    instruction = POLISH_INTENTS.get(intent, POLISH_INTENTS["tighten"])
    prompt = f"{instruction}\n\nTEXT:\n{text}"
    return _llm(prompt, max_tokens=1200)


# ── ship ────────────────────────────────────────────────────────────────────

def ship_newsletter(
    title: str,
    body: str,
    *,
    source: str = "alter_ego",
    topic: str = "",
    key_points: str = "",
    issue_date: str | None = None,
) -> str:
    """
    Archive a finished newsletter into the library AND log it to the
    performance tracker. Call this after the user approves the draft.
    """
    issue_iso = issue_date or date.today().isoformat()
    lib = for_persona("johnny")

    md_bytes = f"# {title}\n\n{body}\n".encode("utf-8")
    result = lib.archive_newsletter(
        md_bytes,
        source=source,
        issue_date=issue_iso,
        original_name=f"{issue_iso}_{source}.md",
        title=title,
        summary=key_points or None,
    )

    log_newsletter(title, topic or source, key_points)

    return (
        f"Shipped: \"{title}\"\n"
        f"  archived → {result.rel_path}  ({result.year}-W{result.week:02d}, {result.word_count} words)\n"
        f"  logged for performance tracking"
    )
