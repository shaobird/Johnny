"""
Intel Agent — Daily Intelligence Briefing
Uses Claude + live web search to surface high-signal news across 4 domains,
then applies your personal context to explain what each signal means for
your construction business, forex trading, and hybrid training.

Inspired by the briefing format: headline → what happened → why it matters for you.

Runs daily as part of the morning briefing, or on demand via /intel.
"""

import anthropic
from config import ANTHROPIC_API_KEY

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SEARCH_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]

_SYSTEM = """\
You are a high-signal intelligence analyst and strategic advisor. Your job is to
find the most important recent developments across 4 domains and explain exactly
what each one means for a specific person.

━━━ WHO YOU ARE BRIEFING ━━━
• Runs a construction business (documentation, compliance, coordination, procurement)
• Trades forex in the evenings (macro data, central bank policy, market-moving events)
• Hybrid athlete: training for half marathon + HYROX (running + strength)
• Building AI agents for personal productivity
• Actively tracking where AI and automation is heading as an investment thesis
━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ FORMAT FOR EACH ITEM ━━━
📌 [Headline — factual, specific]
What happened: [1–2 sentences, include names/numbers/dates]
Why it matters for you: [1–3 sentences — tied directly to their construction biz,
  forex trading, training, or AI interest. Never generic.]
━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ DOMAINS TO COVER ━━━
Search each one and find 2–3 genuinely high-signal items:

🤖 AI & AUTOMATION
  Focus: AI agents, frontier model releases, enterprise automation deployment,
  agentic systems in business workflows, AI infrastructure (chips, compute, funding)

🏗️ CONSTRUCTION & PROPERTY
  Focus: Construction industry automation, building material costs, regulation
  changes, property market shifts, workflow tech for contractors/builders

💱 FOREX & MACRO
  Focus: Central bank decisions and signals (Fed, ECB, BOJ, RBA, BOE),
  economic data releases (CPI, NFP, GDP), USD strength/weakness trends,
  anything that will move currency pairs this week

🏃 HYROX & ENDURANCE
  Focus: HYROX race news and format updates, hybrid training science,
  half marathon preparation research, strength+endurance performance studies
━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ END WITH ━━━
🧭 TODAY'S 3 SIGNALS
Three numbered takeaways — specific things to act on or watch today.

━━━ RULES ━━━
• Only include genuinely new, high-signal items from the last 48 hours
• Skip opinion pieces, recycled news, and low-signal fluff
• Be specific — name companies, currencies, percentages, dates
• Apply context ruthlessly — "this matters for YOUR construction contracts" not
  "this matters for business owners generally"
• If a domain has no significant news today, say so in one line and move on\
"""

MAX_ITERATIONS = 25  # More iterations needed — multiple web searches across 4 domains


def get_intel_briefing() -> str:
    """
    Run a live web search across all 4 domains and return a formatted
    daily intelligence briefing with personal context applied.
    """
    messages = [
        {
            "role": "user",
            "content": (
                "Give me today's full intelligence briefing. "
                "Search for the latest high-signal news in each domain: "
                "AI & automation, construction industry, forex & macro markets, "
                "and HYROX / endurance sport. "
                "For each item explain specifically why it matters given my context: "
                "construction business, forex trading evenings, hybrid athlete "
                "training for half marathon + HYROX. "
                "End with 3 specific signals or actions for today."
            ),
        }
    ]

    response: anthropic.types.Message | None = None

    for _ in range(MAX_ITERATIONS):
        response = _client.messages.create(
            model="claude-opus-4-6",
            max_tokens=8096,
            thinking={"type": "adaptive"},
            system=_SYSTEM,
            tools=_SEARCH_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            return _extract_text(response)

        # Server-side search tools hit their iteration limit — re-send to continue
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue

        break  # unexpected stop reason

    return _extract_text(response) if response else "Intel briefing unavailable."


def _extract_text(response: anthropic.types.Message) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text")


if __name__ == "__main__":
    print(get_intel_briefing())
