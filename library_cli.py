"""
Quick CLI for the Library agent. Works for any persona.

Usage:
    python library_cli.py --persona johnny archive path/to/issue.html \\
        --source Stratechery --date 2026-05-08
    python library_cli.py --persona sally trends --weeks 12
    python library_cli.py term agents
"""

from __future__ import annotations

import argparse

from agents.library import for_persona


def cmd_archive(lib, args: argparse.Namespace) -> None:
    result = lib.archive_newsletter(
        args.path,
        source=args.source,
        issue_date=args.date,
        title=args.title,
        summary=args.summary,
        tags=args.tags or "",
    )
    print(f"archived  {result.rel_path}  ({result.year}-W{result.week:02d}, {result.word_count} words)")


def cmd_add(lib, args: argparse.Namespace) -> None:
    result = lib.add_file(args.path, folder=args.folder or "", tags=args.tags or "", notes=args.notes or "")
    print(f"added  {result['rel_path']}  ({result['size']} bytes)")


def cmd_trends(lib, args: argparse.Namespace) -> None:
    out = lib.trends(weeks=args.weeks, source=args.source, top=args.top)
    label = f" of {out['source']}" if out["source"] else ""
    print(f"top terms across last {out['weeks']} issues{label}")
    for t in out["terms"]:
        print(f"  {t['term']:<24} total={t['total']:<5} issues={t['issues']}")


def cmd_term(lib, args: argparse.Namespace) -> None:
    history = lib.term_history(args.term, source=args.source)
    if not history:
        print("no occurrences")
        return
    for h in history:
        print(f"  {h['issue_date']}  {h['source']:<20}  {h['count']}")


def cmd_list(lib, args: argparse.Namespace) -> None:
    for n in lib.list_newsletters(source=args.source, limit=args.limit):
        print(f"  {n['issue_date']}  {n['source']:<20}  {n['title'] or ''}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--persona", default="johnny")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("archive")
    a.add_argument("path")
    a.add_argument("--source", required=True)
    a.add_argument("--date", required=True, help="YYYY-MM-DD")
    a.add_argument("--title", default=None)
    a.add_argument("--summary", default=None)
    a.add_argument("--tags", default=None)
    a.set_defaults(func=cmd_archive)

    f = sub.add_parser("add")
    f.add_argument("path")
    f.add_argument("--folder", default=None)
    f.add_argument("--tags", default=None)
    f.add_argument("--notes", default=None)
    f.set_defaults(func=cmd_add)

    t = sub.add_parser("trends")
    t.add_argument("--source", default=None)
    t.add_argument("--weeks", type=int, default=12)
    t.add_argument("--top", type=int, default=20)
    t.set_defaults(func=cmd_trends)

    th = sub.add_parser("term")
    th.add_argument("term")
    th.add_argument("--source", default=None)
    th.set_defaults(func=cmd_term)

    ls = sub.add_parser("list")
    ls.add_argument("--source", default=None)
    ls.add_argument("--limit", type=int, default=50)
    ls.set_defaults(func=cmd_list)

    args = p.parse_args()
    lib = for_persona(args.persona)
    args.func(lib, args)


if __name__ == "__main__":
    main()
