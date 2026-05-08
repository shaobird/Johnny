"""
Construction Agent — Weekly Construction Business Intel

Parallel sub-agent architecture. Four focused workers run concurrently and
their outputs are stitched together with a shared header:

  • tech      — top 5 relevant products / systems this week
  • safety    — toolbox talks + WSH/MOM incident scan
  • tenders   — GeBIZ + ST Classifieds + Tenderboard + Ariba pipeline
  • regulatory — BCA / MOM / SCDF / IRAS rolling deadlines + this week's changes

Each worker uses Claude Sonnet with web_search + web_fetch and a search
budget tuned to its section. Wall-time = the slowest section, not the sum.

Falls back to a single-call Gemini run if Claude is unavailable.
"""

import concurrent.futures
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


# ── Date / data loaders ───────────────────────────────────────────────────────

def _week_ending_friday() -> str:
    now = datetime.now(SGT)
    days_back = (now.weekday() - 4) % 7
    friday = now - timedelta(days=days_back)
    return friday.strftime("Fri %d %b %Y")


def _load_st_classifieds() -> str:
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
    return "\n".join(lines)


def _load_private_buyers() -> str:
    if not os.path.exists(PRIVATE_BUYERS):
        return "Private buyer registry: missing (private_buyers.json)."
    try:
        with open(PRIVATE_BUYERS) as f:
            data = json.load(f)
    except Exception as e:
        return f"Private buyer registry: read error — {e}"

    lines = ["SAP ARIBA NETWORK — register once, check Ariba Discovery weekly:"]
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


# ── Shared business context (cached prefix) ───────────────────────────────────

_BUSINESS_CONTEXT = """\
THE BUSINESS — Singapore-registered contractor.
• BCA Workhead CR13 (Waterproofing) — Grade L1
• BCA Workhead CR09 (Repair & Redecoration) — Grade L4
• BCA Workhead CW01 (General Building) — Grade C1
Currency: S$. Timezone: SGT.

EXPLICIT EXCLUSIONS — never pursue:
• CR06 painting (not registered)
• Cleansing-only contracts
• Architect / consultant pre-Q
• Pure M&E / electrical rewiring
• Lift / equipment specialist contracts

GLOBAL RULES:
• Live web search — never invent vendors, tenders, or incidents.
• If unverified, leave the section short.
• Tone: tight, factual, "why it matters to us" framing. No filler.
• Apply scope filter ruthlessly.
"""


# ── Section prompts ───────────────────────────────────────────────────────────

def _tech_prompt() -> str:
    return f"""\
{_BUSINESS_CONTEXT}

You are the TECH sub-agent. Produce ONLY the construction-tech section.
Surface the 5 most relevant products / systems published or trialled recently.

Topic guardrails:
• CR13 — liquid/sheet membranes, cool-roof systems, acoustic/electronic leak
  detection, injection grouting, hybrid PU/PMMA chemistry.
• CR09 — robotic repaint, drywall/skim robots, fast-cure coatings, dust
  extraction, AI defect inspection, scaffold-free access.
• CW01 — BIM-to-slab layout, modular MEP, 360° site capture, AI handover docs,
  prefab façade systems.
Prefer products being trialled or deployed in Singapore / SE Asia / commercial
retrofit. Skip megaproject-only or pure-architecture tech.

OUTPUT — start your reply with this exact header line, then the 5 items:

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌍 CONSTRUCTION TECH — TOP 5 THIS WEEK

For each item:
📌 N. [Product / Tech] — [One-line descriptor] | [CR13 / CR09 / CW01]
What it is: [2-3 sentences. Concrete. Mention the vendor inline.]
Why it matters to us: [2-3 sentences. Tied to one workhead. Suggest a specific
  application — discovery quote, bid differentiator, margin lever.]
Read more:
· [Vendor] — https://[url]

No preamble. No closing remarks. Output the header + 5 items only."""


def _safety_prompt() -> str:
    return f"""\
{_BUSINESS_CONTEXT}

You are the SAFETY sub-agent. Produce ONLY the safety/toolbox section.

Always include the trade-specific reminders below. Then live-search the WSH
Council and MOM media-release feeds for any construction-related incident or
advisory published in the last 7 days. If found, add a "🆕 This week's incident
note:" line with a one-line summary and source link.

OUTPUT — start your reply with this exact header line:

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🦺 SAFETY REMINDERS — TOOLBOX TALKS FOR NEXT WEEK
[One opening line setting context for next week.]

• CR13 waterproofing — working at height (edge protection, harness anchor,
  no solo work); hot-applied membranes (hot-works permit, fire watch,
  extinguisher within 10m); solvent / PMMA primers (ventilation + organic-
  vapour respiratory PPE).
• CR09 repair & redecoration — electrical isolation before tool change;
  silica / gypsum dust (wet cut or LEV, P3 mask); manual handling for tile /
  ceiling removal (two-person lift > 25kg).
• CW01 general building — scaffold green-tag check every shift start;
  lifting only with permit and signaller; site induction every new worker.
• All trades — RA documents dated this quarter; MOM Heightened Safety Period
  status (search and confirm if active).

🆕 This week's incident note: [if found from live search; otherwise omit]

No preamble. No closing remarks."""


def _tenders_prompt() -> str:
    st_block = _load_st_classifieds()
    gov_block = _load_gov_buyers()
    private_block = _load_private_buyers()
    return f"""\
{_BUSINESS_CONTEXT}

You are the TENDERS sub-agent. Produce ONLY the pipeline / watchlist / actions
section. Use the parsed ST Classifieds block verbatim. Live-search GeBIZ,
Tenderboard.com.sg (free tier), and SAP Ariba Discovery for additional in-scope
opportunities. Cross-reference against the buyer registries below.

━━━ ST CLASSIFIEDS — PARSED FOR YOU THIS WEEK ━━━
{st_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ GOVERNMENT BUYER REGISTRY (GeBIZ procuring entities) ━━━
{gov_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ PRIVATE-SECTOR BUYER REGISTRY (Ariba + supplier portals) ━━━
{private_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GeBIZ keyword sweep: "waterproofing", "re-roofing", "repaint", "A&A",
"addition and alteration", "minor improvement", "ceiling repair",
"external wall". Filter: workhead matches CR13 / CR09 / CW01, closing 4-8
weeks out, indicative value ≤ S$13M.

OUTPUT — start your reply with this exact header line:

━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 TENDER PIPELINE + WATCHLIST + ACTIONS

📋 ST Classifieds — list IN-SCOPE tenders verbatim from the parsed block;
summarise OUT-OF-SCOPE in one line each.

📋 GeBIZ — live-search results (in scope only), format:
• [Title] — [Buyer] — Closes [date] — [Est value] — [GeBIZ link]
If none in scope: "No matching tenders this week."

📋 Tenderboard.com.sg (free tier) — surface in-scope listings not on GeBIZ.
If nothing: "No matching free-tier listings."

📋 SAP Ariba / private supplier portals — list any active RFQs from the
registry above. If nothing public: "No public RFQs surfaced this week."

📋 Buyer portals to monitor (always list):
🚢 PSA Singapore — https://www.psa.com.sg → Procurement
🚇 SMRT — https://www.smrt.com.sg/Procurement
✈️ Changi Airport Group — https://www.changiairport.com → Suppliers
🚌 SBS Transit · Tower Transit · Go-Ahead — sbstransit.com.sg / towertransit.sg / go-aheadsingapore.com
⚡ SP Group — https://www.spgroup.com.sg → Procurement
🏭 JTC Corporation — https://www.jtc.gov.sg → Tenders
🏢 17 town councils — GeBIZ → "town council" + relevant keyword

🗓️ Watchlist — closing dates this week / next two weeks. If none: "None matching scope."

🧭 This week's 3 actions:
Three numbered, action-oriented items derived from what was found above.
Each one sentence, concrete verb. No generic advice.

No preamble. No closing remarks."""


def _regulatory_prompt() -> str:
    return f"""\
{_BUSINESS_CONTEXT}

You are the REGULATORY sub-agent. Produce ONLY the regulatory deadlines
section. Live-search BCA / MOM / SCDF / NEA / URA / IRAS for any change,
circular, or advisory issued in the last 7 days that affects a CR13 / CR09 /
CW01 contractor. If found, lead with a "🆕 This week:" line. Then list the
rolling deadlines.

OUTPUT — start your reply with this exact header line:

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 REGULATORY DEADLINES — ROLLING

🆕 This week: [if found from live search; otherwise omit this line entirely]

• BCA CRS renewal — verify expiry dates for CR13-L1, CR09-L4, CW01-C1.
  Submit ≥ 60 days before expiry. Financial-grade audit (NTW + paid-up
  capital) required for L4 and C1 — book auditor early.
• MOM work-permit quota — quarterly sector declaration if applicable.
• SCDF Fire Safety Manager — verify FSM appointment is current.
• IRAS GST — quarterly return due end of the month following each quarter-end.

No preamble. No closing remarks."""


# ── Worker ────────────────────────────────────────────────────────────────────

def _run_section(prompt: str, search_budget: int, fetch_budget: int) -> str:
    """Run a single sub-agent against Claude Sonnet with web tools."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    tools = [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": search_budget},
        {"type": "web_fetch_20260209",  "name": "web_fetch",  "max_uses": fetch_budget},
    ]

    messages = [{
        "role": "user",
        "content": [{
            "type": "text",
            "text": prompt,
            "cache_control": {"type": "ephemeral"},
        }],
    }]
    response = None

    for _ in range(10):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            tools=tools,
            messages=messages,
        )
        if response.stop_reason == "end_turn":
            break
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        break

    if not response:
        return "[section unavailable]"
    return "\n".join(b.text for b in response.content if b.type == "text").strip()


# ── Public API ────────────────────────────────────────────────────────────────

def get_construction_briefing() -> str:
    """
    Generate the weekly newsletter by running 4 sub-agents in parallel and
    stitching the outputs. Falls back to a single-call Gemini run if Claude
    is unavailable.
    """
    if not ANTHROPIC_API_KEY:
        return _gemini_fallback()

    try:
        return _parallel_claude()
    except Exception as e:
        print(f"[Construction] Parallel Claude failed ({e}), falling back to Gemini...")
        return _gemini_fallback()


def _parallel_claude() -> str:
    week = _week_ending_friday()
    header = (
        "🏗️ WEEKLY CONSTRUCTION INTEL\n"
        f"Week ending {week} · Scope: Waterproofing (CR13-L1) · "
        "Repair & Redecoration (CR09-L4) · General Building (CW01-C1)"
    )

    sections = [
        ("tech",       _tech_prompt(),       8, 4),
        ("safety",     _safety_prompt(),     4, 2),
        ("tenders",    _tenders_prompt(),   12, 6),
        ("regulatory", _regulatory_prompt(), 5, 3),
    ]

    results: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(_run_section, prompt, sb, fb): name
            for name, prompt, sb, fb in sections
        }
        for fut in concurrent.futures.as_completed(futures):
            name = futures[fut]
            try:
                results[name] = fut.result()
            except Exception as e:
                results[name] = f"[{name} section failed: {e}]"

    return "\n\n".join([
        header,
        results.get("tech", ""),
        results.get("safety", ""),
        results.get("tenders", ""),
        results.get("regulatory", ""),
    ])


def _gemini_fallback() -> str:
    """Single-call Gemini run — used only if Claude is unavailable."""
    if not GEMINI_API_KEY:
        return "Construction briefing unavailable — no API keys configured."

    week = _week_ending_friday()
    prompt = (
        f"Produce a weekly Singapore-construction newsletter for week ending {week} "
        "covering tech, safety, tenders, and regulatory updates for a contractor "
        "holding CR13-L1, CR09-L4, CW01-C1. Use live Google Search throughout."
    )
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
        ),
    )
    return response.text


if __name__ == "__main__":
    print(get_construction_briefing())
