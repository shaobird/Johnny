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
    prompt = f"""You are an expert hybrid fitness coach. Analyse the data below against the user's specific program.

━━━ THE USER'S PROGRAM ━━━
Hybrid athlete: PPL strength (3x/week) + 3 runs/week
Goals: Half marathon + HYROX

Weekly schedule:
  MON — Push (upper body, can push hard)
  TUE — Easy Run Zone 2 (5–7km, HR 130–145 bpm, ~6:20–6:40/km)
  WED — Pull (upper body, can push hard)
  THU — Tempo Run (1km easy + 3–4km tempo + cooldown)
  FRI — Legs (runner-friendly, ALWAYS leave 2 reps in reserve)
  SAT — Intervals (400m or 800m repeats)
  SUN — Long Run (8–12km, slow pace)

Key rules:
  • Legs = strength support, never train to failure
  • Upper body can be pushed hard
  • Leg day must not ruin Saturday intervals
  • User also plays golf and trades forex in evenings — recovery matters

Run baselines:
  • Easy/Zone 2: ~6:20/km @ ~134 bpm (established baseline)
  • Tempo: target ~5:20–5:35/km (to be established)
  • Long run: slow, conversational pace
━━━━━━━━━━━━━━━━━━━━━━━━━━

Today is {today}.

━━━ LAST 7 DAYS OF DATA ━━━
Strava (runs):
{strava}

Hevy (strength sessions):
{hevy}
━━━━━━━━━━━━━━━━━━━━━━━━━━

Respond with a concise analysis (max 6 bullet points) covering:
1. Weekly compliance — did they hit 3 gym sessions and 3 runs? What's missing?
2. Run quality — compare easy runs to 6:20/km baseline. Tempo pace vs target. Long run distance trend.
3. Strength — are they hitting Push/Pull/Legs structure? Any session skipped?
4. Recovery flags — back-to-back hard sessions? Legs too close to intervals?
5. Today's priority — what should they focus on TODAY given the day of week?
6. One specific recommendation to move toward half marathon / HYROX goals.

Be direct and specific. No filler. Reference their actual data and paces."""

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
