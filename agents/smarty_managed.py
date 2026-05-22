"""
Smarty — Managed Agent (Deep Researcher)
Uses Anthropic's Managed Agents API for deep, multi-step web research.

━━━ ONE-TIME SETUP ━━━
Run this once to create the agent + environment and save their IDs to .env:

    python -m agents.smarty_managed --setup

Then restart Johnny. After that, calling research() uses the managed agent.

━━━ USAGE ━━━
    from agents.smarty_managed import research
    result = research("What are the latest central bank decisions this week?")

━━━ FALLBACK ━━━
If setup hasn't been run, research() falls back to a plain Claude Sonnet
web search loop (same as intel.py's _claude_search).
"""

import os
import sys
import anthropic
from config import ANTHROPIC_API_KEY

# ── Personal context ──────────────────────────────────────────────────────────
_SYSTEM = """\
You are Smarty — a personal research agent for a specific person:
• Runs a construction business (documentation, compliance, coordination, procurement)
• Trades forex in the evenings (macro data, central bank policy, market-moving events)
• Hybrid athlete: training for half marathon + HYROX (running + functional fitness)
• Building AI agents for personal productivity
• Tracking AI and automation as an investment thesis

When given a research question or topic:
1. Break it into 3–5 concrete sub-questions
2. Search for answers using web search and web fetch
3. Synthesise findings into a clear, concise brief
4. Apply personal context — explain what this means for their construction biz,
   forex trading, training, or AI interests. Never generic.
5. Cite sources (URL or publication name)
6. Sign off as "— Smarty"

Rules:
• Use headers and bullets for scannability
• Be specific: names, numbers, dates
• Skip opinion pieces and recycled news
• Keep the brief under 600 words unless depth is explicitly requested\
"""

# ── .env key names (auto-populated after --setup) ─────────────────────────────
_AGENT_ID_KEY  = "SMARTY_AGENT_ID"
_AGENT_VER_KEY = "SMARTY_AGENT_VERSION"
_ENV_ID_KEY    = "SMARTY_ENV_ID"


# ── Setup (run once from CLI) ─────────────────────────────────────────────────

def setup() -> tuple[str, int, str]:
    """
    Create the Smarty managed agent + environment on Anthropic's servers.
    Appends IDs to .env so they persist across restarts.
    Only needs to run once.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print("[Smarty] Creating managed agent...")
    agent = client.beta.agents.create(
        name="Smarty — Deep Researcher",
        description="Multi-step web research with personal context applied.",
        model="claude-sonnet-4-6",
        system=_SYSTEM,
        tools=[{"type": "agent_toolset_20260401"}],
    )
    agent_id  = agent.id
    agent_ver = agent.version
    print(f"[Smarty] ✓ Agent created: {agent_id}  (version {agent_ver})")

    print("[Smarty] Creating environment...")
    env = client.beta.environments.create(name="smarty-research-env")
    env_id = env.id
    print(f"[Smarty] ✓ Environment created: {env_id}")

    _save_to_env(agent_id, agent_ver, env_id)

    # Also set in current process so research() works immediately
    os.environ[_AGENT_ID_KEY]  = agent_id
    os.environ[_AGENT_VER_KEY] = str(agent_ver)
    os.environ[_ENV_ID_KEY]    = env_id

    return agent_id, agent_ver, env_id


def _save_to_env(agent_id: str, agent_ver: int, env_id: str) -> None:
    """Append SMARTY_* keys to the .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    with open(env_path, "a") as f:
        f.write(f"\n# ── Smarty managed agent (auto-generated — do not edit manually) ──\n")
        f.write(f"{_AGENT_ID_KEY}={agent_id}\n")
        f.write(f"{_AGENT_VER_KEY}={agent_ver}\n")
        f.write(f"{_ENV_ID_KEY}={env_id}\n")
    print(f"[Smarty] ✓ IDs appended to .env — restart Johnny to activate")


# ── Runtime: per-query research ───────────────────────────────────────────────

def _get_ids() -> tuple[str, int, str] | None:
    """Read agent + environment IDs from env. Returns None if not set up yet."""
    agent_id  = os.getenv(_AGENT_ID_KEY)
    agent_ver = os.getenv(_AGENT_VER_KEY)
    env_id    = os.getenv(_ENV_ID_KEY)
    if not all([agent_id, agent_ver, env_id]):
        return None
    return agent_id, int(agent_ver), env_id


def research(query: str) -> str:
    """
    Run a deep research query via the Smarty managed agent.

    Creates a fresh session per query (sessions are single-use).
    Falls back to a plain Claude web search loop if the managed agent
    hasn't been set up yet.
    """
    ids = _get_ids()
    if not ids:
        print("[Smarty] Managed agent not set up — run `python -m agents.smarty_managed --setup` once.")
        print("[Smarty] Falling back to plain Claude web search...")
        return _fallback_research(query)

    agent_id, agent_ver, env_id = ids
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        # Each query = a new session (sessions are not reusable)
        session = client.beta.sessions.create(
            environment_id=env_id,
            agent={"type": "agent", "id": agent_id, "version": agent_ver},
        )

        result_parts: list[str] = []

        # Open the stream first (so no events are missed), then send the message
        with client.beta.sessions.events.stream(session.id) as stream:
            client.beta.sessions.events.send(
                session.id,
                events=[{
                    "type": "user.message",
                    "content": [{"type": "text", "text": query}],
                }],
            )
            for event in stream:
                if event.type == "agent.message":
                    for block in event.content:
                        if block.type == "text":
                            result_parts.append(block.text)
                elif event.type == "session.status_terminated":
                    break
                elif event.type == "session.status_idle":
                    # "requires_action" = custom tool needs client response
                    # agent_toolset_20260401 is server-side so we won't hit this,
                    # but handle it defensively
                    stop_type = getattr(getattr(event, "stop_reason", None), "type", None)
                    if stop_type != "requires_action":
                        break

        return "".join(result_parts) or "No research output returned by Smarty."

    except Exception as e:
        print(f"[Smarty] Managed agent error ({e}), falling back...")
        return _fallback_research(query)


# ── Fallback: plain Claude Sonnet + web search ────────────────────────────────

def _fallback_research(query: str) -> str:
    """
    Manual 8-turn Claude Sonnet loop with web_search + web_fetch.
    Used when the managed agent isn't set up or fails.
    Mirrors the pattern in agents/intel.py _claude_search().
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    _SEARCH_TOOLS = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209",  "name": "web_fetch"},
    ]

    messages = [{"role": "user", "content": query}]
    response = None

    for _ in range(8):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_SYSTEM,
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
        return "Research unavailable."
    return "\n".join(b.text for b in response.content if b.type == "text")


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup()
        print("\n[Smarty] Setup complete. Restart Johnny to activate the managed agent.")
    else:
        # Quick test: python -m agents.smarty_managed "what is happening in AI this week?"
        q = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
        if not q:
            q = "What are the most important AI and construction industry developments this week?"
        print(research(q))
