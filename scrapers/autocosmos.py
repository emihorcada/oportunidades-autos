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
        """Parse a single listing card (``article.listing-card``) from the
        search results page."""
        try:
            # Link – the <a itemprop="url"> wrapping the card content
            link_el = element.select_one("a[itemprop='url']")
            if not link_el:
                link_el = element.select_one("a[href]")
            url = link_el["href"] if link_el and link_el.has_attr("href") else ""
            if url and not url.startswith("http"):
                url = "https://www.autocosmos.com.ar" + url

            # Brand / Model / Version – separate <span> elements
            brand_el = element.select_one("span.listing-card__brand")
            brand = brand_el.get_text(strip=True) if brand_el else ""

            model_el = element.select_one("span.listing-card__model")
            model = model_el.get_text(strip=True) if model_el else ""

            version_el = element.select_one("span.listing-card__version")
            version = version_el.get_text(strip=True) if version_el else ""

            # Year
            year_el = element.select_one("span.listing-card__year")
            year_text = year_el.get_text(strip=True) if year_el else ""
            year_match = re.search(r"(\d{4})", year_text)
            year = int(year_match.group(1)) if year_match else None

            # Km
            km_el = element.select_one("span.listing-card__km")
            km = self._parse_km(km_el.get_text(strip=True) if km_el else None)

            # Price – prefer direct price (``span.listing-card__price``),
            # then fall back to anticipo (``div.listing-card__price.m-anticipo``).
            # The numeric value lives in the ``content`` attribute of the
            # ``<span itemprop="price">`` or in the visible text.
            price_raw, currency = None, None

            # 1) Direct / full price
            direct_price = element.select_one("span.listing-card__price")
            if direct_price:
                currency_meta = direct_price.select_one("meta[itemprop='priceCurrency']")
                value_el = direct_price.select_one("span.listing-card__price-value")
                if value_el:
                    content_val = value_el.get("content")
                    if content_val:
                        price_raw = float(content_val)
                    else:
                        price_raw, _ = self._parse_price(value_el.get_text(strip=True))
                    currency = currency_meta["content"] if currency_meta and currency_meta.has_attr("content") else None
                    if not currency:
                        txt = value_el.get_text(strip=True)
                        currency = "USD" if ("u$s" in txt.lower() or "USD" in txt) else "ARS"

            # 2) Anticipo fallback
            if price_raw is None:
                anticipo = element.select_one("div.listing-card__price.m-anticipo")
                if anticipo:
                    currency_meta = anticipo.select_one("meta[itemprop='priceCurrency']")
                    value_el = anticipo.select_one("span.listing-card__price-value")
                    if value_el:
                        content_val = value_el.get("content")
                        if content_val:
                            price_raw = float(content_val)
                        else:
                            price_raw, _ = self._parse_price(value_el.get_text(strip=True))
                        currency = currency_meta["content"] if currency_meta and currency_meta.has_attr("content") else "ARS"

            if currency is None:
                currency = "ARS"

            if currency == "USD":
                price_usd = price_raw
                price_ars = round(price_raw * self.usd_rate, 2) if price_raw else None
            else:
                price_ars = price_raw
                price_usd = convert_ars_to_usd(price_raw, self.usd_rate)

            # Location
            city_el = element.select_one("span.listing-card__city")
            province_el = element.select_one("span.listing-card__province")
            city = city_el.get_text(strip=True).rstrip(" |") if city_el else ""
            province = province_el.get_text(strip=True) if province_el else ""
            location = f"{city}, {province}" if city and province else city or province

            # Image
            img_el = element.select_one("figure.listing-card__image img")
            image_url = ""
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src") or img_el.get("content") or ""

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
        url = BASE_URL if page == 1 else f"{BASE_URL}?pidx={page}"
        logger.info(f"  Fetching Autocosmos page {page}: {url}")

        response = self.session.get(url, headers=self._get_headers(), timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select("article.listing-card")

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
