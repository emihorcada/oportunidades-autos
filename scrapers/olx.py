import logging
import random
import re
import time
import requests
from bs4 import BeautifulSoup
from core.exchange_rate import convert_ars_to_usd

logger = logging.getLogger(__name__)

BASE_URL = "https://www.olx.com.ar/autos"
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


class OLXScraper:
    def __init__(self, usd_rate):
        self.usd_rate = usd_rate
        self.session = requests.Session()

    def _get_headers(self):
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        }

    def _parse_price(self, price_text):
        """Parse price text and return (amount, currency) tuple."""
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
        return (float(num_str), currency) if num_str else (None, None)

    def _parse_km(self, km_text):
        """Parse kilometer text and return integer value."""
        if not km_text:
            return None
        num_str = re.sub(r"[^\d]", "", km_text)
        return int(num_str) if num_str else None

    def parse_listing_element(self, element):
        """Parse a single listing HTML element into a structured dict."""
        # Extract link and URL
        link = element.find("a")
        url = link.get("href", "") if link else ""
        if url and not url.startswith("http"):
            url = f"https://www.olx.com.ar{url}"

        # Extract source_id from URL
        source_id = ""
        id_match = re.search(r"iid-(\w+)", url)
        if id_match:
            source_id = id_match.group(1)

        # Extract title
        title_el = element.find(class_="listing-card__title")
        title = title_el.get_text(strip=True) if title_el else ""

        # Extract price
        price_el = element.find(class_="listing-card__price")
        price_text = price_el.get_text(strip=True) if price_el else None
        price, currency = self._parse_price(price_text)

        # Calculate both ARS and USD prices
        price_ars = None
        price_usd = None
        if price is not None:
            if currency == "USD":
                price_usd = price
                price_ars = round(price * self.usd_rate, 2)
            else:
                price_ars = price
                price_usd = convert_ars_to_usd(price, self.usd_rate)

        # Extract km from detail elements
        detail_els = element.find_all(class_="listing-card__detail")
        km = None
        for detail in detail_els:
            text = detail.get_text(strip=True)
            if "km" in text.lower() or re.search(r"[\d.]+", text):
                parsed_km = self._parse_km(text)
                if parsed_km and parsed_km > 100:  # likely km, not year
                    km = parsed_km
                    break

        # Extract location
        location_el = element.find(class_="listing-card__detail--location")
        location = location_el.get_text(strip=True) if location_el else ""

        # Extract image
        img_el = element.find("img")
        image_url = ""
        if img_el:
            image_url = img_el.get("src", "") or img_el.get("data-src", "")

        # Try to extract year from title
        year = None
        year_match = re.search(r"\b(20[0-2]\d)\b", title)
        if year_match:
            year = int(year_match.group(1))

        return {
            "source": "olx",
            "source_id": source_id,
            "url": url,
            "brand": "",
            "model": title,
            "version": "",
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

    def scrape_page(self, page=1):
        """Scrape a single page of OLX listings."""
        url = BASE_URL if page == 1 else f"{BASE_URL}?page={page}"
        headers = self._get_headers()

        response = self.session.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        listing_elements = soup.find_all("li", class_="listing-card")

        results = []
        for element in listing_elements:
            try:
                listing = self.parse_listing_element(element)
                if listing.get("price_ars") or listing.get("price_usd"):
                    results.append(listing)
            except Exception as e:
                logger.warning(f"Error parsing OLX listing element: {e}")
                continue

        return results

    def scrape_all(self, max_pages=20):
        """Scrape multiple pages of OLX listings."""
        logger.info("Starting OLX scrape...")
        all_listings = []

        for page in range(1, max_pages + 1):
            try:
                results = self.scrape_page(page)
                if not results:
                    logger.info(f"  No results on page {page}, stopping.")
                    break
                all_listings.extend(results)
                logger.info(f"  Page {page}: {len(results)} listings (total: {len(all_listings)})")
                time.sleep(random.uniform(2, 4))
            except Exception as e:
                logger.error(f"  Error on page {page}: {e}")
                break

        logger.info(f"OLX: {len(all_listings)} listings scraped.")
        return all_listings
