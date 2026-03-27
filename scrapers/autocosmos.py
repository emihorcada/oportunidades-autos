import logging
import random
import re
import time

import requests
from bs4 import BeautifulSoup

from core.exchange_rate import convert_ars_to_usd

logger = logging.getLogger(__name__)

BASE_URL = "https://www.autocosmos.com.ar/auto/usado"
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


class AutocosmosScraper:
    def __init__(self, usd_rate):
        self.usd_rate = usd_rate
        self.session = requests.Session()

    def _get_headers(self):
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.5",
        }

    def _parse_price(self, price_text):
        """Extract numeric price from text like '$ 15.000.000' or 'U$S 13.000'."""
        if not price_text:
            return None, None
        clean = price_text.strip()
        if not clean:
            return None, None
        if "U$S" in clean or "USD" in clean:
            currency = "USD"
        else:
            currency = "ARS"
        num_str = re.sub(r"[^\d]", "", clean)
        return (float(num_str), currency) if num_str else (None, currency)

    def _parse_km(self, km_text):
        """Extract numeric km from text like '50.000 km'."""
        if not km_text:
            return None
        num_str = re.sub(r"[^\d]", "", km_text)
        return int(num_str) if num_str else None

    def parse_listing_element(self, element):
        """Parse a single listing card from the search results page.

        CSS selectors are approximate and may need adjustment against
        the live site (see Task 11).
        """
        try:
            # Title usually contains brand + model + version
            title_el = element.select_one("a.title, h2 a, .card-title a, a[title]")
            title = title_el.get_text(strip=True) if title_el else ""
            url = title_el["href"] if title_el and title_el.has_attr("href") else ""
            if url and not url.startswith("http"):
                url = "https://www.autocosmos.com.ar" + url

            # Try to split title into brand / model / version
            parts = title.split(" ", 2)
            brand = parts[0] if len(parts) > 0 else ""
            model = parts[1] if len(parts) > 1 else ""
            version = parts[2] if len(parts) > 2 else ""

            # Year
            year_el = element.select_one(".year, .item-year, span.year")
            year_text = year_el.get_text(strip=True) if year_el else ""
            year_match = re.search(r"(\d{4})", year_text or title)
            year = int(year_match.group(1)) if year_match else None

            # Km
            km_el = element.select_one(".km, .item-km, span.km")
            km = self._parse_km(km_el.get_text(strip=True) if km_el else None)

            # Price
            price_el = element.select_one(".price, .item-price, span.price")
            price_text = price_el.get_text(strip=True) if price_el else None
            price_raw, currency = self._parse_price(price_text)

            if currency == "USD":
                price_usd = price_raw
                price_ars = round(price_raw * self.usd_rate, 2) if price_raw else None
            else:
                price_ars = price_raw
                price_usd = convert_ars_to_usd(price_raw, self.usd_rate)

            # Location
            loc_el = element.select_one(".location, .item-location, span.location")
            location = loc_el.get_text(strip=True) if loc_el else ""

            # Image
            img_el = element.select_one("img")
            image_url = ""
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src") or ""

            return {
                "source": "autocosmos",
                "source_id": url,
                "url": url,
                "brand": brand,
                "model": model,
                "version": version,
                "year": year,
                "km": km,
                "price_ars": price_ars,
                "price_usd": price_usd,
                "currency_original": currency or "ARS",
                "location": location,
                "category": None,
                "transmission": "",
                "fuel": "",
                "image_url": image_url,
            }
        except Exception as e:
            logger.warning(f"Error parsing listing element: {e}")
            return None

    def scrape_page(self, page=1):
        """Fetch and parse a single search-results page."""
        url = BASE_URL if page == 1 else f"{BASE_URL}?pg={page}"
        logger.info(f"  Fetching Autocosmos page {page}: {url}")

        response = self.session.get(url, headers=self._get_headers(), timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        # The listing container selector may need adjustment (Task 11)
        cards = soup.select(".listing-item, .result-item, article.item, .card-vehicle")

        listings = []
        for card in cards:
            listing = self.parse_listing_element(card)
            if listing:
                listings.append(listing)

        return listings

    def scrape_all(self, max_pages=20):
        """Scrape up to max_pages of search results."""
        logger.info("Starting Autocosmos scrape...")
        all_listings = []

        for page in range(1, max_pages + 1):
            try:
                results = self.scrape_page(page)
                if not results:
                    logger.info(f"  No results on page {page}, stopping.")
                    break
                all_listings.extend(results)
                logger.info(f"  Page {page}: {len(results)} listings (total so far: {len(all_listings)})")
                # Rate-limit: random pause between 1.5 and 3 seconds
                time.sleep(random.uniform(1.5, 3.0))
            except Exception as e:
                logger.error(f"  Error on page {page}: {e}")
                break

        logger.info(f"Autocosmos: {len(all_listings)} listings scraped.")
        return all_listings
