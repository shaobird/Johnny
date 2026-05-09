"""
Library Agent — local file manager + weekly newsletter archive with trend tracking.

Reusable across personas (Johnny, Sally, …). Each persona points the agent at
its own root directory; everything (files, newsletters, SQLite index) is
stored under that root, so libraries stay isolated.

Public API:

    lib = Library(root="library_data/johnny")
    lib.add_file(local_path, folder="docs/2026", tags="...", notes="...")
    lib.archive_newsletter(local_path, source="Stratechery", issue_date="2026-05-08", ...)
    lib.list_files(folder="")
    lib.list_newsletters(source=None, year=None)
    lib.trends(weeks=12, source=None, top=20)
    lib.term_history("agents", source=None)
    lib.search("keyword")

The FastAPI wrapper (library.py at repo root) calls these methods directly.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import shutil
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm", ".rst", ".json", ".csv"}
STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "her", "was",
    "one", "our", "out", "his", "has", "had", "how", "its", "who", "did", "may", "use",
    "this", "that", "with", "from", "have", "your", "they", "will", "what", "when",
    "been", "were", "than", "them", "into", "more", "some", "also", "such", "only",
    "very", "much", "most", "over", "just", "like", "about", "their", "these", "those",
    "would", "could", "should", "after", "before", "where", "while", "which", "there",
    "other", "still", "being", "every", "each", "many", "make", "made", "does", "doing",
    "week", "weekly", "newsletter", "edition", "issue", "read", "reading", "reads",
}


# --- helpers (module-level so wrappers can reuse) ---------------------------

def safe_rel(parts: Iterable[str]) -> Path:
    p = Path(*[part for part in parts if part])
    for part in p.parts:
        if part in ("", ".", "..") or part.startswith("/"):
            raise ValueError(f"invalid path component: {part}")
    return p


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slugify(name: str) -> str:
    name = re.sub(r"[^\w\-. ]+", "", name).strip().replace(" ", "_")
    return name or "untitled"


def extract_text(path: Path) -> str:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z\-']{2,}", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 3]


# --- agent ------------------------------------------------------------------

@dataclass
class ArchiveResult:
    file_id: int
    rel_path: str
    year: int
    week: int
    word_count: int


class Library:
    """One Library instance per persona. Pass a unique root directory."""

    def __init__(self, root: str | os.PathLike = "library_data") -> None:
        self.root = Path(root).resolve()
        self.files_dir = self.root / "files"
        self.newsletters_dir = self.root / "newsletters"
        self.db_path = self.root / "index.sqlite"

        self.root.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(exist_ok=True)
        self.newsletters_dir.mkdir(exist_ok=True)
        self._init_db()

    # ── DB ──────────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    rel_path TEXT NOT NULL UNIQUE,
                    original_name TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    mime TEXT,
                    sha256 TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    tags TEXT DEFAULT '',
                    notes TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS newsletters (
                    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
                    source TEXT NOT NULL,
                    issue_date TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    week INTEGER NOT NULL,
                    title TEXT,
                    summary TEXT,
                    word_count INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS terms (
                    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                    term TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    PRIMARY KEY (file_id, term)
                );
                CREATE INDEX IF NOT EXISTS idx_terms_term ON terms(term);
                CREATE INDEX IF NOT EXISTS idx_news_year_week ON newsletters(year, week);
                CREATE INDEX IF NOT EXISTS idx_news_source ON newsletters(source);
                """
            )

    def _index_terms(self, file_id: int, text: str) -> int:
        tokens = tokenize(text)
        if not tokens:
            return 0
        counts = Counter(tokens).most_common(150)
        with self._connect() as conn:
            conn.execute("DELETE FROM terms WHERE file_id = ?", (file_id,))
            conn.executemany(
                "INSERT INTO terms(file_id, term, count) VALUES (?, ?, ?)",
                [(file_id, term, n) for term, n in counts],
            )
        return len(tokens)

    # ── Files ──────────────────────────────────────────────────────────────

    def add_file(
        self,
        source: str | os.PathLike | bytes,
        *,
        original_name: str | None = None,
        folder: str = "",
        tags: str = "",
        notes: str = "",
    ) -> dict:
        """Add a file. `source` can be a path or raw bytes."""
        rel_dir = safe_rel(folder.split("/") if folder else [])
        target_dir = self.files_dir / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(source, (bytes, bytearray)):
            data = bytes(source)
            name = slugify(original_name or "upload")
        else:
            src = Path(source)
            data = src.read_bytes()
            name = slugify(original_name or src.name)

        target = target_dir / name
        if target.exists():
            stem, ext = os.path.splitext(name)
            target = target_dir / f"{stem}_{int(datetime.utcnow().timestamp())}{ext}"
        target.write_bytes(data)

        rel_path = target.relative_to(self.files_dir).as_posix()
        mime = mimetypes.guess_type(target.name)[0]
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO files(kind, rel_path, original_name, size, mime, sha256, uploaded_at, tags, notes)
                   VALUES('file', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rel_path, original_name or name, len(data), mime, hash_bytes(data),
                 datetime.utcnow().isoformat(timespec="seconds"), tags, notes),
            )
            file_id = cur.lastrowid

        text = extract_text(target)
        if text:
            self._index_terms(file_id, text)

        return {"id": file_id, "rel_path": rel_path, "size": len(data)}

    def list_files(self, folder: str = "") -> dict:
        base = self.files_dir / safe_rel(folder.split("/") if folder else [])
        if not base.exists() or not base.is_dir():
            raise FileNotFoundError(f"folder not found: {folder}")

        folders = sorted([p.name for p in base.iterdir() if p.is_dir()])
        rows = []
        with self._connect() as conn:
            for entry in sorted(base.iterdir()):
                if not entry.is_file():
                    continue
                rel = entry.relative_to(self.files_dir).as_posix()
                row = conn.execute(
                    "SELECT id, size, mime, uploaded_at, tags, notes FROM files WHERE rel_path = ? AND kind = 'file'",
                    (rel,),
                ).fetchone()
                rows.append({
                    "name": entry.name,
                    "rel_path": rel,
                    "size": entry.stat().st_size,
                    "id": row["id"] if row else None,
                    "mime": row["mime"] if row else mimetypes.guess_type(entry.name)[0],
                    "uploaded_at": row["uploaded_at"] if row else None,
                    "tags": row["tags"] if row else "",
                    "notes": row["notes"] if row else "",
                })
        return {"folder": folder, "folders": folders, "files": rows}

    def file_path(self, rel_path: str) -> Path:
        target = self.files_dir / safe_rel(rel_path.split("/"))
        if not target.is_file():
            raise FileNotFoundError(rel_path)
        return target

    def delete_file(self, rel_path: str) -> None:
        target = self.file_path(rel_path)
        target.unlink()
        with self._connect() as conn:
            conn.execute("DELETE FROM files WHERE rel_path = ? AND kind = 'file'", (rel_path,))

    def make_folder(self, folder: str) -> str:
        target = self.files_dir / safe_rel(folder.split("/"))
        target.mkdir(parents=True, exist_ok=True)
        return target.relative_to(self.files_dir).as_posix()

    # ── Newsletters ────────────────────────────────────────────────────────

    def archive_newsletter(
        self,
        source_file: str | os.PathLike | bytes,
        *,
        source: str,
        issue_date: str,
        original_name: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        tags: str = "",
    ) -> ArchiveResult:
        try:
            d = date.fromisoformat(issue_date)
        except ValueError as e:
            raise ValueError("issue_date must be YYYY-MM-DD") from e

        iso_year, iso_week, _ = d.isocalendar()
        src_slug = slugify(source).lower()
        week_dir = self.newsletters_dir / f"{iso_year}" / f"W{iso_week:02d}"
        week_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(source_file, (bytes, bytearray)):
            data = bytes(source_file)
            ext = os.path.splitext(original_name or "")[1] or ".txt"
            disp_name = original_name or f"{src_slug}{ext}"
        else:
            src = Path(source_file)
            data = src.read_bytes()
            ext = src.suffix or ".txt"
            disp_name = original_name or src.name

        fname = f"{d.isoformat()}_{src_slug}{ext}"
        target = week_dir / fname
        if target.exists():
            target = week_dir / f"{d.isoformat()}_{src_slug}_{int(datetime.utcnow().timestamp())}{ext}"
        target.write_bytes(data)

        rel_path = target.relative_to(self.newsletters_dir).as_posix()
        mime = mimetypes.guess_type(target.name)[0]
        text = extract_text(target)
        word_count = len(text.split()) if text else 0

        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO files(kind, rel_path, original_name, size, mime, sha256, uploaded_at, tags, notes)
                   VALUES('newsletter', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rel_path, disp_name, len(data), mime, hash_bytes(data),
                 datetime.utcnow().isoformat(timespec="seconds"), tags, summary or ""),
            )
            file_id = cur.lastrowid
            conn.execute(
                """INSERT INTO newsletters(file_id, source, issue_date, year, week, title, summary, word_count)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                (file_id, source, d.isoformat(), iso_year, iso_week, title, summary, word_count),
            )

        if text:
            self._index_terms(file_id, text)

        return ArchiveResult(file_id, rel_path, iso_year, iso_week, word_count)

    def list_newsletters(self, source: str | None = None, year: int | None = None, limit: int = 100) -> list[dict]:
        q = """
            SELECT n.file_id, n.source, n.issue_date, n.year, n.week, n.title, n.summary, n.word_count,
                   f.rel_path, f.size, f.tags
            FROM newsletters n JOIN files f ON f.id = n.file_id
            WHERE 1=1
        """
        params: list = []
        if source:
            q += " AND n.source = ?"
            params.append(source)
        if year:
            q += " AND n.year = ?"
            params.append(year)
        q += " ORDER BY n.issue_date DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(q, params).fetchall()]

    def list_sources(self) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                """SELECT source, COUNT(*) AS issues, MIN(issue_date) AS first, MAX(issue_date) AS latest
                   FROM newsletters GROUP BY source ORDER BY latest DESC"""
            ).fetchall()]

    def newsletter_path(self, file_id: int) -> Path:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT rel_path FROM files WHERE id = ? AND kind = 'newsletter'", (file_id,)
            ).fetchone()
        if not row:
            raise FileNotFoundError(f"newsletter id {file_id}")
        target = self.newsletters_dir / row["rel_path"]
        if not target.is_file():
            raise FileNotFoundError(f"missing on disk: {row['rel_path']}")
        return target

    # ── Trends & search ────────────────────────────────────────────────────

    def trends(self, weeks: int = 12, source: str | None = None, top: int = 20) -> dict:
        with self._connect() as conn:
            params: list = []
            sub = "SELECT n.file_id FROM newsletters n WHERE 1=1"
            if source:
                sub += " AND n.source = ?"
                params.append(source)
            sub += " ORDER BY n.issue_date DESC LIMIT ?"
            params.append(weeks)

            rows = conn.execute(
                f"""SELECT t.term, SUM(t.count) AS total, COUNT(DISTINCT t.file_id) AS issues
                    FROM terms t WHERE t.file_id IN ({sub})
                    GROUP BY t.term ORDER BY total DESC LIMIT ?""",
                params + [top],
            ).fetchall()
        return {"weeks": weeks, "source": source, "terms": [dict(r) for r in rows]}

    def term_history(self, term: str, source: str | None = None) -> list[dict]:
        with self._connect() as conn:
            params: list = [term.lower()]
            q = """
                SELECT n.year, n.week, n.issue_date, n.source, t.count
                FROM terms t JOIN newsletters n ON n.file_id = t.file_id
                WHERE t.term = ?
            """
            if source:
                q += " AND n.source = ?"
                params.append(source)
            q += " ORDER BY n.issue_date"
            return [dict(r) for r in conn.execute(q, params).fetchall()]

    def search(self, query: str, limit: int = 25) -> list[dict]:
        needle = f"%{query.lower()}%"
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, kind, rel_path, original_name, tags, notes, uploaded_at
                   FROM files
                   WHERE LOWER(original_name) LIKE ? OR LOWER(tags) LIKE ? OR LOWER(notes) LIKE ?
                   ORDER BY uploaded_at DESC LIMIT ?""",
                (needle, needle, needle, limit),
            ).fetchall()
        return [dict(r) for r in rows]


# --- shared persona helper --------------------------------------------------

_libraries: dict[str, Library] = {}


def for_persona(name: str = "johnny", root: str | os.PathLike | None = None) -> Library:
    """
    Get (or lazily create) the Library for a persona. Use this from agents:

        from agents.library import for_persona
        lib = for_persona("johnny")
        lib.archive_newsletter(...)

    Storage defaults to `library_data/<persona>/` but can be overridden via
    the LIBRARY_ROOT env var (single shared root) or the `root` arg.
    """
    if name in _libraries:
        return _libraries[name]
    base = Path(root or os.getenv("LIBRARY_ROOT", "library_data"))
    persona_root = base / name.lower() if root is None else base
    lib = Library(persona_root)
    _libraries[name] = lib
    return lib
