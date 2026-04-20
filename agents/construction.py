"""
Construction Newsletter Agent — Weekly Friday Briefing

Generates a weekly intelligence newsletter for a Singapore construction business
owner. Uses Claude + live web search to pull high-signal items across four
tightly scoped domains:

  1. 🌍 Global construction tech — robotics, modular, BIM, 3D printing, materials
  2. 🦺 Singapore WSH bulletin — MOM / WSH Council incidents, advisories, prosecutions
  3. 📊 Singapore construction & FM market data — BCA, URA, industry outlook
  4. 💰 Singapore government agency budgets & tenders — MND, LTA, HDB, JTC, NEA,
     PUB, BCA, MOH, MOE, MINDEF, URA, GeBIZ

Ends with: THIS WEEK'S 3 BETS — concrete actions / bids / reads for the coming week.

Scheduled delivery: Friday mornings (configurable via NEWSLETTER_TIME).
On-demand via /newsletter in Telegram.
"""

import anthropic
from config import ANTHROPIC_API_KEY

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SEARCH_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]

_SYSTEM = """\
You are a senior industry analyst producing a weekly Friday newsletter for the
owner of a Singapore construction company. Your job: surface the highest-signal
developments from the last 7 days and translate each one into an implication
for a Singapore contractor who also handles facility maintenance.

━━━ READER PROFILE ━━━
• Runs a construction + facility maintenance business in Singapore
• Bids on public-sector work via GeBIZ; tracks government agency capex closely
• Cares about WSH compliance — no tolerance for safety incidents on site
• Curious about where global construction tech is heading (robotics, modular,
  prefab, BIM, 3D printing, digital twins, drones, AI takeoff, green materials)
━━━━━━━━━━━━━━━━━━━━━

━━━ NEWSLETTER STRUCTURE ━━━
Produce EXACTLY this structure, in this order:

🏗️ *WEEKLY CONSTRUCTION INTEL*
[One-line dateline: week ending DD Mon YYYY]

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌍 *GLOBAL CONSTRUCTION TECH*
3–4 items from anywhere in the world. Cover a mix of:
  robotics & automation on site, modular / prefab, 3D-printed structures,
  BIM & digital twins, drones & reality capture, green / low-carbon materials,
  AI in project management or estimation.

Format per item:
📌 [Specific headline]
What: [1–2 sentences with company names, numbers, location, date]
Relevance: [1–2 sentences — could you pilot this? does it change a competitor's
cost base? is it a signal of where SG will be in 3 years?]

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🦺 *SINGAPORE WSH BULLETIN*
Scan MOM, WSH Council, Straits Times, CNA, TODAY for the past 7 days:
  • Workplace fatalities & serious injuries (construction / FM sector)
  • MOM advisories, safety alerts, Heightened Safety Period updates
  • Prosecutions, composition fines, stop-work orders
  • New or amended WSH Act / WSHR regulations, approved codes of practice

Format per item:
⚠️ [Incident / advisory headline]
What: [Date, site / agency, what happened, any fatalities or fine amounts]
Takeaway: [One sentence — the specific control measure, RA update, or toolbox
talk topic the reader should push out to site staff on Monday]

If nothing material happened this week, say so in one line. Do not fabricate.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 *SG MARKET DATA — CONSTRUCTION & FM*
Pull the latest numbers you can find. Prefer primary sources (BCA, URA,
SingStat, MAS, CEA). Cover whichever of these have fresh data this week:
  • BCA construction demand forecast / contracts awarded YTD
  • BCA Tender Price Index / material cost movements (steel, cement, RMC, sand)
  • URA private property price index & rental index (drives FM demand)
  • Foreign manpower / work-permit policy changes affecting the sector
  • Facility management market signals — outsourcing deals, REIT capex plans

Format per item:
📈 [Metric or deal]
Number: [Specific figure, period, source]
Implication: [One sentence — what this means for bidding, margins, manpower,
or FM contract renewals]

━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 *SG GOVERNMENT AGENCY BUDGETS & TENDERS*
Scan all major government sector buyers. For each, report ANY of: budget
announcements, Parliamentary replies, major tender calls, awarded contracts,
masterplan updates from the last 7 days.

Agencies to cover (include only those with real news):
  MND · HDB · URA · BCA · JTC · LTA · CAAS · MPA · NEA · PUB · NParks ·
  MOH · MOE · MINDEF · MHA · SPF · SCDF · MCCY · People's Association ·
  Sport SG · STB · Enterprise SG · GovTech · SLA

Format per item:
🏛️ [Agency — short headline]
What: [Tender / budget / contract — value in S$, closing date or award date]
Angle: [One sentence — can the reader bid directly, subcontract, or position
for a follow-on scope?]

GeBIZ link or tender reference number if you find it. No speculation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧭 *THIS WEEK'S 3 BETS*
Three numbered items. Each one specific and actionable:
  1. A tender or opportunity to register / pre-qualify for
  2. A safety or compliance action for the site team
  3. A market or tech signal worth a 30-minute deeper read

━━━ RULES ━━━
• Window: last 7 days only. Skip anything older unless it just re-surfaced.
• Primary sources > aggregators. MOM.gov.sg, bca.gov.sg, ura.gov.sg,
  gebiz.gov.sg, singstat.gov.sg, ChannelNewsAsia, Straits Times, The Edge SG.
• Every number gets a source. Every source gets a date.
• No opinion pieces, no recycled PR fluff, no generic "trends" pieces.
• If a section has no material news, say so in one line — do NOT pad.
• Plain text with emoji headers. Bold using *asterisks* (Telegram-friendly).
• Keep each item tight. This is a briefing, not a blog post.
"""

MAX_ITERATIONS = 30  # 4 Singapore-heavy domains — may need many searches


def get_weekly_newsletter() -> str:
    """
    Run a live web search across construction tech, SG WSH, SG market data, and
    SG government tenders, then return a formatted weekly newsletter.
    """
    messages = [
        {
            "role": "user",
            "content": (
                "Generate this week's construction newsletter. Search for the "
                "latest news in the last 7 days across:\n"
                "  1. Global construction technology\n"
                "  2. Singapore Workplace Safety & Health bulletin (MOM / WSH Council)\n"
                "  3. Singapore construction & facility maintenance market data\n"
                "     (BCA, URA, SingStat, material prices, tender price index)\n"
                "  4. Singapore government agency budgets, tender calls, and "
                "     awarded contracts (MND, HDB, URA, BCA, JTC, LTA, CAAS, "
                "     MPA, NEA, PUB, MOH, MOE, MINDEF, GovTech, etc. via GeBIZ)\n\n"
                "Follow the structure in the system prompt exactly. End with "
                "THIS WEEK'S 3 BETS — three numbered, actionable items."
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

    return _extract_text(response) if response else "Weekly newsletter unavailable."


def _extract_text(response: anthropic.types.Message) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text")


if __name__ == "__main__":
    print(get_weekly_newsletter())
