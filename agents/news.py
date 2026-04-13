"""
News Agent — Forex Factory Economic Calendar
Scrapes today's HIGH-IMPACT events (red icon) from forexfactory.com/calendar.

What gets scraped (matching what you see in the screenshot):
  • Time        e.g. 8:30pm
  • Currency    e.g. USD
  • Event name  e.g. Core Durable Goods Orders m/m
  • Forecast    e.g. 0.5%
  • Previous    e.g. 0.3%

Impact filter:
  Red   (impact-red) = High   ← we include these
  Orange (impact-ora) = Medium ← skipped by default (change INCLUDE_MEDIUM below)
  Yellow (impact-yel) = Low   ← always skipped

No login required — the public calendar is fully accessible.
If Cloudflare blocks simple requests, install playwright and set USE_PLAYWRIGHT=true in .env.
"""

import os
import datetime
import requests
from bs4 import BeautifulSoup

# Set to True in .env if the simple requests approach gets blocked
USE_PLAYWRIGHT = os.getenv("FF_USE_PLAYWRIGHT", "false").lower() == "true"

# Set to True to also include medium-impact (orange) events
INCLUDE_MEDIUM = os.getenv("FF_INCLUDE_MEDIUM", "false").lower() == "true"

CALENDAR_URL = "https://www.forexfactory.com/calendar"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}


def get_high_impact_news() -> str:
    """Return today's high-impact Forex Factory events as a formatted string."""
    try:
        html = _fetch_html()
        events = _parse_events(html)

        if not events:
            return "No high-impact Forex events scheduled for today."

        today_str = datetime.datetime.now().strftime("%a, %b %d").replace(" 0", " ")
        header = f"🔴 High-Impact Forex Events — {today_str}"
        lines = [header, ""]
        for e in events:
            forecast = f"  Forecast: {e['forecast']}" if e["forecast"] else ""
            previous = f"  Prev: {e['previous']}" if e["previous"] else ""
            lines.append(f"• {e['time']:>8}  [{e['currency']}]  {e['event']}")
            if forecast or previous:
                lines.append(f"           {forecast}{previous}".rstrip())

        return "\n".join(lines)

    except Exception as exc:
        return f"Forex Factory unavailable: {exc}"


# ── HTML fetching ─────────────────────────────────────────────────────────────

def _fetch_html() -> str:
    if USE_PLAYWRIGHT:
        return _fetch_with_playwright()
    return _fetch_with_requests()


def _fetch_with_requests() -> str:
    resp = requests.get(CALENDAR_URL, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def _fetch_with_playwright() -> str:
    """Fallback: use Playwright to render JS and bypass Cloudflare."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(CALENDAR_URL, wait_until="networkidle", timeout=30_000)
        html = page.content()
        browser.close()
        return html


# ── Parsing ───────────────────────────────────────────────────────────────────

def _parse_events(html: str) -> list[dict]:
    """
    Parse the Forex Factory calendar table.

    FF renders one date header row for each new day, then multiple event rows.
    We track the current date as we walk rows and stop once we pass today.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="calendar__table")
    if not table:
        return []

    today = datetime.date.today()
    current_date: datetime.date | None = None
    events: list[dict] = []
    last_time = ""

    for row in table.find_all("tr", class_="calendar__row"):
        # ── Date cell (only present on the first row of each new day) ──
        date_cell = row.find("td", class_="calendar__date")
        if date_cell and date_cell.get_text(strip=True):
            parsed = _parse_ff_date(date_cell.get_text(strip=True))
            if parsed:
                current_date = parsed

        # Stop processing once we pass today
        if current_date and current_date > today:
            break

        # Only process today's rows
        if current_date != today:
            continue

        # ── Impact ──
        impact_span = row.find("td", class_="calendar__impact")
        if not impact_span:
            continue

        span = impact_span.find("span")
        classes = " ".join(span.get("class", [])) if span else ""

        if "impact-red" not in classes:
            if not (INCLUDE_MEDIUM and "impact-ora" in classes):
                continue

        # ── Time ── (FF only shows time on first row of a time block)
        time_cell = row.find("td", class_="calendar__time")
        if time_cell:
            t = time_cell.get_text(strip=True)
            if t:
                last_time = t

        # ── Currency ──
        currency_cell = row.find("td", class_="calendar__currency")
        currency = currency_cell.get_text(strip=True) if currency_cell else ""

        # ── Event name ──
        event_cell = row.find("td", class_="calendar__event")
        event_name = event_cell.get_text(strip=True) if event_cell else ""
        if not event_name:
            continue

        # ── Forecast / Previous ──
        forecast_cell = row.find("td", class_="calendar__forecast")
        previous_cell = row.find("td", class_="calendar__previous")
        forecast = forecast_cell.get_text(strip=True) if forecast_cell else ""
        previous = previous_cell.get_text(strip=True) if previous_cell else ""

        events.append(
            {
                "time": last_time,
                "currency": currency,
                "event": event_name,
                "forecast": forecast,
                "previous": previous,
                "impact": "high" if "impact-red" in classes else "medium",
            }
        )

    return events


def _parse_ff_date(text: str) -> datetime.date | None:
    """
    Forex Factory date cells look like:  'Tue\nApr 7'
    We parse them into a datetime.date using the current year.
    """
    text = text.replace("\n", " ").strip()
    # Remove day-of-week prefix  e.g. "Tue Apr 7" → "Apr 7"
    parts = text.split()
    if len(parts) >= 3:
        # "Tue Apr 7" → try last two parts
        date_str = " ".join(parts[-2:])
    else:
        date_str = text

    year = datetime.date.today().year
    for fmt in ("%b %d", "%b %d"):
        try:
            d = datetime.datetime.strptime(f"{date_str} {year}", f"{fmt} %Y").date()
            # Handle year rollover (December → January)
            if d < datetime.date.today() - datetime.timedelta(days=180):
                d = d.replace(year=year + 1)
            return d
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    print(get_high_impact_news())
