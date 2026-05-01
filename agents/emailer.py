"""
Emailer — send plain-text email via SMTP.
Used to hand off the weekly construction newsletter to a work mailbox where
Manus AI (or any downstream agent) can pick it up via subject tag.
"""

import smtplib
from email.message import EmailMessage

from config import (
    EMAIL_SMTP_HOST,
    EMAIL_SMTP_PORT,
    EMAIL_USERNAME,
    EMAIL_PASSWORD,
    EMAIL_FROM,
)


def send_email(to: str, subject: str, body: str) -> None:
    """Send a plain-text email. Raises if SMTP creds aren't configured."""
    if not (EMAIL_USERNAME and EMAIL_PASSWORD):
        raise RuntimeError("SMTP credentials missing — set EMAIL_USERNAME / EMAIL_PASSWORD")

    msg = EmailMessage()
    msg["From"] = EMAIL_FROM or EMAIL_USERNAME
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        smtp.send_message(msg)
