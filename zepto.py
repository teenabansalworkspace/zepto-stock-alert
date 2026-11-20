"""Zepto checker.

Works like a normal visitor in a (headless) browser:
  1. open zepto.com and choose the delivery location with the site's own location box (pincode),
  2. open each product page and read whether it shows "Add to Cart" or "Notify Me",
     plus the quantity the page itself carries for that product.
"""
import json
import random
import re
import time
from urllib.parse import unquote

import config

PVID_RE = re.compile(r"zepto\.com/.*?/pvid/([0-9a-fA-F-]{36})")
HOME = "https://www.zepto.com/"
# a normal product page; it also has the "Select Location" button
FALLBACK_PAGE = "https://www.zepto.com/pn/oppo-k14x-5g-smartphone-prism-violet-4gb-ram-128gb-storage/pvid/eb012377-49a9-4980-9af5-f66648195768"


# ---------------------------------------------------------------- pure helpers (unit-tested)
def extract_pvid(url: str):
    m = PVID_RE.search(url or "")
    return m.group(1).lower() if m else None


def clean_url(url: str) -> str:
    """Product link without tracking junk, keeping marketplaceType if present."""
    url = url.strip()
    base = url.split("?", 1)[0]
    if "marketplaceType=" in url:
        mt = re.search(r"marketplaceType=([A-Z_]+)", url)
        if mt:
            return f"{base}?marketplaceType={mt.group(1)}"
    return base


def _unescape(html: str) -> str:
    # Next.js puts the page data inside JS strings, so quotes arrive escaped once or twice.
    return html.replace('\\\\\\"', '"').replace('\\"', '"')


def parse_product_page(html: str, pvid: str) -> dict:
    """Return {name, qty, oos_flag} from a product page's HTML."""
    text = _unescape(html)
    out = {"name": None, "qty": None, "oos_flag": None}

    # Name: JSON-LD Product block, else <title>
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Product" and item.get("name"):
                out["name"] = item["name"].strip()
                break
        if out["name"]:
            break
    if not out["name"]:
        t = re.search(r"<title>(.*?)</title>", html, re.S)
        if t:
            out["name"] = re.split(r"\s+-\s+Buy at", t.group(1))[0].strip() or None

    # Quantity: the "storeProduct" object that follows this product's own {"id":"<pvid>"}
    marker = f'"id":"{pvid}"'
    parts = text.split('"storeProduct":{')
    for i in range(1, len(parts)):
        if marker in parts[i - 1]:
            m = re.match(r'"availableQuantity":(\d+)', parts[i])
            out["qty"] = int(m.group(1)) if m else 0
            break

    flag = re.search(r'"isOutOfStock":(true|false)', text)
    if flag:
        out["oos_flag"] = flag.group(1) == "true"
    return out


def decide_stock(button_state: str, parsed: dict):
    """Combine the visible button and the page data. Returns (in_stock or None, qty or None)."""
    qty = parsed.get("qty")
    if button_state == "add":
        return True, (qty if qty else None)
    if button_state == "notify":
        return False, 0
    # No button found: fall back to page data
    if qty is not None:
        return qty > 0, qty
    if parsed.get("oos_flag") is not None:
        return (not parsed["oos_flag"]), None
    return None, None


def parse_serviceability(cookie_value: str) -> dict:
    try:
        data = json.loads(unquote(cookie_value))
    except Exception:
        return {"serviceable": False, "store": None, "deliverable": False}
    primary = data.get("primaryStore") or {}
    return {
        "serviceable": bool(primary.get("serviceable")),
        "deliverable": bool(primary.get("isDeliverable")),
        "store": primary.get("storeId"),
    }


# ---------------------------------------------------------------- browser part
class ZeptoChecker:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        args = ["--window-position=-32000,-32000"] if (not config.HEADLESS and config.HIDE_WINDOW) else []
        self.browser = self._pw.chromium.launch(headless=config.HEADLESS, args=args)

    def close(self):
        try:
            self.browser.close()
        finally:
            self._pw.stop()

    @staticmethod
    def _pause():
        time.sleep(random.uniform(*config.PAUSE_BETWEEN_PAGES))

    OPENERS = [
        'button[aria-haspopup="dialog"]',
        'button:has-text("Select Location")',
        '[data-testid*="location" i]',
        'text=Select Location',
    ]

    def _open_picker(self, page):
        """Load Zepto and open the location box. Retries once with a reload (bot-check pages)."""
        box = page.locator('input[placeholder="Search a new address"]')
        for attempt in range(2):
            page.goto(HOME if attempt == 0 else FALLBACK_PAGE, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            # wait until the real site (not a check/blank page) has drawn its header
            for _ in range(20):
                if box.is_visible() or any(page.locator(s).first.is_visible() for s in self.OPENERS):
                    break
                page.wait_for_timeout(1000)
            if box.is_visible():
                return
            for sel in self.OPENERS:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click()
                    try:
                        box.wait_for(state="visible", timeout=10000)
                        return
                    except Exception:
                        continue
        raise RuntimeError(f"Location button nahi mila. Page title: {page.title()!r}, url: {page.url}")

    @staticmethod
    def save_debug(page, name: str) -> None:
        """Screenshot + page text in the debug/ folder so we can see what the browser got."""
        try:
            config.DEBUG_DIR.mkdir(exist_ok=True)
            page.screenshot(path=str(config.DEBUG_DIR / f"{name}.png"), full_page=False)
            (config.DEBUG_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
            body = page.locator("body").inner_text(timeout=5000)[:400].replace("\n", " | ")
            print(f"[debug] title={page.title()!r} url={page.url}\n[debug] page text: {body}")
            print(f"[debug] screenshot: {config.DEBUG_DIR / (name + '.png')}")
        except Exception as exc:
            print(f"[debug] could not save debug info: {exc}")

    def open_location(self, query: str):
        """New browser context with the delivery location set. Returns (context, page, info)."""
        ctx = self.browser.new_context(locale="en-IN", timezone_id="Asia/Kolkata",
                                       viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(30000)
        try:
            self._open_picker(page)
        except Exception:
            self.save_debug(page, f"location_{query}")
            ctx.close()
            raise
        box = page.locator('input[placeholder="Search a new address"]')
        box.click()
        box.fill("")
        box.type(query, delay=90)

        items = page.locator('[data-testid="address-search-item"]')
        items.first.wait_for(state="visible", timeout=20000)
        page.wait_for_timeout(800)
        matching = page.locator('[data-testid="address-search-item"]', has_text=query)
        target = matching.first if matching.count() else items.first
        chosen = " ".join(target.inner_text().split())
        target.click()

        info = {"serviceable": False, "store": None, "deliverable": False}
        for _ in range(30):
            page.wait_for_timeout(500)
            cookie = next((c for c in ctx.cookies() if c["name"] == "serviceability"), None)
            if cookie:
                info = parse_serviceability(cookie["value"])
                if info["store"]:
                    break
        # The exact address Zepto now uses (shown in its header), so you can pick the same one in the app
        place = chosen
        try:
            header = page.locator('button[aria-haspopup="dialog"]').first
            if header.count():
                text = " ".join(header.inner_text(timeout=3000).split())
                if text and "select location" not in text.lower():
                    place = text
        except Exception:
            pass
        info["place"] = place
        info["chosen"] = chosen
        return ctx, page, info

    def check_product(self, page, url: str, pvid: str) -> dict:
        self._pause()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        add = page.locator('button:has-text("Add to Cart")')
        notify = page.locator('button:has-text("Notify Me")')
        button_state = "none"
        try:
            page.locator('button:has-text("Add to Cart"), button:has-text("Notify Me")').first.wait_for(timeout=20000)
        except Exception:
            pass
        if add.count() and add.first.is_visible():
            button_state = "add"
        elif notify.count() and notify.first.is_visible():
            button_state = "notify"
        parsed = parse_product_page(page.content(), pvid)
        in_stock, qty = decide_stock(button_state, parsed)
        return {"in_stock": in_stock, "qty": qty, "name": parsed.get("name")}
