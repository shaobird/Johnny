"""
Peter — Chief of Investment

Peter manages investment strategy, forex positioning, and capital allocation
for the business and personal portfolio. He does NOT handle day-to-day
bookkeeping — that's Lorrie's domain.

Peter calls Smarty's news feed before giving any trading advice — he never
advises blind. Sharp, numbers-first, and opinionated about where to put money
to work. Signs off as "— Peter".
"""

import json
import os
from datetime import datetime

TRADE_LOG = "storage/finance/peter_trades.json"


# ── Storage helpers ────────────────────────────────────────────────────────────

def _load_trade_log() -> list:
    if os.path.exists(TRADE_LOG):
        with open(TRADE_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_trade_log(log: list) -> None:
    os.makedirs(os.path.dirname(TRADE_LOG), exist_ok=True)
    tmp = TRADE_LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    os.replace(tmp, TRADE_LOG)


# ── Trade logging ──────────────────────────────────────────────────────────────

def log_trade(
    pair: str,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    rationale: str,
    size: float = 1.0,
) -> str:
    """Log a new forex/investment trade. Direction: long/short."""
    log = _load_trade_log()
    divisor = 100 if "JPY" in pair.upper() else 10000
    risk = abs(entry - sl) * size * divisor
    reward = abs(tp - entry) * size * divisor
    rr = round(reward / risk, 2) if risk > 0 else 0

    log.append({
        "ts": datetime.now().isoformat(),
        "pair": pair.upper(),
        "direction": direction.lower(),
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "size": size,
        "rationale": rationale,
        "status": "open",
        "rr_ratio": rr,
        "exit_price": None,
        "exit_ts": None,
        "pnl_pips": None,
    })
    _save_trade_log(log)
    return (
        f"Peter logged: {direction.upper()} {pair.upper()} @ {entry} "
        f"| SL {sl} | TP {tp} | R:R {rr} | Size {size}\n\n— Peter"
    )


def update_trade(pair: str, status: str, exit_price: float = 0.0, notes: str = "") -> str:
    """Close or update a trade. Status: closed/stopped/cancelled."""
    log = _load_trade_log()
    for entry in reversed(log):
        if entry.get("pair", "").upper() == pair.upper() and entry.get("status") == "open":
            entry["status"] = status
            entry["exit_ts"] = datetime.now().isoformat()
            if exit_price:
                entry["exit_price"] = exit_price
                direction = entry.get("direction", "long")
                raw = exit_price - entry["entry"] if direction == "long" else entry["entry"] - exit_price
                divisor = 100 if "JPY" in pair.upper() else 10000
                entry["pnl_pips"] = round(raw * divisor * entry.get("size", 1), 1)
            if notes:
                entry["notes"] = notes
            _save_trade_log(log)
            pnl = f" | {entry.get('pnl_pips', '?')} pips" if exit_price else ""
            return f"Peter updated {pair.upper()}: {status}{pnl}\n\n— Peter"
    return f"No open trade found for {pair.upper()}.\n\n— Peter"


def get_trade_log(open_only: bool = False) -> str:
    """Return trade history. open_only=True shows only live positions."""
    log = _load_trade_log()
    trades = [t for t in log if t.get("status") == "open"] if open_only else log

    if not trades:
        label = "open positions" if open_only else "trades"
        return f"No {label} on record.\n\n— Peter"

    lines = [f"━━━ PETER'S {'OPEN POSITIONS' if open_only else 'TRADE LOG'} ━━━\n"]
    for t in reversed(trades[-20:]):
        icon = "🟢" if t["status"] == "open" else ("🔴" if t["status"] == "stopped" else "⚪")
        pnl = f" | {t['pnl_pips']} pips" if t.get("pnl_pips") is not None else ""
        lines.append(
            f"{icon} [{t['ts'][:10]}] {t['direction'].upper()} {t['pair']} @ {t['entry']}"
            f" | SL {t['sl']} / TP {t['tp']} | R:R {t.get('rr_ratio', '?')}{pnl} [{t['status']}]"
        )
        if t.get("rationale"):
            lines.append(f"   → {t['rationale'][:80]}")

    lines.append("\n— Peter")
    return "\n".join(lines)


# ── Investment brief (sub-agent: Smarty's news feed) ─────────────────────────

def get_investment_brief() -> str:
    """
    Full investment view: open positions + track record + today's forex events.
    Pulls Smarty's news feed internally before advising — Peter never advises blind.
    """
    trade_log = _load_trade_log()
    open_trades = [t for t in trade_log if t.get("status") == "open"]
    closed = [t for t in trade_log if t.get("status") != "open"]

    # Sub-agent: Smarty's news for live market context
    forex_context = ""
    try:
        from agents.news import get_high_impact_news
        forex_context = get_high_impact_news()
    except Exception as e:
        forex_context = f"Forex calendar unavailable: {e}"

    lines = ["━━━ PETER'S INVESTMENT BRIEF ━━━\n"]

    if open_trades:
        lines.append(f"📈 OPEN POSITIONS ({len(open_trades)}):")
        for t in open_trades:
            lines.append(
                f"  {t['direction'].upper()} {t['pair']} @ {t['entry']}"
                f" | SL {t['sl']} | TP {t['tp']} | R:R {t.get('rr_ratio', '?')}"
            )
            if t.get("rationale"):
                lines.append(f"     → {t['rationale'][:60]}")
    else:
        lines.append("📈 OPEN POSITIONS: None (flat)")

    if closed:
        wins = [t for t in closed if (t.get("pnl_pips") or 0) > 0]
        win_rate = round(len(wins) / len(closed) * 100) if closed else 0
        lines.append(f"\n📊 TRACK RECORD: {len(closed)} closed | Win rate: {win_rate}%")

    lines.append(f"\n🔴 TODAY'S MARKET EVENTS (via Smarty):\n{forex_context}")
    lines.append("\n— Peter")
    return "\n".join(lines)


# ── Dashboard alerts ───────────────────────────────────────────────────────────

def check_alerts() -> list:
    """Return investment alerts for the shared dashboard."""
    alerts = []
    log = _load_trade_log()
    open_trades = [t for t in log if t.get("status") == "open"]

    if open_trades:
        pairs = ", ".join(t["pair"] for t in open_trades)
        alerts.append({
            "agent": "Peter",
            "priority": "medium",
            "category": "investment",
            "message": f"{len(open_trades)} open position(s): {pairs} — monitor SL/TP",
        })

    return alerts
