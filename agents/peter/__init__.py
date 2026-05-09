"""
Peter — Financial Services sub-agent for Johnny.

Peter is a family-CFO persona serving Boss + Yvonne. He covers four domains:
  • portfolio   — personal investment portfolio review
  • couple      — couple's financial planning (joint goals, savings, scenarios)
  • fx          — forex / macro desk (pre-session, carry, post-trade journal)
  • biz         — construction business finance (project P&L, cashflow, contracts)
  • auto        — Peter picks the relevant skill(s) himself based on the question

Skills are markdown files in agents/peter/skills/. Peter is invoked by Johnny via
the consult_peter() tool — the user always speaks to Johnny.

Adapted from anthropics/financial-services architecture (skills/persona pattern),
with Singapore household context and no MCP / Cowork dependencies.
"""

from .peter import consult_peter, AVAILABLE_MODES
from .router import suggest_mode, format_suggestion

__all__ = ["consult_peter", "AVAILABLE_MODES", "suggest_mode", "format_suggestion"]
