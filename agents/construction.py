"""
Construction Agent — Weekly Construction Business Intel
Uses Gemini (Google Search grounding) to produce a weekly newsletter scoped to a
Singapore-registered contractor holding:
  • CR13-L1  Waterproofing
  • CR09-L4  Repair & Redecoration
  • CW01-C1  General Building

Output sections:
  1. Construction tech — top 5 relevant items this week
  2. Safety reminders / toolbox talks for next week
  3. Tender pipeline, buyer-portal watchlist, three weekly actions
  4. Regulatory deadlines (rolling)

Falls back to Claude web search if Gemini is unavailable.
"""

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types as genai_types

from config import GEMINI_API_KEY, ANTHROPIC_API_KEY

SGT = ZoneInfo("Asia/Singapore")
ST_FEED = "st_classifieds.json"
GOV_BUYERS = "gov_buyers.json"
PRIVATE_BUYERS = "private_buyers.json"


def _week_ending_friday() -> str:
    """Most recent Friday (or today if it is Friday) — 'Fri DD Mon YYYY'."""
    now = datetime.now(SGT)
    # weekday(): Mon=0 ... Fri=4 ... Sun=6
    days_back = (now.weekday() - 4) % 7
    friday = now - timedelta(days=days_back)
    return friday.strftime("Fri %d %b %Y")


def _load_st_classifieds() -> str:
    """Render parsed ST Classifieds tenders as a markdown block for the prompt."""
    if not os.path.exists(ST_FEED):
        return "ST Classifieds: pending manual feed (st_classifieds.json not found)."

    try:
        with open(ST_FEED) as f:
            data = json.load(f)
    except Exception as e:
        return f"ST Classifieds: feed read error — {e}"

    edition = data.get("edition_date", "unknown")
    tenders = data.get("tenders", [])
    if not tenders:
        return f"ST Classifieds (edition {edition}): no tenders parsed."

    in_scope = [t for t in tenders if t.get("in_scope")]
    out_scope = [t for t in tenders if not t.get("in_scope")]

    lines = [f"ST Classifieds — print edition {edition}:"]
    if in_scope:
        lines.append("IN SCOPE:")
        for t in in_scope:
            lines.append(
                f"  • {t['title']} — {t['buyer']} — Closes {t['closing']} — "
                f"{t['eligibility']} — Duration {t.get('duration_months') or '?'} mo — "
                f"Contact: {t['contact']}"
            )
            if t.get("scope_note"):
                lines.append(f"    Note: {t['scope_note']}")
    else:
        lines.append("IN SCOPE: none this edition.")

    if out_scope:
        lines.append("OUT OF SCOPE (for context — do not pursue):")
        for t in out_scope:
            lines.append(f"  • {t['title']} — {t['buyer']} — {t.get('scope_note', 'out of scope')}")

    return "\n".join(lines)


def _load_gov_buyers() -> str:
    """Render the tiered government buyer registry for the prompt."""
    if not os.path.exists(GOV_BUYERS):
        return "Government buyer registry: missing (gov_buyers.json)."
    try:
        with open(GOV_BUYERS) as f:
            data = json.load(f)
    except Exception as e:
        return f"Government buyer registry: read error — {e}"

    lines = ["TIER 1 — search GeBIZ for current open tenders from each:"]
    for b in data.get("tier_1_high_frequency", []):
        lines.append(f"  • {b['name']} ({b['full']}) — {b.get('why','')}")

    lines.append("")
    lines.append("TIER 1 — hospital clusters (R&R + waterproofing pipeline):")
    for h in data.get("tier_1_hospital_clusters", []):
        lines.append(f"  • {h['name']} — {h['full']}")

    lines.append("")
    lines.append("TIER 2 — spot-check if Tier 1 yield is thin:")
    for b in data.get("tier_2_medium_frequency", []):
        lines.append(f"  • {b['name']} — {b['full']}")

    lines.append("")
    lines.append("Skip Tier 3 / admin-only / out-of-scope buyers — see gov_buyers.json.")
    return "\n".join(lines)


def _load_private_buyers() -> str:
    """Render the private-sector buyer registry (SAP Ariba + portals)."""
    if not os.path.exists(PRIVATE_BUYERS):
        return "Private buyer registry: missing (private_buyers.json)."
    try:
        with open(PRIVATE_BUYERS) as f:
            data = json.load(f)
    except Exception as e:
        return f"Private buyer registry: read error — {e}"

    lines = ["SAP ARIBA NETWORK — register once, then check Ariba Discovery weekly:"]
    for b in data.get("sap_ariba_buyers", []):
        lines.append(f"  • {b['name']} — {b['portfolio']}")

    lines.append("")
    lines.append("Developer / REIT supplier portals — check direct:")
    for b in data.get("developer_and_reit_portals", []):
        lines.append(f"  • {b['name']} — {b['portfolio']}")

    lines.append("")
    lines.append("Hospitality — high R&R cadence:")
    for b in data.get("hospitality_buyers", []):
        lines.append(f"  • {b['name']} — {b['portfolio']}")

    lines.append("")
    lines.append("Industrial / DC / Healthcare:")
    for b in data.get("industrial_and_telco", []):
        lines.append(f"  • {b['name']} — {b['portfolio']}")

    return "\n".join(lines)


def _build_prompt() -> str:
    week_ending = _week_ending_friday()
    st_block = _load_st_classifieds()
    gov_block = _load_gov_buyers()
    private_block = _load_private_buyers()
    return f"""\
You are the construction-business intelligence agent for a Singapore-registered
contractor. Produce this week's newsletter using LIVE Google Search. Be specific,
factual, and Singapore-contextual throughout. No invented products, tenders, or
incidents — if you can't verify it, leave that section short.

━━━ THE BUSINESS ━━━
• BCA Workhead CR13 (Waterproofing) — Grade L1
• BCA Workhead CR09 (Repair & Redecoration) — Grade L4
• BCA Workhead CW01 (General Building) — Grade C1
Currency: S$. Timezone: SGT.
━━━━━━━━━━━━━━━━━━━━━━━━

━━━ EXPLICIT EXCLUSIONS — NEVER PURSUE ━━━
• CR06 (Painting) — deprioritised; we are not registered. Skip painting-only tenders.
• Cleansing-only contracts.
• Architect / consultant pre-Q (we are a contractor).
• Pure M&E / electrical rewiring scopes.
• Lift / equipment specialist contracts.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ ST CLASSIFIEDS — PARSED FOR YOU THIS WEEK ━━━
Use this verbatim in the ST Classifieds section below. Do not search; use what's here.

{st_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ GOVERNMENT BUYER REGISTRY (GeBIZ procuring entities) ━━━
{gov_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ PRIVATE-SECTOR BUYER REGISTRY (SAP Ariba + supplier portals) ━━━
{private_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ TENDERBOARD AGGREGATOR ━━━
Live-search the public / free-tier listings on tenderboard.com.sg for tenders
matching CR13 / CR09 / CW01 keywords. Surface anything in scope; skip the
paywalled items unless their headline alone is enough to flag.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ OUTPUT FORMAT — FOLLOW EXACTLY ━━━

🏗️ WEEKLY CONSTRUCTION INTEL
Week ending {week_ending} · Scope: Waterproofing (CR13-L1) · Repair & Redecoration (CR09-L4) · General Building (CW01-C1)

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌍 CONSTRUCTION TECH — TOP 5 THIS WEEK

For each of 5 items, format exactly as:

📌 N. [Product / Tech] — [One-line descriptor] | [CR13 / CR09 / CW01]
What it is: [2-3 sentences. Concrete. Mention the vendor inline.]
Why it matters to us: [2-3 sentences. Tied directly to one of the three workheads.
  Suggest a specific application — discovery quote, bid differentiator, margin lever.]
Read more:
· [Vendor] — https://[url]

Topic guardrails:
• CR13 — liquid/sheet membranes, cool-roof systems, acoustic/electronic leak detection,
  injection grouting, hybrid PU/PMMA chemistry.
• CR09 — robotic repaint, drywall/skim robots, fast-cure coatings, dust extraction,
  AI defect inspection, scaffold-free access systems.
• CW01 — BIM-to-slab layout, modular MEP, 360° site capture, AI handover docs,
  prefab façade systems.
Prefer products being trialled or deployed in Singapore / SE Asia / commercial
retrofit. Skip megaproject-only or pure-architecture tech.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🦺 SAFETY REMINDERS — TOOLBOX TALKS FOR NEXT WEEK
One line: "Trade-specific reminders + any incidents in the public record this week."

• CR13 waterproofing — working at height (edge protection, harness anchor, no solo work);
  hot-applied membranes (hot-works permit, fire watch, extinguisher within 10m);
  solvent primers (ventilation + respiratory PPE).
• CR09 repair & redecoration — electrical isolation before tool change;
  silica / gypsum dust (wet cut or LEV); manual handling for tile / ceiling removal.
• CW01 general building — scaffold green-tag check every shift start;
  lifting ops only with permit; site induction every new worker.
• All trades — RA documents dated this quarter; MOM Heightened Safety Period status.

If WSH / MOM published a notable construction incident or advisory this week, add:
🆕 This week's incident note: [one line, source-linked]

━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 TENDER PIPELINE + WATCHLIST + ACTIONS

📋 GeBIZ — live search results matching keywords: "waterproofing", "re-roofing",
"repaint", "A&A", "addition and alteration", "minor improvement",
"ceiling repair", "external wall". Cross-reference against the Tier 1
government buyer registry above — prioritise tenders from those buyers.
Filter strictly:
  - Workhead matches CR13 / CR09 / CW01
  - Closing 4-8 weeks out
  - Indicative value within scope (≤ S$13M)
Format each: • [Title] — [Buyer] — Closes [date] — [Est value] — [GeBIZ link]
If nothing in scope this week, say so in one line.

📋 Tenderboard.com.sg (free tier) — surface in-scope listings not on GeBIZ.

📋 SAP Ariba / private supplier portals — list any active RFQs found via
live search from the Private-Sector Buyer Registry above. If nothing
public, say so in one line.

📋 ST Classifieds — use the PARSED block supplied above verbatim.
List IN-SCOPE tenders with all details (title, buyer, closing, eligibility, contact).
Then summarise OUT-OF-SCOPE in one line each so we know what was screened out and why.
If the parsed block reports the feed is pending or empty, repeat that line.

📋 Buyer portals to check this week (always list):
🚢 PSA Singapore — port building works, warehouse roof waterproofing, R&R office blocks
   📍 https://www.psa.com.sg → Procurement
🚇 SMRT — depot R&R, tunnel/station waterproofing, depot office building works
   📍 https://www.smrt.com.sg/Procurement
✈️ Changi Airport Group — terminal R&R, airside building waterproofing
   📍 https://www.changiairport.com → Suppliers / Procurement
🚌 SBS Transit · Tower Transit · Go-Ahead — bus depot building works, interchange A&A
   📍 sbstransit.com.sg / towertransit.sg / go-aheadsingapore.com
⚡ SP Group — substation building works, leak repair
   📍 https://www.spgroup.com.sg → Procurement
🏭 JTC Corporation — factory and warehouse R&R, industrial roof waterproofing
   📍 https://www.jtc.gov.sg → Tenders
🏢 17 town councils — block waterproofing, ceiling repaint, void deck R&R
   📍 GeBIZ → search "town council" + relevant keyword

🗓️ Watchlist — known closing dates this week / next two weeks:
[list from live search; if none, "None matching scope."]

🧭 This week's 3 actions:
Three numbered, action-oriented items derived from what was actually found above.
Each one sentence, concrete verb. No generic advice.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 REGULATORY DEADLINES — ROLLING

If BCA / MOM / SCDF / NEA / URA published a relevant change this week, lead with:
🆕 This week: [one line, source-linked]

Then always include:
• BCA CRS renewal — verify expiry dates for CR13-L1, CR09-L4, CW01-C1.
  Submit renewal ≥ 60 days before expiry. Financial-grade audit (NTW + paid-up
  capital) likely required for L4 and C1.
• MOM work-permit quota — quarterly sector declaration if applicable.
• SCDF Fire Safety Manager — verify FSM appointment is current.
• IRAS GST — quarterly return due end of the month following each quarter-end.

━━━ RULES ━━━
• Live search every section. Do not invent vendors, tenders, or incidents.
• Tone: tight, factual, "why it matters to us" framing. No filler, no preamble.
• Apply scope filter ruthlessly — no items outside CR13 / CR09 / CW01.
• Use S$ for currency. SGT for times. Singapore-first context.\
"""


def get_construction_briefing() -> str:
    """
    Run a live Google Search via Gemini and return the weekly construction-business
    newsletter. Falls back to Claude web search if Gemini is unavailable.
    """
    if GEMINI_API_KEY:
        try:
            return _gemini_search()
        except Exception as e:
            print(f"[Construction] Gemini failed ({e}), falling back to Claude...")

    return _claude_search()


def _gemini_search() -> str:
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=_build_prompt(),
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

    messages = [{"role": "user", "content": _build_prompt()}]
    response = None

    for _ in range(40):
        response = client.messages.create(
            model="claude-opus-4-6",
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
        return "Construction briefing unavailable."
    return "\n".join(b.text for b in response.content if b.type == "text")


if __name__ == "__main__":
    print(get_construction_briefing())
