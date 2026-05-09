"""
FastAPI wrapper around the Library agent — gives Johnny (or Sally) a local
web UI for files, newsletters, and trends.

The actual logic lives in agents/library.py so it can be reused without
running an HTTP server.

Run:
    uvicorn library:app --host 127.0.0.1 --port 8765 --reload

Choose persona via env (default = johnny):
    LIBRARY_PERSONA=sally uvicorn library:app
"""

from __future__ import annotations

import os

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from agents.library import for_persona

PERSONA = os.getenv("LIBRARY_PERSONA", "johnny")
lib = for_persona(PERSONA)

app = FastAPI(title=f"{PERSONA.capitalize()} Library")


# --- file manager -----------------------------------------------------------

@app.get("/api/files")
def list_files(folder: str = ""):
    try:
        return lib.list_files(folder)
    except FileNotFoundError:
        raise HTTPException(404, "folder not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/files/upload")
async def upload_file(
    folder: str = Form(""),
    tags: str = Form(""),
    notes: str = Form(""),
    file: UploadFile = File(...),
):
    data = await file.read()
    try:
        return lib.add_file(
            data,
            original_name=file.filename or "upload",
            folder=folder,
            tags=tags,
            notes=notes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/files/folder")
def create_folder(folder: str = Form(...)):
    try:
        return {"folder": lib.make_folder(folder)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/files/download")
def download_file(rel_path: str):
    try:
        target = lib.file_path(rel_path)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "file not found")
    return FileResponse(target, filename=target.name)


@app.delete("/api/files")
def delete_file(rel_path: str):
    try:
        lib.delete_file(rel_path)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "file not found")
    return {"deleted": rel_path}


# --- newsletters ------------------------------------------------------------

@app.post("/api/newsletters")
async def archive_newsletter(
    source: str = Form(...),
    issue_date: str = Form(...),
    title: str = Form(""),
    summary: str = Form(""),
    tags: str = Form(""),
    file: UploadFile = File(...),
):
    data = await file.read()
    try:
        result = lib.archive_newsletter(
            data,
            source=source,
            issue_date=issue_date,
            original_name=file.filename,
            title=title or None,
            summary=summary or None,
            tags=tags,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "id": result.file_id,
        "rel_path": result.rel_path,
        "year": result.year,
        "week": result.week,
        "word_count": result.word_count,
    }


@app.get("/api/newsletters")
def list_newsletters(source: str | None = None, year: int | None = None, limit: int = 100):
    return {"newsletters": lib.list_newsletters(source=source, year=year, limit=limit)}


@app.get("/api/newsletters/sources")
def list_sources():
    return {"sources": lib.list_sources()}


@app.get("/api/newsletters/{file_id}/download")
def newsletter_download(file_id: int):
    try:
        target = lib.newsletter_path(file_id)
    except FileNotFoundError:
        raise HTTPException(404, "newsletter not found")
    return FileResponse(target, filename=target.name)


# --- trends -----------------------------------------------------------------

@app.get("/api/trends")
def trends(
    source: str | None = None,
    weeks: int = Query(12, ge=1, le=104),
    top: int = Query(20, ge=1, le=100),
):
    return lib.trends(weeks=weeks, source=source, top=top)


@app.get("/api/trends/term")
def term_history(term: str, source: str | None = None):
    return {"term": term, "history": lib.term_history(term, source=source)}


@app.get("/api/search")
def search(q: str, limit: int = 25):
    return {"results": lib.search(q, limit=limit)}


# --- UI ---------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML.replace("{{PERSONA}}", PERSONA.capitalize()))


@app.get("/healthz")
def healthz():
    return {"ok": True, "persona": PERSONA, "root": str(lib.root)}


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>{{PERSONA}} Library</title>
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
</style></head><body>
<h1>{{PERSONA}} Library</h1>
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
