"""
Shared dashboard — aggregates alerts from all agents in parallel.

Each agent exposes check_alerts() -> list[dict] with keys:
  agent, priority (high/medium/low), category, message

Johnny calls get_full_dashboard() to surface what needs attention.
"""

import concurrent.futures
from datetime import datetime


def get_full_dashboard() -> str:
    """Pull alerts from all agents in parallel and return a prioritised dashboard."""
    from agents.lorrie import check_alerts as lorrie_alerts
    from agents.peter import check_alerts as peter_alerts
    from agents.kanaan import check_alerts as kanaan_alerts
    from agents.newsletter import check_alerts as sally_alerts

    alert_fns = {
        "lorrie": lorrie_alerts,
        "peter":  peter_alerts,
        "kanaan": kanaan_alerts,
        "sally":  sally_alerts,
    }

    all_alerts: list = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {name: executor.submit(fn) for name, fn in alert_fns.items()}
        for name, fut in futures.items():
            try:
                all_alerts.extend(fut.result(timeout=15))
            except Exception:
                pass  # failing agent doesn't break the dashboard

    priority_order = {"high": 0, "medium": 1, "low": 2}
    all_alerts.sort(key=lambda a: priority_order.get(a.get("priority", "medium"), 1))

    if not all_alerts:
        return (
            f"━━━ DASHBOARD ━━━\n\n"
            f"All clear — no items requiring attention.\n\n"
            f"— {datetime.now().strftime('%d %b %Y, %H:%M')}"
        )

    high   = [a for a in all_alerts if a["priority"] == "high"]
    medium = [a for a in all_alerts if a["priority"] == "medium"]
    low    = [a for a in all_alerts if a["priority"] == "low"]

    lines = ["━━━ DASHBOARD: ITEMS REQUIRING ATTENTION ━━━\n"]

    if high:
        lines.append(f"🔴 HIGH ({len(high)}):")
        for a in high:
            lines.append(f"  [{a['agent'].upper()}] {a['message']}")

    if medium:
        lines.append(f"\n🟡 MEDIUM ({len(medium)}):")
        for a in medium:
            lines.append(f"  [{a['agent'].upper()}] {a['message']}")

    if low:
        lines.append(f"\n🔵 LOW ({len(low)}):")
        for a in low:
            lines.append(f"  [{a['agent'].upper()}] {a['message']}")

    lines.append(f"\n— Refreshed {datetime.now().strftime('%d %b %Y, %H:%M')}")
    return "\n".join(lines)
