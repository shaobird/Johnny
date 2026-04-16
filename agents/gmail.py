"""
Gmail Agent — Johnny's Email Monitor
Scans Johnny's Gmail inbox for high-signal emails and returns summaries.

Uses Gmail API (same OAuth credentials as Calendar).
Filters out newsletters, promotions, and low-signal emails.
Pushes important ones to Telegram instantly.

Setup:
  1. Enable Gmail API in Google Cloud Console (same project as Calendar)
  2. Add Gmail scope to credentials — handled automatically on next OAuth flow
  3. Run: python -m agents.gmail  (triggers re-auth if needed)
"""

import os
import json
import base64
import pickle
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import GOOGLE_CREDENTIALS_FILE

# Include Gmail read scope alongside Calendar
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

TOKEN_FILE = "token.pickle"
SEEN_EMAILS_FILE = "seen_emails.json"

# ── Labels/categories to skip ─────────────────────────────────────────────────
SKIP_CATEGORIES = {
    "CATEGORY_PROMOTIONS",
    "CATEGORY_SOCIAL",
    "CATEGORY_UPDATES",
    "CATEGORY_FORUMS",
}

# ── Keywords that flag an email as high priority ───────────────────────────────
HIGH_PRIORITY_KEYWORDS = [
    "urgent", "action required", "invoice", "payment", "contract",
    "proposal", "quote", "deadline", "breach", "alert", "warning",
    "price", "rate", "market", "forex", "trading", "hyrox", "race",
    "construction", "project", "site", "delivery", "schedule",
]


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_service():
    """Authenticate and return Gmail API service."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                GOOGLE_CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("gmail", "v1", credentials=creds)


# ── Seen emails tracker ───────────────────────────────────────────────────────

def _load_seen() -> set:
    if os.path.exists(SEEN_EMAILS_FILE):
        with open(SEEN_EMAILS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def _save_seen(seen: set) -> None:
    items = list(seen)[-1000:]
    with open(SEEN_EMAILS_FILE, "w") as f:
        json.dump(items, f)


# ── Email parsing ─────────────────────────────────────────────────────────────

def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _get_body(payload: dict) -> str:
    """Extract plain text body from email payload."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    break
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return body[:2000]  # cap at 2000 chars


def _is_high_priority(subject: str, sender: str, body: str) -> bool:
    """Check if email warrants immediate attention."""
    combined = (subject + " " + body).lower()
    return any(kw in combined for kw in HIGH_PRIORITY_KEYWORDS)


def _classify_priority(subject: str, body: str) -> str:
    combined = (subject + " " + body).lower()
    if any(kw in combined for kw in ["urgent", "action required", "deadline", "breach", "warning"]):
        return "🔴 URGENT"
    if any(kw in combined for kw in ["invoice", "payment", "contract", "proposal", "quote"]):
        return "🟡 ACTION NEEDED"
    if any(kw in combined for kw in ["market", "forex", "trading", "price", "rate", "hyrox", "race"]):
        return "📊 MARKET/TRADING"
    if any(kw in combined for kw in ["construction", "project", "site", "delivery", "schedule"]):
        return "🏗️ CONSTRUCTION"
    return "📧 FYI"


# ── Main fetch function ───────────────────────────────────────────────────────

def get_new_emails() -> list[dict]:
    """
    Fetch unread emails from the last 24 hours.
    Returns only new emails not yet seen, filtered for relevance.
    """
    try:
        service = _get_service()
    except Exception as e:
        print(f"[Gmail] Auth failed: {e}")
        return []

    seen = _load_seen()
    new_emails = []

    try:
        # Fetch unread emails from last 24h
        after = int((datetime.now() - timedelta(hours=24)).timestamp())
        result = service.users().messages().list(
            userId="me",
            q=f"is:unread after:{after}",
            maxResults=20,
        ).execute()

        messages = result.get("messages", [])

        for msg in messages:
            msg_id = msg["id"]
            if msg_id in seen:
                continue

            # Get full message
            full = service.users().messages().get(
                userId="me",
                id=msg_id,
                format="full",
            ).execute()

            # Skip promotional/social categories
            label_ids = full.get("labelIds", [])
            if any(cat in label_ids for cat in SKIP_CATEGORIES):
                seen.add(msg_id)
                continue

            headers = full.get("payload", {}).get("headers", [])
            subject = _get_header(headers, "Subject")
            sender  = _get_header(headers, "From")
            date    = _get_header(headers, "Date")
            body    = _get_body(full.get("payload", {}))

            # Only include relevant emails
            if not _is_high_priority(subject, sender, body):
                seen.add(msg_id)
                continue

            priority = _classify_priority(subject, body)

            new_emails.append({
                "id":       msg_id,
                "subject":  subject,
                "sender":   sender,
                "date":     date,
                "body":     body[:500],
                "priority": priority,
            })
            seen.add(msg_id)

    except Exception as e:
        print(f"[Gmail] Fetch failed: {e}")

    _save_seen(seen)
    return new_emails


def format_email(email: dict) -> str:
    """Format an email for Telegram push."""
    lines = [
        f"{email['priority']}",
        f"",
        f"*From:* {email['sender']}",
        f"*Subject:* {email['subject']}",
        f"",
        f"{email['body'][:400]}",
    ]
    if len(email.get("body", "")) > 400:
        lines.append("_[truncated — check Gmail for full email]_")
    return "\n".join(lines)


def get_email_summary() -> str:
    """
    Returns a formatted summary of new relevant emails.
    Called by Johnny as a tool or by the scheduler.
    """
    emails = get_new_emails()
    if not emails:
        return "No new relevant emails."

    lines = [f"📬 {len(emails)} new email(s) worth your attention:\n"]
    for e in emails:
        lines.append(f"{e['priority']} — {e['subject']}")
        lines.append(f"  From: {e['sender']}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    emails = get_new_emails()
    if emails:
        for e in emails:
            print(format_email(e))
            print("---")
    else:
        print("No new relevant emails.")
