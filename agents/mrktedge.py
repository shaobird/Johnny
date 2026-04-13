"""
MrktEdge Agent — High Impact News Monitor
Logs into app.mrktedge.ai, scrapes the High Impact news feed,
and returns any items not yet seen.

Uses Playwright for JS-rendered content and stores session cookies
so it only needs to re-login when the session expires.

Seen items are tracked in seen_mrktedge.json to prevent duplicates.
"""

import asyncio
import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from config import MRKTEDGE_EMAIL, MRKTEDGE_PASSWORD

COOKIES_FILE = "mrktedge_cookies.json"
SEEN_FILE = "seen_mrktedge.json"
LOGIN_URL = "https://app.mrktedge.ai"
HOME_URL = "https://app.mrktedge.ai/home"


# ── Seen items tracker ────────────────────────────────────────────────────────

def _load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def _save_seen(seen: set) -> None:
    # Keep last 500 IDs to avoid unbounded growth
    items = list(seen)[-500:]
    with open(SEEN_FILE, "w") as f:
        json.dump(items, f)


def _item_id(headline: str) -> str:
    """Stable ID from headline text."""
    return hashlib.md5(headline.strip().lower().encode()).hexdigest()[:12]


# ── Cookie management ─────────────────────────────────────────────────────────

def _load_cookies() -> list | None:
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, "r") as f:
            return json.load(f)
    return None


def _save_cookies(cookies: list) -> None:
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f)


# ── Core scraper ──────────────────────────────────────────────────────────────

async def _scrape(headless: bool = True) -> list[dict]:
    """
    Login to mrktedge, navigate to High Impact news feed,
    and return a list of news items.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        # Try stored cookies first
        cookies = _load_cookies()
        if cookies:
            await context.add_cookies(cookies)

        page = await context.new_page()

        try:
            await page.goto(HOME_URL, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            await page.goto(HOME_URL, timeout=30000)

        # Check if we need to log in (redirected to login page)
        if "login" in page.url.lower() or "signin" in page.url.lower() or page.url == LOGIN_URL + "/":
            await _login(page)
            # Save cookies after login
            _save_cookies(await context.cookies())
            # Navigate to home after login
            try:
                await page.goto(HOME_URL, wait_until="networkidle", timeout=30000)
            except PlaywrightTimeout:
                pass

        # Wait for news feed to load
        try:
            await page.wait_for_selector("text=High Impact", timeout=15000)
        except PlaywrightTimeout:
            await browser.close()
            return []

        # Click the "High Impact" filter tab
        try:
            # Find and click the High Impact filter button in the news feed
            high_impact_buttons = await page.locator("text=High Impact").all()
            for btn in high_impact_buttons:
                if await btn.is_visible():
                    await btn.click()
                    break
            await page.wait_for_timeout(2000)
        except Exception:
            pass

        # Extract news items
        items = await _extract_news(page)

        # Save fresh cookies
        _save_cookies(await context.cookies())
        await browser.close()
        return items


async def _login(page) -> None:
    """Handle login — tries email/password form."""
    # Wait for login form
    await page.wait_for_load_state("networkidle")

    # Try to find email input
    try:
        await page.wait_for_selector("input[type='email'], input[name='email'], input[placeholder*='email' i]", timeout=10000)
        await page.fill("input[type='email'], input[name='email'], input[placeholder*='email' i]", MRKTEDGE_EMAIL)
    except PlaywrightTimeout:
        # Try generic text input
        await page.fill("input[type='text']", MRKTEDGE_EMAIL)

    # Fill password
    await page.fill("input[type='password']", MRKTEDGE_PASSWORD)

    # Submit
    await page.press("input[type='password']", "Enter")

    # Wait for navigation
    try:
        await page.wait_for_navigation(timeout=15000)
    except PlaywrightTimeout:
        await page.wait_for_timeout(3000)


async def _extract_news(page) -> list[dict]:
    """Extract high impact news items from the page."""
    items = []

    try:
        # Look for HIGH IMPACT tagged items in the news feed
        # The feed shows items with "HIGH IMPACT" badge
        await page.wait_for_timeout(1000)

        # Get all news card elements — try multiple selectors
        selectors = [
            "[class*='news-item']",
            "[class*='newsItem']",
            "[class*='feed-item']",
            "[class*='article']",
            "[class*='card']",
        ]

        cards = []
        for sel in selectors:
            found = await page.locator(sel).all()
            if found:
                cards = found
                break

        # If no specific selector works, get all text content from news feed area
        if not cards:
            # Fall back: grab all HIGH IMPACT labeled sections
            content = await page.inner_text("body")
            items = _parse_text_fallback(content)
            return items

        for card in cards[:20]:  # cap at 20 items
            try:
                text = await card.inner_text()
                if not text.strip():
                    continue

                # Parse the card text
                item = _parse_card_text(text)
                if item:
                    items.append(item)
            except Exception:
                continue

    except Exception as e:
        print(f"[MrktEdge] Extraction error: {e}")

    return items


def _parse_card_text(text: str) -> dict | None:
    """Parse raw card text into structured news item."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return None

    # Must contain HIGH IMPACT to be relevant
    combined = " ".join(lines).upper()
    if "HIGH IMPACT" not in combined:
        return None

    # Find headline — typically the longest uppercase-heavy line
    headline = ""
    summary = ""
    timestamp = ""
    pairs = []

    for i, line in enumerate(lines):
        if "HIGH IMPACT" in line.upper():
            continue
        if any(c.isdigit() for c in line) and ("PM" in line or "AM" in line or "ago" in line.lower()):
            timestamp = line
            continue
        # Currency pairs (e.g. USDCAD ↓ -0.05%)
        if any(pair in line for pair in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "XAU", "XAG"]) and any(c in line for c in ["↓", "↑", "+", "-", "%"]):
            pairs.append(line)
            continue
        # Headline = first substantial all-caps line
        if not headline and len(line) > 20 and line == line.upper():
            headline = line
        elif not summary and len(line) > 20 and headline:
            summary = line

    if not headline:
        # Take first long line as headline
        for line in lines:
            if len(line) > 30 and "HIGH IMPACT" not in line.upper():
                headline = line
                break

    if not headline:
        return None

    return {
        "headline": headline,
        "summary": summary,
        "timestamp": timestamp,
        "pairs": pairs,
        "raw": text[:500],
    }


def _parse_text_fallback(content: str) -> list[dict]:
    """Fallback: parse raw page text for HIGH IMPACT items."""
    items = []
    lines = content.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "HIGH IMPACT" in line.upper() and len(line) < 50:
            # Next substantial line is likely the headline
            headline = ""
            summary = ""
            timestamp = ""
            for j in range(i + 1, min(i + 10, len(lines))):
                l = lines[j].strip()
                if not l:
                    continue
                if not headline and len(l) > 20:
                    headline = l
                elif not summary and len(l) > 20:
                    summary = l
                if headline and summary:
                    break
            if headline:
                items.append({
                    "headline": headline,
                    "summary": summary,
                    "timestamp": timestamp,
                    "pairs": [],
                    "raw": "\n".join(lines[i:i+10]),
                })
        i += 1

    return items


# ── Public API ────────────────────────────────────────────────────────────────

def check_new_items() -> list[dict]:
    """
    Synchronous wrapper — checks for new HIGH IMPACT items.
    Returns only items not yet seen. Updates seen tracker.
    """
    try:
        all_items = asyncio.run(_scrape())
    except Exception as e:
        print(f"[MrktEdge] Scrape failed: {e}")
        return []

    seen = _load_seen()
    new_items = []

    for item in all_items:
        item_id = _item_id(item["headline"])
        if item_id not in seen:
            new_items.append(item)
            seen.add(item_id)

    if new_items:
        _save_seen(seen)

    return new_items


def format_item(item: dict) -> str:
    """Format a news item for Telegram."""
    lines = ["🔴 *HIGH IMPACT ALERT*"]

    if item.get("timestamp"):
        lines.append(f"🕐 {item['timestamp']}")

    lines.append(f"\n{item['headline']}")

    if item.get("summary"):
        lines.append(f"\n_{item['summary']}_")

    if item.get("pairs"):
        lines.append("\n*Pairs affected:*")
        for pair in item["pairs"]:
            lines.append(f"  • {pair}")

    return "\n".join(lines)


if __name__ == "__main__":
    items = check_new_items()
    if items:
        for item in items:
            print(format_item(item))
            print("---")
    else:
        print("No new HIGH IMPACT items.")
