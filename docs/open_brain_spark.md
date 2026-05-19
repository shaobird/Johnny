# Open Brain Spark — Johnny Zhang

*Generated during the Open Brain Spark interview. This is a one-time analysis of
how the Open Brain pattern fits Johnny Zhang's actual workflow as of the date
this file was committed. Re-run the Spark every 3 months as AI use deepens.*

---

## Snapshot of context at time of Spark

- Singapore construction business owner, evening forex trader (XAU/USD + majors),
  competitive HYROX athlete.
- Mostly office-based, occasional construction site visits.
- Forex window: ~8–9pm SGT (before New York session opens).
- Hard stop on business work at 8pm SGT unless a call is scheduled.
- Daily tools (non-AI): WhatsApp, Gmail, Excel, Telegram.
- Current AI use: light — general questions and research only, not deep workflow
  integration. Open Brain is being built as a *foundation* for future deeper use,
  not to catch up on past use.
- Active 13-week run training plan ("10K with HM focus") building to a 2XU race.
  Currently on Week 5, days postponed by 1.
- Biggest memory gap: forgetting to follow up on project requests and work items.

---

## Your Open Brain Use Cases

### Save This — preserving AI-generated output worth keeping
- Construction research from Gemini on materials/regulations/techniques for a specific project.
- Forex setup analysis done pre-NY-session.
- HYROX/running research — pacing, recovery, taper.
- Business reframes that land — a sharper way to look at cash flow, pricing, or hiring.

### Before I Forget — capturing perishable context  *(HIGHEST ROI)*
- Site visit notes — anything a foreman/contractor/supplier says while you're walking the site.
- WhatsApp quotes and commitments before they scroll past.
- Mid-workout business ideas — phone is on you for the run anyway.
- Phone call action items — capture the moment you hang up.
- Post-NY-session trade journal — what was taken/skipped, why.

### Cross-Pollinate — searching across tools
- Morning planning in Claude — pull the week's open follow-ups captured from prior days.
- Pre-NY-session in Claude/Gemini — pull past notes on the pair being traded.
- Mid-conversation with a contractor — recall past commitments and quotes.
- Newsletter QC pass — pull original research and past issue angles to avoid repetition.

### Build the Thread — compounding over time
- Per-project construction log — every site visit, supplier, decision, delay → defensible timeline.
- Forex trade journal — taken AND skipped trades with reasoning → personal edge map over 3 months.
- Training log alongside the 13-week 2XU plan — how each session felt, adjustments, niggles.
- Newsletter angle history — angle + framing + open rate per issue → improves Sally's drafts.

### People Context — *capture as they come up*
No upfront enumeration. When a name surfaces in conversation (foreman, supplier,
client, coach), the AI should prompt: *"Want me to add [name] to your Open Brain?
One line is enough."*

---

## Your Daily Rhythm

| When | What |
|---|---|
| **~7-8am** | 30-second review of "open follow-ups captured this week" alongside Johnny's morning briefing. |
| **Through the day (office + site)** | Capture mode. 3-5 *Before I Forget* dumps per day. Raw, no analysis. |
| **~7:45pm** | Search the brain for the pair / setup you're trading tonight. Pull notes. Plan the trade. |
| **~10:30pm** | One trade journal capture — taken or skipped, reasoning, market read. |
| **Sunday morning** | Weekly Review prompt. 5 minutes. |

---

## Your First 5 Captures (do these once the local system is running)

1. The 2-3 follow-ups currently sitting in your head that haven't been actioned.
2. Tonight's forex plan if trading — pair, bias, key levels, skip-conditions — captured before 8pm.
3. Today's training session debrief — did Week 5 happen, how it felt, any niggles.
4. The last decision made this week worth explaining in a month — supplier choice, design change, hire decision, with rationale.
5. ONE person from the business — most important weekly contact, one-line context. Seeds the people layer.

---

## How this travels to your Mac Mini

When you set up the new local server:
1. Clone the repo on the Mac Mini.
2. Copy `storage/thoughts/thoughts.json` from wherever it lives now to the new
   machine — that file holds all 50+ captures.
3. Run `python mcp_server.py` (or set `MCP_TRANSPORT=http` for SSE mode).
4. Point Claude Desktop / Cursor / any MCP client at the new server.
5. All this context becomes searchable from any AI tool.
