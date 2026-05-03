"""
File Agent — parses files sent via Telegram into text Johnny can analyse.

Supported formats:
  • Excel (.xlsx, .xls)  — pandas
  • CSV (.csv)           — pandas
  • PDF (.pdf)           — pdfplumber
  • Plain text (.txt, .md, .json) — direct read

Returns a structured text representation that Johnny can reason over.
"""

import os

MAX_ROWS_PREVIEW = 100   # Cap rows shown per sheet to keep tokens reasonable
MAX_CHARS = 20000        # Hard cap on total output to protect Claude context


def parse_file(file_path: str) -> str:
    """Parse a file and return a text representation suitable for Claude."""
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext in (".xlsx", ".xls"):
            return _parse_excel(file_path)
        if ext == ".csv":
            return _parse_csv(file_path)
        if ext == ".pdf":
            return _parse_pdf(file_path)
        if ext in (".txt", ".md", ".json", ".log"):
            return _parse_text(file_path)
        return f"Unsupported file type: {ext}. Supported: .xlsx, .xls, .csv, .pdf, .txt, .md, .json"
    except Exception as e:
        return f"Failed to parse {ext} file: {e}"


def _parse_excel(file_path: str) -> str:
    import pandas as pd

    xls = pd.ExcelFile(file_path)
    parts = [f"Excel file with {len(xls.sheet_names)} sheet(s): {', '.join(xls.sheet_names)}\n"]

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        parts.append(f"\n━━━ SHEET: {sheet} ━━━")
        parts.append(f"Rows: {len(df)} · Columns: {len(df.columns)}")
        parts.append(f"Columns: {', '.join(str(c) for c in df.columns)}")

        if len(df) == 0:
            parts.append("(empty sheet)")
            continue

        preview = df.head(MAX_ROWS_PREVIEW).to_string(index=False, max_colwidth=40)
        parts.append(preview)

        if len(df) > MAX_ROWS_PREVIEW:
            parts.append(f"\n… {len(df) - MAX_ROWS_PREVIEW} more rows truncated")

    return _truncate("\n".join(parts))


def _parse_csv(file_path: str) -> str:
    import pandas as pd

    df = pd.read_csv(file_path)
    parts = [
        f"CSV file · Rows: {len(df)} · Columns: {len(df.columns)}",
        f"Columns: {', '.join(str(c) for c in df.columns)}",
        "",
        df.head(MAX_ROWS_PREVIEW).to_string(index=False, max_colwidth=40),
    ]
    if len(df) > MAX_ROWS_PREVIEW:
        parts.append(f"\n… {len(df) - MAX_ROWS_PREVIEW} more rows truncated")
    return _truncate("\n".join(parts))


def _parse_pdf(file_path: str) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(file_path) as pdf:
        parts.append(f"PDF · {len(pdf.pages)} pages")
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                parts.append(f"\n━━━ PAGE {i} ━━━\n{text.strip()}")
    return _truncate("\n".join(parts))


def _parse_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return _truncate(f.read())


def _truncate(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS] + f"\n\n… [truncated, {len(text) - MAX_CHARS} more chars]"
