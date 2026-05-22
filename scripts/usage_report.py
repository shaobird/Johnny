#!/usr/bin/env python3
"""
Usage report — shows API cost breakdown from usage_log.json.

Run: python scripts/usage_report.py

Pricing (Anthropic, May 2026):
  Opus 4.7   — $15 / 1M input,  $75 / 1M output
  Sonnet 4.6 — $3  / 1M input,  $15 / 1M output
  Haiku 4.5  — $0.80 / 1M input, $4 / 1M output
"""

import json, os, sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USAGE_LOG = "usage_log.json"

# Prices per 1M tokens (USD)
PRICING = {
    "claude-opus-4-7":          {"in": 15.00, "out": 75.00},
    "claude-sonnet-4-6":        {"in":  3.00, "out": 15.00},
    "claude-haiku-4-5-20251001":{"in":  0.80, "out":  4.00},
}
DEFAULT_PRICE = {"in": 3.00, "out": 15.00}  # Sonnet as fallback


def cost(tokens_in, tokens_out, model="claude-sonnet-4-6"):
    p = PRICING.get(model, DEFAULT_PRICE)
    return (tokens_in * p["in"] + tokens_out * p["out"]) / 1_000_000


def main():
    if not os.path.exists(USAGE_LOG):
        print("No usage log found. Run main.py first and send some messages.")
        return

    with open(USAGE_LOG) as f:
        log = json.load(f)

    if not log:
        print("Usage log is empty.")
        return

    now = datetime.now()
    today     = [e for e in log if e["ts"][:10] == now.strftime("%Y-%m-%d")]
    this_week = [e for e in log if datetime.fromisoformat(e["ts"]) >= now - timedelta(days=7)]

    def summarise(entries, label):
        if not entries:
            print(f"\n{label}: no data")
            return
        total_in  = sum(e.get("input_tokens", 0) for e in entries)
        total_out = sum(e.get("output_tokens", 0) for e in entries)
        # Use Sonnet pricing as default (most calls are Sonnet)
        total_cost = cost(total_in, total_out)
        # Rough estimate: Opus calls cost ~5x more
        print(f"\n{'━'*45}")
        print(f"  {label}  ({len(entries)} API calls)")
        print(f"{'━'*45}")
        print(f"  Input tokens:   {total_in:>10,}")
        print(f"  Output tokens:  {total_out:>10,}")
        print(f"  Est. cost (USD): ${total_cost:.4f}   ← Sonnet baseline")
        print(f"  Note: Opus calls cost ~5x this. Check console.anthropic.com for exact.")

    summarise(today, "TODAY")
    summarise(this_week, "LAST 7 DAYS")
    summarise(log, "ALL TIME")

    print(f"\n{'━'*45}")
    print("  Exact billing: console.anthropic.com → Usage")
    print(f"{'━'*45}\n")


if __name__ == "__main__":
    main()
