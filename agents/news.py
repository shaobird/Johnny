"""
News Agent — Forex Factory Economic Calendar
Fetches this week's HIGH-IMPACT events via Forex Factory's public XML feed.

Feed URL: https://nfs.faireconomy.media/ff_calendar_thisweek.xml

Filters:
  - impact == "High" only
  - today's date only
  - major currency pairs only (USD, EUR, GBP, JPY, AUD, CAD, NZD, CHF)

Times are converted from US Eastern (ET) to Asia/Singapore (SGT).
No browser or Playwright required.
"""

import os
import datetime
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import requests

# Set to True to also include medium-impact events
INCLUDE_MEDIUM = os.getenv("FF_INCLUDE_MEDIUM", "false").lower() == "true"

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

MAJOR_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "NZD", "CHF"}

ET_ZONE  = ZoneInfo("America/New_York")
SGT_ZONE = ZoneInfo("Asia/Singapore")


def get_high_impact_news() -> str:
    """Return today's high-impact Forex Factory events as a formatted string."""
    try:
        events = _fetch_and_parse()

        if not events:
            return "No high-impact Forex events scheduled for today."

        today_str = datetime.datetime.now(SGT_ZONE).strftime("%a, %b %d").replace(" 0", " ")
        lines = [f"🔴 High-Impact Forex Events — {today_str}", ""]

        for e in events:
            forecast = f"  Forecast: {e['forecast']}" if e["forecast"] else ""
            previous = f"  Prev: {e['previous']}"   if e["previous"]  else ""
            lines.append(f"• {e['time']:>8}  [{e['country']}]  {e['title']}")
            if forecast or previous:
                lines.append(f"           {forecast}{previous}".rstrip())

        return "\n".join(lines)

    except Exception as exc:
        return f"Forex Factory unavailable: {exc}"


# ── Fetch + parse ─────────────────────────────────────────────────────────────

def _fetch_and_parse() -> list[dict]:
    """Fetch the XML feed and return filtered today's high-impact events."""
    resp = requests.get(FEED_URL, timeout=10)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    today_sgt = datetime.datetime.now(SGT_ZONE).date()
    events = []

    for event in root.findall("event"):
        country  = (event.findtext("country") or "").strip()
        title    = (event.findtext("title")   or "").strip()
        impact   = (event.findtext("impact")  or "").strip()
        date_str = (event.findtext("date")    or "").strip()
        time_str = (event.findtext("time")    or "").strip()
        forecast = (event.findtext("forecast") or "").strip()
        previous = (event.findtext("previous") or "").strip()

        # Filter by currency
        if country not in MAJOR_CURRENCIES:
            continue

        # Filter by impact
        if impact == "High":
            pass
        elif INCLUDE_MEDIUM and impact == "Medium":
            pass
        else:
            continue

        # Parse and convert time ET → SGT
        sgt_time, event_date = _convert_time(date_str, time_str)
        if event_date != today_sgt:
            continue

        events.append({
            "title":    title,
            "country":  country,
            "time":     sgt_time,
            "impact":   impact,
            "forecast": forecast,
            "previous": previous,
        })

    # Sort by time
    events.sort(key=lambda e: e["time"])
    return events


def _convert_time(date_str: str, time_str: str) -> tuple[str, datetime.date]:
    """
    Convert an ET datetime string to SGT.
    date_str: e.g. "04-13-2026"
    time_str: e.g. "8:30am"
    Returns: ("8:30pm", date_in_sgt)
    """
    try:
        # Parse date
        event_date_et = datetime.datetime.strptime(date_str, "%m-%d-%Y").date()

        # Parse time — may be empty ("All Day" events)
        if not time_str or time_str.lower() in ("", "all day", "tentative"):
            # No specific time — use midnight ET for date comparison
            et_dt = datetime.datetime.combine(event_date_et, datetime.time(0, 0), tzinfo=ET_ZONE)
        else:
            # e.g. "8:30am", "12:00pm"
            t = datetime.datetime.strptime(time_str.lower().strip(), "%I:%M%p")
            et_dt = datetime.datetime.combine(
                event_date_et,
                t.time(),
                tzinfo=ET_ZONE,
            )

        sgt_dt = et_dt.astimezone(SGT_ZONE)
        time_label = sgt_dt.strftime("%I:%M%p").lstrip("0").lower()  # e.g. "8:30pm"
        return time_label, sgt_dt.date()

    except Exception:
        # If parsing fails, return raw values and today's date
        return time_str, datetime.datetime.now(SGT_ZONE).date()


if __name__ == "__main__":
    print(get_high_impact_news())
