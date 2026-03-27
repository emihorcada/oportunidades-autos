import logging
import random
import re
import time
import requests
from bs4 import BeautifulSoup
from core.exchange_rate import convert_ars_to_usd

logger = logging.getLogger(__name__)

BASE_URL = "https://www.demotores.com.ar/autos/usados"
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15",
]


class DeMotoresScraper:
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
        """Parse price text and return (amount, currency)."""
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
        """Parse km text like '50.000 km' and return integer."""
        if not km_text:
            return None
        num_str = re.sub(r"[^\d]", "", km_text)
        return int(num_str) if num_str else None

    def parse_listing_element(self, element):
        """Parse a single listing HTML element into a structured dict."""
        try:
            # Title
            title_el = element.find(class_="listing-card__title")
            title = title_el.get_text(strip=True) if title_el else ""

            # Split title into brand/model/version heuristic
            parts = title.split() if title else []
            brand = parts[0] if len(parts) >= 1 else ""
            model = parts[1] if len(parts) >= 2 else ""
            version = " ".join(parts[2:]) if len(parts) >= 3 else ""

            # URL
            link_el = element.find("a", class_="listing-card__link")
            href = link_el.get("href", "") if link_el else ""
            url = f"https://www.demotores.com.ar{href}" if href and not href.startswith("http") else href

            # Image
            img_el = element.find("img", class_="listing-card__image")
            image_url = ""
            if img_el:
                image_url = img_el.get("src", "") or img_el.get("data-src", "")

            # Price
            price_el = element.find(class_="listing-card__price")
            price_text = price_el.get_text(strip=True) if price_el else None
            price, currency = self._parse_price(price_text)

            if currency == "USD" and price is not None:
                price_usd = price
                price_ars = round(price * self.usd_rate, 2)
            elif currency == "ARS" and price is not None:
                price_ars = price
                price_usd = convert_ars_to_usd(price, self.usd_rate)
            else:
                price_ars = None
                price_usd = None

            # Year
            year_el = element.find(class_="listing-card__year")
            year_text = year_el.get_text(strip=True) if year_el else None
            year = int(re.sub(r"[^\d]", "", year_text)) if year_text and re.sub(r"[^\d]", "", year_text) else None

            # Km
            km_el = element.find(class_="listing-card__km")
            km_text = km_el.get_text(strip=True) if km_el else None
            km = self._parse_km(km_text)

            # Location
            loc_el = element.find(class_="listing-card__location")
            location = loc_el.get_text(strip=True) if loc_el else ""

            return {
                "source": "demotores",
                "source_id": href.split("/")[-1] if href else "",
                "url": url,
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
                "transmission": None,
                "fuel": None,
                "image_url": image_url,
            }
        except Exception as e:
            logger.warning(f"Failed to parse listing element: {e}")
            return None

    def _check_site_alive(self, response):
        """Check if the site is still operational (not redirected to closure page)."""
        if "soloautos.mx" in response.url or "mxclose" in response.url:
            return False
        if "aviso de cierre" in response.text.lower() or "closingPage" in response.text:
            return False
        return True

    def scrape_page(self, page=1):
        """Scrape a single page of listings."""
        url = f"{BASE_URL}?pagina={page}" if page > 1 else BASE_URL
        headers = self._get_headers()

        response = self.session.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        if not self._check_site_alive(response):
            logger.warning(
                "DeMotores has shut down (redirects to %s). "
                "Scraper disabled -- remove or replace this source.",
                response.url,
            )
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.find_all("div", class_="listing-card")

        listings = []
        for card in cards:
            parsed = self.parse_listing_element(card)
            if parsed:
                listings.append(parsed)

        return listings

    def scrape_all(self, max_pages=20):
        """Scrape multiple pages of listings."""
        logger.info("Starting DeMotores scrape...")
        all_listings = []

        for page in range(1, max_pages + 1):
            try:
                results = self.scrape_page(page)
                if not results:
                    logger.info(f"  No results on page {page}, stopping.")
                    break
                all_listings.extend(results)
                logger.info(f"  Page {page}: {len(results)} listings (total: {len(all_listings)})")
                time.sleep(random.uniform(1.5, 3.0))
            except Exception as e:
                logger.error(f"  Error on page {page}: {e}")
                break

        logger.info(f"DeMotores: {len(all_listings)} listings scraped.")
        return all_listings
