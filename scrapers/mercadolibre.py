from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional

from playwright.sync_api import sync_playwright

from core.exchange_rate import convert_ars_to_usd

logger = logging.getLogger(__name__)

ML_CATEGORY = "MLA1743"
# Default ML sort = relevance/recent.  We removed `_OrderId_PRICE` (ascending
# price) because that sort biased the 1000-listing cap toward the cheapest
# spam/plan-de-ahorro listings, leaving brands like Toyota/Hilux unrepresented.
ML_BASE_URL = "https://autos.mercadolibre.com.ar/autos/desde-2016/_NoIndex_True"

# ML now serves an empty shell page (or redirects to account-verification)
# for unauthenticated requests/sessions originating from servers.  Plain
# requests get a 5KB stub.  Playwright (real Chromium) passes the check
# and returns the full polycard-embedded HTML.

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Items per page on ML website (fixed at 48 for grid view).
_PAGE_SIZE = 48


class MercadoLibreScraper:
    def __init__(self, usd_rate):
        self.usd_rate = usd_rate
        self._pw = None
        self._browser = None
        self._context = None

    def _ensure_browser(self):
        if self._context is not None:
            return
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=_UA,
            locale="es-AR",
        )

    def _close_browser(self):
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._pw:
            self._pw.stop()
            self._pw = None

    # ------------------------------------------------------------------
    # Legacy API-style parse_listing – kept for backward compatibility
    # with callers that already have API-shaped dicts (and for tests).
    # ------------------------------------------------------------------

    def _get_attr(self, attributes, attr_id):
        for attr in attributes:
            if attr.get("id") == attr_id:
                return attr.get("value_name")
        return None

    def parse_listing(self, item):
        """Parse a single listing from the *old* API format.

        This method is retained so that existing tests and any code that
        already holds API-shaped item dicts can keep working.
        """
        attributes = item.get("attributes", [])
        brand = self._get_attr(attributes, "BRAND") or ""
        model = self._get_attr(attributes, "MODEL") or ""
        version = self._get_attr(attributes, "TRIM") or ""
        year_str = self._get_attr(attributes, "VEHICLE_YEAR")
        year = int(year_str) if year_str else None
        km_str = self._get_attr(attributes, "KILOMETERS")
        km = int("".join(filter(str.isdigit, km_str))) if km_str else None
        transmission_raw = self._get_attr(attributes, "TRANSMISSION") or ""
        transmission = transmission_raw.lower()
        fuel_raw = self._get_attr(attributes, "FUEL_TYPE") or ""
        fuel = fuel_raw.lower()

        price = float(item.get("price", 0))
        currency = item.get("currency_id", "ARS")

        if currency == "USD":
            price_usd = price
            price_ars = round(price * self.usd_rate, 2)
        else:
            price_ars = price
            price_usd = convert_ars_to_usd(price, self.usd_rate)

        location_data = item.get("location", {})
        city = location_data.get("city", {}).get("name", "")
        state = location_data.get("state", {}).get("name", "")
        location = f"{city}, {state}" if city else state

        return {
            "source": "mercadolibre",
            "source_id": item["id"],
            "url": item.get("permalink", ""),
            "brand": brand,
            "model": model,
            "version": version,
            "year": year,
            "km": km,
            "price_ars": price_ars,
            "price_usd": price_usd,
            "currency_original": currency,
            "location": location,
            "category": None,
            "transmission": transmission,
            "fuel": fuel,
            "image_url": item.get("thumbnail", ""),
        }

    # ------------------------------------------------------------------
    # New HTML-based scraping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_polycards(html: str):
        """Return a list of polycard dicts from the embedded JS blob."""
        match = re.search(r"_n\.ctx\.r=(\{.+?\});\s*</script>", html, re.DOTALL)
        if not match:
            return [], 0

        blob = match.group(1)

        # Total results count
        total = 0
        total_match = re.search(r'"total"\s*:\s*(\d+)', blob)
        if total_match:
            total = int(total_match.group(1))

        # Extract polycard JSON objects by finding them between markers.
        cards = []
        for m in re.finditer(r'"polycard"\s*:\s*\{', blob):
            start = m.start() + len('"polycard":')
            depth = 0
            end = start
            for i in range(start, min(start + 5000, len(blob))):
                if blob[i] == "{":
                    depth += 1
                elif blob[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            raw = blob[start:end]
            # Unescape unicode sequences
            raw = raw.replace("\\u002F", "/")
            try:
                card = json.loads(raw)
                cards.append(card)
            except json.JSONDecodeError:
                continue

        return cards, total

    def _parse_polycard(self, card: dict) -> Optional[dict]:
        """Convert a polycard dict into the standard listing dict."""
        metadata = card.get("metadata", {})
        item_id = metadata.get("id", "")
        if not item_id.startswith("MLA"):
            return None

        raw_url = metadata.get("url", "")
        permalink = f"https://{raw_url}" if raw_url and not raw_url.startswith("http") else raw_url

        # Extract components by type for quick lookup
        components = {c["type"]: c for c in card.get("components", []) if "type" in c}

        # Title / brand / model
        title_comp = components.get("title", {})
        title_text = title_comp.get("title", {}).get("text", "")

        # Price
        price_comp = components.get("price", {})
        current_price = price_comp.get("price", {}).get("current_price", {})
        price_value = float(current_price.get("value", 0))
        currency = current_price.get("currency", "ARS")

        if currency == "USD":
            price_usd = price_value
            price_ars = round(price_value * self.usd_rate, 2)
        else:
            price_ars = price_value
            price_usd = convert_ars_to_usd(price_value, self.usd_rate)

        # Attributes list  e.g. ["2025", "7.000 Km"]
        attrs_comp = components.get("attributes_list", {})
        attr_texts = attrs_comp.get("attributes_list", {}).get("texts", [])

        year = None
        km = None
        for text in attr_texts:
            text_stripped = text.strip()
            if re.match(r"^\d{4}$", text_stripped):
                year = int(text_stripped)
            elif "km" in text_stripped.lower():
                digits = "".join(filter(str.isdigit, text_stripped))
                if digits:
                    km = int(digits)

        # Location  e.g. "Capital Federal - Capital Federal"
        loc_comp = components.get("location", {})
        location = loc_comp.get("location", {}).get("text", "")

        # Image
        pictures = card.get("pictures", {}).get("pictures", [])
        image_url = ""
        if pictures:
            pic_id = pictures[0].get("id", "")
            if pic_id:
                image_url = f"https://http2.mlstatic.com/D_{pic_id}-O.jpg"

        # Try to extract brand from title (first word is typically the brand)
        title_parts = title_text.split()
        brand = title_parts[0] if title_parts else ""
        model = " ".join(title_parts[1:3]) if len(title_parts) > 1 else ""
        version = " ".join(title_parts[3:]) if len(title_parts) > 3 else ""

        return {
            "source": "mercadolibre",
            "source_id": item_id,
            "url": permalink,
            "brand": brand,
            "model": model,
            "version": version,
            "year": year,
            "km": km,
            "price_ars": price_ars,
            "price_usd": price_usd,
            "currency_original": currency,
            "location": location,
            "category": None,
            "transmission": "",
            "fuel": "",
            "image_url": image_url,
        }

    # ------------------------------------------------------------------
    # Public fetch / scrape methods
    # ------------------------------------------------------------------

    def _build_url(self, offset: int) -> str:
        """Build the ML search URL for a given offset.

        MercadoLibre uses ``_Desde_<N>`` in the URL path where N is the
        1-based position of the first item on the page.
        """
        base = ML_BASE_URL
        if offset > 0:
            # Insert _Desde_N before _NoIndex_True
            base = base.replace("_NoIndex_True", f"_Desde_{offset + 1}_NoIndex_True")
        return base

    def fetch_page(self, offset=0):
        """Fetch one page of results by scraping the ML website HTML.

        Returns ``(results, total)`` matching the original API interface.
        """
        self._ensure_browser()
        url = self._build_url(offset)
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_selector("li.ui-search-layout__item", timeout=15000)
            except Exception:
                # No cards rendered — give it one more grace period
                page.wait_for_timeout(3000)
            html = page.content()
        finally:
            page.close()

        cards, total = self._extract_polycards(html)

        results = []
        seen_ids = set()
        for card in cards:
            parsed = self._parse_polycard(card)
            if parsed and parsed["source_id"] not in seen_ids:
                seen_ids.add(parsed["source_id"])
                results.append(parsed)

        return results, total

    def scrape_all(self):
        logger.info("Starting MercadoLibre scrape...")
        all_listings = []
        offset = 0
        total = None

        try:
            while total is None or offset < min(total, 1000):
                try:
                    results, total = self.fetch_page(offset)
                    all_listings.extend(results)
                    logger.info(
                        f"  Fetched {len(results)} listings "
                        f"(offset={offset}, total={total})"
                    )
                    offset += _PAGE_SIZE
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"  Error at offset {offset}: {e}")
                    break
        finally:
            self._close_browser()

        logger.info(f"MercadoLibre: {len(all_listings)} listings scraped.")
        return all_listings
