"""
Intel Agent — Daily Intelligence Briefing
Uses Gemini (Google Search grounding) to surface high-signal news across 4 domains,
then applies personal context to explain what each signal means.

Gemini's native Google Search gives real-time, comprehensive results at no cost
on the free tier (1,500 requests/day).
"""

from google import genai
from google.genai import types as genai_types
from config import GEMINI_API_KEY, ANTHROPIC_API_KEY

_PROMPT = """\
You are a high-signal intelligence analyst briefing a specific person. Find the most
important recent developments across 4 domains and explain exactly what each means for them.

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

Search for the latest high-signal news in each of these 4 domains and find 2–3 items each:

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

━━━ END WITH ━━━
🧭 TODAY'S 3 SIGNALS
Three numbered takeaways — specific things to act on or watch today.

━━━ RULES ━━━
• Only include genuinely new, high-signal items from the last 48 hours
• Skip opinion pieces, recycled news, and low-signal fluff
• Be specific — name companies, currencies, percentages, dates
• Apply context ruthlessly — never generic advice
• If a domain has no significant news today, say so in one line and move on\
"""


def get_intel_briefing() -> str:
    """
    Run a live Google Search via Gemini and return a formatted
    daily intelligence briefing with personal context applied.
    Falls back to Claude web search if Gemini is unavailable.
    """
    if GEMINI_API_KEY:
        try:
            return _gemini_search()
        except Exception as e:
            print(f"[Intel] Gemini failed ({e}), falling back to Claude...")

    return _claude_search()


def _gemini_search() -> str:
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=_PROMPT,
        config=genai_types.GenerateContentConfig(
            tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
        ),
    )
    return response.text


def _claude_search() -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    _SEARCH_TOOLS = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209",  "name": "web_fetch"},
    ]

    messages = [{"role": "user", "content": _PROMPT}]
    response = None

    for _ in range(25):
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=8096,
            thinking={"type": "adaptive"},
            tools=_SEARCH_TOOLS,
            messages=messages,
        )
        if response.stop_reason == "end_turn":
            break
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        break

    if not response:
        return "Intel briefing unavailable."
    return "\n".join(b.text for b in response.content if b.type == "text")


if __name__ == "__main__":
    print(get_intel_briefing())
