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
🌍 *CONSTRUCTION TECH — TOP 5 THIS WEEK*
Exactly 5 items. Filter HARD to the reader's workheads — interior finishing,
painting, cleaning, light building works, FM. Drop generic mega-project tech.

Each item must be ELABORATED, not a one-liner. Give enough depth that a site
manager reading on the MRT understands what it is, why it matters, and where
to dig deeper.

Format per item (numbered 1–5):
📌 [#] *[Company / product — specific headline]*
What it is: [2–3 sentences. Include company, geography, how it works, typical
  deployment. Be concrete.]
Why it matters to us: [1–2 sentences tied to our trades — e.g. cost base
  change for CR06, night-shift savings for CR13, BIM requirement on future
  bids for CW01]
Read more: [1–3 links — prefer the official product page first, then a
  reputable news / case-study article. Format each as:
  · [Short label] — <https://...>
  Do NOT fabricate URLs. If you're not 100% sure a URL exists, use the
  company's root domain (e.g. https://canvas.build) rather than a guessed
  deep link.]

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
💰 *TENDER PIPELINE + WATCHLIST + ACTIONS*

This is the combined commercial section. Three parts inside one header:

PART A — *Tenders called this week* (from live web search + any ST Classifieds
PDF attached). Merge into one list. Tag ST Classifieds items with 📰.
HARD FILTERS:
  1. Scope must match one of the reader's registered workheads.
  2. Tender value ≤ S${TENDER_MAX_SGD_M:.0f}M.
For EACH item state which workhead it maps to.

Sources to scan (cite which one for every item):
  PUBLIC: GeBIZ · Sesami · BCA Tenders Portal · LTA eProcurement ·
  PUB eTender · HDB iTender · JTC eTender · all 17 town council websites ·
  agency sites (NParks, NEA, SPF, SCDF, MOE, MOH cluster sites).
  PRIVATE: SGX (REIT AEI disclosures) · REIT websites (CapitaLand, Mapletree,
  Frasers, Keppel, Lendlease, Suntec, Starhill, ESR-LOGOS, Sabana, Paragon) ·
  Developer sites (CDL, UOL, GuocoLand, Hong Leong, Far East, Allgreen) ·
  Managing agents (Savills, Knight Frank, JLL, CBRE, Colliers, Edmund Tie,
  Cushman & Wakefield) · Healthcare groups · Data-centre operators · REDAS /
  SCAL / SCIC notices.

Format per item:
🏛️ / 🏢 / 📰 [Buyer — headline]  |  workhead: CW01 / CR06 / etc.
What: [Scope · S$ value · close/award date · reference no.]
📍 Where to see: [Short label — "GeBIZ (search by ref)", "Aljunied-Hougang
                   TC website", "SGX REIT announcements", "Savills tender
                   page", "ST Classifieds <date>, p.C11", etc.]
Angle: [One line — bid direct, JV, sub, or pre-qualify]

PART B — *Watchlist (2–4 weeks out)*. 3–5 known tenders closing in the next
2–4 weeks that match the workhead filter — open items to start costing now.
Format: ⏳ [Buyer — scope] · workhead · S$XXX · closes DD Mon · 📍 source

PART C — *This week's 3 actions*. Three numbered items. Each specific and
actionable at SME scale:
  1. A biddable tender (≤ S${TENDER_MAX_SGD_M:.0f}M, matches workheads) — name it.
  2. A safety / compliance / regulatory action for the team this week.
  3. A tender prep, briefing, or costing task that has to start now.

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
