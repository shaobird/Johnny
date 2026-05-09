import os
from dotenv import load_dotenv

load_dotenv()

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # Boss's chat ID
TELEGRAM_CHAT_ID_YVONNE = os.getenv("TELEGRAM_CHAT_ID_YVONNE")  # Yvonne's chat ID (Peter access)

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

# Macro brief — FX + central-bank + week-ahead data (research agent)
# Defaults to right after intel; tune to match your trading session prep window
MACRO_BRIEF_TIME = os.getenv("MACRO_BRIEF_TIME", "07:45")

# MrktEdge — High Impact news monitor
MRKTEDGE_EMAIL = os.getenv("MRKTEDGE_EMAIL")
MRKTEDGE_PASSWORD = os.getenv("MRKTEDGE_PASSWORD")

# OpenAI — Whisper voice transcription
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Gemini — web search / intel layer
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
