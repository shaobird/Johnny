"""
Johnny — Personal AI Chief of Staff (Supervisor Edition)

Intelligence levers active:
  1. Adaptive thinking  — Claude reasons before every response
  2. Persistent memory  — reads user profile + notes at start of each briefing
  3. Cross-agent synthesis — explicitly instructed to connect dots across domains
  4. Supervisor prompt  — told to prioritise and advise, not just report data
"""

import concurrent.futures
import json
import os
from datetime import datetime
import anthropic
from agents.calendar import get_todays_events
from agents.fitness import get_fitness_summary
from agents.news import get_high_impact_news
from agents.intel import get_intel_briefing
from agents.training_loop import get_training_analysis, log_proposal, record_outcome
from agents.gmail import get_email_summary
from agents.newsletter import (
    log_newsletter,
    record_metrics as record_newsletter_metrics,
    get_recent_topics,
    get_top_performers,
    prepare_research_brief,
    draft_newsletter,
)
from agents.mo import search as mo_search, get_context as mo_context, list_files as mo_list, get_file_content as mo_get
from agents.lorrie import (
    log_expense, log_invoice, update_invoice_status,
    set_budget, get_budget_status, get_finance_summary, get_job_summary,
)
from agents.peter import log_trade, update_trade, get_trade_log, get_investment_brief
from agents.kanaan import (
    log_tech_decision, log_tech_task, complete_task as complete_tech_task,
    get_dev_status, code_task as kanaan_code_task, apply_code_proposal,
)
from agents.dashboard import get_full_dashboard
from agents.agent_ideas import generate_daily_idea, get_past_ideas
from agents.ai_sessions import (
    capture_session as capture_ai_session_fn,
    search_sessions as search_ai_sessions_fn,
    get_recent_sessions as get_recent_ai_sessions_fn,
    get_session_stats as ai_session_stats_fn,
)
from agents.thoughts import (
    capture_thought as capture_thought_fn,
    list_recent_thoughts as list_recent_thoughts_fn,
    thought_stats as thought_stats_fn,
)
from agents.mnemon import (
    log_pattern, log_decision, update_decision_outcome,
    log_insight, get_context as mnemon_get_context,
    get_all_patterns, get_decisions,
)
import memory as mem
from config import ANTHROPIC_API_KEY, GEMINI_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MAX_ITERATIONS = 15

# Keywords that indicate the user's message likely needs an agent tool call.
# If any of these appear, route to Anthropic (with tools). Otherwise → Gemini (free).
_TOOL_KEYWORDS = (
    "calendar", "meeting", "schedule", "today's events",
    "fitness", "training", "workout", "run ", "running", "gym", "lift",
    "forex", "currency", "trade", "market", "pair", "release",
    "intel", "news", "briefing",
    "email", "inbox", "gmail",
    "save note", "remember this", "log ", "record ",
    "newsletter", "brief", "draft", "write newsletter", "create newsletter",
    "analyse this", "analyze this",
    "expense", "invoice", "finance", "budget", "cost", "job summary",
    "trade", "forex", "position", "investment", "capital", "deploy",
    "tech", "build", "stack", "backlog", "software", "automation",
    "dashboard", "attention", "alerts", "what needs",
    "consult", "team brief", "ask the team",
    "file", "storage", "document", "upload",
    "lorrie", "peter", "kanaan", "val", "sally", "smarty", "mo",
)

_RESEARCH_KEYWORDS = (
    "search for", "research", "find out", "what's happening",
    "latest on", "look up", "google", "web search",
)

_OPUS_KEYWORDS = (
    "full briefing", "daily briefing", "morning briefing",
    "full analysis", "deep dive", "investment thesis",
    "synthesise", "synthesize", "full picture", "qc this",
)


def _needs_anthropic(message: str) -> bool:
    msg = message.lower()
    return any(kw in msg for kw in _TOOL_KEYWORDS)


def _needs_research(message: str) -> bool:
    msg = message.lower()
    return any(kw in msg for kw in _RESEARCH_KEYWORDS)


def _needs_opus(message: str) -> bool:
    msg = message.lower()
    return any(kw in msg for kw in _OPUS_KEYWORDS)


# ── System prompt (rebuilt fresh each call so memory is always current) ───────

def _build_system_prompt() -> str:
    user_context = mem.get_context()

    # Pull Mnemon's top learnings into every system prompt — free, no API call
    mnemon_section = ""
    try:
        learned = mnemon_get_context()  # no topic filter = top patterns across all domains
        if learned:
            mnemon_section = f"\n\n━━━ WHAT MNEMON HAS LEARNED ━━━\n{learned}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    except Exception:
        pass

    return f"""\
You are Johnny Zhang — Zhang Zhi Yi — personal AI chief of staff and trusted senior advisor. \
Your English name is Johnny. Your Chinese name is Zhang Zhi Yi (张智义). \
You have a strong, distinct personality — sharp, direct, honest, and collaborative. \
You address the user as "Boss" unless their name is in the profile below.

━━━ YOUR PERSONALITY ━━━
• Direct — get to the point immediately. No preamble, no "Great question!", no filler.
• Concise — say more with less. One clear sentence beats three vague ones.
• Technically deep — don't just say what, explain why. The reasoning matters.
• Brutally honest — if something won't work, say so clearly and explain why.
  Never just agree to avoid conflict. Push back when you see a flaw.
• Collaborative — work through problems together. Ask sharp questions.
  Think out loud when useful. Say "I'm not sure, let me think..." when you're not.
• Confident but not arrogant — you have strong views, held loosely.
  When new evidence arrives, update immediately without ego.
• Dry wit — occasional, never forced. Never use emojis in casual conversation
  (section headers in briefings are fine).
• No sycophancy — never start with praise or validation. Just answer.
━━━━━━━━━━━━━━━━━━━━━━

━━━ WHAT YOU KNOW ABOUT THE USER ━━━
{user_context}{mnemon_section}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ YOUR SPECIALIST AGENTS ━━━
Each agent is a mini-coordinator — they pull from their own sub-sources before responding.

• Smarty  — Chief of Research: calendar, forex news, intel briefing (AI/construction/macro/HYROX)
• Val     — Chief of Fitness: Strava + Hevy, training load, lactate zones, HYROX/half marathon
• Sally   — Chief of Market Comms: newsletter performance, topic memory, research briefs, full drafts.
            Sally drafts — you QC. When drafting a newsletter: call draft_newsletter, review Sally's
            copy, make direct improvements (don't just comment), return the polished final draft +
            3 QC notes at the bottom explaining what you changed and why. User pastes it into Manus AI.
• Mo      — Chief Warehouse Manager: file storage + retrieval, feeds context to all other agents.
            Sub-agent: Mnemon — every Mo context call also returns Mnemon's learnings on that topic.
• Mnemon  — Memory & Learning (lives under Mo): patterns, decisions + outcomes, insights.
            Use log_pattern when you notice a behavioural regularity.
            Use log_decision when a significant choice is made — update outcome when known.
            Use log_insight for one-line truths worth keeping forever.
• Lorrie  — Chief of Finance: day-to-day money — expenses, invoices, budgets, cash flow, job costing.
            Lorrie consults Mo automatically for stored budget/contract docs.
• Peter   — Chief of Investment: forex positioning, capital allocation, investment thesis.
            Peter pulls Smarty's live news before giving any trade advice — never advises blind.
• Kanaan  — Chief of Tech & Dev: software architecture, AI/automation, Johnny's dev roadmap,
            build vs buy decisions. Can write code via kanaan_code_task — proposes changes,
            user approves, then apply_code_proposal writes the file. Never auto-commits.
• Mo MCP  — Centralised AI Session Store: Mo also manages a unified memory of everything
            researched across ALL AI tools (Claude, Gemini, ChatGPT, Perplexity, Manus).
            capture_ai_session: save any AI Q&A so it's searchable later.
            search_ai_sessions: search what was previously researched across all AI tools.
            get_recent_ai_sessions: review recent research sessions by source.
            This means research done in Gemini is findable when asking Claude, and vice versa.

CROSS-AGENT COLLABORATION:
Use consult_team when a question spans domains. Use get_dashboard when the user wants
a status check across all agents at once. Examples:
  • "What needs my attention?" → get_dashboard (all agents check in parallel)
  • "Should I buy this equipment?" → consult_team: lorrie + kanaan + mo
  • "What's my financial and market position?" → consult_team: lorrie + peter + smarty
  • "Plan my week" → consult_team: val + smarty, then check_calendar separately
Always synthesise team inputs into ONE clear recommendation. Don't just list what each said.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ STRATEGIC PLAYBOOK ━━━
You have a playbook of mental models from Munger, Buffett, Dalio, Hormozi, and Naval. \
Apply these frameworks proactively — don't wait to be asked. \
When giving advice: invert the problem (Munger), check for moats (Buffett), \
look for systems to build (Dalio), find leverage (Naval), and maximise value delivery (Hormozi). \
Reference specific models by name when relevant so the user learns them over time.
━━━━━━━━━━━━━━━━━━━━━━━━

━━━ SUPERVISOR MINDSET ━━━
You are NOT a data reporter. You are a synthesiser and advisor.

Step 1 — GATHER: Call only the agents that are actually needed. Don't call all agents
  for a simple question — that wastes API budget. Be surgical: one question → one or two agents max.
Step 2 — SYNTHESISE: Look for connections across domains:
  • Forex event overlapping a calendar meeting? Flag it.
  • Consecutive hard training sessions? Warn before overtraining hits.
  • Budget overrun on a job that also has an overdue invoice? Lorrie + context together.
  • Tech decision with capital implications? Kanaan + Peter together.
Step 3 — PRIORITISE: Lead with the 2–3 things that matter MOST. Ruthlessly cut the rest.
Step 4 — ADVISE: End with one clear action. Not three. One.

COST & EFFICIENCY RULES:
  • ROUTING: LLaMA (local/free) for simple chat → Gemini for research →
             Sonnet for tool calls → Opus for briefings/QC/deep synthesis.
             LLaMA falls back to Gemini, then Sonnet if unavailable.
  • Use Sonnet for tool calls, Opus only for full morning briefings.
  • consult_team runs agents in parallel — always prefer that over sequential calls.
  • If Mo already has the answer in stored files, don't call a slow external API.
  • Intel briefing (Gemini search) is expensive — only run it when explicitly requested.
  • Keep responses tight. One clear answer beats three verbose ones every time.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ MEMORY ━━━
You can save notes to your memory using the save_note tool. Use it when you:
  • Notice a pattern (e.g. "skips workouts when 3+ meetings")
  • Learn a preference the user states explicitly
  • Want to track a baseline (e.g. "avg run pace as of Apr 7: 5:45/km")

━━━ FORMATTING ━━━
  • Plain text with emoji section headers (📅 💪 🔴 🧠) in briefings only
  • Bullet points for lists
  • Bold key insights using *asterisks* (Telegram renders these as bold)
  • Keep each section tight — no filler, no padding
  • If an agent fails, note it in one line and move on\
"""


# ── Tools ─────────────────────────────────────────────────────────────────────

# ── Cross-agent consultation ──────────────────────────────────────────────────

def _consult_team(topic: str, agents: list) -> str:
    """Fan out to multiple agents in parallel and collect their perspectives."""
    from agents.smarty import get_full_research_brief

    agent_fns = {
        "lorrie": lambda: get_finance_summary(),
        "peter":  lambda: get_investment_brief(),
        "val":    lambda: get_fitness_summary(),
        "smarty": lambda: get_high_impact_news(),
        "sally":  lambda: get_recent_topics(),
        "mo":     lambda: mo_context(topic),
        "kanaan": lambda: get_dev_status(),
    }

    selected = {a.lower(): agent_fns[a.lower()] for a in agents if a.lower() in agent_fns}
    if not selected:
        return f"No valid agent names provided. Available: {', '.join(agent_fns)}"

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {name: executor.submit(fn) for name, fn in selected.items()}
        results = {}
        for name, fut in futures.items():
            try:
                results[name] = fut.result(timeout=120)
            except Exception as e:
                results[name] = f"Error: {e}"

    agent_labels = {
        "lorrie": "LORRIE (Finance — budgets & cash flow)",
        "peter":  "PETER (Investment — forex & capital)",
        "val":    "VAL (Fitness)",
        "smarty": "SMARTY (Research & Markets)",
        "sally":  "SALLY (Market Communications)",
        "mo":     "MO (Warehouse — relevant docs)",
        "kanaan": "KANAAN (Tech & Development)",
    }

    parts = [f"━━━ TEAM BRIEF: {topic} ━━━\n"]
    for agent, output in results.items():
        label = agent_labels.get(agent, agent.upper())
        parts.append(f"\n🔹 {label}\n{output}")
    parts.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(parts)


_TOOLS = [
    {
        "name": "check_calendar",
        "description": "Fetch today's meetings and events from Google Calendar.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_fitness",
        "description": (
            "Fetch the last 7 days of Strava and Hevy activity. "
            "Returns a progress summary and a Claude-generated fitness recommendation."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_forex_news",
        "description": (
            "Scrape today's HIGH-IMPACT economic events from Forex Factory. "
            "Returns time, currency, event name, forecast, and previous values."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_intel_briefing",
        "description": (
            "Run a live web search and generate a daily intelligence briefing "
            "across 4 domains: AI & automation, construction industry, "
            "forex & macro markets, and HYROX / endurance sport. "
            "Each item includes a 'why it matters for you' analysis. "
            "Ends with 3 actionable signals for today. Takes 1–2 minutes to run."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "save_note",
        "description": (
            "Save a note to Johnny's persistent memory. Use this to record patterns, "
            "preferences, baselines, or anything worth remembering for future briefings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "The note to save. Be specific and concise.",
                }
            },
            "required": ["note"],
        },
    },
    {
        "name": "check_emails",
        "description": (
            "Check Johnny's Gmail inbox for new relevant emails. "
            "Filters out promotions and low-signal mail. "
            "Returns urgent, action-needed, market, and construction emails only."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "analyze_training",
        "description": (
            "Analyze the last 4 weeks of training data (Strava + Hevy). "
            "Identifies trends in run volume, pace, gym compliance. "
            "Proposes one specific adjustment for next week using the Karpathy Loop pattern. "
            "Returns winning/losing patterns detected over time."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "log_training_proposal",
        "description": (
            "Log a proposed training adjustment so Johnny can track whether it worked next week."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal": {"type": "string", "description": "The specific change proposed."},
                "variable":  {"type": "string", "description": "What training variable is being changed."},
                "hypothesis": {"type": "string", "description": "Why this change should help."},
            },
            "required": ["proposal", "variable", "hypothesis"],
        },
    },
    {
        "name": "record_training_outcome",
        "description": (
            "Record whether last week's proposed training adjustment worked. "
            "Updates the winning/losing patterns log."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "outcome":          {"type": "string", "description": "What happened."},
                "metric_improved":  {"type": "boolean", "description": "True if the target metric improved."},
            },
            "required": ["outcome", "metric_improved"],
        },
    },
    {
        "name": "log_newsletter",
        "description": "Record a newsletter that was sent. Use after publishing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":      {"type": "string", "description": "Newsletter title or subject line."},
                "topic":      {"type": "string", "description": "Main topic in 2-5 words (e.g. 'supplier costs', 'safety regs')."},
                "key_points": {"type": "string", "description": "1-2 sentence summary of what was covered."},
            },
            "required": ["title", "topic"],
        },
    },
    {
        "name": "record_newsletter_metrics",
        "description": "Attach open/click metrics to a previously logged newsletter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":   {"type": "string", "description": "The newsletter title to match."},
                "opens":   {"type": "integer", "description": "Number of unique opens."},
                "clicks":  {"type": "integer", "description": "Number of clicks."},
                "sent_to": {"type": "integer", "description": "Total recipients (for rate calc)."},
            },
            "required": ["title", "opens", "clicks", "sent_to"],
        },
    },
    {
        "name": "get_recent_newsletter_topics",
        "description": (
            "List newsletter topics from the last 6-8 weeks so we don't repeat content. "
            "Use before suggesting a new newsletter angle."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "weeks": {"type": "integer", "description": "Lookback window in weeks (default 8)."},
            },
            "required": [],
        },
    },
    {
        "name": "get_top_newsletters",
        "description": "Return the highest-performing past newsletters by open rate.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "prepare_newsletter_brief",
        "description": (
            "Generate a full research brief for the next newsletter. "
            "Pulls live intel briefing, recent topics covered, and top performers. "
            "Takes 1-2 minutes (runs Gemini search). Use when planning a new newsletter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "angle": {"type": "string", "description": "Optional angle or theme to focus on."},
            },
            "required": [],
        },
    },
    {
        "name": "draft_newsletter",
        "description": (
            "Sally drafts a full newsletter — subject line, headline, body, CTA. "
            "She checks recent topics, pulls today's intel, then writes the complete copy. "
            "After calling this, YOU (Johnny) must QC the draft: improve the subject line if weak, "
            "tighten the copy, ensure CTA is sharp, fix any factual issues. "
            "Return the polished final draft + brief QC notes at the bottom. "
            "Use when the user asks to write, draft, or create a newsletter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "angle": {"type": "string", "description": "Angle or theme for the newsletter."},
                "topic": {"type": "string", "description": "Specific topic to focus on."},
            },
            "required": [],
        },
    },
    {
        "name": "ask_mo",
        "description": (
            "Ask Mo (chief warehouse manager) for context on a topic. "
            "Mo searches his stored files and returns relevant summaries. "
            "Use before answering questions about construction docs, past quotes, newsletters, supplier info."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic or question to find context for."},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "mo_search",
        "description": "Search Mo's warehouse by keyword. Optionally filter by category (construction/finance/newsletters/research/personal).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":    {"type": "string", "description": "Search keyword."},
                "category": {"type": "string", "description": "Optional category filter."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "mo_list",
        "description": "List all files Mo has stored. Optionally filter by category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Optional category filter."},
            },
            "required": [],
        },
    },
    {
        "name": "mo_get_file",
        "description": "Get the full parsed content of a file stored by Mo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Exact filename to retrieve."},
            },
            "required": ["filename"],
        },
    },
    # ── Mnemon tools (memory & learning — sub-agent under Mo) ─────────────────
    {
        "name": "log_pattern",
        "description": (
            "Mnemon records a behavioural pattern you've observed — something the user "
            "does repeatedly. Each repeat reinforces confidence. "
            "Use whenever you notice a regularity across sessions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "fitness/finance/trading/construction/work/general"},
                "pattern":  {"type": "string", "description": "The pattern observed, stated plainly."},
            },
            "required": ["category", "pattern"],
        },
    },
    {
        "name": "log_decision",
        "description": (
            "Mnemon logs a significant decision and its outcome. "
            "Log when a notable choice is made. Update the outcome later with update_decision_outcome."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domain":   {"type": "string", "description": "construction/finance/trading/tech/personal/general"},
                "decision": {"type": "string", "description": "What was decided."},
                "outcome":  {"type": "string", "description": "positive/negative/neutral/pending (default pending)"},
                "lesson":   {"type": "string", "description": "What we learned from this outcome."},
            },
            "required": ["domain", "decision"],
        },
    },
    {
        "name": "update_decision_outcome",
        "description": "Update the outcome of a previously logged decision once results are known.",
        "input_schema": {
            "type": "object",
            "properties": {
                "decision_fragment": {"type": "string", "description": "Partial text of the original decision."},
                "outcome":           {"type": "string", "description": "positive/negative/neutral"},
                "lesson":            {"type": "string", "description": "What we learned."},
            },
            "required": ["decision_fragment", "outcome"],
        },
    },
    {
        "name": "log_insight",
        "description": (
            "Mnemon saves a one-line truth about the business, user, or market that's worth keeping forever. "
            "Use for things like 'Q1 cash flow is always tight' or 'supplier X is 10% cheaper consistently'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category":  {"type": "string", "description": "finance/construction/trading/fitness/general"},
                "insight":   {"type": "string", "description": "The insight, stated as a clear one-liner."},
                "relevance": {"type": "string", "description": "high/medium/low"},
            },
            "required": ["category", "insight"],
        },
    },
    {
        "name": "get_patterns",
        "description": "Return all patterns Mnemon has logged, optionally filtered by category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Optional category filter."},
            },
            "required": [],
        },
    },
    {
        "name": "get_decision_log",
        "description": "Return past decisions and their outcomes from Mnemon.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Optional domain filter."},
            },
            "required": [],
        },
    },
    # ── Lorrie tools (Chief of Finance — day-to-day money tracking) ──────────
    {
        "name": "log_expense",
        "description": "Lorrie logs an expense for the construction business.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount":      {"type": "number", "description": "Amount spent."},
                "category":    {"type": "string", "description": "materials/labour/overhead/equipment/other"},
                "description": {"type": "string", "description": "What was spent on."},
                "job":         {"type": "string", "description": "Job or project name (optional)."},
                "currency":    {"type": "string", "description": "Currency code, default SGD."},
            },
            "required": ["amount", "category", "description"],
        },
    },
    {
        "name": "log_invoice",
        "description": "Lorrie logs an invoice issued to a client.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount":      {"type": "number", "description": "Invoice amount."},
                "client":      {"type": "string", "description": "Client name."},
                "description": {"type": "string", "description": "Work description."},
                "job":         {"type": "string", "description": "Job or project name (optional)."},
                "status":      {"type": "string", "description": "pending/paid/overdue"},
                "currency":    {"type": "string", "description": "Currency code, default SGD."},
            },
            "required": ["amount", "client", "description"],
        },
    },
    {
        "name": "update_invoice_status",
        "description": "Lorrie updates an invoice status — e.g. pending → paid or overdue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client":     {"type": "string", "description": "Client name (partial match)."},
                "new_status": {"type": "string", "description": "paid/overdue/pending"},
            },
            "required": ["client", "new_status"],
        },
    },
    {
        "name": "set_budget",
        "description": "Lorrie sets a monthly (or quarterly/annual) budget limit for an expense category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "materials/labour/overhead/equipment/other"},
                "amount":   {"type": "number", "description": "Budget limit amount."},
                "period":   {"type": "string", "description": "monthly/quarterly/annual (default monthly)"},
                "currency": {"type": "string", "description": "Currency code, default SGD."},
            },
            "required": ["category", "amount"],
        },
    },
    {
        "name": "get_budget_status",
        "description": (
            "Lorrie shows actual spend vs budget for the current month. "
            "Also queries Mo for any stored budget documents. "
            "Use when the user asks about spending, budget, or how much has been used."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_finance_summary",
        "description": "Lorrie summarises income vs expenses over the last N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Lookback window in days (default 30)."},
            },
            "required": [],
        },
    },
    {
        "name": "get_job_summary",
        "description": "Lorrie summarises all costs and invoices for a specific job.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job": {"type": "string", "description": "Job or project name."},
            },
            "required": ["job"],
        },
    },
    # ── Peter tools (Chief of Investment — strategy & forex) ─────────────────
    {
        "name": "log_trade",
        "description": "Peter logs a new forex or investment trade.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pair":      {"type": "string", "description": "Currency pair or asset, e.g. GBP/USD."},
                "direction": {"type": "string", "description": "long or short."},
                "entry":     {"type": "number", "description": "Entry price."},
                "sl":        {"type": "number", "description": "Stop-loss price."},
                "tp":        {"type": "number", "description": "Take-profit price."},
                "rationale": {"type": "string", "description": "Why you took this trade."},
                "size":      {"type": "number", "description": "Position size in lots (default 1.0)."},
            },
            "required": ["pair", "direction", "entry", "sl", "tp", "rationale"],
        },
    },
    {
        "name": "update_trade",
        "description": "Peter closes or updates an open trade.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pair":       {"type": "string", "description": "Currency pair to update."},
                "status":     {"type": "string", "description": "closed/stopped/cancelled"},
                "exit_price": {"type": "number", "description": "Exit price (for PnL calc)."},
                "notes":      {"type": "string", "description": "Post-trade notes."},
            },
            "required": ["pair", "status"],
        },
    },
    {
        "name": "get_trade_log",
        "description": "Peter returns trade history. Use open_only=true to see live positions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "open_only": {"type": "boolean", "description": "True = open positions only."},
            },
            "required": [],
        },
    },
    {
        "name": "get_investment_brief",
        "description": (
            "Peter's full investment view: open positions, track record, and today's live forex events. "
            "Peter pulls Smarty's news feed internally before advising. "
            "Use when user asks about trades, forex, where to deploy capital."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # ── Dashboard ─────────────────────────────────────────────────────────────
    {
        "name": "get_dashboard",
        "description": (
            "Pull the live dashboard — all agents check their state in parallel and return "
            "anything that needs attention (overdue invoices, budget alerts, open trades, "
            "backlog tasks, overdue newsletters). Use when the user asks 'what needs my attention', "
            "'any alerts', or 'dashboard'."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # ── Kanaan tools ──────────────────────────────────────────────────────────
    {
        "name": "log_tech_decision",
        "description": (
            "Kanaan logs a technology decision — build vs. buy, tool selection, "
            "architecture choice, AI/automation strategy. Use when a tech direction is confirmed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "decision":  {"type": "string", "description": "What was decided."},
                "rationale": {"type": "string", "description": "Why this choice was made."},
                "status":    {"type": "string", "description": "decided/pending/deferred/rejected"},
            },
            "required": ["decision", "rationale"],
        },
    },
    {
        "name": "log_tech_task",
        "description": (
            "Kanaan adds a development task to the backlog — for Johnny itself or "
            "the construction business tech stack. Use when the user flags something to build."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task":     {"type": "string", "description": "Task description."},
                "priority": {"type": "string", "description": "high/medium/low"},
                "notes":    {"type": "string", "description": "Extra context or acceptance criteria."},
            },
            "required": ["task"],
        },
    },
    {
        "name": "complete_tech_task",
        "description": "Mark a backlog task as done by partial name match.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task name or partial match."},
            },
            "required": ["task"],
        },
    },
    {
        "name": "get_dev_status",
        "description": (
            "Get Kanaan's current development backlog and recent tech decisions. "
            "Use when the user asks about Johnny's roadmap, open tech tasks, or past decisions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # ── Kanaan code capability ────────────────────────────────────────────────
    {
        "name": "kanaan_code_task",
        "description": (
            "Kanaan uses Claude Sonnet to implement a coding task within the Johnny codebase. "
            "He reads the relevant files, writes a complete implementation, and returns a proposal. "
            "IMPORTANT: changes are proposed only — not written to disk until user approves. "
            "Use when user asks Kanaan to build, fix, or modify something in Johnny."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task":  {"type": "string", "description": "What to build or fix, in plain English."},
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Relevant file paths relative to Johnny root (e.g. ['agents/fitness.py']).",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "apply_code_proposal",
        "description": (
            "Apply a specific file change from Kanaan's code proposal. "
            "Only call this AFTER the user has reviewed and approved Kanaan's output. "
            "Writes the file to disk. Does NOT commit — user runs git commands separately."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path of the file to write."},
                "content":   {"type": "string", "description": "Full file content to write."},
            },
            "required": ["file_path", "content"],
        },
    },
    # ── Agent ideas (Smarty + Kanaan) ─────────────────────────────────────────
    {
        "name": "generate_agent_idea",
        "description": "Smarty and Kanaan collaborate to generate a fresh AI agent idea. Smarty researches trends, Kanaan evaluates feasibility. Use when user asks for new agent ideas or what AI we could build next.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_past_agent_ideas",
        "description": "Return the last N daily agent ideas generated by Smarty and Kanaan.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Number of past ideas to return (default 7)."}},
            "required": [],
        },
    },
    # ── Open Brain thoughts (Memory Migration / Spark / Weekly Review) ───────
    {
        "name": "capture_thought",
        "description": (
            "Save a single self-contained thought to the Open Brain. "
            "Use when the user shares context, decisions, people, preferences, or topics "
            "worth remembering across all AI tools. Smart-routes preferences → Mnemon patterns, "
            "decisions → Mnemon decisions. "
            "Category: people | projects | preferences | decisions | topics | professional | personal | general"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "thought":   {"type": "string", "description": "Self-contained statement that makes sense to any AI later."},
                "category":  {"type": "string", "description": "One of: people, projects, preferences, decisions, topics, professional, personal, general."},
                "tags":      {"type": "array", "items": {"type": "string"}, "description": "Optional keywords for future search."},
                "source_ai": {"type": "string", "description": "Which AI captured this (default claude)."},
            },
            "required": ["thought"],
        },
    },
    {
        "name": "list_recent_thoughts",
        "description": "Return the most recent thoughts from the Open Brain. Optionally filter by category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit":    {"type": "integer", "description": "How many to return (default 10)."},
                "category": {"type": "string",  "description": "Optional category filter."},
            },
            "required": [],
        },
    },
    {
        "name": "thought_stats",
        "description": "Summary of Open Brain captures: total, by category, by source AI, last 7 days.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # ── AI Session Store (Mo's MCP layer) ─────────────────────────────────────
    {
        "name": "capture_ai_session",
        "description": (
            "Save a Q&A exchange from any AI (Claude, Gemini, ChatGPT, Perplexity, etc.) to Mo's unified memory. "
            "Use at end of research conversations so findings are searchable later. "
            "source_ai: claude | gemini | chatgpt | perplexity | grok | manus | other"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query":     {"type": "string", "description": "The question or search that was asked."},
                "response":  {"type": "string", "description": "The AI's response or research result."},
                "source_ai": {"type": "string", "description": "Which AI produced this (claude/gemini/chatgpt/etc)."},
                "tags":      {"type": "array",  "items": {"type": "string"}, "description": "Optional keywords."},
                "topic":     {"type": "string", "description": "Topic override (blank = auto-detect)."},
            },
            "required": ["query", "response"],
        },
    },
    {
        "name": "search_ai_sessions",
        "description": "Search past AI sessions (from Claude, Gemini, ChatGPT, etc.) by keyword. Optionally filter by source AI.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":     {"type": "string", "description": "Keyword to search for."},
                "source_ai": {"type": "string", "description": "Filter to one AI source (optional)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_recent_ai_sessions",
        "description": "Get the most recent AI sessions. Optionally filter by source AI (claude/gemini/chatgpt/etc).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit":     {"type": "integer", "description": "Number of sessions to return (default 10)."},
                "source_ai": {"type": "string",  "description": "Filter by AI source (optional)."},
            },
            "required": [],
        },
    },
    {
        "name": "ai_session_stats",
        "description": "Show how many AI sessions are stored per source (Claude, Gemini, ChatGPT, etc.).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # ── Cross-agent collaboration ──────────────────────────────────────────────
    {
        "name": "consult_team",
        "description": (
            "Fan out to multiple specialist agents simultaneously and get their perspectives on a topic. "
            "Use when a question spans multiple domains. Each agent runs in parallel — fast and efficient. "
            "Available agents: lorrie (finance/budgets), peter (investment/forex), val (fitness), "
            "smarty (news/intel), sally (newsletter), mo (stored docs on topic), kanaan (tech/dev). "
            "You synthesise the results into one recommendation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The question or topic each agent should address.",
                },
                "agents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Agent names to consult: peter, val, smarty, sally, mo, kanaan",
                },
            },
            "required": ["topic", "agents"],
        },
    },
]

_HANDLERS = {
    "check_emails":            lambda _:   get_email_summary(),
    "check_calendar":          lambda _:   get_todays_events(),
    "check_fitness":           lambda _:   get_fitness_summary(),
    "get_forex_news":          lambda _:   get_high_impact_news(),
    "get_intel_briefing":      lambda _:   get_intel_briefing(),
    "save_note":               lambda inp: mem.add_note(inp["note"]),
    "analyze_training":        lambda _:   get_training_analysis(),
    "log_training_proposal":   lambda inp: log_proposal(inp["proposal"], inp["variable"], inp["hypothesis"]),
    "record_training_outcome": lambda inp: record_outcome(inp["outcome"], inp["metric_improved"]),
    "log_newsletter":            lambda inp: log_newsletter(inp["title"], inp["topic"], inp.get("key_points", "")),
    "record_newsletter_metrics": lambda inp: record_newsletter_metrics(inp["title"], inp["opens"], inp["clicks"], inp["sent_to"]),
    "get_recent_newsletter_topics": lambda inp: get_recent_topics(inp.get("weeks", 8)),
    "get_top_newsletters":       lambda _:   get_top_performers(),
    "prepare_newsletter_brief":  lambda inp: prepare_research_brief(inp.get("angle", "")),
    "draft_newsletter":          lambda inp: draft_newsletter(inp.get("angle", ""), inp.get("topic", "")),
    "ask_mo":                    lambda inp: mo_context(inp["topic"]),
    "mo_search":                 lambda inp: mo_search(inp["query"], inp.get("category", "")),
    "mo_list":                   lambda inp: mo_list(inp.get("category", "")),
    "mo_get_file":               lambda inp: mo_get(inp["filename"]),
    # Mnemon — memory & learning
    "log_pattern":               lambda inp: log_pattern(inp["category"], inp["pattern"]),
    "log_decision":              lambda inp: log_decision(inp["domain"], inp["decision"], inp.get("outcome", "pending"), inp.get("lesson", "")),
    "update_decision_outcome":   lambda inp: update_decision_outcome(inp["decision_fragment"], inp["outcome"], inp.get("lesson", "")),
    "log_insight":               lambda inp: log_insight(inp["category"], inp["insight"], inp.get("relevance", "medium")),
    "get_patterns":              lambda inp: get_all_patterns(inp.get("category", "")),
    "get_decision_log":          lambda inp: get_decisions(inp.get("domain", "")),
    # Lorrie — finance operations
    "log_expense":               lambda inp: log_expense(inp["amount"], inp["category"], inp["description"], inp.get("job", ""), inp.get("currency", "SGD")),
    "log_invoice":               lambda inp: log_invoice(inp["amount"], inp["client"], inp["description"], inp.get("job", ""), inp.get("status", "pending"), inp.get("currency", "SGD")),
    "update_invoice_status":     lambda inp: update_invoice_status(inp["client"], inp["new_status"]),
    "set_budget":                lambda inp: set_budget(inp["category"], inp["amount"], inp.get("period", "monthly"), inp.get("currency", "SGD")),
    "get_budget_status":         lambda _:   get_budget_status(),
    "get_finance_summary":       lambda inp: get_finance_summary(inp.get("days", 30)),
    "get_job_summary":           lambda inp: get_job_summary(inp["job"]),
    # Peter — investment operations
    "log_trade":                 lambda inp: log_trade(inp["pair"], inp["direction"], inp["entry"], inp["sl"], inp["tp"], inp["rationale"], inp.get("size", 1.0)),
    "update_trade":              lambda inp: update_trade(inp["pair"], inp["status"], inp.get("exit_price", 0.0), inp.get("notes", "")),
    "get_trade_log":             lambda inp: get_trade_log(inp.get("open_only", False)),
    "get_investment_brief":      lambda _:   get_investment_brief(),
    # Kanaan — tech operations
    "log_tech_decision":         lambda inp: log_tech_decision(inp["decision"], inp["rationale"], inp.get("status", "decided")),
    "log_tech_task":             lambda inp: log_tech_task(inp["task"], inp.get("priority", "medium"), inp.get("notes", "")),
    "complete_tech_task":        lambda inp: complete_tech_task(inp["task"]),
    "get_dev_status":            lambda _:   get_dev_status(),
    "kanaan_code_task":          lambda inp: kanaan_code_task(inp["task"], inp.get("files", [])),
    "apply_code_proposal":       lambda inp: apply_code_proposal(inp["file_path"], inp["content"]),
    # Agent ideas
    "generate_agent_idea":  lambda _:   generate_daily_idea(),
    "get_past_agent_ideas": lambda inp: get_past_ideas(inp.get("limit", 7)),
    # Open Brain thoughts
    "capture_thought":       lambda inp: capture_thought_fn(inp["thought"], inp.get("category", "general"), inp.get("tags", []), inp.get("source_ai", "claude")),
    "list_recent_thoughts":  lambda inp: list_recent_thoughts_fn(inp.get("limit", 10), inp.get("category", "")),
    "thought_stats":         lambda _:   thought_stats_fn(),
    # AI Session Store (Mo's MCP layer)
    "capture_ai_session":    lambda inp: capture_ai_session_fn(inp["query"], inp["response"], inp.get("source_ai", "claude"), inp.get("tags", []), inp.get("topic", "")),
    "search_ai_sessions":    lambda inp: search_ai_sessions_fn(inp["query"], inp.get("source_ai", "")),
    "get_recent_ai_sessions": lambda inp: get_recent_ai_sessions_fn(inp.get("limit", 10), inp.get("source_ai", "")),
    "ai_session_stats":      lambda _:   ai_session_stats_fn(),
    # Cross-agent
    "consult_team":              lambda inp: _consult_team(inp["topic"], inp["agents"]),
    "get_dashboard":             lambda _:   get_full_dashboard(),
}


# ── Public API ────────────────────────────────────────────────────────────────

def chat(message: str, history: list[dict] | None = None, use_opus: bool = False) -> str:
    """
    4-tier routing:
      Opus    — briefings, deep synthesis, QC
      Gemini  — research layer (web search, intel)
      Sonnet  — tool calls, agent orchestration
      LLaMA   — simple chat (local, free)
    """
    msgs = list(history or []) + [{"role": "user", "content": message}]

    # Tier 1: Opus — explicit flag or briefing-class request
    if use_opus or _needs_opus(message):
        return _run_loop(msgs, use_opus=True)

    # Tier 2: Sonnet — any message needing agent tools
    if _needs_anthropic(message):
        return _run_loop(msgs, use_opus=False)

    # Tier 3: Gemini — research queries (no tools needed, just search)
    if GEMINI_API_KEY and _needs_research(message):
        try:
            return _chat_gemini(message, history or [])
        except Exception as e:
            print(f"[Chat] Gemini research failed ({e}), falling back...")

    # Tier 4: LLaMA — simple chat (local, free)
    try:
        return _chat_llama(message, history or [])
    except Exception as e:
        print(f"[Chat] LLaMA unavailable ({e}), falling back to Gemini...")

    # Fallback: Gemini
    if GEMINI_API_KEY:
        try:
            return _chat_gemini(message, history or [])
        except Exception as e:
            print(f"[Chat] Gemini fallback failed ({e}), using Sonnet...")

    # Final fallback: Anthropic Sonnet
    return _run_loop(msgs, use_opus=False)


def _chat_gemini(message: str, history: list[dict]) -> str:
    """
    Free chat via Gemini 2.5 Pro — no tools, but full memory context.
    Used for simple conversation that doesn't need agent calls.
    """
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Convert Anthropic-format history to Gemini format
    contents = []
    for turn in history:
        role = "user" if turn["role"] == "user" else "model"
        text = turn["content"] if isinstance(turn["content"], str) else str(turn["content"])
        contents.append(genai_types.Content(role=role, parts=[genai_types.Part(text=text)]))
    contents.append(genai_types.Content(role="user", parts=[genai_types.Part(text=message)]))

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=_build_system_prompt(),
        ),
    )
    return response.text or "(no response)"


def _chat_llama(message: str, history: list) -> str:
    """Local LLaMA via Ollama — free tier for simple chat."""
    import requests
    messages = [{"role": "system", "content": _build_system_prompt()}]
    for turn in history:
        messages.append({"role": turn["role"], "content": str(turn["content"])})
    messages.append({"role": "user", "content": message})
    response = requests.post(
        f"{OLLAMA_BASE_URL}/v1/chat/completions",
        json={"model": OLLAMA_MODEL, "messages": messages},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def daily_briefing() -> str:
    """Trigger the full morning briefing — Johnny calls all agents and synthesises."""
    return chat(
        "Good morning. Give me my complete daily briefing. "
        "Call check_calendar, check_fitness, and get_forex_news first, "
        "then structure your reply exactly like this:\n\n"
        "📅 CALENDAR\n"
        "List today's meetings with times. If none, say so.\n\n"
        "💪 FITNESS\n"
        "Last 7 days summary. Am I on track? Any warning signs?\n\n"
        "🔴 FOREX\n"
        "Today's high-impact events with times (SGT) and currencies. If none, say so.\n\n"
        "⚡ PRIORITIES\n"
        "The 2–3 things that matter most today. Be specific, not generic.\n\n"
        "✅ ONE ACTION\n"
        "Single most important thing I should do right now.\n\n"
        "Save any patterns or baselines you notice to memory.",
        use_opus=True,
    )


# ── Usage tracking ───────────────────────────────────────────────────────────

USAGE_LOG = "usage_log.json"

def _log_usage(response: anthropic.types.Message) -> None:
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    log = []
    if os.path.exists(USAGE_LOG):
        with open(USAGE_LOG, "r") as f:
            log = json.load(f)
    log.append(entry)
    with open(USAGE_LOG, "w") as f:
        json.dump(log, f, indent=2)


# ── Agentic loop ──────────────────────────────────────────────────────────────

def _run_loop(messages: list[dict], use_opus: bool = False) -> str:
    """
    Run the tool-use loop until Johnny reaches end_turn.
    Opus is used for briefings; Sonnet for freeform chat (80% cheaper).
    """
    model = "claude-opus-4-6" if use_opus else "claude-sonnet-4-6"
    response: anthropic.types.Message | None = None

    for _ in range(MAX_ITERATIONS):
        response = _client.messages.create(
            model=model,
            max_tokens=8096,
            thinking={"type": "adaptive"},
            system=_build_system_prompt(),
            tools=_TOOLS,
            messages=messages,
        )
        _log_usage(response)

        if response.stop_reason == "end_turn":
            return _extract_text(response)

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_blocks = [b for b in response.content if b.type == "tool_use"]

            def _call(block):
                try:
                    handler = _HANDLERS.get(block.name)
                    result = handler(block.input) if handler else f"Unknown tool: {block.name}"
                except Exception as e:
                    result = f"Tool error: {e}"
                return {"type": "tool_result", "tool_use_id": block.id, "content": str(result)}

            try:
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = {executor.submit(_call, block): block for block in tool_blocks}
                    tool_results = []
                    for fut in concurrent.futures.as_completed(futures, timeout=90):
                        tool_results.append(fut.result())
            except concurrent.futures.TimeoutError:
                return "Tool call timed out after 90 seconds. Please try again."

            messages.append({"role": "user", "content": tool_results})
            continue

        break  # unexpected stop reason

    return _extract_text(response) if response else "No response."


def _extract_text(response: anthropic.types.Message) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text")
