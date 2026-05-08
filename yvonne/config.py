"""Yvonne-specific configuration. Falls back to shared keys where appropriate."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # used for embeddings (optional)

YVONNE_TELEGRAM_BOT_TOKEN = os.getenv("YVONNE_TELEGRAM_BOT_TOKEN")
YVONNE_TELEGRAM_CHAT_ID = os.getenv("YVONNE_TELEGRAM_CHAT_ID")

DATA_DIR = Path(os.getenv("YVONNE_DATA_DIR", Path(__file__).parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

WORKSPACE_DIR = Path(os.getenv("YVONNE_WORKSPACE_DIR", DATA_DIR / "workspace"))
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

EMBEDDING_MODEL = os.getenv("YVONNE_EMBEDDING_MODEL", "text-embedding-3-small")

FOUNDER_MODEL = os.getenv("YVONNE_FOUNDER_MODEL", "claude-sonnet-4-6")
SUBAGENT_MODEL = os.getenv("YVONNE_SUBAGENT_MODEL", "claude-haiku-4-5-20251001")

# Local server URL for future on-device tools (LLMs, document indexers, etc.)
LOCAL_SERVER_URL = os.getenv("YVONNE_LOCAL_SERVER_URL")
