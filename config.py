import os
from dotenv import load_dotenv

load_dotenv()

# Anthropic — thinking / logic / tool-orchestration layer
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

# Google Calendar
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# Strava
STRAVA_CLIENT_ID      = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET  = os.getenv("STRAVA_CLIENT_SECRET")
STRAVA_REFRESH_TOKEN  = os.getenv("STRAVA_REFRESH_TOKEN")

# Hevy
HEVY_API_KEY = os.getenv("HEVY_API_KEY")

# Scheduler times (24h format)
BRIEFING_TIME       = os.getenv("BRIEFING_TIME",       "07:00")
INTEL_BRIEFING_TIME = os.getenv("INTEL_BRIEFING_TIME", "07:30")
AGENT_IDEA_TIME     = os.getenv("AGENT_IDEA_TIME",     "09:00")  # daily Smarty+Kanaan AI agent idea

# MrktEdge
MRKTEDGE_EMAIL    = os.getenv("MRKTEDGE_EMAIL")
MRKTEDGE_PASSWORD = os.getenv("MRKTEDGE_PASSWORD")

# OpenAI — Whisper voice transcription only
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Gemini — research layer (web search, intel briefing, newsletter drafting)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Ollama — local LLaMA execution layer (simple chat, routine tasks, free)
# Point OLLAMA_BASE_URL at your Mac Mini once it's running:
#   e.g. http://192.168.1.XX:11434
# Model recommendations by Mac Mini RAM:
#   8 GB  → llama3.2:3b (safe) or llama3.1:8b (better, tight)
#   16 GB → llama3.3:70b (best quality, full function calling)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL",    "llama3.1:8b")
