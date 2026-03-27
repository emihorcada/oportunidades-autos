import logging
import time
import requests
from core.exchange_rate import convert_ars_to_usd

logger = logging.getLogger(__name__)

ML_CATEGORY = "MLA1743"
ML_API_URL = "https://api.mercadolibre.com/sites/MLA/search"


class MercadoLibreScraper:
    def __init__(self, usd_rate):
        self.usd_rate = usd_rate

    def _get_attr(self, attributes, attr_id):
        for attr in attributes:
            if attr.get("id") == attr_id:
                return attr.get("value_name")
        return None

    def parse_listing(self, item):
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

    def fetch_page(self, offset=0):
        params = {
            "category": ML_CATEGORY,
            "offset": offset,
            "limit": 50,
            "VEHICLE_YEAR": "[2016-2026]",
            "sort": "price_asc",
        }
        response = requests.get(ML_API_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        results = [self.parse_listing(item) for item in data.get("results", [])]
        total = data.get("paging", {}).get("total", 0)
        return results, total

    def scrape_all(self):
        logger.info("Starting MercadoLibre scrape...")
        all_listings = []
        offset = 0
        total = None

        while total is None or offset < min(total, 1000):
            try:
                results, total = self.fetch_page(offset)
                all_listings.extend(results)
                logger.info(f"  Fetched {len(results)} listings (offset={offset}, total={total})")
                offset += 50
                time.sleep(1)
            except Exception as e:
                logger.error(f"  Error at offset {offset}: {e}")
                break

        logger.info(f"MercadoLibre: {len(all_listings)} listings scraped.")
        return all_listings
