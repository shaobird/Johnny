"""Gladys-specific configuration. Falls back to shared keys where appropriate."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # used for embeddings (optional)

GLADYS_TELEGRAM_BOT_TOKEN = os.getenv("GLADYS_TELEGRAM_BOT_TOKEN")
GLADYS_TELEGRAM_CHAT_ID = os.getenv("GLADYS_TELEGRAM_CHAT_ID")

DATA_DIR = Path(os.getenv("GLADYS_DATA_DIR", Path(__file__).parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

WORKSPACE_DIR = Path(os.getenv("GLADYS_WORKSPACE_DIR", DATA_DIR / "workspace"))
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

EMBEDDING_MODEL = os.getenv("GLADYS_EMBEDDING_MODEL", "text-embedding-3-small")

FOUNDER_MODEL = os.getenv("GLADYS_FOUNDER_MODEL", "claude-sonnet-4-6")
SUBAGENT_MODEL = os.getenv("GLADYS_SUBAGENT_MODEL", "claude-haiku-4-5-20251001")
