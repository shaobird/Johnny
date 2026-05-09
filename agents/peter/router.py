"""
Peter mode router — recommends the best skill for a given question.

Uses cheap keyword scoring (no LLM call). Returns the picked mode plus a
human-readable reason so Boss and Yvonne can see *why* Peter routed it that way.
"""

import re

# Per-mode keyword scoring. Order doesn't matter; weight does.
# Phrases (with spaces) score 2, single words score 1.
_KEYWORDS: dict[str, dict[str, int]] = {
    "portfolio": {
        "portfolio": 2, "holdings": 2, "watchlist": 2, "rebalance": 2,
        "rebalancing": 2, "allocation": 2, "exposure": 2, "concentration": 2,
        "stock": 1, "stocks": 1, "shares": 1, "ticker": 1, "etf": 1,
        "nvda": 2, "msft": 2, "googl": 2, "meta": 2, "amzn": 2, "tsla": 2,
        "ai exposure": 2, "tech exposure": 2, "p/l": 1, "pnl": 1, "drawdown": 1,
    },
    "couple": {
        "yvonne": 2, "we ": 1, "us ": 1, "our ": 1, "joint": 2, "together": 1,
        "savings": 2, "saving rate": 2, "retirement": 2, "retire": 2,
        "bto": 2, "hdb": 2, "condo": 1, "downpayment": 2, "mortgage": 2,
        "kids": 2, "children": 2, "child": 2, "school fees": 2, "baby": 2,
        "cpf": 2, "srs": 2, "insurance": 1, "wedding": 2, "honeymoon": 1,
        "emergency fund": 2, "net worth": 2, "balance sheet": 2,
        "financial plan": 2, "goal": 1, "goals": 1, "scenario": 1,
    },
    "fx": {
        "forex": 2, "fx": 2, "currency": 2, "pair": 1, "pairs": 1,
        "eurusd": 2, "usdjpy": 2, "audusd": 2, "gbpusd": 2, "usdsgd": 2,
        "central bank": 2, "fed": 2, "ecb": 2, "boj": 2, "boe": 2, "rba": 2,
        "rate hike": 2, "rate cut": 2, "rates": 1, "carry": 2, "carry trade": 2,
        "macro": 1, "cpi": 2, "nfp": 2, "gdp": 1, "trade": 1, "trade journal": 2,
        "ny session": 2, "london session": 2, "asian session": 2, "post-trade": 2,
    },
    "biz": {
        "construction": 2, "project": 1, "projects": 1, "site": 1,
        "subcontractor": 2, "subbie": 2, "vendor": 2, "supplier": 2,
        "contract": 2, "tender": 2, "quotation": 1, "invoice": 2, "invoices": 2,
        "receivable": 2, "receivables": 2, "payable": 2, "payables": 2,
        "ar aging": 2, "cashflow": 2, "cash flow": 2, "working capital": 2,
        "p&l": 2, "project p&l": 2, "margin": 1, "variance": 1,
        "company tax": 2, "corporate tax": 2, "iras": 2, "gst": 2, "wip": 2,
        "drawings": 1, "director fees": 2, "director's fees": 2,
    },
}

# When two modes tie, prefer this order (couple wins ties because joint scope
# is the safer default for a household question).
_TIEBREAK_ORDER = ["couple", "portfolio", "biz", "fx"]


def suggest_mode(question: str) -> tuple[str, str]:
    """
    Score the question against each mode's keywords and return (mode, reason).

    If nothing scores above zero, falls back to 'auto' so Peter can decide.
    """
    if not question or not question.strip():
        return "auto", "no question text"

    text = " " + question.lower() + " "
    scores: dict[str, int] = {m: 0 for m in _KEYWORDS}
    hits: dict[str, list[str]] = {m: [] for m in _KEYWORDS}

    for mode, kw_map in _KEYWORDS.items():
        for kw, weight in kw_map.items():
            # Word-boundary match for single tokens; substring for phrases.
            pattern = (
                rf"\b{re.escape(kw.strip())}\b"
                if " " not in kw.strip()
                else re.escape(kw)
            )
            if re.search(pattern, text):
                scores[mode] += weight
                hits[mode].append(kw.strip())

    top_mode = max(scores, key=lambda m: (scores[m], -_TIEBREAK_ORDER.index(m)))
    top_score = scores[top_mode]

    if top_score == 0:
        return "auto", "no clear domain — letting Peter pick across all four skills"

    runner_up = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0
    if top_score - runner_up <= 1 and runner_up > 0:
        # Close call — flag it
        runners = [m for m, s in scores.items() if s == runner_up and m != top_mode]
        runner_label = f" (close call vs. {', '.join(runners)})" if runners else ""
    else:
        runner_label = ""

    keywords_used = ", ".join(hits[top_mode][:4])
    reason = f"matched on {keywords_used}{runner_label}"
    return top_mode, reason


def format_suggestion(mode: str, reason: str) -> str:
    """Short one-line tag suitable for prepending to Peter's reply."""
    if mode == "auto":
        return f"📍 Peter: auto — {reason}"
    return f"📍 Peter routed to *{mode}* — {reason}"
