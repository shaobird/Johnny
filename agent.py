"""
General-purpose AI assistant with web search, web fetch, and custom tools.

Usage:
    export ANTHROPIC_API_KEY=your_key_here
    python agent.py

Commands during chat:
    clear   — reset conversation history
    quit    — exit
"""

import os
import anthropic
from dotenv import load_dotenv
from tools import CUSTOM_TOOL_SCHEMAS, execute_tool

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Server-side tools run automatically on Anthropic's infrastructure.
# The _20260209 versions include dynamic filtering for better accuracy.
SERVER_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]

ALL_TOOLS = SERVER_TOOLS + CUSTOM_TOOL_SCHEMAS

SYSTEM_PROMPT = """\
You are a helpful general-purpose AI assistant. Your capabilities include:
- Answering questions and holding conversations
- Searching the web for current information
- Fetching and analysing content from specific URLs
- Performing calculations and getting the current date/time
- Saving and reading notes locally

Use web search whenever the user asks about recent events, news, or information
that might have changed since your training. Be concise but thorough.\
"""

MAX_AGENTIC_ITERATIONS = 15  # safety cap on tool-use loops


def run_turn(messages: list) -> anthropic.types.Message:
    """
    Run one user turn through the agentic loop until the model finishes.

    Handles:
    - Custom tool calls (tool_use stop reason) — executed client-side
    - Server-side tool continuations (pause_turn stop reason) — re-sent automatically
    - Normal completion (end_turn stop reason)

    Mutates `messages` in-place with assistant and tool-result turns.
    Returns the final Message object.
    """
    for _ in range(MAX_AGENTIC_ITERATIONS):
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            tools=ALL_TOOLS,
            messages=messages,
        )

        # Server-side tools (web search/fetch) hit their iteration limit.
        # Append the assistant turn and re-send — the server resumes automatically.
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue

        # Model is done — no more tool calls needed.
        if response.stop_reason == "end_turn":
            messages.append({"role": "assistant", "content": response.content})
            return response

        # The model wants to call one or more custom tools.
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [tool: {block.name}]", flush=True)
                    result = execute_tool(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason — return whatever we have.
        messages.append({"role": "assistant", "content": response.content})
        return response

    # Reached the iteration cap — return the last response.
    return response


def extract_text(response: anthropic.types.Message) -> str:
    """Return all text blocks from a response, joined by newlines."""
    return "\n".join(
        block.text for block in response.content if block.type == "text"
    )


def main() -> None:
    messages: list = []

    print("=" * 52)
    print("  AI Assistant  (web search + custom tools)")
    print("  Commands: 'clear' to reset, 'quit' to exit")
    print("=" * 52)
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        if user_input.lower() == "clear":
            messages = []
            print("[Conversation cleared]\n")
            continue

        messages.append({"role": "user", "content": user_input})

        print("\nAssistant:", flush=True)
        response = run_turn(messages)
        reply = extract_text(response)
        print(reply)
        print()


if __name__ == "__main__":
    main()
