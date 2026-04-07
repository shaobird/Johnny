"""
Calendar Agent — Google Calendar
Fetches today's meetings and returns them as a formatted string.

First-time setup:
  1. Go to console.cloud.google.com → create a project
  2. Enable the Google Calendar API
  3. Create OAuth2 credentials (Desktop app) → download as credentials.json
  4. Run this module once directly: python -m agents.calendar
     A browser window will open to authorise access. Token is saved to token.pickle.
"""

import os
import pickle
import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import GOOGLE_CREDENTIALS_FILE

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TOKEN_FILE = "token.pickle"


def get_todays_events() -> str:
    """Return today's calendar events as a formatted string."""
    try:
        creds = _get_credentials()
        service = build("calendar", "v3", credentials=creds)

        now = datetime.datetime.utcnow()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
        day_end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + "Z"

        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=day_start,
                timeMax=day_end,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = result.get("items", [])
        if not events:
            return "No meetings scheduled for today."

        lines = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date", ""))
            summary = event.get("summary", "No title")
            location = event.get("location", "")

            if "T" in start:
                # Timed event — parse and format as local time string
                dt = datetime.datetime.fromisoformat(start)
                time_str = dt.strftime("%I:%M %p").lstrip("0")
            else:
                time_str = "All day"

            line = f"• {time_str} — {summary}"
            if location:
                line += f" ({location})"
            lines.append(line)

        return "\n".join(lines)

    except FileNotFoundError:
        return (
            "Google Calendar not configured. "
            "Add credentials.json and run: python -m agents.calendar"
        )
    except Exception as exc:
        return f"Calendar unavailable: {exc}"


def _get_credentials() -> Credentials:
    creds = None

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return creds


if __name__ == "__main__":
    # Run once to trigger the OAuth browser flow and save token.pickle
    print(get_todays_events())
