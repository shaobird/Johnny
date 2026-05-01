import os
from dotenv import load_dotenv

load_dotenv()

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # Your personal chat ID

# Google Calendar
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# Strava
STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
STRAVA_REFRESH_TOKEN = os.getenv("STRAVA_REFRESH_TOKEN")

# Hevy
HEVY_API_KEY = os.getenv("HEVY_API_KEY")

# Scheduler — 24h format, e.g. "07:00"
BRIEFING_TIME = os.getenv("BRIEFING_TIME", "07:00")

# Intel briefing — runs daily at a separate time (web searches take longer)
# Recommend sending 30–60 min after the morning briefing
INTEL_BRIEFING_TIME = os.getenv("INTEL_BRIEFING_TIME", "07:30")

# Weekly construction newsletter — fires every Friday
NEWSLETTER_TIME = os.getenv("NEWSLETTER_TIME", "08:00")

# BCA Contractors Registration System — the user's registered workheads.
# Comma-separated. Optionally append grade (e.g. "CW01-C1") so the agent
# enforces tender-size limits per workhead.
# Approx grade ceilings:
#   CW grades — C3 ≈ 0.65M · C2 ≈ 1.3M · C1 ≈ 4M · B2 ≈ 13M · B1 ≈ 40M
#   CR L grades — L1 ≈ 0.65M · L2 ≈ 1.3M · L3 ≈ 3M · L4 ≈ 13M · L5 ≈ 30M
BCA_WORKHEADS = os.getenv(
    "BCA_WORKHEADS",
    "CR13-L1,CR09-L4,CW01-C1",  # Waterproofing · Repair & Redec · GB
)

# Max tender value to surface, in S$ millions. Override if you want to bid
# bigger. Default matches a C1-grade contractor's ceiling.
TENDER_MAX_SGD_M = float(os.getenv("TENDER_MAX_SGD_M", "10"))

# MrktEdge — High Impact news monitor
MRKTEDGE_EMAIL = os.getenv("MRKTEDGE_EMAIL")
MRKTEDGE_PASSWORD = os.getenv("MRKTEDGE_PASSWORD")

# OpenAI — Whisper voice transcription
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
