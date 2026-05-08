"""
Construction Agent — Weekly Construction Business Intel

Parallel sub-agent + editor architecture:

  Workers (run concurrently, ~30-45s):
    • tech       — top 5 relevant products / systems this week
    • safety     — toolbox talks + WSH/MOM incident scan
    • tenders    — GeBIZ + ST Classifieds + Tenderboard + Ariba pipeline
    • regulatory — BCA / MOM / SCDF / IRAS rolling deadlines

  Editor (runs after workers finish, ~10s):
    • Reviews each section for factual integrity and tone
    • Removes cross-section redundancy
    • Writes a "This week at a glance" opener
    • Outputs the polished newsletter ready to send to colleagues + community

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
NEWSLETTERS_DIR = "newsletters"
HISTORY_WEEKS = 3                # how many past newsletters the editor sees


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

    final = _editor_pass(week, results)
    _save_newsletter(week, final)
    return final


def _load_recent_newsletters(n: int = HISTORY_WEEKS) -> str:
    """Return the most recent N newsletters concatenated, or empty if none."""
    if not os.path.isdir(NEWSLETTERS_DIR):
        return ""
    files = sorted(
        (f for f in os.listdir(NEWSLETTERS_DIR) if f.endswith(".md")),
        reverse=True,
    )[:n]
    if not files:
        return ""
    chunks = []
    for fname in files:
        try:
            with open(os.path.join(NEWSLETTERS_DIR, fname)) as f:
                chunks.append(f"--- {fname} ---\n{f.read()}")
        except Exception:
            continue
    return "\n\n".join(chunks)


def _save_newsletter(week_label: str, content: str) -> None:
    """Persist the final newsletter so future runs can detect repeats."""
    os.makedirs(NEWSLETTERS_DIR, exist_ok=True)
    # Filename: yyyy-mm-dd derived from "Fri DD Mon YYYY"
    try:
        dt = datetime.strptime(week_label, "Fri %d %b %Y")
        fname = dt.strftime("%Y-%m-%d") + ".md"
    except Exception:
        fname = datetime.now(SGT).strftime("%Y-%m-%d") + ".md"
    try:
        with open(os.path.join(NEWSLETTERS_DIR, fname), "w") as f:
            f.write(content)
    except Exception as e:
        print(f"[Construction] Could not save newsletter ({e}).")


def _editor_pass(week: str, sections: dict[str, str]) -> str:
    """
    Final editor pass — reviews the 4 worker outputs, sanity-checks each,
    removes cross-section redundancy, writes a "This week at a glance"
    opener, and stitches into the final newsletter.

    No web tools — this is a polishing pass only. Fast (~10s).
    If the editor call fails, falls back to plain concatenation.
    """
    import anthropic

    raw = "\n\n".join([
        f"=== TECH SECTION (raw) ===\n{sections.get('tech','')}",
        f"=== SAFETY SECTION (raw) ===\n{sections.get('safety','')}",
        f"=== TENDERS SECTION (raw) ===\n{sections.get('tenders','')}",
        f"=== REGULATORY SECTION (raw) ===\n{sections.get('regulatory','')}",
    ])
    history = _load_recent_newsletters()
    history_block = (
        f"━━━ PREVIOUS NEWSLETTERS — DO NOT REPEAT THIS CONTENT ━━━\n{history}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if history else
        "(No prior newsletters on file — nothing to dedupe against.)"
    )

    editor_prompt = f"""\
You are the EDITOR for a weekly construction-business newsletter going to
colleagues and an industry community in Singapore. Four sub-agents have
produced raw drafts. Your job is to polish, dedupe, and stitch — not to add.

━━━ EDITORIAL STANDARDS ━━━
1. GRAMMAR — fix spelling, punctuation, subject-verb agreement, article use,
   and Singapore English conventions (S$, SGT, BCA, MOM, MCST). Capitalise
   product and agency names correctly (Sika, JTC, BCA CRS).
2. CLARITY — every bullet must be one clear sentence. Strip filler words
   ("essentially", "basically", "really"), passive voice, and adverb stacking.
   If a sentence reads ambiguous, tighten or cut it.
3. CONCISION — target 1-2 sentences per bullet. If a worker wrote 4 sentences
   where 2 would do, condense.
4. CONSISTENCY — keep tone tight, factual, "why it matters to us". No
   marketing-speak. No emojis except the established section headers.
5. SANITY — drop vendor names that read fake, URLs that look made-up, or
   internal contradictions. Quietly remove. Do not flag in the output.

━━━ NO-REPEAT RULES (vs. the prior newsletters below) ━━━
• TECH section — hard rule. If a product / vendor was featured in the last
  3 weeks, REMOVE it and ask one of the lower-ranked items to take its place.
  If the worker only surfaced repeats, output fewer than 5 items rather than
  recycle. Quality over quota.
• TENDERS — open tenders may legitimately persist week-to-week. If a tender
  appeared previously and is STILL OPEN, label it "🔁 Continued tracking —
  closes [date]" rather than rewriting the description. Newly surfaced
  tenders carry no label.
• SAFETY — the trade-specific bullet list is evergreen and may repeat. The
  opening line and any "🆕 This week's incident note" must be fresh.
• REGULATORY — the rolling deadlines list is evergreen and may repeat. The
  "🆕 This week" line must be fresh; if the same change is mentioned again,
  drop it.

━━━ STRUCTURAL RULES ━━━
• Write a 3-bullet "👀 THIS WEEK AT A GLANCE" opener crossing sections — the
  top tech signal, the top tender / pipeline action, the top safety or
  regulatory flag.
• Keep each section's existing emoji header bar.
• DO NOT add new content. DO NOT invent vendors, tenders, or incidents.

━━━ FINAL OUTPUT FORMAT ━━━

🏗️ WEEKLY CONSTRUCTION INTEL
Week ending {week} · Scope: Waterproofing (CR13-L1) · Repair & Redecoration (CR09-L4) · General Building (CW01-C1)

━━━━━━━━━━━━━━━━━━━━━━━━━━━
👀 THIS WEEK AT A GLANCE
• [Top tech signal — one line]
• [Top tender / pipeline action — one line]
• [Top safety or regulatory flag — one line]

[edited tech section]
[edited safety section]
[edited tenders section]
[edited regulatory section]

End with one line:
"Questions or additions for next week — reply to this email."

{history_block}

━━━ THIS WEEK'S RAW WORKER DRAFTS ━━━
{raw}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Output the final newsletter only. No preamble. No editor's note."""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            messages=[{"role": "user", "content": editor_prompt}],
        )
        return "\n".join(b.text for b in response.content if b.type == "text").strip()
    except Exception as e:
        print(f"[Construction] Editor pass failed ({e}), falling back to raw stitch...")
        header = (
            "🏗️ WEEKLY CONSTRUCTION INTEL\n"
            f"Week ending {week} · Scope: Waterproofing (CR13-L1) · "
            "Repair & Redecoration (CR09-L4) · General Building (CW01-C1)"
        )
        return "\n\n".join([
            header,
            sections.get("tech", ""),
            sections.get("safety", ""),
            sections.get("tenders", ""),
            sections.get("regulatory", ""),
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
