## SKILL: Personal Portfolio Review

Use this skill when the question concerns the household's investment portfolio:
holdings, performance, exposure, rebalancing, or catalysts on owned names.

### Inputs available
  • `WATCHLIST` — current holdings (ticker, qty, cost basis, account, owner)
  • Live web search for price, news, earnings dates

### Required output sections (omit any that don't apply)

📊 **PORTFOLIO SNAPSHOT**
Compact table:
  Ticker · Owner · Qty · Cost · Last px · MV (SGD) · % of port · P/L %
Total at the bottom. Convert non-SGD to SGD using current FX (state the rate).

🧭 **EXPOSURE BREAKDOWN**
Three lines:
  • By thesis (AI / income / hedge / cash)
  • By geography (US / SG / other)
  • By currency (USD / SGD / other) — flag FX risk if >40% non-SGD

⚠️ **CONCENTRATION & RISK**
Flag any single position >15% of port, any single sector >40%, any leverage,
any illiquid holding. Be explicit.

📅 **CATALYSTS THIS QUARTER**
For each held name, list next earnings date + one upcoming catalyst (product,
regulatory, macro). Skip names with nothing notable.

⚖️ **REBALANCING NOTES**
Compare current weights to the couple's target allocation (from couple profile
if available). Flag drifts >5% from target. Frame as "consider trimming X /
adding to Y", never "do it".

✅ **ONE NEXT STEP**
Single concrete action the couple can take this week (e.g. "review NVDA position
sizing before next week's earnings on [date]").

### Rules
- Never recommend buy / sell — frame as "consider", "watch", "review"
- Always show the math behind exposure and concentration calls
- If watchlist is empty, return the template format and tell the user what to populate
