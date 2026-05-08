"""
Email drafting sub-agent — runs its own focused Claude call.

Yvonne hands it the goal + context. It returns a draft. Yvonne reviews
the draft (tone, accuracy, Gladys's voice) before showing it to her.
"""

from __future__ import annotations

import anthropic

from ..config import ANTHROPIC_API_KEY, SUBAGENT_MODEL
from .. import memory as mem

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM = """\
You are an email drafter for Gladys, an insurance agent. Draft the email
exactly as she would send it — warm, professional, concise. No filler.
No marketing-speak. Use her preferences and prior style notes when given.
Output ONLY the email body (and a Subject: line on top). Nothing else.
"""


def draft_email(recipient: str, goal: str, context: str = "") -> str:
    voice_hits = mem.recall_text(f"email tone preferences {goal}", limit=3, kind="note")
    profile = mem.get_context()

    user_msg = (
        f"Recipient: {recipient}\n"
        f"Goal of the email: {goal}\n\n"
        f"━━ Gladys's profile ━━\n{profile}\n\n"
        f"━━ Relevant past notes ━━\n{voice_hits}\n\n"
        f"━━ Extra context from Yvonne ━━\n{context or '(none)'}"
    )

    resp = _client.messages.create(
        model=SUBAGENT_MODEL,
        max_tokens=1500,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    return "\n".join(b.text for b in resp.content if b.type == "text")
