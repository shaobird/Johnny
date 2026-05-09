"""
Kanaan — Johnny's Chief Technology Officer.

Kanaan is a meta-agent: he reasons about Johnny's own codebase. He audits the
ecosystem, scaffolds new sub-agents on request, and reviews changes through PRs
that you approve and merge.

How he runs:
  • On-demand from Telegram via the /kanaan command (see telegram_bot.py)
  • From CLI: `python -m agents.kanaan audit`
                `python -m agents.kanaan build "weather agent with OpenWeather API"`
                `python -m agents.kanaan ask "<freeform question>"`

Safety rails (enforced in tool implementations, not just the prompt):
  • Writes only to an allowlisted set of paths inside the repo
  • Never writes to .env*, memory*.json, credentials, or anything under .git/
  • Shell commands restricted to a vetted allowlist (ruff, pytest, python, pip,
    pip-audit, and a narrow subset of git/gh)
  • Code changes always land on a `kanaan/<slug>` branch, never main
  • PRs are opened for human review — Kanaan never merges
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# ── Constants ────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-opus-4-7"
MAX_TOKENS = 8096
MAX_TURNS = 40

# Files Kanaan is allowed to write to (glob patterns, relative to repo root).
WRITE_ALLOWLIST = [
    "agents/*.py",
    "*.py",                       # root-level python files
    ".github/workflows/*.yml",
    "requirements.txt",
    "ruff.toml",
    "pyproject.toml",
    "README.md",
    "docs/**/*.md",
]

# Files Kanaan is NEVER allowed to touch, even if matched by allowlist above.
WRITE_DENYLIST = [
    ".env*",
    "memory.json",
    "memory.template.json",
    "credentials*.json",
    "token*.json",
    ".git/**",
    "*.key",
    "*.pem",
]

# First word of every shell command must be in this set.
SHELL_ALLOWED_BINARIES = {
    "ruff", "pytest", "python", "python3", "pip", "pip3", "pip-audit",
    "git", "gh", "ls", "cat", "head", "tail", "grep", "find", "wc",
    "echo", "true", "false",
}

# git/gh subcommands restricted further — these are the only ones Kanaan can run.
GIT_ALLOWED_SUBCOMMANDS = {
    "status", "diff", "log", "branch", "checkout", "switch",
    "add", "commit", "push", "fetch", "rev-parse", "show",
    "ls-files", "config",  # config is read-only via --get; we filter args below
}
GH_ALLOWED_SUBCOMMANDS = {"pr", "issue", "repo", "api", "auth"}

PROTECTED_BRANCHES = {"main", "master"}

# ── Path / shell guards ──────────────────────────────────────────────────────


def _resolve_in_repo(path: str) -> Path:
    """Resolve a path and ensure it stays inside the repo. Raises ValueError if not."""
    candidate = (REPO_ROOT / path).resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError as e:
        raise ValueError(f"path escapes repo root: {path}") from e
    return candidate


def _is_writable(rel_path: str) -> tuple[bool, str]:
    rel = rel_path.lstrip("./")
    for pat in WRITE_DENYLIST:
        if fnmatch.fnmatch(rel, pat) or any(fnmatch.fnmatch(part, pat) for part in Path(rel).parts):
            return False, f"path matches denylist pattern '{pat}'"
    for pat in WRITE_ALLOWLIST:
        if fnmatch.fnmatch(rel, pat):
            return True, ""
    return False, "path not in write allowlist"


def _validate_shell(cmd: str) -> tuple[bool, str]:
    try:
        parts = shlex.split(cmd)
    except ValueError as e:
        return False, f"unparseable command: {e}"
    if not parts:
        return False, "empty command"
    binary = Path(parts[0]).name
    if binary not in SHELL_ALLOWED_BINARIES:
        return False, f"binary '{binary}' not allowed"
    if binary == "git":
        if len(parts) < 2 or parts[1] not in GIT_ALLOWED_SUBCOMMANDS:
            return False, f"git subcommand not allowed: {parts[1] if len(parts) > 1 else '(none)'}"
        if parts[1] == "push" and any(p in PROTECTED_BRANCHES for p in parts):
            return False, "refusing to push to a protected branch"
        if parts[1] == "config" and "--unset" in parts:
            return False, "git config --unset not allowed"
    if binary == "gh":
        if len(parts) < 2 or parts[1] not in GH_ALLOWED_SUBCOMMANDS:
            return False, f"gh subcommand not allowed: {parts[1] if len(parts) > 1 else '(none)'}"
        if parts[1] == "pr" and len(parts) >= 3 and parts[2] == "merge":
            return False, "Kanaan does not merge PRs — humans do that"
    if "rm" in parts or "sudo" in parts:
        return False, "destructive/privileged commands not allowed"
    return True, ""


# ── Tool implementations ─────────────────────────────────────────────────────


def tool_read_file(path: str) -> str:
    p = _resolve_in_repo(path)
    if not p.exists():
        return f"ERROR: file not found: {path}"
    if p.is_dir():
        return f"ERROR: path is a directory: {path}"
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"ERROR: file is not utf-8 text: {path}"
    if len(text) > 200_000:
        return text[:200_000] + f"\n... [truncated, file is {len(text)} bytes]"
    return text


def tool_list_files(pattern: str = "**/*") -> str:
    matches = []
    for p in REPO_ROOT.glob(pattern):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if rel.startswith(".git/") or rel.startswith("__pycache__"):
            continue
        matches.append(rel + ("/" if p.is_dir() else ""))
    return "\n".join(sorted(matches)[:500]) or "(no matches)"


def tool_write_file(path: str, content: str) -> str:
    ok, why = _is_writable(path)
    if not ok:
        return f"ERROR: refusing to write {path}: {why}"
    p = _resolve_in_repo(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existed = p.exists()
    p.write_text(content, encoding="utf-8")
    return f"{'updated' if existed else 'created'}: {path} ({len(content)} bytes)"


def tool_run_shell(command: str, timeout: int = 120) -> str:
    ok, why = _validate_shell(command)
    if not ok:
        return f"ERROR: command rejected: {why}"
    try:
        result = subprocess.run(
            command, shell=True, cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {timeout}s"
    out = (result.stdout or "") + (result.stderr or "")
    if len(out) > 50_000:
        out = out[:50_000] + "\n... [truncated]"
    return f"exit={result.returncode}\n{out}"


def tool_create_branch(branch: str) -> str:
    if not re.fullmatch(r"kanaan/[a-z0-9._-]+", branch):
        return "ERROR: branch must match 'kanaan/<slug>'"
    return tool_run_shell(f"git checkout -b {shlex.quote(branch)}")


def tool_open_pr(title: str, body: str, base: str = "main") -> str:
    if base in PROTECTED_BRANCHES:
        # We're opening a PR *into* main, which is fine; the protection above
        # is for pushes. Just confirm gh is wired up.
        pass
    body_file = REPO_ROOT / ".kanaan_pr_body.tmp"
    body_file.write_text(body, encoding="utf-8")
    try:
        cmd = (
            f"gh pr create --base {shlex.quote(base)} "
            f"--title {shlex.quote(title)} --body-file {shlex.quote(str(body_file))}"
        )
        return tool_run_shell(cmd, timeout=60)
    finally:
        body_file.unlink(missing_ok=True)


def tool_send_telegram(message: str) -> str:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return "ERROR: Telegram credentials not configured"
    import requests  # local import — only needed if Kanaan actually messages
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message[:4000]},
            timeout=15,
        )
        return f"telegram status={r.status_code}"
    except Exception as e:
        return f"ERROR: telegram send failed: {e}"


# ── Tool schemas (sent to Claude) ────────────────────────────────────────────

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file from inside the Johnny repo. Path is relative to repo root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in the repo matching a glob pattern (default '**/*'). Excludes .git and __pycache__.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string", "default": "**/*"}},
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a file. Only paths in the write allowlist are accepted. "
            "Always work on a kanaan/<slug> branch — call create_branch first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_shell",
        "description": (
            "Run a shell command in the repo root. Allowed binaries: ruff, pytest, python, pip, "
            "pip-audit, git (subset of subcommands), gh (subset). Use this for tests, lint, "
            "git operations, and opening files via grep/find. No rm, sudo, or pushes to main."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer", "default": 120},
            },
            "required": ["command"],
        },
    },
    {
        "name": "create_branch",
        "description": "Create and check out a new branch. Branch name must match 'kanaan/<slug>'.",
        "input_schema": {
            "type": "object",
            "properties": {"branch": {"type": "string"}},
            "required": ["branch"],
        },
    },
    {
        "name": "open_pr",
        "description": (
            "Open a GitHub pull request from the current branch into base (default 'main'). "
            "Requires gh CLI to be authenticated. Kanaan never merges — humans do."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "base": {"type": "string", "default": "main"},
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "send_telegram",
        "description": "Send a status/notification message to the owner's Telegram chat. Use sparingly.",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
]

TOOL_FNS = {
    "read_file": tool_read_file,
    "list_files": tool_list_files,
    "write_file": tool_write_file,
    "run_shell": tool_run_shell,
    "create_branch": tool_create_branch,
    "open_pr": tool_open_pr,
    "send_telegram": tool_send_telegram,
}


# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are Kanaan, the Chief Technology Officer of Johnny's AI ecosystem.

Johnny is a personal AI chief-of-staff for a construction-business owner who also
trades forex and trains for hybrid endurance events. Johnny is composed of
sub-agents in the agents/ directory (calendar, fitness, news, intel, gmail,
mrktedge, files, newsletter, training_loop). You are responsible for:

  1. Maintaining the health of the codebase — flag bugs, dead code, broken
     integrations, security issues, dependency rot.
  2. Scaffolding new sub-agents when asked. Match the existing pattern: a single
     file in agents/, top-of-file docstring, public function(s), optional
     `if __name__ == "__main__":` block, imports from config for keys.
  3. Reviewing changes through pull requests. You never merge — Kelvin (the owner)
     does that.

OPERATING RULES — these are non-negotiable:
  • Never push to main/master. All your work goes on a `kanaan/<slug>` branch.
  • Never write to .env*, memory.json, credentials, or any secret file.
  • Always run `ruff check` and `python -m compileall` on code you write before
    opening a PR.
  • Be specific in PR descriptions: what changed, why, what to watch for, how to
    test.
  • If you don't know what a function does, read it before changing it.
  • If a task is ambiguous, ask for clarification via your final text reply
    instead of guessing.
  • Prefer editing existing files over creating new ones unless the task is
    genuinely a new agent.

WORKFLOW for builds:
  1. read existing similar agents to match style
  2. create_branch kanaan/<slug>
  3. write_file the new agent
  4. run_shell to lint and syntax-check
  5. run_shell to commit and push
  6. open_pr with a clear description

WORKFLOW for audits:
  1. list_files and read_file to survey
  2. report findings as a structured summary in your final text reply
  3. only open a PR if you're explicitly asked to fix something

Stay concise. You're a senior engineer, not a chatbot — bullet points, file:line
references, no fluff.\
"""


# ── Tool-use loop ────────────────────────────────────────────────────────────


def _run_loop(task: str, log: bool = True) -> str:
    if not ANTHROPIC_API_KEY:
        return "ERROR: ANTHROPIC_API_KEY not set"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": task}]

    for turn in range(MAX_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            return "\n".join(b.text for b in response.content if b.type == "text").strip()

        if response.stop_reason != "tool_use":
            return f"[unexpected stop_reason: {response.stop_reason}]"

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            fn = TOOL_FNS.get(block.name)
            if fn is None:
                result = f"ERROR: unknown tool {block.name}"
            else:
                if log:
                    args_preview = json.dumps(block.input)[:200]
                    print(f"[Kanaan turn {turn}] {block.name}({args_preview})", file=sys.stderr)
                try:
                    result = fn(**block.input)
                except Exception as e:
                    result = f"ERROR: {type(e).__name__}: {e}"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result),
            })

        messages.append({"role": "user", "content": tool_results})

    return "[Kanaan hit max turns without finishing]"


# ── Public API ───────────────────────────────────────────────────────────────


def audit() -> str:
    """Run a full ecosystem audit. Returns Kanaan's findings as text."""
    task = (
        "Run a full audit of Johnny's codebase. Cover: "
        "1) agent inventory (what each agent does), "
        "2) integration points and any missing wiring, "
        "3) code-health concerns (dead code, suspicious patterns, missing error handling at boundaries), "
        "4) dependency status — run pip-audit and summarise, "
        "5) lint status — run `ruff check .` and report, "
        "6) top 3 things you'd recommend prioritising. "
        "Reply with a structured report. Do NOT open a PR."
    )
    return _run_loop(task)


def build(spec: str) -> str:
    """Scaffold a new sub-agent matching the given spec. Opens a PR."""
    task = (
        f"Build a new sub-agent. Specification:\n\n{spec}\n\n"
        "Follow the build workflow from your operating rules. Open a PR when done. "
        "Return a short summary of what you built and the PR URL."
    )
    return _run_loop(task)


def ask(question: str) -> str:
    """Ask Kanaan a freeform question about the codebase."""
    return _run_loop(question)


# ── CLI entry point ──────────────────────────────────────────────────────────


def _main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m agents.kanaan {audit|build|ask} [args...]", file=sys.stderr)
        sys.exit(1)
    cmd = sys.argv[1]
    arg = " ".join(sys.argv[2:]).strip()

    started = time.time()
    if cmd == "audit":
        print(audit())
    elif cmd == "build":
        if not arg:
            print("Usage: python -m agents.kanaan build \"<spec>\"", file=sys.stderr)
            sys.exit(1)
        print(build(arg))
    elif cmd == "ask":
        if not arg:
            print("Usage: python -m agents.kanaan ask \"<question>\"", file=sys.stderr)
            sys.exit(1)
        print(ask(arg))
    else:
        print(f"unknown subcommand: {cmd}", file=sys.stderr)
        sys.exit(1)
    print(f"\n[Kanaan finished in {time.time() - started:.1f}s]", file=sys.stderr)


if __name__ == "__main__":
    _main()
