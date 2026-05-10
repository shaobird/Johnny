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
)
from agents.mo import search as mo_search, get_context as mo_context, list_files as mo_list, get_file_content as mo_get
from agents.peter import log_expense, log_invoice, get_finance_summary, get_job_summary
from agents.kanaan import (
    log_tech_decision, log_tech_task, complete_task as complete_tech_task, get_dev_status,
)
import memory as mem
from config import ANTHROPIC_API_KEY, GEMINI_API_KEY

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
    "newsletter", "brief",
    "analyse this", "analyze this",
    "expense", "invoice", "finance", "budget", "cost", "job summary",
    "tech", "build", "stack", "tool", "backlog", "software", "automation",
    "consult", "team brief", "ask the team",
    "file", "storage", "document", "upload",
)


def _needs_anthropic(message: str) -> bool:
    msg = message.lower()
    return any(kw in msg for kw in _TOOL_KEYWORDS)


# ── System prompt (rebuilt fresh each call so memory is always current) ───────

def _build_system_prompt() -> str:
    user_context = mem.get_context()
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
{user_context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ YOUR SPECIALIST AGENTS ━━━
• Smarty  — Chief of Research: calendar, forex news, daily intel briefing (AI/construction/macro/HYROX)
• Val     — Chief of Fitness: Strava + Hevy, training analysis, lactate zones, HYROX/half marathon progress
• Sally   — Chief of Market Communications: newsletter performance, topic memory, research briefs
• Mo      — Chief Warehouse Manager: stores and retrieves all files, provides context to other agents
• Peter   — Chief Finance & Investment Officer: forex trading strategy, investment thesis, capital allocation.
            Channel Peter when the user asks about where to deploy capital, investment opportunities, or market positioning.
• Kanaan  — Chief of Technology & Development: software architecture, AI/automation choices, Johnny's own
            development roadmap, tech stack decisions for the construction business. Channel Kanaan when the
            user asks "should I build/buy X", "which tool", or anything technical.

CROSS-AGENT COLLABORATION:
When a question spans multiple domains, use the consult_team tool to pull all relevant agents simultaneously.
Examples:
  • "Should I buy this equipment?" → consult peter (financing) + kanaan (tech fit) + mo (any stored specs)
  • "What's my position across work and markets?" → consult peter + smarty + calendar
  • "Plan my week" → consult val (training load) + calendar + smarty (key events)
Always synthesise the team's inputs into one clear recommendation rather than just listing what each said.
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

Step 1 — GATHER: Call all relevant agents before forming any opinion.
Step 2 — SYNTHESISE: Look for connections across the three domains:
  • Does a high-impact forex release overlap with a calendar meeting? Flag it.
  • Are there forex events for the pairs the user watches? Highlight those first.
  • Has the user been overtraining (consecutive hard sessions, no rest)? Warn them.
  • Is today's calendar light — a good opportunity to train?
  • Is the user behind on their weekly fitness goals based on their targets?
  • Are there patterns worth noting (always skips Mondays, pace improving, etc.)?
Step 3 — PRIORITISE: Lead with the 2–3 things that matter MOST today.
Step 4 — ADVISE: End with one clear action recommendation.
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
        "peter":  lambda: get_finance_summary(),
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
        "peter": "PETER (Finance & Investment)",
        "val": "VAL (Fitness)",
        "smarty": "SMARTY (Research & Markets)",
        "sally": "SALLY (Market Communications)",
        "mo": "MO (Warehouse — relevant docs)",
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
    {
        "name": "log_expense",
        "description": "Peter logs an expense for the construction business.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount":      {"type": "number",  "description": "Amount spent."},
                "category":    {"type": "string",  "description": "materials/labour/overhead/equipment/other"},
                "description": {"type": "string",  "description": "What was spent on."},
                "job":         {"type": "string",  "description": "Job or project name (optional)."},
                "currency":    {"type": "string",  "description": "Currency code, default SGD."},
            },
            "required": ["amount", "category", "description"],
        },
    },
    {
        "name": "log_invoice",
        "description": "Peter logs an invoice issued to a client.",
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
        "name": "get_finance_summary",
        "description": "Peter summarises income vs expenses over the last N days.",
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
        "description": "Peter summarises all costs and invoices for a specific job.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job": {"type": "string", "description": "Job or project name."},
            },
            "required": ["job"],
        },
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
    # ── Cross-agent collaboration ──────────────────────────────────────────────
    {
        "name": "consult_team",
        "description": (
            "Fan out to multiple specialist agents simultaneously and get their perspectives on a topic. "
            "Use when a question spans multiple domains — e.g. finance + tech, fitness + schedule, "
            "market intel + construction. Each agent runs in parallel. You then synthesise the results. "
            "Available agents: peter (finance/investment), val (fitness), smarty (forex/news/intel), "
            "sally (newsletter/market comms), mo (stored docs on topic), kanaan (tech/dev)."
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
    "ask_mo":                    lambda inp: mo_context(inp["topic"]),
    "mo_search":                 lambda inp: mo_search(inp["query"], inp.get("category", "")),
    "mo_list":                   lambda inp: mo_list(inp.get("category", "")),
    "mo_get_file":               lambda inp: mo_get(inp["filename"]),
    "log_expense":               lambda inp: log_expense(inp["amount"], inp["category"], inp["description"], inp.get("job", ""), inp.get("currency", "SGD")),
    "log_invoice":               lambda inp: log_invoice(inp["amount"], inp["client"], inp["description"], inp.get("job", ""), inp.get("status", "pending"), inp.get("currency", "SGD")),
    "get_finance_summary":       lambda inp: get_finance_summary(inp.get("days", 30)),
    "get_job_summary":           lambda inp: get_job_summary(inp["job"]),
    "log_tech_decision":         lambda inp: log_tech_decision(inp["decision"], inp["rationale"], inp.get("status", "decided")),
    "log_tech_task":             lambda inp: log_tech_task(inp["task"], inp.get("priority", "medium"), inp.get("notes", "")),
    "complete_tech_task":        lambda inp: complete_tech_task(inp["task"]),
    "get_dev_status":            lambda _:   get_dev_status(),
    "consult_team":              lambda inp: _consult_team(inp["topic"], inp["agents"]),
}


# ── Public API ────────────────────────────────────────────────────────────────

def chat(message: str, history: list[dict] | None = None, use_opus: bool = False) -> str:
    """
    Send a message to Johnny and return his reply.

    Routing:
      - use_opus=True  → Anthropic Opus (briefings, complex synthesis)
      - tool keywords  → Anthropic Sonnet (with all agent tools available)
      - simple chat    → Gemini 2.5 Pro (free tier, no tools)

    Pass the prior conversation turns as `history` to maintain context.
    """
    if not use_opus and GEMINI_API_KEY and not _needs_anthropic(message):
        try:
            return _chat_gemini(message, history or [])
        except Exception as e:
            print(f"[Chat] Gemini failed ({e}), falling back to Anthropic Sonnet...")

    messages = list(history or []) + [{"role": "user", "content": message}]
    return _run_loop(messages, use_opus=use_opus)


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

            with concurrent.futures.ThreadPoolExecutor() as executor:
                tool_results = list(executor.map(_call, tool_blocks))

            messages.append({"role": "user", "content": tool_results})
            continue

        break  # unexpected stop reason

    return _extract_text(response) if response else "No response."


def _extract_text(response: anthropic.types.Message) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text")
