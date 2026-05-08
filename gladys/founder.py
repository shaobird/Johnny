"""
Gladys's founder agent.

The founder is the only agent Gladys talks to. Its job:
  1. Build a relationship — get to know Gladys, learn how she works, capture
     her preferences into profile.json and the vector store.
  2. Delegate — when a task fits a sub-agent (clients, policies, follow-ups,
     email drafts, files), call it via tools.
  3. Review — every sub-agent output is checked before reaching Gladys.
     Drafts get critiqued and tightened. Data lookups get sanity-checked.
     If something looks off, the founder calls the sub-agent again or asks
     Gladys for clarification.
  4. Remember — patterns, preferences, and decisions get saved to memory so
     the next conversation starts smarter.
"""

from __future__ import annotations

import concurrent.futures
import json

import anthropic

from .config import ANTHROPIC_API_KEY, FOUNDER_MODEL
from . import memory as mem
from .agents import clients as clients_agent
from .agents import policies as policies_agent
from .agents import followups as followups_agent
from .agents import email_drafter
from .agents import files as files_agent

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MAX_ITERATIONS = 15


def _build_system_prompt() -> str:
    profile = mem.get_context()
    return f"""\
You are Gladys's Founder Agent — her personal AI chief of staff. Gladys is an
insurance agent. You exist to make her work easier, sharper, and more
consistent. You are the ONLY agent she talks to. Behind you are specialist
sub-agents you delegate to.

━━━ HOW YOU SPEAK TO GLADYS ━━━
• Warm but efficient. She's busy. Get to the point.
• First-person. Address her as Gladys (or whatever name she sets).
• Ask one good question rather than three mediocre ones.
• Never invent client names, policy details, or numbers. If you don't have
  it in memory or a tool, say so and ask.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ WHAT YOU KNOW ABOUT GLADYS ━━━
{profile}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ ONBOARDING MODE ━━━
If the profile is mostly empty, your priority is to learn:
  • Her full name, company, the products she sells.
  • Her target client (segment, age, life stage).
  • Her tone in client emails — formal, warm, casual?
  • Her work rhythm — when she prospects, when she follows up.
  • Hard rules — anything she NEVER does or always does.
Capture each answer immediately via update_profile, add_rule, or remember.
Do not interrogate. Weave the questions into normal conversation.
━━━━━━━━━━━━━━━━━━━━━━━━

━━━ YOUR SUB-AGENTS ━━━
• clients_*    — CRM: add/find clients, log interactions
• policies_*   — Policy library: store and look up products
• followups_*  — Track who needs a follow-up and when
• draft_email  — Drafts emails in Gladys's voice (LLM-driven)
• files_*      — Read/write files in Gladys's workspace
• remember / recall — Long-term semantic memory
━━━━━━━━━━━━━━━━━━━━━━━━

━━━ REVIEW EVERY SUB-AGENT OUTPUT ━━━
Sub-agents are not infallible. Before you show ANY sub-agent output to
Gladys you must:
  1. Sanity-check it against what you know (profile, memory, conversation).
  2. For drafts (emails, scripts): check tone matches her voice, no
     hallucinated facts, no boilerplate fluff. If it's off, call the
     sub-agent again with sharper instructions OR refine it yourself.
  3. For data lookups: confirm the result actually answers her question.
     If a search returns nothing useful, say so plainly — don't pad.
  4. Only present a result once you'd stake your reputation on it.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ MEMORY DISCIPLINE ━━━
Use update_profile for stable structured facts (her company, products, work
style). Use add_rule for hard "always/never" rules. Use remember for
context-rich notes that may matter later (a client preference, a phrase she
liked, a decision she made). Do this proactively — don't ask permission for
small notes.
━━━━━━━━━━━━━━━━━━━━━━

━━━ FORMATTING ━━━
Plain text. Bold with *asterisks* (Telegram bold). Emoji headers only when
presenting structured results (📋 Clients, 📑 Policies, 📅 Follow-ups).
Otherwise just talk to her like a colleague.
"""


# ── Tools ─────────────────────────────────────────────────────────────────────

_TOOLS = [
    {
        "name": "update_profile",
        "description": "Set a structured fact in Gladys's profile (e.g. company, products_sold). Path is a list of nested keys.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "array", "items": {"type": "string"}},
                "value": {"description": "Any JSON value"},
            },
            "required": ["path", "value"],
        },
    },
    {
        "name": "add_rule",
        "description": "Add a hard rule Gladys wants the founder to always honour.",
        "input_schema": {
            "type": "object",
            "properties": {"rule": {"type": "string"}},
            "required": ["rule"],
        },
    },
    {
        "name": "remember",
        "description": "Save a free-form note to long-term memory (vector store). Use for preferences, decisions, context worth recalling later.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "kind": {"type": "string", "description": "Category tag, e.g. 'preference', 'decision', 'voice', 'client', 'policy'."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "recall",
        "description": "Semantic search over past memories. Use before answering anything that might be in memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "kind": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "clients_add",
        "description": "Add a client to the CRM.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "phone": {"type": "string"},
                "email": {"type": "string"},
                "segment": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "clients_log_interaction",
        "description": "Append an interaction summary to a client (lookup by name or id).",
        "input_schema": {
            "type": "object",
            "properties": {
                "client": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["client", "summary"],
        },
    },
    {
        "name": "clients_find",
        "description": "Look up a client by name or id.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "clients_list",
        "description": "List all clients on file.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "policies_add",
        "description": "Save an insurance policy / product to the library.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "provider": {"type": "string"},
                "category": {"type": "string", "description": "e.g. life, health, ILP, savings, term, motor"},
                "summary": {"type": "string"},
                "details": {"type": "object"},
            },
            "required": ["name", "provider", "category", "summary"],
        },
    },
    {
        "name": "policies_find",
        "description": "Search the policy library by name, provider, category, or summary keyword.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "policies_list",
        "description": "List policies, optionally filtered by category.",
        "input_schema": {
            "type": "object",
            "properties": {"category": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "policies_compare",
        "description": "Return full records for two or more policies side-by-side.",
        "input_schema": {
            "type": "object",
            "properties": {"ids_or_names": {"type": "array", "items": {"type": "string"}}},
            "required": ["ids_or_names"],
        },
    },
    {
        "name": "followups_add",
        "description": "Schedule a follow-up. Date is YYYY-MM-DD.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client": {"type": "string"},
                "due": {"type": "string"},
                "reason": {"type": "string"},
                "channel": {"type": "string", "description": "call, whatsapp, email, in-person"},
            },
            "required": ["client", "due", "reason"],
        },
    },
    {
        "name": "followups_complete",
        "description": "Mark a follow-up done with the outcome.",
        "input_schema": {
            "type": "object",
            "properties": {
                "followup_id": {"type": "string"},
                "outcome": {"type": "string"},
            },
            "required": ["followup_id", "outcome"],
        },
    },
    {
        "name": "followups_due_today",
        "description": "List follow-ups due today (or earlier and still open).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "followups_list_open",
        "description": "List all open follow-ups, sorted by due date.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "draft_email",
        "description": "Have the email-drafting sub-agent produce a draft. You MUST review the draft before showing it to Gladys.",
        "input_schema": {
            "type": "object",
            "properties": {
                "recipient": {"type": "string"},
                "goal": {"type": "string"},
                "context": {"type": "string"},
            },
            "required": ["recipient", "goal"],
        },
    },
    {
        "name": "files_list",
        "description": "List files in Gladys's workspace (optionally inside a subdir).",
        "input_schema": {
            "type": "object",
            "properties": {"subdir": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "files_read",
        "description": "Read a workspace file (UTF-8 text).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "files_write",
        "description": "Write (overwrite) a workspace file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "files_append",
        "description": "Append text to a workspace file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "files_search",
        "description": "Substring search across workspace files.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def _call_tool(name: str, args: dict) -> str:
    if name == "update_profile":
        return mem.update_profile(args["path"], args["value"])
    if name == "add_rule":
        return mem.add_rule(args["rule"])
    if name == "remember":
        return mem.remember(args["text"], kind=args.get("kind", "note"))
    if name == "recall":
        return mem.recall_text(args["query"], limit=args.get("limit", 5), kind=args.get("kind"))

    if name == "clients_add":
        name_ = args.pop("name")
        return clients_agent.add_client(name_, **args)
    if name == "clients_log_interaction":
        return clients_agent.log_interaction(args["client"], args["summary"])
    if name == "clients_find":
        return clients_agent.find_client(args["query"])
    if name == "clients_list":
        return clients_agent.list_clients()

    if name == "policies_add":
        return policies_agent.add_policy(
            args["name"], args["provider"], args["category"],
            args["summary"], args.get("details"),
        )
    if name == "policies_find":
        return policies_agent.find_policy(args["query"])
    if name == "policies_list":
        return policies_agent.list_policies(args.get("category"))
    if name == "policies_compare":
        return policies_agent.compare_policies(args["ids_or_names"])

    if name == "followups_add":
        return followups_agent.add_followup(
            args["client"], args["due"], args["reason"],
            args.get("channel", "call"),
        )
    if name == "followups_complete":
        return followups_agent.complete_followup(args["followup_id"], args["outcome"])
    if name == "followups_due_today":
        return followups_agent.due_today()
    if name == "followups_list_open":
        return followups_agent.list_open()

    if name == "draft_email":
        return email_drafter.draft_email(
            args["recipient"], args["goal"], args.get("context", ""),
        )

    if name == "files_list":
        return files_agent.list_files(args.get("subdir", ""))
    if name == "files_read":
        return files_agent.read_file(args["path"])
    if name == "files_write":
        return files_agent.write_file(args["path"], args["content"])
    if name == "files_append":
        return files_agent.append_file(args["path"], args["content"])
    if name == "files_search":
        return files_agent.search_files(args["query"])

    return f"Unknown tool: {name}"


# ── Public API ────────────────────────────────────────────────────────────────

def chat(message: str, history: list[dict] | None = None) -> str:
    messages = list(history or []) + [{"role": "user", "content": message}]
    return _run_loop(messages)


def _run_loop(messages: list[dict]) -> str:
    response: anthropic.types.Message | None = None
    for _ in range(MAX_ITERATIONS):
        response = _client.messages.create(
            model=FOUNDER_MODEL,
            max_tokens=4096,
            system=_build_system_prompt(),
            tools=_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            return _extract_text(response)

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_blocks = [b for b in response.content if b.type == "tool_use"]

            def _run(block):
                try:
                    result = _call_tool(block.name, dict(block.input))
                except Exception as e:
                    result = f"Tool error: {e}"
                return {"type": "tool_result", "tool_use_id": block.id,
                        "content": str(result)}

            with concurrent.futures.ThreadPoolExecutor() as ex:
                tool_results = list(ex.map(_run, tool_blocks))
            messages.append({"role": "user", "content": tool_results})
            continue

        break

    return _extract_text(response) if response else "(no response)"


def _extract_text(response: anthropic.types.Message) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text")
