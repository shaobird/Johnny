"""
Sally — Chief of Market Communications

Sally manages all outbound content and newsletter operations.
Three jobs:
  1. Track which newsletters performed best (open rate, click rate)
  2. Remember recent topics so Johnny doesn't suggest repeats
  3. Pull intel briefing data as raw research input
"""

from datetime import datetime, timedelta

import memory as mem
from agents.intel import get_intel_briefing


# ── Logging newsletters ──────────────────────────────────────────────────────

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


# ── Topic memory ─────────────────────────────────────────────────────────────

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
        date = nl["ts"][:10]
        metrics = nl.get("metrics") or {}
        perf = ""
        if metrics.get("open_rate_pct") is not None:
            perf = f" · {metrics['open_rate_pct']}% open / {metrics['click_rate_pct']}% click"
        lines.append(f"  [{date}] {nl['title']} — topic: {nl['topic']}{perf}")
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


# ── Research brief ───────────────────────────────────────────────────────────

def prepare_research_brief(angle: str = "") -> str:
    """
    Generate a fresh research brief for the next newsletter.
    Combines: intel briefing + recent topic gap analysis + suggested angles.
    """
    recent = get_recent_topics(weeks=6)
    top = get_top_performers(limit=5)

    print("[Sally] Pulling intel briefing — this may take 1-2 min...")
    intel = get_intel_briefing()

    angle_note = f"REQUESTED ANGLE: {angle}\n\n" if angle else ""

    return f"""━━━ SALLY'S NEWSLETTER BRIEF ━━━
{angle_note}{recent}

{top}

━━━ FRESH INTEL (from today's intel briefing) ━━━
{intel}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Use the intel above as raw input. Avoid repeating topics from the last 6 weeks.
Reference what's worked (top performers) when picking angles.
"""
