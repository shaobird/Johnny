"""
Lorrie — Chief of Finance

Lorrie tracks every dollar that flows through the construction business.
She monitors budgets, logs expenses and invoices, flags anomalies, and
keeps a live view of cash position vs plan.

Lorrie consults Mo automatically when budget context from stored
documents is needed — she doesn't guess, she checks the files.

She is methodical, precise, and commercially switched-on.
Signs off as "— Lorrie".
"""

import json
import os
from datetime import datetime, timedelta

FINANCE_LOG = "storage/finance/lorrie_log.json"
BUDGET_FILE = "storage/finance/lorrie_budget.json"


# ── Storage helpers ────────────────────────────────────────────────────────────

def _load_log() -> list:
    if os.path.exists(FINANCE_LOG):
        with open(FINANCE_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_log(log: list) -> None:
    os.makedirs(os.path.dirname(FINANCE_LOG), exist_ok=True)
    tmp = FINANCE_LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    os.replace(tmp, FINANCE_LOG)


def _load_budget() -> dict:
    if os.path.exists(BUDGET_FILE):
        with open(BUDGET_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"budgets": {}, "last_updated": ""}


def _save_budget(data: dict) -> None:
    os.makedirs(os.path.dirname(BUDGET_FILE), exist_ok=True)
    tmp = BUDGET_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, BUDGET_FILE)


# ── Expense & invoice logging ──────────────────────────────────────────────────

def log_expense(
    amount: float,
    category: str,
    description: str,
    job: str = "",
    currency: str = "SGD",
) -> str:
    """Log an expense. Category: materials/labour/overhead/equipment/other."""
    if amount <= 0:
        return f"Lorrie rejected expense: amount must be positive (got {amount}).\n\n— Lorrie"
    log = _load_log()
    log.append({
        "type": "expense",
        "ts": datetime.now().isoformat(),
        "amount": amount,
        "currency": currency,
        "category": category.lower(),
        "description": description,
        "job": job,
    })
    _save_log(log)
    return (
        f"Lorrie logged expense: {currency} {amount:.2f} — {description} [{category}]"
        f"{f' (Job: {job})' if job else ''}\n\n— Lorrie"
    )


def log_invoice(
    amount: float,
    client: str,
    description: str,
    job: str = "",
    status: str = "pending",
    currency: str = "SGD",
) -> str:
    """Log an invoice issued. Status: pending/paid/overdue."""
    if amount <= 0:
        return f"Lorrie rejected expense: amount must be positive (got {amount}).\n\n— Lorrie"
    log = _load_log()
    log.append({
        "type": "invoice",
        "ts": datetime.now().isoformat(),
        "amount": amount,
        "currency": currency,
        "client": client,
        "description": description,
        "job": job,
        "status": status,
    })
    _save_log(log)
    return (
        f"Lorrie logged invoice: {currency} {amount:.2f} → {client} — {description} [{status}]\n\n— Lorrie"
    )


def update_invoice_status(client: str, new_status: str) -> str:
    """Update an invoice status (pending → paid / overdue)."""
    log = _load_log()
    for entry in reversed(log):
        if entry.get("type") == "invoice" and client.lower() in entry.get("client", "").lower():
            old = entry["status"]
            entry["status"] = new_status
            _save_log(log)
            return f"Lorrie updated {entry['client']} invoice: {old} → {new_status}\n\n— Lorrie"
    return f"No invoice found for client matching \"{client}\".\n\n— Lorrie"


# ── Budget management ──────────────────────────────────────────────────────────

def set_budget(category: str, amount: float, period: str = "monthly", currency: str = "SGD") -> str:
    """Set a budget limit for a category. Period: monthly/quarterly/annual."""
    data = _load_budget()
    data["budgets"][category.lower()] = {
        "amount": amount,
        "period": period,
        "currency": currency,
    }
    data["last_updated"] = datetime.now().isoformat()
    _save_budget(data)
    return f"Lorrie set {period} budget — {category}: {currency} {amount:,.2f}\n\n— Lorrie"


def get_budget_status() -> str:
    """Compare actual spend vs budget for the current period, with Mo's doc context."""
    log = _load_log()
    budget = _load_budget()

    # Sub-agent: pull relevant stored budget/contract docs from Mo
    mo_context_str = ""
    try:
        from agents.mo import get_context as mo_context
        mo_context_str = mo_context("budget expense cost forecast")
    except Exception:
        pass

    budgets = budget.get("budgets", {})
    if not budgets:
        note = "\n\nNo budgets set yet. Use set_budget to define limits per category."
        return f"━━━ LORRIE'S BUDGET STATUS ━━━{note}\n\n— Lorrie"

    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    monthly = [e for e in log if e["type"] == "expense" and e.get("ts", "") >= month_start]

    by_cat: dict = {}
    for e in monthly:
        cat = e.get("category", "other")
        by_cat[cat] = by_cat.get(cat, 0) + e["amount"]

    days_in_month = 30
    days_elapsed = now.day
    month_pct = days_elapsed / days_in_month

    lines = [f"━━━ LORRIE'S BUDGET STATUS ({now.strftime('%B %Y')}) ━━━\n"]
    lines.append(f"{'Category':<14} {'Budget':>10} {'Actual':>10} {'Used%':>7} {'Status'}")
    lines.append("─" * 58)

    for cat, b in sorted(budgets.items()):
        actual = by_cat.get(cat, 0)
        limit = b["amount"]
        pct = actual / limit * 100 if limit > 0 else 0
        expected_pct = month_pct * 100

        if pct >= 100:
            status = "❌ OVER"
        elif pct >= 90:
            status = "⚠️  NEAR"
        elif pct > expected_pct + 20:
            status = "📈 AHEAD"
        else:
            status = "✅ OK"

        lines.append(f"{cat.title():<14} {b['currency']} {limit:>8,.0f} {b['currency']} {actual:>8,.0f} {pct:>6.1f}% {status}")

    total_budget = sum(b["amount"] for b in budgets.values())
    total_actual = sum(by_cat.get(cat, 0) for cat in budgets)
    total_pct = total_actual / total_budget * 100 if total_budget > 0 else 0
    lines.append("─" * 58)
    lines.append(f"{'TOTAL':<14} SGD {total_budget:>8,.0f} SGD {total_actual:>8,.0f} {total_pct:>6.1f}%")

    if mo_context_str and mo_context_str.strip() and "No files" not in mo_context_str:
        lines.append(f"\n📂 FROM MO'S FILES:\n{mo_context_str[:400]}")

    lines.append("\n— Lorrie")
    return "\n".join(lines)


def get_finance_summary(days: int = 30) -> str:
    """Summarise income vs expenses over the last N days."""
    log = _load_log()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    recent = [e for e in log if e.get("ts", "") >= cutoff]

    if not recent:
        return f"No finance entries in the last {days} days. Start logging expenses and invoices.\n\n— Lorrie"

    expenses = [e for e in recent if e["type"] == "expense"]
    invoices = [e for e in recent if e["type"] == "invoice"]
    total_expenses = sum(e["amount"] for e in expenses)
    total_invoiced = sum(i["amount"] for i in invoices)
    total_paid = sum(i["amount"] for i in invoices if i.get("status") == "paid")
    total_pending = sum(i["amount"] for i in invoices if i.get("status") == "pending")
    total_overdue = sum(i["amount"] for i in invoices if i.get("status") == "overdue")

    by_cat: dict = {}
    for e in expenses:
        cat = e.get("category", "other")
        by_cat[cat] = by_cat.get(cat, 0) + e["amount"]

    lines = [f"━━━ LORRIE'S FINANCE SUMMARY (last {days} days) ━━━\n"]
    lines.append(f"💸 EXPENSES: SGD {total_expenses:,.2f}")
    for cat, amt in sorted(by_cat.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"   • {cat}: SGD {amt:,.2f}")

    lines += [
        f"\n🧾 INVOICED: SGD {total_invoiced:,.2f}",
        f"   • Paid:    SGD {total_paid:,.2f}",
        f"   • Pending: SGD {total_pending:,.2f}",
        f"   • Overdue: SGD {total_overdue:,.2f}",
        f"\n📊 NET (paid − expenses): SGD {total_paid - total_expenses:,.2f}",
    ]

    if total_overdue > 0:
        overdue_clients = list({i["client"] for i in invoices if i.get("status") == "overdue"})
        lines.append(f"\n⚠️  OVERDUE from: {', '.join(overdue_clients)}")

    lines.append("\n— Lorrie")
    return "\n".join(lines)


def get_job_summary(job: str) -> str:
    """Summarise all expenses and invoices for a specific job."""
    log = _load_log()
    job_entries = [e for e in log if e.get("job", "").lower() == job.lower()]

    if not job_entries:
        return f"No entries logged for job \"{job}\".\n\n— Lorrie"

    expenses = [e for e in job_entries if e["type"] == "expense"]
    invoices = [e for e in job_entries if e["type"] == "invoice"]
    total_cost = sum(e["amount"] for e in expenses)
    total_billed = sum(i["amount"] for i in invoices)

    lines = [
        f"━━━ JOB: {job.upper()} ━━━\n",
        f"Total costs:  SGD {total_cost:,.2f}",
        f"Total billed: SGD {total_billed:,.2f}",
        f"Gross margin: SGD {total_billed - total_cost:,.2f}",
        f"\nExpenses ({len(expenses)}):",
    ]
    for e in expenses:
        lines.append(f"  [{e['ts'][:10]}] {e['description']} — SGD {e['amount']:.2f}")
    lines.append(f"\nInvoices ({len(invoices)}):")
    for i in invoices:
        lines.append(f"  [{i['ts'][:10]}] {i['client']} — SGD {i['amount']:.2f} [{i['status']}]")

    lines.append("\n— Lorrie")
    return "\n".join(lines)


# ── Dashboard alerts ───────────────────────────────────────────────────────────

def check_alerts() -> list:
    """Return a list of finance alerts for the dashboard."""
    alerts = []
    log = _load_log()
    budget = _load_budget()

    # Overdue invoices
    for entry in log:
        if entry["type"] == "invoice" and entry.get("status") == "overdue":
            alerts.append({
                "agent": "Lorrie",
                "priority": "high",
                "category": "finance",
                "message": (
                    f"Invoice overdue — {entry['client']}, "
                    f"{entry.get('currency', 'SGD')} {entry['amount']:,.2f}"
                    + (f" (Job: {entry['job']})" if entry.get('job') else "")
                ),
            })

    # Budget tracking (current month)
    budgets = budget.get("budgets", {})
    if budgets:
        now = datetime.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        monthly = [e for e in log if e["type"] == "expense" and e.get("ts", "") >= month_start]
        by_cat: dict = {}
        for e in monthly:
            cat = e.get("category", "other")
            by_cat[cat] = by_cat.get(cat, 0) + e["amount"]

        for cat, b in budgets.items():
            actual = by_cat.get(cat, 0)
            limit = b["amount"]
            pct = actual / limit * 100 if limit > 0 else 0
            if pct >= 100:
                alerts.append({
                    "agent": "Lorrie",
                    "priority": "high",
                    "category": "finance",
                    "message": f"{cat.title()} budget exceeded — {pct:.0f}% used (SGD {actual:,.0f} / {limit:,.0f})",
                })
            elif pct >= 85:
                alerts.append({
                    "agent": "Lorrie",
                    "priority": "medium",
                    "category": "finance",
                    "message": f"{cat.title()} budget at {pct:.0f}% — SGD {limit - actual:,.0f} remaining this month",
                })

    # Pending invoices older than 30 days
    cutoff_30 = (datetime.now() - timedelta(days=30)).isoformat()
    old_pending = [
        e for e in log
        if e["type"] == "invoice"
        and e.get("status") == "pending"
        and e.get("ts", "") < cutoff_30
    ]
    if old_pending:
        total = sum(i["amount"] for i in old_pending)
        alerts.append({
            "agent": "Lorrie",
            "priority": "medium",
            "category": "finance",
            "message": f"{len(old_pending)} invoice(s) pending >30 days — SGD {total:,.2f} uncollected",
        })

    return alerts
