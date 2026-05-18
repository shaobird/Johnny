"""
Sally — Chief of Market Communications

Sally manages all outbound content and newsletter operations:
  1. Track which newsletters performed best (open rate, click rate)
  2. Remember recent topics so Johnny doesn't suggest repeats
  3. Pull intel briefing data as raw research input
  4. Draft full newsletters — subject line, headline, body, CTA
     (Johnny QCs before anything goes to the user)
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


# ── Newsletter drafting ──────────────────────────────────────────────────────

def draft_newsletter(angle: str = "", topic: str = "") -> str:
    """
    Sally drafts a full, ready-to-paste newsletter.
    She checks recent topics, pulls today's intel, then writes the complete copy.
    Uses Gemini (free) first, falls back to Haiku.
    Johnny QCs before this reaches the user.
    """
    from config import GEMINI_API_KEY, ANTHROPIC_API_KEY

    recent = get_recent_topics(weeks=6)
    top = get_top_performers(limit=3)

    print("[Sally] Pulling intel for draft...")
    try:
        intel = get_intel_briefing()
    except Exception as e:
        intel = f"Intel pull failed: {e}"

    angle_line = f"REQUESTED ANGLE: {angle}" if angle else "ANGLE: Your best judgment based on the intel below"
    topic_line = f"TOPIC FOCUS: {topic}\n" if topic else ""

    prompt = f"""You are Sally, Chief of Market Communications for a Singapore construction business newsletter.

{angle_line}
{topic_line}
RECENT TOPICS COVERED — DO NOT repeat these:
{recent}

TOP PERFORMING NEWSLETTERS — emulate what resonates:
{top}

TODAY'S INTEL — use as source material:
{intel}

Write a complete, ready-to-send newsletter. Structure:

SUBJECT LINE: [under 60 characters — must earn the open]

HEADLINE: [punchy main headline]

[Full newsletter body]
• Opening hook (1 short paragraph — why this matters NOW)
• 2-3 substantive sections, each with a subheading
• Practical takeaways the reader can act on this week
• Closing CTA (clear, single action)

Target audience: Singapore construction business owners and contractors.
Tone: Professional but direct. Practical value over theory. No fluff.
Length: 400-550 words for the body.
Format: Plain text, structured for easy paste into a design tool like Manus AI."""

    # Gemini first — free tier
    if GEMINI_API_KEY:
        try:
            from google import genai
            from google.genai import types as genai_types
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt,
            )
            if response.text:
                return response.text
        except Exception as e:
            print(f"[Sally] Gemini draft failed ({e}), falling back to Haiku...")

    # Fallback: Haiku (cheapest Anthropic model)
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1800,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ── Research brief ───────────────────────────────────────────────────────────

def check_alerts() -> list:
    """Return newsletter alerts for the shared dashboard."""
    data = mem.load()
    newsletters = data.get("newsletters", [])
    if not newsletters:
        return []

    last = newsletters[-1]
    try:
        last_ts = datetime.fromisoformat(last["ts"])
        days_since = (datetime.now() - last_ts).days
        if days_since > 21:
            return [{
                "agent": "Sally",
                "priority": "medium",
                "category": "comms",
                "message": f"No newsletter in {days_since} days — last: \"{last['title']}\"",
            }]
        if days_since > 14:
            return [{
                "agent": "Sally",
                "priority": "low",
                "category": "comms",
                "message": f"Newsletter overdue by {days_since - 14} days — consider publishing",
            }]
    except Exception:
        pass
    return []


def prepare_research_brief(angle: str = "") -> str:
    """
    Generate a fresh research brief for the next newsletter.
    Combines: intel briefing + recent topic gap analysis + suggested angles.
    """
    recent = get_recent_topics(weeks=6)
    top = get_top_performers(limit=5)

    print("[Sally] Pulling intel briefing — this may take 1-2 min...")
    try:
        intel = get_intel_briefing()
    except Exception as e:
        intel = "Intel unavailable."

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
