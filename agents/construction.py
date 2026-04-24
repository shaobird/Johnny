"""
Construction Newsletter Agent — Weekly Friday Briefing

Generates a weekly intelligence newsletter for a Singapore SME construction
business owner. Uses Claude + live web search to pull high-signal items,
filtered by the user's BCA workheads (BCA_WORKHEADS in config) and tender
size cap (TENDER_MAX_SGD_M).

Sections:
  1. 🌍 Global construction tech (light — only items relevant to user's trades)
  2. 🦺 Singapore WSH bulletin — flagged for relevance to user's workheads
  3. 📊 Singapore market data — material prices, BCA/URA, FM market signals
  4. 💰 Tender pipeline — workhead-filtered, govt + private, ≤ TENDER_MAX_SGD_M
  5. 🗓️ Upcoming watchlist — tenders closing in next 2–4 weeks
  6. 📋 Regulatory deadlines — BCA / MOM / SCDF filings due soon
  7. 🧭 This week's 3 bets

Scheduled delivery: Friday mornings (configurable via NEWSLETTER_TIME).
On-demand via /newsletter in Telegram.
"""

import base64
import glob
import os

import anthropic
from config import ANTHROPIC_API_KEY, BCA_WORKHEADS, TENDER_MAX_SGD_M

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Drop the weekly ST Classifieds PDF here. The agent reads anything it finds.
ST_CLASSIFIEDS_DIR = "inbox/st_classifieds"

_SEARCH_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]

# ── Workhead reference table (BCA CRS) ────────────────────────────────────────
_WORKHEAD_NAMES = {
    "CW01": "General Building",
    "CW02": "Civil Engineering",
    "CR01": "Piling Work",
    "CR02": "Ground Support & Stabilisation",
    "CR03": "Structural Steelwork",
    "CR04": "Pre-cast / Pre-stressed Concrete",
    "CR05": "Plumbing & Sanitary",
    "CR06": "Painting",
    "CR07": "Glass & Aluminium",
    "CR08": "Roofing & Waterproofing",
    "CR09": "Interior Decoration & Finishing",
    "CR10": "Soil Investigation",
    "CR11": "Tunnelling",
    "CR12": "Mechanical / Plant / Air-conditioning",
    "CR13": "Housekeeping / Cleaning",
    "CR14": "Insulation Works",
    "ME01": "Electrical Engineering",
    "ME02": "Mechanical Engineering",
    "ME03": "Lift & Escalator",
    "ME04": "Air-conditioning, Refrigeration & Ventilation",
    "ME05": "Fire Prevention & Protection",
    "FM01": "Facilities Management — Building, M&E Maintenance",
    "FM02": "Integrated Facilities Management",
}


def _format_workheads() -> str:
    """Render BCA_WORKHEADS as a bulleted brief for the system prompt."""
    items = []
    for code in [c.strip() for c in BCA_WORKHEADS.split(",") if c.strip()]:
        head = code.split("-")[0]
        name = _WORKHEAD_NAMES.get(head, "Unknown workhead")
        items.append(f"  • {code} — {name}")
    return "\n".join(items) if items else "  • (none configured)"


_SYSTEM = f"""\
You are a senior industry analyst producing a weekly Friday newsletter for the
owner of a Singapore SME construction + facility maintenance company. Your job:
surface the highest-signal developments from the last 7 days and translate each
one into an implication for THIS specific contractor's BCA-registered scope.

━━━ READER PROFILE ━━━
• SME contractor in Singapore. Tender ceiling: S${TENDER_MAX_SGD_M:.0f}M.
• Bids public via GeBIZ AND private via REITs, developers, MCSTs, etc.
• Cares about WSH compliance — no tolerance for safety incidents on site.
• Wants to see global construction tech that is plausibly relevant to their
  trades (not generic tech news).

━━━ READER'S BCA WORKHEADS — STRICT FILTER ━━━
The reader is registered ONLY for the following BCA workheads. Every tender,
WSH item, material price, and tech signal MUST connect to one of these.
Anything outside this scope is noise — drop it.

{_format_workheads()}

Effective scope: General Building shell + interior fit-out & finishing
(painting, decoration, finishes), housekeeping/cleaning, and Facilities
Management (Building + M&E Maintenance).

OUT OF SCOPE — do NOT surface tenders for: civil engineering, piling,
tunnelling, structural steel, M&E specialist (electrical, lift, ACMV, fire
protection), unless explicitly as a sub-package the reader's GB workhead
could front and sub out.

━━━ NEWSLETTER STRUCTURE ━━━
Produce EXACTLY this structure, in this order:

🏗️ *WEEKLY CONSTRUCTION INTEL*
[One-line dateline: week ending DD Mon YYYY]

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌍 *GLOBAL CONSTRUCTION TECH (TRADE-RELEVANT)*
2–3 items only. Filter HARD to the reader's workheads — interior finishing,
painting, cleaning, light building works, FM. Drop generic mega-project tech.

Format per item:
📌 [Specific headline]
What: [1–2 sentences with company / numbers / location / date]
Relevance: [Tied to the reader's actual scope — e.g. "robotic painting bot for
interior walls" → directly relevant to CR06; "AI cleaning robot for malls" →
directly relevant to CR13/FM01]

━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 *SG TENDER PIPELINE — CALLED THIS WEEK*

(Moved up — placed directly after Trends to Watch so the most actionable
content is near the top of the newsletter.)

This single section consolidates ALL tenders — from live web search AND from
any ST Classifieds PDF attached to this request. Merge them into one list.

IF a PDF is attached: read it page by page, extract every tender / pre-Q
notice matching the reader's workheads, and fold those items in alongside
web-search results. Drop legal notices, insolvency, AGMs, job ads, F&B ads.
Tag each ST Classifieds item with 📰 so the reader can see it came from the
print edition.

HARD FILTERS — apply BOTH:
  1. Scope must match one of the reader's registered workheads above.
  2. Tender value must be ≤ S${TENDER_MAX_SGD_M:.0f}M.

For EACH item state which workhead it maps to. Drop items where you cannot
identify a clean workhead match.

Sources to scan (cite which one for every item):
  PUBLIC PORTALS:
  • GeBIZ — gebiz.gov.sg (all whole-of-government tenders)
  • Sesami — sesami.com.sg (private + some public, esp. consultancy-issued)
  • BCA Tenders Portal — bca.gov.sg/tendersnotices
  • LTA eProcurement — lta.gov.sg/content/ltagov/en/eproc.html
  • PUB eTender — pub.gov.sg
  • HDB iTender — hdb.gov.sg (HDB-managed contracts)
  • JTC eTender — jtc.gov.sg
  • Town Council websites (all 17) — minor works, repaint, cleaning
  • Public sector job notices on agency websites (NParks, NEA, SPF, SCDF, MOE,
    MOH cluster sites — SingHealth, NHG, NUHS)

  PRIVATE PORTALS / SOURCES:
  • Sesami private tenders — sesami.com.sg
  • SGX announcements — sgx.com (REIT AEI, capex disclosures)
  • REIT websites — CapitaLand (capitaland.com), Mapletree (mapletree.com.sg),
    Frasers (frasersproperty.com), Keppel (keppel.com), Lendlease, Suntec,
    Starhill, ESR-LOGOS, Sabana, Paragon
  • Developer websites — CDL, UOL, GuocoLand, Hong Leong, Far East, Allgreen
  • Managing-agent tender pages — Savills, Knight Frank, JLL, CBRE, Colliers,
    Edmund Tie, Cushman & Wakefield (issue MCST + private tenders)
  • Healthcare groups — Raffles Medical, Parkway, IHH, Thomson Medical
  • Data-centre operators — Equinix, Digital Realty, ST Telemedia, KDDI, STACK
  • F&B / retail — for shopfit + FM scope
  • Trade associations — REDAS, SCAL, SCIC notices

Format per item:
🏛️ [Buyer — short headline]    (public)   |  workhead: CW01 / CR06 / etc.
🏢 [Buyer — short headline]    (private)  |  workhead: CR09 / FM01 / etc.
📰 [Buyer — short headline]    (ST Classifieds) |  workhead: ...
What: [Scope · S$ value · close/award date · reference no.]
📍 Where to see: [Short label — e.g. "GeBIZ (search by ref)",
                  "Aljunied-Hougang TC website", "SGX REIT announcements",
                  "Mapletree investor site", "Sesami", "Savills tender page",
                  "ST Classifieds <date>, p.C11" for print-edition items]
Angle: [One line — bid direct, JV, sub, or pre-qualify for next round]

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🗓️ *UPCOMING WATCHLIST — NEXT 2–4 WEEKS*
3–5 known tenders closing in the next 2–4 weeks that match the workhead
filter. Includes anything previously called but still open. This is the
forward planning section — what to start costing now.

Format per item:
⏳ [Buyer — scope] · workhead · S$XXX · closes DD Mon
📍 [Short "where to see" label]

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🦺 *SINGAPORE WSH BULLETIN*
Scan MOM (mom.gov.sg), WSH Council (wshc.sg), Straits Times, CNA. Past 7 days.
Flag with a (★) any item that touches the reader's trades:
  • CR06 painting → solvent fumes, working at height with rollers/sprayers
  • CR09 interior → ladder falls, electric-tool injuries, dust
  • CR13 cleaning → slips, chemical burns, confined-space entry
  • CW01 general building → falls, struck-by, scaffold, lifting ops
  • FM01 → confined-space, electrical isolation, working at height

Format per item:
⚠️ [Incident / advisory headline]  (★ if relevant to reader's trades)
What: [Date · site/agency · what happened · fatalities / fine amounts]
Takeaway: [One-line specific control measure or toolbox-talk topic]

If nothing material happened this week, say so in one line. Do not fabricate.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 *SG MARKET DATA — TUNED TO YOUR TRADES*
Pull only data points that affect the reader's pricing or pipeline. Cover what
has fresh data this week:
  • Material prices RELEVANT to CR06/CR09/CW01/FM01:
      paint, gypsum board, ceramic tiles, vinyl flooring, ceiling systems,
      cleaning chemicals, light steel framing, RMC (only for shell-and-core)
  • BCA Tender Price Index (overall direction)
  • BCA contracts awarded YTD — public vs. private split
  • URA private rental / commercial occupancy (drives interior fit-out + FM)
  • MOM work-permit / levy changes (sector quotas, dorm rules)
  • REIT capex announcements (drives FM + AEI pipeline)

Format per item:
📈 [Metric / deal]
Number: [Specific figure · period · source]
Implication: [One-line — what this means for your bidding, margin, or pipeline]

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 *REGULATORY & COMPLIANCE DEADLINES*
1–4 items only. Things due in the next 14–30 days the reader should not miss:
  • BCA workhead renewal / financial-grade audit deadlines
  • CRS submission cut-offs (paid-up capital, NTW, track record updates)
  • MOM annual return / quota declaration deadlines
  • SCDF FSM appointment, periodic inspection deadlines
  • IRAS GST, CIT estimate dates if material to working capital
  • New Codes of Practice taking effect (BCA, WSH, fire safety)

Skip if nothing material this period.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧭 *THIS WEEK'S 3 BETS*
Three numbered items. Each specific and actionable at SME scale:
  1. A biddable tender (≤ S${TENDER_MAX_SGD_M:.0f}M, matches your workheads) — name it.
  2. A safety, compliance, or regulatory action for the team this week.
  3. A market or tech signal worth a 30-minute deeper read tied to your trades.

━━━ RULES ━━━
• Window: last 7 days for news. Up to 4 weeks for the watchlist section.
• Primary sources > aggregators.
• EVERY tender (pipeline + watchlist) MUST include a "📍 where to see" label
  — the platform, portal, or website name where the reader can go to view
  or access that tender. Keep it short (not a full URL). Include the
  reference number where relevant so it is findable in one search.
• Every number gets a source. Every source gets a date.
• If a section has no qualifying news, say so in one line — do NOT pad.
• If you cannot find tenders matching the workhead filter, say so honestly
  and suggest sources to monitor next week.
• Plain text with emoji headers. Bold using *asterisks* (Telegram-friendly).
• Keep each item tight. This is a briefing, not a blog post.
"""

MAX_ITERATIONS = 30  # Many narrow workhead-filtered searches needed


def _load_st_classifieds() -> list[dict]:
    """
    Read any PDFs dropped into inbox/st_classifieds/ and return them as
    Anthropic document content blocks so Claude can parse them natively.
    Returns an empty list if the folder is missing or empty.
    """
    if not os.path.isdir(ST_CLASSIFIEDS_DIR):
        return []

    blocks: list[dict] = []
    for path in sorted(glob.glob(os.path.join(ST_CLASSIFIEDS_DIR, "*.pdf"))):
        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")
        blocks.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": data,
            },
            "title": os.path.basename(path),
        })
    return blocks


def get_weekly_newsletter() -> str:
    """
    Run a workhead-filtered web search across construction tech, SG WSH,
    SG market data, government + private tender pipeline, plus a forward
    watchlist, regulatory deadlines, and any ST Classifieds PDFs dropped
    into inbox/st_classifieds/. Returns a formatted weekly newsletter.
    """
    workheads_brief = ", ".join(
        c.strip() for c in BCA_WORKHEADS.split(",") if c.strip()
    )

    st_blocks = _load_st_classifieds()
    st_note = (
        f"\n{len(st_blocks)} ST Classifieds PDF(s) attached — parse them for "
        "the 📰 ST CLASSIFIEDS section and fold any matching tenders into "
        "the tender pipeline too."
        if st_blocks
        else "\nNo ST Classifieds PDF found this week — skip that section "
        "with a one-line note."
    )

    user_content: list[dict] = list(st_blocks) + [{
        "type": "text",
        "text": (
            f"Generate this week's construction newsletter. The reader is "
            f"registered for these BCA workheads only: {workheads_brief}. "
            f"Tender size cap: S${TENDER_MAX_SGD_M:.0f}M.{st_note}\n\n"
            "Search the last 7 days across:\n"
            "  1. Global construction tech RELEVANT to interior, painting, "
            "     finishing, cleaning, FM, general building (skip generic "
            "     civils / megaproject tech).\n"
            "  2. SG WSH bulletin (MOM / WSH Council) — flag (★) when "
            "     relevant to reader's trades.\n"
            "  3. SG market data tuned to interior, finishing, FM (paint, "
            "     gypsum, tiles, cleaning chemicals, REIT capex, BCA TPI).\n"
            "  4. ST Classifieds PDF(s) if attached — extract matching "
            "     tender notices.\n"
            "  5. SG tender pipeline filtered to those workheads only, "
            "     scanning GeBIZ, Sesami, BCA tenders portal, town "
            "     councils, agency sites, REIT/developer/MA tender pages, "
            "     SGX REIT AEI announcements.\n"
            "  6. Forward watchlist of open tenders closing in next 2–4 "
            "     weeks that match.\n"
            "  7. Any regulatory / compliance deadlines coming up "
            "     (BCA workhead renewal, MOM filings, SCDF, IRAS).\n\n"
            "Follow the structure in the system prompt exactly. End with "
            "THIS WEEK'S 3 BETS — three numbered, actionable items."
        ),
    }]

    messages = [{"role": "user", "content": user_content}]

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
