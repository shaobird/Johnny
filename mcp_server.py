"""
Johnny-Mo MCP Server — centralised knowledge store for all AI systems.

Mo manages storage (files, documents, research).
Mnemon manages memory (patterns, decisions, insights).
AI Sessions captures Q&A from any AI tool (Claude, Gemini, ChatGPT, etc.).

━━━ TRANSPORTS ━━━
  stdio  (default) — Claude Desktop, Cursor, Cline, any stdio MCP client
  http   (SSE)     — set MCP_TRANSPORT=http, port via MCP_PORT (default 8765)

━━━ CLAUDE DESKTOP SETUP ━━━
Add to ~/.config/Claude/claude_desktop_config.json  (Mac: ~/Library/Application Support/Claude/)

  {
    "mcpServers": {
      "johnny-mo": {
        "command": "python",
        "args": ["/path/to/Johnny/mcp_server.py"],
        "env": {
          "PYTHONPATH": "/path/to/Johnny"
        }
      }
    }
  }

━━━ HTTP / GEMINI INTEGRATION ━━━
Run:  MCP_TRANSPORT=http python mcp_server.py
Then POST to http://127.0.0.1:8765/sse  (MCP SSE endpoint)
Or use the capture CLI:  python capture_cli.py

━━━ TOOLS EXPOSED ━━━
  store_document        — save text/research to Mo's warehouse
  search_knowledge      — search files + AI session history
  get_context           — Mo + Mnemon combined context for a topic
  list_documents        — list Mo's warehouse by category
  get_document          — retrieve a stored file's full content
  capture_ai_session    — save a Q&A from any AI
  search_ai_sessions    — search past AI sessions
  get_recent_sessions   — latest sessions across all AI sources
  log_memory            — save pattern/insight/decision to Mnemon
  get_memory            — retrieve Mnemon learnings for a topic

━━━ RESOURCES ━━━
  memory://context   — Mnemon's top patterns and insights
  files://index      — Mo's full warehouse index
  sessions://recent  — Last 20 AI sessions
"""

import os
import sys

# Ensure Johnny root is always in the Python path regardless of cwd
JOHNNY_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, JOHNNY_ROOT)
os.chdir(JOHNNY_ROOT)  # Storage paths are relative to Johnny root

from mcp.server.fastmcp import FastMCP

from agents.mo import search, get_context as mo_get_context, list_files, get_file_content
from agents.mnemon import (
    log_pattern,
    log_insight,
    log_decision,
    get_context as mnemon_context,
    get_all_patterns,
    get_decisions,
)
from agents.ai_sessions import (
    capture_session,
    store_text_document,
    search_sessions,
    get_recent_sessions,
    get_session_stats,
)
from agents.thoughts import (
    capture_thought as capture_thought_fn,
    search_thoughts,
    list_recent_thoughts as list_recent_thoughts_fn,
    thought_stats as thought_stats_fn,
    semantic_search_thoughts as semantic_search_thoughts_fn,
)

mcp = FastMCP(
    "Johnny-Mo",
    instructions=(
        "Mo is Johnny Zhang's central knowledge warehouse for his Singapore construction business, "
        "forex trading, and HYROX training. "
        "ALWAYS call get_context before answering questions about his business, finances, trades, or fitness. "
        "ALWAYS call capture_ai_session at the end of any significant research conversation to save it. "
        "Use store_document to permanently save useful findings, reports, or analysis."
    ),
)


# ── Document Storage ───────────────────────────────────────────────────────────

@mcp.tool()
def store_document(
    title: str,
    content: str,
    category: str = "research",
    tags: list[str] | None = None,
    source_ai: str = "claude",
) -> str:
    """
    Save any document, note, or research to Mo's warehouse.

    categories: construction | finance | newsletters | research | personal | other
    source_ai:  claude | gemini | chatgpt | perplexity | grok | manus | other

    Use for: web research results, meeting notes, site reports, supplier quotes,
    contract summaries, market analysis — anything worth keeping long-term.
    """
    return store_text_document(
        title=title,
        content=content,
        category=category,
        tags=tags or [],
        source_ai=source_ai,
    )


@mcp.tool()
def search_knowledge(query: str, category: str = "") -> str:
    """
    Search across ALL stored knowledge — Mo's warehouse AND AI session history.

    Searches simultaneously:
    • Mo's indexed documents (files, reports, research)
    • AI session history (past Claude, Gemini, ChatGPT conversations)

    Optionally filter by category: construction | finance | research | personal
    """
    mo_results       = search(query, category)
    session_results  = search_sessions(query)
    thought_results  = search_thoughts(query, category if category in {
        "people", "projects", "preferences", "decisions",
        "topics", "professional", "personal", "general"
    } else "")

    parts = []
    if "nothing matching" not in mo_results.lower() and "warehouse is empty" not in mo_results.lower():
        parts.append(mo_results)
    if "no thoughts" not in thought_results.lower():
        parts.append(f"\n── Open Brain Thoughts ──\n{thought_results}")
    if "no ai sessions" not in session_results.lower() and "no sessions" not in session_results.lower():
        parts.append(f"\n── AI Session History ──\n{session_results}")

    return "\n".join(parts) if parts else f"Nothing found for \"{query}\" across all storage."


@mcp.tool()
def get_context(topic: str) -> str:
    """
    Get all relevant context for a topic — files, memories, and AI session history.

    Returns Mo's best matching documents + Mnemon's patterns/decisions/insights
    on the same topic. Call this BEFORE answering any question about Johnny's
    business, trading, fitness, or personal context.
    """
    return mo_get_context(topic)


@mcp.tool()
def list_documents(category: str = "") -> str:
    """
    List all documents stored in Mo's warehouse.
    Filter by category: construction | finance | newsletters | research | personal
    Leave empty to list everything.
    """
    return list_files(category)


@mcp.tool()
def get_document(filename: str) -> str:
    """
    Retrieve the full content of a stored document by filename.
    Use list_documents first to find the correct filename.
    """
    return get_file_content(filename)


# ── Open Brain: capture_thought (Memory Migration / Spark / Weekly Review) ───

@mcp.tool()
def capture_thought(
    thought: str,
    category: str = "general",
    tags: list[str] | None = None,
    source_ai: str = "claude",
) -> str:
    """
    Save a single self-contained thought to the Open Brain.

    category: people | projects | preferences | decisions | topics |
              professional | personal | general

    Each thought should be a standalone statement that makes sense
    when retrieved later by a different AI with zero prior context.

    Smart routing:
    • preferences → also logged as a Mnemon pattern
    • decisions   → also logged as a Mnemon decision
    """
    return capture_thought_fn(
        thought=thought,
        category=category,
        tags=tags or [],
        source_ai=source_ai,
    )


@mcp.tool()
def list_recent_thoughts(limit: int = 10, category: str = "") -> str:
    """
    Return the most recent thoughts captured to the Open Brain.
    limit:    number of thoughts to return (default 10)
    category: filter by category (optional)
    """
    return list_recent_thoughts_fn(limit, category)


@mcp.tool()
def thought_stats() -> str:
    """
    Summary of captured thoughts: total, per-category, recent activity, source AIs.
    """
    return thought_stats_fn()


@mcp.tool()
def semantic_search(
    query: str,
    top_k: int = 5,
    category: str = "",
) -> str:
    """
    Meaning-based search across the Open Brain — finds conceptually similar
    thoughts even when exact keywords don't match.

    Examples:
      • "cash reserves" → finds thoughts about "business extraction", "rainy day fund"
      • "workout felt heavy" → finds thoughts about "fatigue", "overtraining signs"

    top_k:    number of results to return (default 5, max 20)
    category: optional filter — people | projects | preferences | decisions |
              topics | professional | personal | general

    Falls back to keyword search if the local model hasn't been downloaded yet.
    """
    top_k = min(max(1, top_k), 20)
    return semantic_search_thoughts_fn(query, top_k=top_k, category=category)


# ── AI Session Capture ─────────────────────────────────────────────────────────

@mcp.tool()
def capture_ai_session(
    query: str,
    response: str,
    source_ai: str = "claude",
    tags: list[str] | None = None,
    topic: str = "",
) -> str:
    """
    Save a Q&A exchange from any AI to Johnny's unified memory.

    source_ai: claude | gemini | chatgpt | perplexity | grok | manus | other
    topic:     optional override — if blank, Mo infers it from the query
    tags:      optional list of keywords for future search

    Call this at the end of any research session so the findings are
    searchable later across all AI tools.
    """
    return capture_session(
        query=query,
        response=response,
        source_ai=source_ai,
        tags=tags or [],
        topic=topic,
    )


@mcp.tool()
def search_ai_sessions(query: str, source_ai: str = "") -> str:
    """
    Search past AI sessions by keyword across all sources.
    Optionally filter by source_ai: claude | gemini | chatgpt | perplexity | grok
    """
    return search_sessions(query, source_ai)


@mcp.tool()
def get_recent_ai_sessions(limit: int = 10, source_ai: str = "") -> str:
    """
    Get the most recent AI sessions.
    limit:     number of sessions to return (default 10, max 50)
    source_ai: filter by AI — claude | gemini | chatgpt | perplexity | grok | manus
    """
    limit = min(max(1, limit), 50)
    return get_recent_sessions(limit, source_ai)


@mcp.tool()
def ai_session_stats() -> str:
    """
    How many sessions are stored per AI source.
    Quick overview of which AI tools are being used most.
    """
    return get_session_stats()


# ── Memory (Mnemon) ────────────────────────────────────────────────────────────

@mcp.tool()
def log_memory(
    memory_type: str,
    category: str,
    content: str,
    relevance: str = "medium",
) -> str:
    """
    Save a learning to Mnemon's permanent memory.

    memory_type: pattern  — recurring behaviour ("skips leg day when tired")
                 insight  — one-line truth about business/market/user
                 decision — a choice made (add outcome later)

    category:    fitness | finance | trading | construction | work | general
    relevance:   high | medium | low  (for insights only)
    """
    if memory_type == "pattern":
        return log_pattern(category, content)
    elif memory_type == "decision":
        return log_decision(category, content)
    elif memory_type == "insight":
        return log_insight(category, content, relevance)
    else:
        return f"Unknown memory_type \"{memory_type}\". Use: pattern | insight | decision"


@mcp.tool()
def get_memory(topic: str = "") -> str:
    """
    Retrieve Mnemon's patterns, decisions, and insights for a topic.
    Leave topic empty to get top learnings across all categories.
    """
    result = mnemon_context(topic)
    return result if result else "No relevant memories found yet."


@mcp.tool()
def get_all_memory(category: str = "") -> str:
    """
    Get Mnemon's full pattern library and decision log.
    Optionally filter by category: fitness | finance | trading | construction | general
    """
    patterns  = get_all_patterns(category)
    decisions = get_decisions()
    return f"{patterns}\n\n{decisions}"


# ── Resources (read-only live views) ──────────────────────────────────────────

@mcp.resource("memory://context")
def memory_context_resource() -> str:
    """Live view: Mnemon's top patterns and high-relevance insights."""
    return mnemon_context("") or "No memories stored yet."


@mcp.resource("files://index")
def files_index_resource() -> str:
    """Live view: all documents in Mo's warehouse."""
    return list_files()


@mcp.resource("sessions://recent")
def recent_sessions_resource() -> str:
    """Live view: last 20 AI sessions across all sources."""
    return get_recent_sessions(20)


@mcp.resource("sessions://stats")
def session_stats_resource() -> str:
    """Live view: AI session counts by source."""
    return get_session_stats()


@mcp.resource("thoughts://recent")
def recent_thoughts_resource() -> str:
    """Live view: last 20 Open Brain thoughts across all categories."""
    return list_recent_thoughts_fn(20)


@mcp.resource("thoughts://stats")
def thought_stats_resource() -> str:
    """Live view: Open Brain stats by category and source AI."""
    return thought_stats_fn()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()

    if transport == "http":
        host = os.getenv("MCP_HOST", "127.0.0.1")
        port = int(os.getenv("MCP_PORT", "8765"))
        print(f"[Johnny-Mo MCP] SSE server starting on http://{host}:{port}", flush=True)
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
