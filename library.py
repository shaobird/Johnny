"""
Johnny's library — a local file manager and newsletter archive.

Run standalone:
    uvicorn library:app --host 127.0.0.1 --port 8765 --reload

Storage layout (under LIBRARY_ROOT, default ./library_data):
    files/                  — general file manager (free-form folders)
    newsletters/<YYYY>/<WW>/  — weekly newsletter archive
    index.sqlite            — metadata, full-text search, trend signals
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import sqlite3
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse


LIBRARY_ROOT = Path(os.getenv("LIBRARY_ROOT", "library_data")).resolve()
FILES_DIR = LIBRARY_ROOT / "files"
NEWSLETTERS_DIR = LIBRARY_ROOT / "newsletters"
DB_PATH = LIBRARY_ROOT / "index.sqlite"

LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
FILES_DIR.mkdir(exist_ok=True)
NEWSLETTERS_DIR.mkdir(exist_ok=True)

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


# --- DB ---------------------------------------------------------------------

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,            -- 'file' or 'newsletter'
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
                issue_date TEXT NOT NULL,      -- ISO date
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


init_db()


# --- helpers ----------------------------------------------------------------

def safe_rel(parts: Iterable[str]) -> Path:
    """Join path parts and reject any traversal."""
    p = Path(*[part for part in parts if part])
    for part in p.parts:
        if part in ("", ".", "..") or part.startswith("/"):
            raise HTTPException(400, f"invalid path component: {part}")
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


def index_terms(file_id: int, text: str) -> int:
    tokens = tokenize(text)
    if not tokens:
        return 0
    counts = Counter(tokens).most_common(150)
    with db() as conn:
        conn.execute("DELETE FROM terms WHERE file_id = ?", (file_id,))
        conn.executemany(
            "INSERT INTO terms(file_id, term, count) VALUES (?, ?, ?)",
            [(file_id, term, n) for term, n in counts],
        )
    return len(tokens)


# --- FastAPI ----------------------------------------------------------------

app = FastAPI(title="Johnny Library")


# --- file manager API -------------------------------------------------------

@app.get("/api/files")
def list_files(folder: str = ""):
    base = FILES_DIR / safe_rel(folder.split("/") if folder else [])
    if not base.exists() or not base.is_dir():
        raise HTTPException(404, "folder not found")

    folders = sorted([p.name for p in base.iterdir() if p.is_dir()])
    rows = []
    with db() as conn:
        for entry in sorted(base.iterdir()):
            if not entry.is_file():
                continue
            rel = entry.relative_to(FILES_DIR).as_posix()
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


@app.post("/api/files/upload")
async def upload_file(
    folder: str = Form(""),
    tags: str = Form(""),
    notes: str = Form(""),
    file: UploadFile = File(...),
):
    rel_dir = safe_rel(folder.split("/") if folder else [])
    target_dir = FILES_DIR / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    data = await file.read()
    name = slugify(file.filename or "upload")
    target = target_dir / name
    if target.exists():
        stem, ext = os.path.splitext(name)
        target = target_dir / f"{stem}_{int(datetime.utcnow().timestamp())}{ext}"

    target.write_bytes(data)
    rel_path = target.relative_to(FILES_DIR).as_posix()
    sha = hash_bytes(data)
    mime = file.content_type or mimetypes.guess_type(target.name)[0]

    with db() as conn:
        cur = conn.execute(
            """INSERT INTO files(kind, rel_path, original_name, size, mime, sha256, uploaded_at, tags, notes)
               VALUES('file', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rel_path, file.filename or name, len(data), mime, sha,
             datetime.utcnow().isoformat(timespec="seconds"), tags, notes),
        )
        file_id = cur.lastrowid

    text = extract_text(target)
    if text:
        index_terms(file_id, text)

    return {"id": file_id, "rel_path": rel_path, "size": len(data)}


@app.post("/api/files/folder")
def create_folder(folder: str = Form(...)):
    target = FILES_DIR / safe_rel(folder.split("/"))
    target.mkdir(parents=True, exist_ok=True)
    return {"folder": target.relative_to(FILES_DIR).as_posix()}


@app.get("/api/files/download")
def download_file(rel_path: str):
    target = FILES_DIR / safe_rel(rel_path.split("/"))
    if not target.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(target, filename=target.name)


@app.delete("/api/files")
def delete_file(rel_path: str):
    target = FILES_DIR / safe_rel(rel_path.split("/"))
    if not target.is_file():
        raise HTTPException(404, "file not found")
    target.unlink()
    with db() as conn:
        conn.execute("DELETE FROM files WHERE rel_path = ? AND kind = 'file'", (rel_path,))
    return {"deleted": rel_path}


# --- newsletters ------------------------------------------------------------

@app.post("/api/newsletters")
async def archive_newsletter(
    source: str = Form(...),
    issue_date: str = Form(...),  # YYYY-MM-DD
    title: str = Form(""),
    summary: str = Form(""),
    tags: str = Form(""),
    file: UploadFile = File(...),
):
    try:
        d = date.fromisoformat(issue_date)
    except ValueError:
        raise HTTPException(400, "issue_date must be YYYY-MM-DD")

    iso_year, iso_week, _ = d.isocalendar()
    src_slug = slugify(source).lower()
    week_dir = NEWSLETTERS_DIR / f"{iso_year}" / f"W{iso_week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)

    data = await file.read()
    ext = os.path.splitext(file.filename or "")[1] or ".txt"
    fname = f"{d.isoformat()}_{src_slug}{ext}"
    target = week_dir / fname
    if target.exists():
        target = week_dir / f"{d.isoformat()}_{src_slug}_{int(datetime.utcnow().timestamp())}{ext}"

    target.write_bytes(data)
    rel_path = target.relative_to(NEWSLETTERS_DIR).as_posix()
    sha = hash_bytes(data)
    mime = file.content_type or mimetypes.guess_type(target.name)[0]

    text = extract_text(target)
    word_count = len(text.split()) if text else 0

    with db() as conn:
        cur = conn.execute(
            """INSERT INTO files(kind, rel_path, original_name, size, mime, sha256, uploaded_at, tags, notes)
               VALUES('newsletter', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rel_path, file.filename or fname, len(data), mime, sha,
             datetime.utcnow().isoformat(timespec="seconds"), tags, summary),
        )
        file_id = cur.lastrowid
        conn.execute(
            """INSERT INTO newsletters(file_id, source, issue_date, year, week, title, summary, word_count)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
            (file_id, source, d.isoformat(), iso_year, iso_week, title or None,
             summary or None, word_count),
        )

    if text:
        index_terms(file_id, text)

    return {
        "id": file_id,
        "rel_path": rel_path,
        "year": iso_year,
        "week": iso_week,
        "word_count": word_count,
    }


@app.get("/api/newsletters")
def list_newsletters(source: str | None = None, year: int | None = None, limit: int = 100):
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
    with db() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return {"newsletters": rows}


@app.get("/api/newsletters/sources")
def list_sources():
    with db() as conn:
        rows = conn.execute(
            """SELECT source, COUNT(*) AS issues, MIN(issue_date) AS first, MAX(issue_date) AS latest
               FROM newsletters GROUP BY source ORDER BY latest DESC"""
        ).fetchall()
    return {"sources": [dict(r) for r in rows]}


@app.get("/api/newsletters/{file_id}/download")
def newsletter_download(file_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT rel_path FROM files WHERE id = ? AND kind = 'newsletter'", (file_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "newsletter not found")
    target = NEWSLETTERS_DIR / row["rel_path"]
    if not target.is_file():
        raise HTTPException(404, "file missing on disk")
    return FileResponse(target, filename=target.name)


# --- trends -----------------------------------------------------------------

@app.get("/api/trends")
def trends(
    source: str | None = None,
    weeks: int = Query(12, ge=1, le=104),
    top: int = Query(20, ge=1, le=100),
):
    """Top terms across the most recent N weeks of newsletters."""
    with db() as conn:
        params: list = []
        sub = """
            SELECT n.file_id FROM newsletters n
            WHERE 1=1
        """
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


@app.get("/api/trends/term")
def term_history(term: str, source: str | None = None):
    """Per-week count of a term across the archive."""
    with db() as conn:
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
        rows = conn.execute(q, params).fetchall()
    return {"term": term, "history": [dict(r) for r in rows]}


@app.get("/api/search")
def search(q: str, limit: int = 25):
    needle = f"%{q.lower()}%"
    with db() as conn:
        rows = conn.execute(
            """SELECT id, kind, rel_path, original_name, tags, notes, uploaded_at
               FROM files
               WHERE LOWER(original_name) LIKE ? OR LOWER(tags) LIKE ? OR LOWER(notes) LIKE ?
               ORDER BY uploaded_at DESC LIMIT ?""",
            (needle, needle, needle, limit),
        ).fetchall()
    return {"results": [dict(r) for r in rows]}


# --- UI ---------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


@app.get("/healthz")
def healthz():
    return {"ok": True, "root": str(LIBRARY_ROOT)}


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Johnny Library</title>
<style>
 body { font: 14px -apple-system, system-ui, sans-serif; max-width: 1000px; margin: 24px auto; padding: 0 16px; color: #222; }
 h1 { margin: 0 0 4px; } h2 { margin-top: 32px; border-bottom: 1px solid #eee; padding-bottom: 4px; }
 nav a { margin-right: 12px; }
 table { width: 100%; border-collapse: collapse; margin-top: 8px; }
 th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; vertical-align: top; }
 th { background: #fafafa; }
 form { background: #f7f7f9; padding: 12px; border-radius: 6px; margin-top: 8px; }
 input, textarea, select, button { font: inherit; padding: 6px 8px; margin: 4px 4px 4px 0; }
 .row { display:flex; gap:8px; flex-wrap:wrap; }
 .pill { background:#eef; padding:2px 8px; border-radius:10px; font-size:12px; }
 small { color:#666; }
 code { background:#f0f0f0; padding:1px 4px; border-radius:3px; }
</style></head><body>
<h1>Johnny Library</h1>
<small>Local file manager + weekly newsletter archive</small>

<nav><a href="#files">Files</a><a href="#newsletters">Newsletters</a><a href="#trends">Trends</a></nav>

<h2 id="files">Files</h2>
<form id="fileForm" enctype="multipart/form-data">
  <div class="row">
    <input name="folder" placeholder="folder (optional, e.g. docs/2026)">
    <input name="tags" placeholder="tags (comma-sep)">
    <input name="notes" placeholder="notes">
    <input name="file" type="file" required>
    <button>Upload</button>
  </div>
</form>
<div id="filesList"></div>

<h2 id="newsletters">Newsletters</h2>
<form id="nlForm" enctype="multipart/form-data">
  <div class="row">
    <input name="source" placeholder="source (e.g. Stratechery)" required>
    <input name="issue_date" type="date" required>
    <input name="title" placeholder="title">
    <input name="tags" placeholder="tags">
  </div>
  <textarea name="summary" placeholder="summary / TL;DR" rows="2" style="width:100%"></textarea>
  <div class="row"><input name="file" type="file" required><button>Archive</button></div>
</form>
<div id="nlList"></div>

<h2 id="trends">Trends</h2>
<form id="trendForm">
  <div class="row">
    <input name="source" placeholder="source (blank = all)">
    <input name="weeks" type="number" value="12" min="1" max="104">
    <button>Show top terms</button>
  </div>
</form>
<div id="trendOut"></div>

<form id="termForm">
  <div class="row">
    <input name="term" placeholder="track a term over time" required>
    <input name="source" placeholder="source (optional)">
    <button>Plot history</button>
  </div>
</form>
<div id="termOut"></div>

<script>
async function j(url, opts){ const r = await fetch(url, opts); if(!r.ok) throw new Error(await r.text()); return r.json(); }

async function loadFiles(){
  const data = await j('/api/files');
  const rows = data.files.map(f => `<tr>
    <td><a href="/api/files/download?rel_path=${encodeURIComponent(f.rel_path)}">${f.name}</a></td>
    <td>${(f.size/1024).toFixed(1)} KB</td>
    <td>${f.tags||''}</td>
    <td>${f.notes||''}</td>
    <td><button onclick="del('${f.rel_path}')">delete</button></td>
  </tr>`).join('');
  document.getElementById('filesList').innerHTML =
    `<table><tr><th>Name</th><th>Size</th><th>Tags</th><th>Notes</th><th></th></tr>${rows}</table>`;
}

async function del(rel){
  if(!confirm('Delete '+rel+'?')) return;
  await fetch('/api/files?rel_path='+encodeURIComponent(rel),{method:'DELETE'});
  loadFiles();
}

async function loadNL(){
  const data = await j('/api/newsletters');
  const rows = data.newsletters.map(n => `<tr>
    <td>${n.issue_date}</td><td>${n.source}</td><td>${n.title||''}</td>
    <td><span class="pill">${n.year}-W${String(n.week).padStart(2,'0')}</span></td>
    <td>${n.word_count}</td>
    <td><a href="/api/newsletters/${n.file_id}/download">download</a></td>
  </tr>`).join('');
  document.getElementById('nlList').innerHTML =
    `<table><tr><th>Date</th><th>Source</th><th>Title</th><th>Week</th><th>Words</th><th></th></tr>${rows}</table>`;
}

document.getElementById('fileForm').onsubmit = async e => {
  e.preventDefault();
  await fetch('/api/files/upload', {method:'POST', body: new FormData(e.target)});
  e.target.reset(); loadFiles();
};

document.getElementById('nlForm').onsubmit = async e => {
  e.preventDefault();
  await fetch('/api/newsletters', {method:'POST', body: new FormData(e.target)});
  e.target.reset(); loadNL();
};

document.getElementById('trendForm').onsubmit = async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const params = new URLSearchParams();
  if(fd.get('source')) params.set('source', fd.get('source'));
  params.set('weeks', fd.get('weeks'));
  const data = await j('/api/trends?'+params);
  const rows = data.terms.map(t=>`<tr><td>${t.term}</td><td>${t.total}</td><td>${t.issues}</td></tr>`).join('');
  document.getElementById('trendOut').innerHTML =
    `<table><tr><th>Term</th><th>Total</th><th>Issues</th></tr>${rows}</table>`;
};

document.getElementById('termForm').onsubmit = async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const params = new URLSearchParams({term: fd.get('term')});
  if(fd.get('source')) params.set('source', fd.get('source'));
  const data = await j('/api/trends/term?'+params);
  const rows = data.history.map(h=>`<tr><td>${h.issue_date}</td><td>${h.source}</td><td>${h.count}</td></tr>`).join('');
  document.getElementById('termOut').innerHTML = rows
    ? `<table><tr><th>Date</th><th>Source</th><th>Count</th></tr>${rows}</table>`
    : '<p><small>no occurrences yet</small></p>';
};

loadFiles(); loadNL();
</script>
</body></html>
"""
