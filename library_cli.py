"""
Quick CLI for archiving a newsletter from the terminal.

Usage:
    python library_cli.py archive --source Stratechery --date 2026-05-08 path/to/issue.html
    python library_cli.py trends --weeks 12
    python library_cli.py term ai-agents
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import library as lib


def cmd_archive(args: argparse.Namespace) -> None:
    src_path = Path(args.path)
    if not src_path.is_file():
        sys.exit(f"file not found: {src_path}")
    issue_date = date.fromisoformat(args.date)
    iso_year, iso_week, _ = issue_date.isocalendar()
    week_dir = lib.NEWSLETTERS_DIR / f"{iso_year}" / f"W{iso_week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)

    src_slug = lib.slugify(args.source).lower()
    target = week_dir / f"{issue_date.isoformat()}_{src_slug}{src_path.suffix or '.txt'}"
    data = src_path.read_bytes()
    target.write_bytes(data)

    rel_path = target.relative_to(lib.NEWSLETTERS_DIR).as_posix()
    text = lib.extract_text(target)
    word_count = len(text.split()) if text else 0

    with lib.db() as conn:
        cur = conn.execute(
            """INSERT INTO files(kind, rel_path, original_name, size, mime, sha256, uploaded_at, tags, notes)
               VALUES('newsletter', ?, ?, ?, ?, ?, datetime('now'), ?, ?)""",
            (rel_path, src_path.name, len(data), None, lib.hash_bytes(data),
             args.tags or "", args.summary or ""),
        )
        file_id = cur.lastrowid
        conn.execute(
            """INSERT INTO newsletters(file_id, source, issue_date, year, week, title, summary, word_count)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
            (file_id, args.source, issue_date.isoformat(), iso_year, iso_week,
             args.title, args.summary, word_count),
        )

    if text:
        lib.index_terms(file_id, text)
    print(f"archived {target}  ({iso_year}-W{iso_week:02d}, {word_count} words)")


def cmd_trends(args: argparse.Namespace) -> None:
    out = lib.trends(source=args.source, weeks=args.weeks, top=args.top)
    print(f"top terms across last {out['weeks']} issues" + (f" of {out['source']}" if out['source'] else ""))
    for t in out["terms"]:
        print(f"  {t['term']:<24} total={t['total']:<5} issues={t['issues']}")


def cmd_term(args: argparse.Namespace) -> None:
    out = lib.term_history(args.term, source=args.source)
    if not out["history"]:
        print("no occurrences")
        return
    for h in out["history"]:
        print(f"  {h['issue_date']}  {h['source']:<20}  {h['count']}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("archive")
    a.add_argument("path")
    a.add_argument("--source", required=True)
    a.add_argument("--date", required=True, help="YYYY-MM-DD")
    a.add_argument("--title", default=None)
    a.add_argument("--summary", default=None)
    a.add_argument("--tags", default=None)
    a.set_defaults(func=cmd_archive)

    t = sub.add_parser("trends")
    t.add_argument("--source", default=None)
    t.add_argument("--weeks", type=int, default=12)
    t.add_argument("--top", type=int, default=20)
    t.set_defaults(func=cmd_trends)

    th = sub.add_parser("term")
    th.add_argument("term")
    th.add_argument("--source", default=None)
    th.set_defaults(func=cmd_term)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
