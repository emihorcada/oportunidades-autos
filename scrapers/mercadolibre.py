from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Optional

import requests

from core.exchange_rate import convert_ars_to_usd

logger = logging.getLogger(__name__)

ML_CATEGORY = "MLA1743"
# Default ML sort = relevance/recent.  We removed `_OrderId_PRICE` (ascending
# price) because that sort biased the 1000-listing cap toward the cheapest
# spam/plan-de-ahorro listings, leaving brands like Toyota/Hilux unrepresented.
ML_BASE_URL = "https://autos.mercadolibre.com.ar/autos/desde-2016/_NoIndex_True"

# ML blocks unauthenticated server requests (5KB stub or account-verification
# redirect).  We use Firecrawl with stealth proxy to bypass — they rotate
# residential IPs and handle fingerprinting.  The raw HTML they return is
# the same the browser sees, so the existing polycard parser works unchanged.

_FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"

# Items per page on ML website (fixed at 48 for grid view).
_PAGE_SIZE = 48


def _get_firecrawl_key() -> str:
    key = os.environ.get("FIRECRAWL_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets["FIRECRAWL_API_KEY"]
    except Exception:
        raise RuntimeError(
            "FIRECRAWL_API_KEY not set. Add it to .streamlit/secrets.toml or env."
        )


class MercadoLibreScraper:
    def __init__(self, usd_rate):
        self.usd_rate = usd_rate
        self._fc_key = _get_firecrawl_key()

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
        url = self._build_url(offset)
        resp = requests.post(
            _FIRECRAWL_URL,
            headers={
                "Authorization": f"Bearer {self._fc_key}",
                "Content-Type": "application/json",
            },
            json={
                "url": url,
                "formats": ["rawHtml"],
                "proxy": "stealth",
                "onlyMainContent": False,
            },
            timeout=120,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Firecrawl HTTP {resp.status_code}: {resp.text[:300]}")
        payload = resp.json()
        if not payload.get("success"):
            raise RuntimeError(f"Firecrawl scrape failed: {payload}")
        html = payload.get("data", {}).get("rawHtml", "")

        cards, total = self._extract_polycards(html)

        results = []
        seen_ids = set()
        for card in cards:
            parsed = self._parse_polycard(card)
            if parsed and parsed["source_id"] not in seen_ids:
                seen_ids.add(parsed["source_id"])
                results.append(parsed)

        return results, total

    def _scrape_url(self, url: str):
        """Scrape a single ML search URL and return parsed listings + total."""
        resp = requests.post(
            _FIRECRAWL_URL,
            headers={
                "Authorization": f"Bearer {self._fc_key}",
                "Content-Type": "application/json",
            },
            json={
                "url": url,
                "formats": ["rawHtml"],
                "proxy": "stealth",
                "onlyMainContent": False,
            },
            timeout=120,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Firecrawl HTTP {resp.status_code}: {resp.text[:300]}")
        payload = resp.json()
        if not payload.get("success"):
            raise RuntimeError(f"Firecrawl scrape failed: {payload}")
        html = payload.get("data", {}).get("rawHtml", "")
        cards, total = self._extract_polycards(html)
        results = []
        seen = set()
        for c in cards:
            p = self._parse_polycard(c)
            if p and p["source_id"] not in seen:
                seen.add(p["source_id"])
                results.append(p)
        return results, total

    def scrape_brand_model_year(self, brand: str, model_token: str, year: int, max_pages: int = 3):
        """Scrape ML for a specific brand/model/year — used by the price
        calculator for on-demand comparable data.

        Returns up to `max_pages * 48` deduplicated listings.
        """
        brand_slug = brand.strip().lower().replace(" ", "-")
        model_slug = model_token.strip().lower().replace(" ", "-")
        base = (
            f"https://autos.mercadolibre.com.ar/{brand_slug}/{model_slug}/"
            f"desde-{year}-hasta-{year}/_NoIndex_True"
        )
        all_listings = []
        seen = set()
        for page in range(max_pages):
            offset = page * _PAGE_SIZE
            url = base if offset == 0 else base.replace(
                "_NoIndex_True", f"_Desde_{offset + 1}_NoIndex_True"
            )
            try:
                results, total = self._scrape_url(url)
            except Exception as e:
                logger.error(f"on-demand scrape page {page} failed: {e}")
                break
            new = [r for r in results if r["source_id"] not in seen]
            for r in new:
                seen.add(r["source_id"])
            all_listings.extend(new)
            if not new or offset + _PAGE_SIZE >= min(total, max_pages * _PAGE_SIZE):
                break
        return all_listings

    def scrape_all(self):
        logger.info("Starting MercadoLibre scrape (via Firecrawl)...")
        all_listings = []
        offset = 0
        total = None

        while total is None or offset < min(total, 1000):
            try:
                results, total = self.fetch_page(offset)
                all_listings.extend(results)
                logger.info(
                    f"  Fetched {len(results)} listings "
                    f"(offset={offset}, total={total})"
                )
                offset += _PAGE_SIZE
            except Exception as e:
                logger.error(f"  Error at offset {offset}: {e}")
                break

        logger.info(f"MercadoLibre: {len(all_listings)} listings scraped.")
        return all_listings
