"""
Fitness Agent — Strava + Hevy
Fetches recent activity data from both apps, then uses Claude to
analyse progress and generate a short advisory for Johnny to relay.

Strava setup:
  1. Go to strava.com/settings/api → create an app
  2. Get client_id, client_secret, and a refresh_token with activity:read scope
  3. Add to .env

Hevy setup:
  1. Open Hevy app → Profile → Settings → API Access → copy your API key
  2. Add to .env
"""

import requests
from datetime import datetime, timedelta

import anthropic

from config import (
    STRAVA_CLIENT_ID,
    STRAVA_CLIENT_SECRET,
    STRAVA_REFRESH_TOKEN,
    HEVY_API_KEY,
    ANTHROPIC_API_KEY,
)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
HEVY_WORKOUTS_URL = "https://api.hevyapp.com/v1/workouts"

LOOKBACK_DAYS = 7


def get_fitness_summary() -> str:
    """
    Pull last 7 days from Strava and Hevy, then ask Claude to
    summarise progress and offer a brief recommendation.
    """
    strava = _fetch_strava()
    hevy = _fetch_hevy()

    if "unavailable" in strava.lower() and "unavailable" in hevy.lower():
        return "Fitness data unavailable — check Strava and Hevy credentials."

    today = datetime.now().strftime("%A")  # e.g. "Monday"
    prompt = f"""You are Val — a sharp, no-nonsense hybrid fitness coach. \
You specialise in run-strength hybrid athletes training for half marathons and HYROX. \
You are direct, data-driven, and never give generic advice. \
You sign off every analysis as "— Val".

━━━ THE USER'S PROGRAM ━━━
Hybrid athlete: PPL strength (3x/week) + 3 runs/week
Goals: Half marathon + HYROX

Weekly schedule:
  MON — Push gym (45 min) + Zone 2 run (25 min, HR 120–139)
  TUE — Easy Run Zone 2 (45 min, conversational)
  WED — Zone 4 intervals (30 min: 10 warm-up + 5×2 min Zone 4 + cooldown). No gym.
  THU — Legs gym (60 min, 2 reps in reserve) + Zone 2 run (25 min, very relaxed)
  FRI — Pull gym (45 min) + Zone 2 run (23 min, optional if fatigued)
  SAT — Easy Run Zone 2 (45 min, same effort as Tuesday)
  SUN — Zone 3 Endurance (1h22: 40 min Z2 → 30 min Z3 → 12 min steady)

Key rules:
  • Legs = strength support only, never to failure, always 2 reps in reserve
  • Upper body can be pushed hard — hit 12 reps both sets then increase weight
  • No gym on Wednesday — recovery spacing critical
  • Sunday Zone 3 session is the most important of the week — protect it

Lactate test zones (22 Apr 2026 — use these, not generic zones):
  • Z1 Easy:      HR <126,     pace >8:25/km
  • Z2 Steady:    HR 127–138,  pace 8:24–7:03/km
  • Z3 Mod Hard:  HR 139–148,  pace 7:02–6:04/km
  • Z4 Hard:      HR 149–154,  pace 6:03–5:47/km
  • Z5 Very Hard: HR 155+,     pace <5:46/km
  • LT1 (aerobic threshold): 133 bpm / 7:30/km
  • LT2 (anaerobic threshold): 149 bpm / 6:03/km

Reality check on goals:
  • 1:45 half marathon = 4:58/km — currently faster than user's Z5. Not realistic short-term.
  • Realistic half marathon range now: 2:05–2:15
  • Path to 1:45: push LT2 down from 6:03/km via consistent Z2 base + Z4 intervals
  • Flag if user is doing "easy" runs at HR >138 — that's actually Z3, not aerobic base
━━━━━━━━━━━━━━━━━━━━━━━━━━

Today is {today}.

━━━ LAST 7 DAYS OF DATA ━━━
Strava (runs):
{strava}

Hevy (strength sessions):
{hevy}
━━━━━━━━━━━━━━━━━━━━━━━━━━

Output exactly this format — no extra text:

*RUNS THIS WEEK*
| Day | Type | Distance | Time | HR | vs Target |
|-----|------|----------|------|----|-----------|
[one row per run, mark ✅ or ⚠️ in vs Target]

*GYM THIS WEEK*
| Day | Session | Exercises |
|-----|---------|-----------|
[one row per session]

*COMPLIANCE:* X/3 gym · X/6 runs
*ZONE ALERT:* [flag any run with HR >138 as Z3, not Z2]
*TODAY:* [one sentence — what to do today]
*FIX THIS WEEK:* [one sentence — biggest gap]"""

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    texts = [b.text for b in response.content if b.type == "text"]
    return texts[0] if texts else "Fitness analysis unavailable."


# ── Strava ────────────────────────────────────────────────────────────────────

def _fetch_strava() -> str:
    if not all([STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN]):
        return "Strava unavailable — credentials not configured."

    try:
        access_token = _refresh_strava_token()
        since = int((datetime.now() - timedelta(days=LOOKBACK_DAYS)).timestamp())

        resp = requests.get(
            STRAVA_ACTIVITIES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"after": since, "per_page": 15},
            timeout=15,
        )
        resp.raise_for_status()
        activities = resp.json()

        if not activities:
            return f"No Strava activities in the last {LOOKBACK_DAYS} days."

        lines = []
        for a in activities:
            date = a.get("start_date_local", "")[:10]
            sport = a.get("sport_type") or a.get("type", "Activity")
            name = a.get("name", sport)
            km = round(a.get("distance", 0) / 1000, 2)
            mins = a.get("moving_time", 0) // 60
            hr = a.get("average_heartrate")
            hr_str = f", avg HR {int(hr)} bpm" if hr else ""
            lines.append(f"• {date} [{sport}] {name} — {km} km, {mins} min{hr_str}")

        return "\n".join(lines)

    except Exception as exc:
        return f"Strava unavailable: {exc}"


def _refresh_strava_token() -> str:
    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "refresh_token": STRAVA_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


# ── Hevy ──────────────────────────────────────────────────────────────────────

def _fetch_hevy() -> str:
    if not HEVY_API_KEY:
        return "Hevy unavailable — API key not configured."

    try:
        resp = requests.get(
            HEVY_WORKOUTS_URL,
            headers={"api-key": HEVY_API_KEY},
            params={"page": 1, "pageSize": 10},
            timeout=15,
        )
        resp.raise_for_status()
        workouts = resp.json().get("workouts", [])

        if not workouts:
            return "No recent Hevy workouts."

        lines = []
        for w in workouts:
            date = (w.get("start_time") or "")[:10]
            title = w.get("title", "Workout")
            exercises = w.get("exercises", [])
            ex_list = [e.get("title", "") for e in exercises[:4] if e.get("title")]
            ex_str = ", ".join(ex_list) + ("…" if len(exercises) > 4 else "")
            lines.append(f"• {date} — {title}: {ex_str}")

        return "\n".join(lines)

    except Exception as exc:
        return f"Hevy unavailable: {exc}"


if __name__ == "__main__":
    print(get_fitness_summary())
