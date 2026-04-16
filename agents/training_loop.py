"""
Training Loop Analyzer — Karpathy Loop applied to athletic training.

How it works:
  1. Each week, Johnny reads your Strava + Hevy data (via fitness agent)
  2. Compares against your targets and last week's performance
  3. Proposes one specific adjustment to your training variables
  4. Logs the proposal in training_log.json
  5. Next week, measures whether the metric improved
  6. Keeps patterns that work, flags patterns that don't

Variables tracked:
  - Weekly run volume (km)
  - Long run distance
  - Easy run pace vs Zone 2 target (6:20/km)
  - Gym sessions completed vs planned
  - Rest days taken
  - Subjective recovery (if logged)

Metrics measured:
  - Run pace trend (improving / flat / declining)
  - Weekly consistency (sessions hit / sessions planned)
  - Volume progression (10% rule compliance)
  - Strength progression (weight/reps per movement)

Activates automatically once Strava + Hevy are connected.
Until then, get_training_analysis() returns a placeholder message.
"""

import json
import os
from datetime import datetime, timedelta

TRAINING_LOG_FILE = "training_log.json"

# ── Training log I/O ──────────────────────────────────────────────────────────

def _load_log() -> dict:
    if os.path.exists(TRAINING_LOG_FILE):
        with open(TRAINING_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "weeks": [],
        "proposals": [],
        "patterns": {
            "winning": [],
            "losing":  [],
        },
        "baselines": {
            "easy_run_pace_per_km": "6:20",
            "weekly_run_target_km": 25,
            "gym_sessions_per_week": 3,
            "long_run_target_km": 10,
        }
    }


def _save_log(data: dict) -> None:
    with open(TRAINING_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Log a week's data ─────────────────────────────────────────────────────────

def log_week(
    week_start: str,
    run_volume_km: float,
    long_run_km: float,
    easy_pace_per_km: str,
    gym_sessions: int,
    rest_days: int,
    notes: str = "",
) -> str:
    """
    Log one week of training data. Called automatically by the weekly retro
    once Strava + Hevy are connected and data is available.
    """
    data = _load_log()
    entry = {
        "week_start": week_start,
        "logged_at": datetime.now().isoformat(),
        "run_volume_km": run_volume_km,
        "long_run_km": long_run_km,
        "easy_pace_per_km": easy_pace_per_km,
        "gym_sessions": gym_sessions,
        "rest_days": rest_days,
        "notes": notes,
    }
    data["weeks"].append(entry)
    # Keep last 52 weeks (1 year)
    data["weeks"] = data["weeks"][-52:]
    _save_log(data)
    return f"Week {week_start} logged."


def log_proposal(proposal: str, variable: str, hypothesis: str) -> str:
    """
    Log Johnny's proposed training adjustment for this week.
    Next week's analysis will check if the metric improved.
    """
    data = _load_log()
    data["proposals"].append({
        "ts": datetime.now().isoformat(),
        "proposal": proposal,
        "variable": variable,
        "hypothesis": hypothesis,
        "outcome": None,  # filled in next week
    })
    data["proposals"] = data["proposals"][-26:]  # keep last 6 months
    _save_log(data)
    return "Proposal logged."


def record_outcome(outcome: str, metric_improved: bool) -> str:
    """
    After a week, record whether the proposed change worked.
    Updates the winning/losing patterns lists.
    """
    data = _load_log()
    proposals = data.get("proposals", [])

    # Find the most recent unresolved proposal
    for p in reversed(proposals):
        if p.get("outcome") is None:
            p["outcome"] = outcome
            p["metric_improved"] = metric_improved
            if metric_improved:
                data["patterns"]["winning"].append(p["proposal"])
                data["patterns"]["winning"] = data["patterns"]["winning"][-20:]
            else:
                data["patterns"]["losing"].append(p["proposal"])
                data["patterns"]["losing"] = data["patterns"]["losing"][-20:]
            break

    _save_log(data)
    return "Outcome recorded."


# ── Analysis ──────────────────────────────────────────────────────────────────

def get_training_analysis() -> str:
    """
    Main function called by Johnny during weekly retro.
    Returns a structured analysis of training trends and a proposed adjustment.
    """
    data = _load_log()
    weeks = data.get("weeks", [])

    if len(weeks) < 2:
        return (
            "Training loop: not enough data yet. "
            "Connect Strava and Hevy to start tracking. "
            "Need at least 2 weeks of data before pattern analysis begins."
        )

    baselines = data.get("baselines", {})
    recent = weeks[-4:]  # last 4 weeks
    last_week = weeks[-1]
    prev_week = weeks[-2]

    lines = ["📈 TRAINING LOOP ANALYSIS"]

    # ── Volume trend ──
    volumes = [w["run_volume_km"] for w in recent]
    avg_volume = sum(volumes) / len(volumes)
    target_volume = baselines.get("weekly_run_target_km", 25)
    volume_gap = target_volume - avg_volume
    lines.append(f"\nRun volume (4-week avg): {avg_volume:.1f}km / target {target_volume}km")
    if volume_gap > 5:
        lines.append(f"  ⚠️ Under-target by {volume_gap:.1f}km — consistency issue or recovery needed")
    elif volume_gap < -3:
        lines.append(f"  ⚠️ Over-target by {abs(volume_gap):.1f}km — watch for overtraining")
    else:
        lines.append(f"  ✅ On target")

    # ── Pace trend ──
    def pace_to_seconds(pace: str) -> int:
        try:
            m, s = pace.split(":")
            return int(m) * 60 + int(s)
        except Exception:
            return 0

    target_pace_secs = pace_to_seconds(baselines.get("easy_run_pace_per_km", "6:20"))
    last_pace_secs = pace_to_seconds(last_week.get("easy_pace_per_km", "0:00"))
    prev_pace_secs = pace_to_seconds(prev_week.get("easy_pace_per_km", "0:00"))

    if last_pace_secs and prev_pace_secs:
        pace_delta = last_pace_secs - prev_pace_secs
        direction = "faster 🟢" if pace_delta < 0 else "slower 🔴" if pace_delta > 0 else "same"
        lines.append(f"\nEasy run pace: {last_week.get('easy_pace_per_km')} (was {prev_week.get('easy_pace_per_km')}, {direction})")
        if last_pace_secs > target_pace_secs + 30:
            lines.append(f"  Pace is slower than Zone 2 target — possible fatigue or low aerobic base")

    # ── Gym compliance ──
    gym_target = baselines.get("gym_sessions_per_week", 3)
    last_gym = last_week.get("gym_sessions", 0)
    lines.append(f"\nGym sessions last week: {last_gym} / {gym_target} planned")
    if last_gym < gym_target:
        lines.append(f"  Missed {gym_target - last_gym} session(s)")

    # ── Patterns ──
    patterns = data.get("patterns", {})
    winning = patterns.get("winning", [])
    losing  = patterns.get("losing",  [])
    if winning:
        lines.append(f"\n✅ What's working ({len(winning)} confirmed patterns):")
        for p in winning[-3:]:
            lines.append(f"  • {p}")
    if losing:
        lines.append(f"\n❌ What's not working ({len(losing)} confirmed patterns):")
        for p in losing[-3:]:
            lines.append(f"  • {p}")

    # ── Proposal for next week ──
    proposal = _generate_proposal(data, last_week, prev_week, avg_volume, target_volume)
    lines.append(f"\n🔄 PROPOSED ADJUSTMENT FOR NEXT WEEK:\n{proposal}")

    return "\n".join(lines)


def _generate_proposal(
    data: dict,
    last_week: dict,
    prev_week: dict,
    avg_volume: float,
    target_volume: float,
) -> str:
    """Generate one specific, testable training adjustment for next week."""
    baselines = data.get("baselines", {})
    gym_target = baselines.get("gym_sessions_per_week", 3)

    # Priority 1: gym compliance
    if last_week.get("gym_sessions", 0) < gym_target:
        missed = gym_target - last_week["gym_sessions"]
        return (
            f"Protect your {gym_target} gym sessions next week — you missed {missed} last week. "
            f"Schedule them Monday, Wednesday, Friday before 12pm so meetings can't displace them. "
            f"Hypothesis: pre-scheduling reduces missed sessions by removing the decision."
        )

    # Priority 2: volume too low
    if avg_volume < target_volume - 5:
        return (
            f"Add one extra easy run (5–6km, Zone 2) midweek. "
            f"Your 4-week average is {avg_volume:.1f}km vs {target_volume}km target. "
            f"Hypothesis: one extra easy session closes the volume gap without adding fatigue."
        )

    # Priority 3: pace stagnating
    def pace_to_seconds(pace: str) -> int:
        try:
            m, s = pace.split(":")
            return int(m) * 60 + int(s)
        except Exception:
            return 0

    last_pace = pace_to_seconds(last_week.get("easy_pace_per_km", "0:00"))
    prev_pace = pace_to_seconds(prev_week.get("easy_pace_per_km", "0:00"))
    if last_pace and prev_pace and last_pace >= prev_pace:
        return (
            f"On your next easy run, drop pace to 6:40–6:50/km for the first 20 minutes "
            f"before settling into natural rhythm. "
            f"Hypothesis: starting slower keeps HR lower and builds more aerobic base."
        )

    # Default: hold the course
    return (
        "Hold the current plan — training is on track. "
        "Focus on sleep quality and protein intake this week. "
        "Hypothesis: recovery quality is now the limiting factor, not training stimulus."
    )


# ── Public summary for Johnny ─────────────────────────────────────────────────

def get_summary_for_briefing() -> str:
    """Short version for daily briefing — just the key numbers."""
    data = _load_log()
    weeks = data.get("weeks", [])
    if not weeks:
        return "Training loop: awaiting Strava + Hevy connection."

    last = weeks[-1]
    return (
        f"Last week: {last.get('run_volume_km', 0)}km run, "
        f"{last.get('gym_sessions', 0)} gym sessions, "
        f"{last.get('rest_days', 0)} rest days, "
        f"easy pace {last.get('easy_pace_per_km', 'N/A')}/km"
    )
