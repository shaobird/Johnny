"""
Capture CLI — save AI sessions from Gemini, ChatGPT, or any AI to Mo's memory.

Usage:
  python capture_cli.py                    # interactive mode (paste Q + A)
  python capture_cli.py --stats            # show session stats
  python capture_cli.py --recent 10        # show last 10 sessions
  python capture_cli.py --search "forex"   # search sessions

When you finish a research session in Gemini, ChatGPT, or Perplexity:
  1. Copy the question you asked
  2. Copy the AI's response
  3. Run this script and paste both in

Everything gets saved to Mo's unified AI session store.
"""

import argparse
import os
import sys

JOHNNY_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, JOHNNY_ROOT)
os.chdir(JOHNNY_ROOT)

from agents.ai_sessions import (
    capture_session,
    search_sessions,
    get_recent_sessions,
    get_session_stats,
)

SOURCES = ["claude", "gemini", "chatgpt", "perplexity", "grok", "manus", "other"]


def _pick_source() -> str:
    print("\nWhich AI? (default: gemini)")
    for i, s in enumerate(SOURCES, 1):
        print(f"  {i}. {s}")
    choice = input("Enter number or name [2]: ").strip() or "2"
    if choice.isdigit():
        idx = int(choice) - 1
        return SOURCES[idx] if 0 <= idx < len(SOURCES) else "other"
    return choice.lower() if choice.lower() in SOURCES else "other"


def _multiline_input(prompt: str) -> str:
    """Read multiline input until the user types END on a blank line."""
    print(prompt)
    print("  (paste text, then type END on a new line and press Enter)")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def interactive_capture() -> None:
    print("━━━ Mo's AI Session Capture ━━━")
    source = _pick_source()
    print(f"\nSource: {source.upper()}")

    query    = _multiline_input("\nPaste your QUESTION / search query:")
    response = _multiline_input("\nPaste the AI's RESPONSE:")

    topic_in = input("\nTopic (leave blank to auto-detect): ").strip()
    tags_in  = input("Tags (comma-separated, leave blank for none): ").strip()
    tags     = [t.strip() for t in tags_in.split(",") if t.strip()]

    if not query or not response:
        print("No query or response — nothing saved.")
        return

    result = capture_session(
        query=query,
        response=response,
        source_ai=source,
        tags=tags,
        topic=topic_in,
    )
    print(f"\n✅ {result}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture AI sessions into Mo's memory")
    parser.add_argument("--stats",          action="store_true",  help="Show session stats")
    parser.add_argument("--recent",         type=int, metavar="N", help="Show last N sessions")
    parser.add_argument("--search",         type=str, metavar="QUERY", help="Search sessions")
    parser.add_argument("--source",         type=str, default="",  help="Filter by AI source")
    args = parser.parse_args()

    if args.stats:
        print(get_session_stats())
    elif args.recent:
        print(get_recent_sessions(args.recent, args.source))
    elif args.search:
        print(search_sessions(args.search, args.source))
    else:
        interactive_capture()


if __name__ == "__main__":
    main()
