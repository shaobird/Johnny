"""
Peter — Chief of Finance

Peter manages all financial tracking for the construction business.
He reads Mo's finance files, tracks job costs, monitors budgets,
logs expenses and invoices, and flags anomalies.

Peter is precise, numbers-first, and never vague. Signs off as "— Peter".
"""

import json
import os
from datetime import datetime, timedelta

import memory as mem

FINANCE_LOG = "storage/finance/peter_log.json"


# ── Finance log helpers ───────────────────────────────────────────────────────

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


# ── Core operations ───────────────────────────────────────────────────────────

def log_expense(
    amount: float,
    category: str,
    description: str,
    job: str = "",
    currency: str = "SGD",
) -> str:
    """Log an expense. Category: materials/labour/overhead/equipment/other."""
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
    return f"Peter logged expense: {currency} {amount:.2f} — {description} [{category}]{f' (Job: {job})' if job else ''}"


def log_invoice(
    amount: float,
    client: str,
    description: str,
    job: str = "",
    status: str = "pending",
    currency: str = "SGD",
) -> str:
    """Log an invoice issued. Status: pending/paid/overdue."""
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
    return f"Peter logged invoice: {currency} {amount:.2f} → {client} — {description} [{status}]"


def get_finance_summary(days: int = 30) -> str:
    """Summarise income vs expenses over the last N days."""
    log = _load_log()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    recent = [e for e in log if e.get("ts", "") >= cutoff]

    if not recent:
        # Fall back to Mo's finance files if no log entries yet
        try:
            from agents.mo import get_context as mo_context
            mo_data = mo_context("finance budget invoice expense")
            return (
                f"No manual entries logged yet. Here's what Mo has in finance storage:\n\n"
                f"{mo_data}\n\n— Peter"
            )
        except Exception:
            return "No finance data available yet. Log expenses and invoices to get started.\n\n— Peter"

    expenses = [e for e in recent if e["type"] == "expense"]
    invoices = [e for e in recent if e["type"] == "invoice"]

    total_expenses = sum(e["amount"] for e in expenses)
    total_invoiced = sum(i["amount"] for i in invoices)
    total_paid = sum(i["amount"] for i in invoices if i.get("status") == "paid")
    total_pending = sum(i["amount"] for i in invoices if i.get("status") == "pending")
    total_overdue = sum(i["amount"] for i in invoices if i.get("status") == "overdue")

    # Expenses by category
    by_cat: dict = {}
    for e in expenses:
        cat = e.get("category", "other")
        by_cat[cat] = by_cat.get(cat, 0) + e["amount"]

    lines = [
        f"━━━ PETER'S FINANCE SUMMARY (last {days} days) ━━━\n",
        f"💸 EXPENSES: SGD {total_expenses:,.2f}",
    ]
    for cat, amt in sorted(by_cat.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"   • {cat}: SGD {amt:,.2f}")

    lines += [
        f"\n🧾 INVOICED: SGD {total_invoiced:,.2f}",
        f"   • Paid:    SGD {total_paid:,.2f}",
        f"   • Pending: SGD {total_pending:,.2f}",
        f"   • Overdue: SGD {total_overdue:,.2f}",
        f"\n📊 NET (paid - expenses): SGD {total_paid - total_expenses:,.2f}",
    ]

    if total_overdue > 0:
        overdue_clients = [i["client"] for i in invoices if i.get("status") == "overdue"]
        lines.append(f"\n⚠️  OVERDUE from: {', '.join(set(overdue_clients))}")

    lines.append("\n— Peter")
    return "\n".join(lines)


def get_job_summary(job: str) -> str:
    """Summarise all expenses and invoices for a specific job."""
    log = _load_log()
    job_entries = [e for e in log if e.get("job", "").lower() == job.lower()]

    if not job_entries:
        return f"No entries logged for job \"{job}\".\n\n— Peter"

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

    lines.append("\n— Peter")
    return "\n".join(lines)
