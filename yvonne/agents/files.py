"""
File management sub-agent — Gladys's workspace (managed by Yvonne).

A single sandboxed directory under data/workspace/. Yvonne can list, read,
write, and search files there (proposals, policy PDFs converted to text,
client notes, scripts). All paths are resolved relative to WORKSPACE_DIR
and any path that escapes it is refused.
"""

from __future__ import annotations

from pathlib import Path

from ..config import WORKSPACE_DIR

MAX_READ_BYTES = 200_000


def _resolve(rel: str) -> Path:
    target = (WORKSPACE_DIR / rel).resolve()
    workspace = WORKSPACE_DIR.resolve()
    if workspace not in target.parents and target != workspace:
        raise ValueError(f"Path escapes workspace: {rel}")
    return target


def list_files(subdir: str = "") -> str:
    base = _resolve(subdir) if subdir else WORKSPACE_DIR
    if not base.exists():
        return f"No such folder: {subdir or '/'}"
    entries = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = p.relative_to(WORKSPACE_DIR)
            entries.append(f"  {rel}  ({p.stat().st_size} bytes)")
    return "\n".join(entries) if entries else "(workspace empty)"


def read_file(rel: str) -> str:
    target = _resolve(rel)
    if not target.exists() or not target.is_file():
        return f"No such file: {rel}"
    raw = target.read_bytes()[:MAX_READ_BYTES]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return f"(binary file, {len(raw)} bytes — cannot display as text)"


def write_file(rel: str, content: str) -> str:
    target = _resolve(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {rel}."


def append_file(rel: str, content: str) -> str:
    target = _resolve(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(content)
    return f"Appended {len(content)} chars to {rel}."


def search_files(query: str) -> str:
    q = query.lower()
    hits: list[str] = []
    for p in WORKSPACE_DIR.rglob("*"):
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if q in text.lower():
            rel = p.relative_to(WORKSPACE_DIR)
            for i, line in enumerate(text.splitlines(), 1):
                if q in line.lower():
                    hits.append(f"  {rel}:{i}: {line.strip()[:160]}")
                    if len(hits) >= 30:
                        break
        if len(hits) >= 30:
            break
    return "\n".join(hits) if hits else f"No matches for {query!r}."
