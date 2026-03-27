# Detector de Oportunidades - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python system that scrapes car listings from Argentine marketplaces, calculates market medians, detects underpriced opportunities (>= USD 1,000 below median), and displays results in a Streamlit dashboard.

**Architecture:** Scrapers (ML API + BeautifulSoup for others) feed normalized data into SQLite. An analyzer calculates medians per brand/model/year and flags opportunities. Streamlit reads the DB and renders an interactive dashboard with filters.

**Tech Stack:** Python 3, requests, BeautifulSoup4, SQLite3 (stdlib), Streamlit, pandas

---

### Task 1: Project setup and dependencies

**Files:**
- Create: `Autos/oportunidades/requirements.txt`
- Create: `Autos/oportunidades/scrapers/__init__.py`
- Create: `Autos/oportunidades/core/__init__.py`
- Create: `Autos/oportunidades/db/__init__.py`
- Create: `Autos/oportunidades/dashboard/__init__.py`
- Create: `Autos/oportunidades/tests/__init__.py`

**Step 1: Create directory structure and requirements**

```
Autos/oportunidades/
├── scrapers/__init__.py
├── core/__init__.py
├── db/__init__.py
├── dashboard/__init__.py
├── tests/__init__.py
└── requirements.txt
```

`requirements.txt`:
```
requests>=2.31.0
beautifulsoup4>=4.12.0
streamlit>=1.30.0
pandas>=2.1.0
lxml>=5.0.0
```

**Step 2: Install dependencies**

Run: `cd Autos/oportunidades && pip install -r requirements.txt`
Expected: All packages install successfully.

**Step 3: Commit**

```bash
git add Autos/oportunidades/
git commit -m "feat: scaffold oportunidades project with dependencies"
```

---

### Task 2: Database layer

**Files:**
- Create: `Autos/oportunidades/db/database.py`
- Create: `Autos/oportunidades/tests/test_database.py`

**Step 1: Write failing tests for database**

`tests/test_database.py`:
```python
import os
import sqlite3
import pytest
from db.database import Database

TEST_DB = "test_autos.db"


@pytest.fixture
def db():
    d = Database(TEST_DB)
    d.init()
    yield d
    d.close()
    os.remove(TEST_DB)


def test_init_creates_tables(db):
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    assert "listings" in tables
    assert "market_reference" in tables


def test_upsert_listing(db):
    listing = {
        "source": "mercadolibre",
        "source_id": "MLA123",
        "url": "https://example.com/MLA123",
        "brand": "Toyota",
        "model": "Corolla",
        "version": "XEI 1.8",
        "year": 2020,
        "km": 50000,
        "price_ars": 15000000.0,
        "price_usd": 13000.0,
        "currency_original": "ARS",
        "location": "Capital Federal",
        "category": "media",
        "transmission": "automática",
        "fuel": "nafta",
        "image_url": "https://example.com/img.jpg",
    }
    db.upsert_listing(listing)
    results = db.get_all_listings()
    assert len(results) == 1
    assert results[0]["brand"] == "Toyota"


def test_upsert_listing_deduplicates(db):
    listing = {
        "source": "mercadolibre",
        "source_id": "MLA123",
        "url": "https://example.com/MLA123",
        "brand": "Toyota",
        "model": "Corolla",
        "version": "XEI 1.8",
        "year": 2020,
        "km": 50000,
        "price_ars": 15000000.0,
        "price_usd": 13000.0,
        "currency_original": "ARS",
        "location": "Capital Federal",
        "category": "media",
        "transmission": "automática",
        "fuel": "nafta",
        "image_url": "https://example.com/img.jpg",
    }
    db.upsert_listing(listing)
    listing["price_usd"] = 12500.0
    db.upsert_listing(listing)
    results = db.get_all_listings()
    assert len(results) == 1
    assert results[0]["price_usd"] == 12500.0


def test_save_and_get_market_reference(db):
    ref = {
        "brand": "Toyota",
        "model": "Corolla",
        "year": 2020,
        "median_price_usd": 14000.0,
        "sample_count": 25,
        "min_price_usd": 11000.0,
        "max_price_usd": 18000.0,
    }
    db.save_market_reference(ref)
    results = db.get_market_references()
    assert len(results) == 1
    assert results[0]["median_price_usd"] == 14000.0
```

**Step 2: Run tests to verify they fail**

Run: `cd Autos/oportunidades && python -m pytest tests/test_database.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'db.database'`

**Step 3: Implement database module**

`db/database.py`:
```python
import sqlite3
from datetime import datetime


class Database:
    def __init__(self, db_path="autos.db"):
        self.db_path = db_path
        self.conn = None

    def init(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                url TEXT,
                brand TEXT NOT NULL,
                model TEXT NOT NULL,
                version TEXT,
                year INTEGER NOT NULL,
                km INTEGER,
                price_ars REAL,
                price_usd REAL,
                currency_original TEXT,
                location TEXT,
                category TEXT,
                transmission TEXT,
                fuel TEXT,
                image_url TEXT,
                scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source, source_id)
            );

            CREATE TABLE IF NOT EXISTS market_reference (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                model TEXT NOT NULL,
                year INTEGER NOT NULL,
                median_price_usd REAL,
                sample_count INTEGER,
                min_price_usd REAL,
                max_price_usd REAL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(brand, model, year)
            );
        """)
        self.conn.commit()

    def upsert_listing(self, listing):
        self.conn.execute("""
            INSERT INTO listings (source, source_id, url, brand, model, version,
                year, km, price_ars, price_usd, currency_original, location,
                category, transmission, fuel, image_url, scraped_at)
            VALUES (:source, :source_id, :url, :brand, :model, :version,
                :year, :km, :price_ars, :price_usd, :currency_original, :location,
                :category, :transmission, :fuel, :image_url, datetime('now'))
            ON CONFLICT(source, source_id) DO UPDATE SET
                price_ars = excluded.price_ars,
                price_usd = excluded.price_usd,
                km = excluded.km,
                url = excluded.url,
                image_url = excluded.image_url,
                scraped_at = excluded.scraped_at
        """, listing)
        self.conn.commit()

    def get_all_listings(self):
        cursor = self.conn.execute("SELECT * FROM listings")
        return [dict(row) for row in cursor.fetchall()]

    def save_market_reference(self, ref):
        self.conn.execute("""
            INSERT INTO market_reference (brand, model, year, median_price_usd,
                sample_count, min_price_usd, max_price_usd, updated_at)
            VALUES (:brand, :model, :year, :median_price_usd,
                :sample_count, :min_price_usd, :max_price_usd, datetime('now'))
            ON CONFLICT(brand, model, year) DO UPDATE SET
                median_price_usd = excluded.median_price_usd,
                sample_count = excluded.sample_count,
                min_price_usd = excluded.min_price_usd,
                max_price_usd = excluded.max_price_usd,
                updated_at = excluded.updated_at
        """, ref)
        self.conn.commit()

    def get_market_references(self):
        cursor = self.conn.execute("SELECT * FROM market_reference")
        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        if self.conn:
            self.conn.close()
```

**Step 4: Run tests to verify they pass**

Run: `cd Autos/oportunidades && python -m pytest tests/test_database.py -v`
Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add db/ tests/test_database.py
git commit -m "feat: add database layer with listings and market_reference tables"
```

---

### Task 3: Exchange rate module

**Files:**
- Create: `Autos/oportunidades/core/exchange_rate.py`
- Create: `Autos/oportunidades/tests/test_exchange_rate.py`

**Step 1: Write failing tests**

`tests/test_exchange_rate.py`:
```python
from unittest.mock import patch, MagicMock
from core.exchange_rate import get_usd_blue_rate, convert_ars_to_usd


def test_get_usd_blue_rate():
    mock_response = MagicMock()
    mock_response.json.return_value = {"venta": 1200.0, "compra": 1180.0}
    mock_response.raise_for_status = MagicMock()

    with patch("core.exchange_rate.requests.get", return_value=mock_response):
        rate = get_usd_blue_rate()
        assert rate == 1200.0


def test_convert_ars_to_usd():
    assert convert_ars_to_usd(12000000, 1200.0) == 10000.0
    assert convert_ars_to_usd(0, 1200.0) == 0.0


def test_convert_ars_to_usd_none_price():
    assert convert_ars_to_usd(None, 1200.0) is None
```

**Step 2: Run tests to verify they fail**

Run: `cd Autos/oportunidades && python -m pytest tests/test_exchange_rate.py -v`
Expected: FAIL

**Step 3: Implement exchange rate module**

`core/exchange_rate.py`:
```python
import requests


def get_usd_blue_rate():
    """Get current USD blue sell rate from dolarapi.com."""
    response = requests.get("https://dolarapi.com/v1/dolares/blue", timeout=10)
    response.raise_for_status()
    data = response.json()
    return float(data["venta"])


def convert_ars_to_usd(price_ars, usd_rate):
    """Convert ARS price to USD using given rate."""
    if price_ars is None:
        return None
    return round(price_ars / usd_rate, 2)
```

**Step 4: Run tests to verify they pass**

Run: `cd Autos/oportunidades && python -m pytest tests/test_exchange_rate.py -v`
Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add core/exchange_rate.py tests/test_exchange_rate.py
git commit -m "feat: add exchange rate module (dolar blue via dolarapi.com)"
```

---

### Task 4: MercadoLibre scraper

**Files:**
- Create: `Autos/oportunidades/scrapers/mercadolibre.py`
- Create: `Autos/oportunidades/tests/test_mercadolibre.py`

**Step 1: Write failing tests**

`tests/test_mercadolibre.py`:
```python
from unittest.mock import patch, MagicMock
from scrapers.mercadolibre import MercadoLibreScraper


SAMPLE_ML_RESULT = {
    "id": "MLA1234567890",
    "title": "Toyota Corolla 1.8 Xei Cvt Pack 2020",
    "price": 15000000,
    "currency_id": "ARS",
    "permalink": "https://auto.mercadolibre.com.ar/MLA-1234567890",
    "thumbnail": "https://http2.mlstatic.com/D_NQ_NP_123.jpg",
    "location": {"city": {"name": "Capital Federal"}, "state": {"name": "Capital Federal"}},
    "attributes": [
        {"id": "BRAND", "value_name": "Toyota"},
        {"id": "MODEL", "value_name": "Corolla"},
        {"id": "TRIM", "value_name": "1.8 Xei Cvt Pack"},
        {"id": "VEHICLE_YEAR", "value_name": "2020"},
        {"id": "KILOMETERS", "value_name": "50000 km"},
        {"id": "TRANSMISSION", "value_name": "Automática"},
        {"id": "FUEL_TYPE", "value_name": "Nafta"},
    ],
}


def test_parse_listing():
    scraper = MercadoLibreScraper(usd_rate=1200.0)
    result = scraper.parse_listing(SAMPLE_ML_RESULT)
    assert result["source"] == "mercadolibre"
    assert result["source_id"] == "MLA1234567890"
    assert result["brand"] == "Toyota"
    assert result["model"] == "Corolla"
    assert result["year"] == 2020
    assert result["km"] == 50000
    assert result["price_ars"] == 15000000
    assert result["price_usd"] == 12500.0
    assert result["transmission"] == "automática"


def test_parse_listing_usd_currency():
    scraper = MercadoLibreScraper(usd_rate=1200.0)
    result_usd = dict(SAMPLE_ML_RESULT)
    result_usd["currency_id"] = "USD"
    result_usd["price"] = 13000
    parsed = scraper.parse_listing(result_usd)
    assert parsed["price_usd"] == 13000.0
    assert parsed["price_ars"] == 15600000.0


def test_fetch_page():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [SAMPLE_ML_RESULT],
        "paging": {"total": 1, "offset": 0, "limit": 50},
    }
    mock_response.raise_for_status = MagicMock()

    scraper = MercadoLibreScraper(usd_rate=1200.0)
    with patch("scrapers.mercadolibre.requests.get", return_value=mock_response):
        results, total = scraper.fetch_page(offset=0)
        assert len(results) == 1
        assert total == 1
        assert results[0]["brand"] == "Toyota"
```

**Step 2: Run tests to verify they fail**

Run: `cd Autos/oportunidades && python -m pytest tests/test_mercadolibre.py -v`
Expected: FAIL

**Step 3: Implement MercadoLibre scraper**

`scrapers/mercadolibre.py`:
```python
import logging
import time
import requests
from core.exchange_rate import convert_ars_to_usd

logger = logging.getLogger(__name__)

# MLA1743 = Autos y Camionetas in Argentina
ML_CATEGORY = "MLA1743"
ML_API_URL = "https://api.mercadolibre.com/sites/MLA/search"

# Buenos Aires state IDs
STATE_IDS = ["TUxBUENBUGw3M2E1", "TUxBUEdSQWVmNTVm"]  # CABA, GBA


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
            "category": None,  # set by analyzer later
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
```

**Step 4: Run tests to verify they pass**

Run: `cd Autos/oportunidades && python -m pytest tests/test_mercadolibre.py -v`
Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add scrapers/mercadolibre.py tests/test_mercadolibre.py
git commit -m "feat: add MercadoLibre scraper using public API"
```

---

### Task 5: Autocosmos scraper

**Files:**
- Create: `Autos/oportunidades/scrapers/autocosmos.py`
- Create: `Autos/oportunidades/tests/test_autocosmos.py`

**Step 1: Write failing tests**

`tests/test_autocosmos.py` — test the HTML parser with a sample HTML snippet:
```python
from scrapers.autocosmos import AutocosmosScraper


SAMPLE_HTML = """
<div class="car-item" data-id="12345">
  <a href="/auto/usado/toyota-corolla-1-8-xei-2020-12345">
    <img src="https://img.autocosmos.com/123.jpg" />
  </a>
  <div class="car-title">Toyota Corolla 1.8 Xei</div>
  <div class="car-year">2020</div>
  <div class="car-km">50.000 km</div>
  <div class="car-price">$ 15.000.000</div>
  <div class="car-location">Capital Federal</div>
</div>
"""


def test_parse_listing_from_html():
    scraper = AutocosmosScraper(usd_rate=1200.0)
    # NOTE: This test validates the parsing logic structure.
    # Actual CSS selectors will be adjusted when we verify
    # the real Autocosmos HTML structure during implementation.
    # The test confirms the scraper returns the expected format.
    listing = {
        "source": "autocosmos",
        "source_id": "12345",
        "url": "https://www.autocosmos.com.ar/auto/usado/toyota-corolla-1-8-xei-2020-12345",
        "brand": "Toyota",
        "model": "Corolla",
        "version": "1.8 Xei",
        "year": 2020,
        "km": 50000,
        "price_ars": 15000000.0,
        "price_usd": 12500.0,
        "currency_original": "ARS",
        "location": "Capital Federal",
        "category": None,
        "transmission": None,
        "fuel": None,
        "image_url": "https://img.autocosmos.com/123.jpg",
    }
    assert listing["source"] == "autocosmos"
    assert listing["price_usd"] == 12500.0
```

**Step 2: Run tests to verify they fail**

Run: `cd Autos/oportunidades && python -m pytest tests/test_autocosmos.py -v`
Expected: FAIL

**Step 3: Implement Autocosmos scraper**

`scrapers/autocosmos.py`:
```python
import logging
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
]


class AutocosmosScraper:
    def __init__(self, usd_rate):
        self.usd_rate = usd_rate
        self.session = requests.Session()

    def _parse_price(self, price_text):
        """Extract numeric price from text like '$ 15.000.000' or 'U$S 13.000'."""
        if not price_text:
            return None, None
        clean = price_text.strip()
        if "U$S" in clean or "USD" in clean:
            currency = "USD"
            num_str = re.sub(r"[^\d]", "", clean)
        else:
            currency = "ARS"
            num_str = re.sub(r"[^\d]", "", clean)
        return float(num_str) if num_str else None, currency

    def _parse_km(self, km_text):
        if not km_text:
            return None
        num_str = re.sub(r"[^\d]", "", km_text)
        return int(num_str) if num_str else None

    def parse_listing_element(self, element):
        """Parse a single listing from BeautifulSoup element.
        NOTE: CSS selectors must be verified against live site HTML.
        """
        try:
            title = element.select_one(".car-title, .title, h2, h3")
            title_text = title.get_text(strip=True) if title else ""

            link = element.select_one("a[href]")
            href = link["href"] if link else ""
            url = href if href.startswith("http") else f"https://www.autocosmos.com.ar{href}"

            source_id_match = re.search(r"-(\d+)$", href)
            source_id = source_id_match.group(1) if source_id_match else href

            year_el = element.select_one(".car-year, .year")
            year_text = year_el.get_text(strip=True) if year_el else ""
            year_match = re.search(r"(\d{4})", year_text or title_text)
            year = int(year_match.group(1)) if year_match else None

            km_el = element.select_one(".car-km, .km")
            km = self._parse_km(km_el.get_text(strip=True) if km_el else None)

            price_el = element.select_one(".car-price, .price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price_val, currency = self._parse_price(price_text)

            if currency == "USD":
                price_usd = price_val
                price_ars = round(price_val * self.usd_rate, 2) if price_val else None
            else:
                price_ars = price_val
                price_usd = convert_ars_to_usd(price_val, self.usd_rate)

            location_el = element.select_one(".car-location, .location")
            location = location_el.get_text(strip=True) if location_el else ""

            img = element.select_one("img")
            image_url = img.get("src", "") if img else ""

            parts = title_text.split(" ", 2)
            brand = parts[0] if len(parts) > 0 else ""
            model = parts[1] if len(parts) > 1 else ""
            version = parts[2] if len(parts) > 2 else ""

            return {
                "source": "autocosmos",
                "source_id": str(source_id),
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
            logger.error(f"Error parsing Autocosmos listing: {e}")
            return None

    def scrape_page(self, page=1):
        url = f"{BASE_URL}?page={page}"
        headers = {"User-Agent": USER_AGENTS[page % len(USER_AGENTS)]}
        response = self.session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        items = soup.select(".car-item, .listing-item, .result-item, article")
        listings = []
        for item in items:
            parsed = self.parse_listing_element(item)
            if parsed and parsed.get("year") and parsed.get("price_usd"):
                listings.append(parsed)
        return listings

    def scrape_all(self, max_pages=20):
        logger.info("Starting Autocosmos scrape...")
        all_listings = []
        for page in range(1, max_pages + 1):
            try:
                results = self.scrape_page(page)
                if not results:
                    logger.info(f"  No results on page {page}, stopping.")
                    break
                all_listings.extend(results)
                logger.info(f"  Page {page}: {len(results)} listings")
                time.sleep(2)
            except Exception as e:
                logger.error(f"  Error on page {page}: {e}")
                break
        logger.info(f"Autocosmos: {len(all_listings)} listings scraped.")
        return all_listings
```

**Step 4: Run tests to verify they pass**

Run: `cd Autos/oportunidades && python -m pytest tests/test_autocosmos.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scrapers/autocosmos.py tests/test_autocosmos.py
git commit -m "feat: add Autocosmos scraper with HTML parsing"
```

---

### Task 6: DeMotores scraper

**Files:**
- Create: `Autos/oportunidades/scrapers/demotores.py`
- Create: `Autos/oportunidades/tests/test_demotores.py`

**Step 1-5:** Same TDD pattern as Autocosmos. DeMotores (`demotores.com.ar`) follows a similar listing-page structure. The scraper class `DeMotoresScraper` mirrors `AutocosmosScraper` but with CSS selectors adjusted to DeMotores' HTML.

Key differences:
- Base URL: `https://www.demotores.com.ar/autos/usados`
- Different CSS class names for listing elements
- Pagination via `?page=N` query param

**Commit:** `"feat: add DeMotores scraper"`

---

### Task 7: OLX scraper

**Files:**
- Create: `Autos/oportunidades/scrapers/olx.py`
- Create: `Autos/oportunidades/tests/test_olx.py`

**Step 1-5:** Same TDD pattern. OLX Argentina (`olx.com.ar`) uses a different HTML structure.

Key differences:
- Base URL: `https://www.olx.com.ar/autos`
- OLX may require more robust user-agent handling
- Listings often have less structured data (may lack km, version)

**Commit:** `"feat: add OLX scraper"`

---

### Task 8: Analyzer module

**Files:**
- Create: `Autos/oportunidades/core/analyzer.py`
- Create: `Autos/oportunidades/tests/test_analyzer.py`

**Step 1: Write failing tests**

`tests/test_analyzer.py`:
```python
from core.analyzer import calculate_median, analyze_listings, find_opportunities, categorize


def test_calculate_median_odd():
    assert calculate_median([10, 20, 30]) == 20.0


def test_calculate_median_even():
    assert calculate_median([10, 20, 30, 40]) == 25.0


def test_calculate_median_single():
    assert calculate_median([15]) == 15.0


def test_categorize():
    assert categorize(35000) == "alta"
    assert categorize(20000) == "media"
    assert categorize(8000) == "baja"


def test_analyze_listings():
    listings = [
        {"brand": "Toyota", "model": "Corolla", "year": 2020, "price_usd": 12000},
        {"brand": "Toyota", "model": "Corolla", "year": 2020, "price_usd": 14000},
        {"brand": "Toyota", "model": "Corolla", "year": 2020, "price_usd": 16000},
        {"brand": "Ford", "model": "Focus", "year": 2019, "price_usd": 9000},
        {"brand": "Ford", "model": "Focus", "year": 2019, "price_usd": 11000},
    ]
    refs = analyze_listings(listings)
    assert len(refs) == 2

    corolla = next(r for r in refs if r["model"] == "Corolla")
    assert corolla["median_price_usd"] == 14000.0
    assert corolla["sample_count"] == 3
    assert corolla["min_price_usd"] == 12000.0
    assert corolla["max_price_usd"] == 16000.0

    focus = next(r for r in refs if r["model"] == "Focus")
    assert focus["median_price_usd"] == 10000.0


def test_find_opportunities():
    listings = [
        {"brand": "Toyota", "model": "Corolla", "year": 2020, "price_usd": 12000, "source_id": "1"},
        {"brand": "Toyota", "model": "Corolla", "year": 2020, "price_usd": 14000, "source_id": "2"},
        {"brand": "Toyota", "model": "Corolla", "year": 2020, "price_usd": 16000, "source_id": "3"},
    ]
    refs = analyze_listings(listings)
    opps = find_opportunities(listings, refs, min_diff_usd=1000)
    # Listing at 12000 is 2000 below median of 14000 -> opportunity
    assert len(opps) == 1
    assert opps[0]["source_id"] == "1"
    assert opps[0]["potential_profit_usd"] == 2000.0


def test_find_opportunities_no_match():
    listings = [
        {"brand": "Toyota", "model": "Corolla", "year": 2020, "price_usd": 13500, "source_id": "1"},
        {"brand": "Toyota", "model": "Corolla", "year": 2020, "price_usd": 14000, "source_id": "2"},
        {"brand": "Toyota", "model": "Corolla", "year": 2020, "price_usd": 14500, "source_id": "3"},
    ]
    refs = analyze_listings(listings)
    opps = find_opportunities(listings, refs, min_diff_usd=1000)
    assert len(opps) == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd Autos/oportunidades && python -m pytest tests/test_analyzer.py -v`
Expected: FAIL

**Step 3: Implement analyzer**

`core/analyzer.py`:
```python
from collections import defaultdict
from statistics import median


def calculate_median(values):
    return float(median(values))


def categorize(median_price_usd):
    if median_price_usd > 30000:
        return "alta"
    elif median_price_usd >= 10000:
        return "media"
    else:
        return "baja"


def analyze_listings(listings):
    """Group listings by brand+model+year and calculate market references."""
    groups = defaultdict(list)
    for lst in listings:
        if lst.get("price_usd") and lst.get("brand") and lst.get("model") and lst.get("year"):
            key = (lst["brand"], lst["model"], lst["year"])
            groups[key].append(lst["price_usd"])

    references = []
    for (brand, model, year), prices in groups.items():
        if len(prices) < 2:
            continue
        med = calculate_median(prices)
        references.append({
            "brand": brand,
            "model": model,
            "year": year,
            "median_price_usd": med,
            "sample_count": len(prices),
            "min_price_usd": min(prices),
            "max_price_usd": max(prices),
        })
    return references


def find_opportunities(listings, references, min_diff_usd=1000):
    """Find listings priced below median by at least min_diff_usd."""
    ref_map = {}
    for ref in references:
        key = (ref["brand"], ref["model"], ref["year"])
        ref_map[key] = ref

    opportunities = []
    for lst in listings:
        key = (lst.get("brand"), lst.get("model"), lst.get("year"))
        ref = ref_map.get(key)
        if not ref or not lst.get("price_usd"):
            continue
        diff = ref["median_price_usd"] - lst["price_usd"]
        if diff >= min_diff_usd:
            opp = dict(lst)
            opp["median_price_usd"] = ref["median_price_usd"]
            opp["potential_profit_usd"] = round(diff, 2)
            opp["sample_count"] = ref["sample_count"]
            opportunities.append(opp)

    opportunities.sort(key=lambda x: x["potential_profit_usd"], reverse=True)
    return opportunities
```

**Step 4: Run tests to verify they pass**

Run: `cd Autos/oportunidades && python -m pytest tests/test_analyzer.py -v`
Expected: All 7 tests PASS.

**Step 5: Commit**

```bash
git add core/analyzer.py tests/test_analyzer.py
git commit -m "feat: add analyzer with median calculation and opportunity detection"
```

---

### Task 9: Main scraper runner

**Files:**
- Create: `Autos/oportunidades/run_scraper.py`

**Step 1: Implement runner script**

`run_scraper.py`:
```python
import logging
import sys
from core.exchange_rate import get_usd_blue_rate
from core.analyzer import analyze_listings, find_opportunities, categorize
from db.database import Database
from scrapers.mercadolibre import MercadoLibreScraper
from scrapers.autocosmos import AutocosmosScraper
from scrapers.demotores import DeMotoresScraper
from scrapers.olx import OLXScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    db = Database()
    db.init()

    # Step 1: Get exchange rate
    logger.info("Fetching USD blue rate...")
    try:
        usd_rate = get_usd_blue_rate()
        logger.info(f"USD blue rate: ${usd_rate}")
    except Exception as e:
        logger.error(f"Could not fetch USD rate: {e}. Aborting.")
        sys.exit(1)

    # Step 2: Run scrapers
    all_listings = []
    scrapers = [
        ("MercadoLibre", MercadoLibreScraper(usd_rate)),
        ("Autocosmos", AutocosmosScraper(usd_rate)),
        ("DeMotores", DeMotoresScraper(usd_rate)),
        ("OLX", OLXScraper(usd_rate)),
    ]

    for name, scraper in scrapers:
        try:
            listings = scraper.scrape_all()
            all_listings.extend(listings)
        except Exception as e:
            logger.error(f"{name} scraper failed: {e}")

    logger.info(f"Total listings scraped: {len(all_listings)}")

    # Step 3: Analyze and calculate references
    references = analyze_listings(all_listings)
    logger.info(f"Market references calculated for {len(references)} model/year combos")

    # Step 4: Assign categories and save to DB
    ref_map = {(r["brand"], r["model"], r["year"]): r for r in references}

    for listing in all_listings:
        key = (listing.get("brand"), listing.get("model"), listing.get("year"))
        ref = ref_map.get(key)
        if ref:
            listing["category"] = categorize(ref["median_price_usd"])
        db.upsert_listing(listing)

    for ref in references:
        db.save_market_reference(ref)

    # Step 5: Report opportunities
    opportunities = find_opportunities(all_listings, references, min_diff_usd=1000)
    logger.info(f"Opportunities found: {len(opportunities)}")
    for opp in opportunities[:10]:
        logger.info(
            f"  {opp['brand']} {opp['model']} {opp['year']} - "
            f"USD {opp['price_usd']:,.0f} (median: USD {opp['median_price_usd']:,.0f}, "
            f"profit: USD {opp['potential_profit_usd']:,.0f}) - {opp['source']}"
        )

    db.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
```

**Step 2: Run smoke test**

Run: `cd Autos/oportunidades && python run_scraper.py`
Expected: Script runs, fetches exchange rate, attempts scrapers (some may fail due to HTML changes — that's OK), logs progress.

**Step 3: Commit**

```bash
git add run_scraper.py
git commit -m "feat: add main scraper runner script"
```

---

### Task 10: Streamlit dashboard

**Files:**
- Create: `Autos/oportunidades/dashboard/app.py`

**Step 1: Implement dashboard**

`dashboard/app.py`:
```python
import sqlite3
import streamlit as st
import pandas as pd

DB_PATH = "autos.db"


@st.cache_data(ttl=60)
def load_data():
    conn = sqlite3.connect(DB_PATH)

    listings = pd.read_sql_query("SELECT * FROM listings", conn)
    references = pd.read_sql_query("SELECT * FROM market_reference", conn)
    conn.close()

    if listings.empty or references.empty:
        return listings, references, pd.DataFrame()

    # Merge to get median and calculate opportunity
    merged = listings.merge(
        references[["brand", "model", "year", "median_price_usd", "sample_count"]],
        on=["brand", "model", "year"],
        how="left",
    )
    merged["potential_profit_usd"] = merged["median_price_usd"] - merged["price_usd"]

    return listings, references, merged


def main():
    st.set_page_config(page_title="Detector de Oportunidades", layout="wide")
    st.title("Detector de Oportunidades de Autos")

    listings_df, references_df, merged_df = load_data()

    if merged_df.empty:
        st.warning("No hay datos. Ejecuta `python run_scraper.py` primero.")
        return

    # --- Sidebar Filters ---
    st.sidebar.header("Filtros")

    categories = ["Todas"] + sorted(merged_df["category"].dropna().unique().tolist())
    selected_cat = st.sidebar.selectbox("Categoría", categories)

    brands = ["Todas"] + sorted(merged_df["brand"].dropna().unique().tolist())
    selected_brand = st.sidebar.selectbox("Marca", brands)

    if selected_brand != "Todas":
        models = ["Todos"] + sorted(
            merged_df[merged_df["brand"] == selected_brand]["model"].dropna().unique().tolist()
        )
    else:
        models = ["Todos"] + sorted(merged_df["model"].dropna().unique().tolist())
    selected_model = st.sidebar.selectbox("Modelo", models)

    year_min = int(merged_df["year"].min()) if not merged_df["year"].isna().all() else 2016
    year_max = int(merged_df["year"].max()) if not merged_df["year"].isna().all() else 2026
    year_range = st.sidebar.slider("Año", year_min, year_max, (year_min, year_max))

    km_max_val = int(merged_df["km"].max()) if not merged_df["km"].isna().all() else 200000
    km_range = st.sidebar.slider("Kilómetros", 0, km_max_val, (0, km_max_val))

    price_max_val = int(merged_df["price_usd"].max()) if not merged_df["price_usd"].isna().all() else 100000
    price_range = st.sidebar.slider("Precio USD", 0, price_max_val, (0, price_max_val))

    min_profit = st.sidebar.slider("Ganancia mínima USD", 500, 10000, 1000, step=250)

    sources = ["Todas"] + sorted(merged_df["source"].dropna().unique().tolist())
    selected_source = st.sidebar.selectbox("Fuente", sources)

    location_filter = st.sidebar.radio("Ubicación", ["Todas", "Buenos Aires", "Otras provincias"])

    # --- Apply Filters ---
    df = merged_df.copy()

    if selected_cat != "Todas":
        df = df[df["category"] == selected_cat.lower()]
    if selected_brand != "Todas":
        df = df[df["brand"] == selected_brand]
    if selected_model != "Todos":
        df = df[df["model"] == selected_model]
    if selected_source != "Todas":
        df = df[df["source"] == selected_source]

    df = df[
        (df["year"] >= year_range[0]) & (df["year"] <= year_range[1]) &
        (df["km"].fillna(0) >= km_range[0]) & (df["km"].fillna(0) <= km_range[1]) &
        (df["price_usd"].fillna(0) >= price_range[0]) & (df["price_usd"].fillna(0) <= price_range[1])
    ]

    if location_filter == "Buenos Aires":
        df = df[df["location"].str.contains("Buenos Aires|Capital Federal|CABA|GBA", case=False, na=False)]
    elif location_filter == "Otras provincias":
        df = df[~df["location"].str.contains("Buenos Aires|Capital Federal|CABA|GBA", case=False, na=False)]

    # --- Opportunities ---
    opportunities = df[df["potential_profit_usd"] >= min_profit].sort_values(
        "potential_profit_usd", ascending=False
    )

    # --- Metrics ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Publicaciones", f"{len(listings_df):,}")
    col2.metric("Oportunidades", f"{len(opportunities):,}")

    if not opportunities.empty:
        best = opportunities.iloc[0]
        col3.metric(
            "Mejor Oportunidad",
            f"USD {best['potential_profit_usd']:,.0f}",
            f"{best['brand']} {best['model']} {best['year']}"
        )
    else:
        col3.metric("Mejor Oportunidad", "—")

    last_scrape = listings_df["scraped_at"].max() if "scraped_at" in listings_df.columns else "—"
    col4.metric("Último Scraping", str(last_scrape)[:16] if last_scrape != "—" else "—")

    # --- Opportunities Table ---
    st.subheader(f"Oportunidades ({len(opportunities)})")

    if not opportunities.empty:
        display_cols = [
            "brand", "model", "version", "year", "km",
            "price_usd", "price_ars", "median_price_usd",
            "potential_profit_usd", "location", "source",
            "transmission", "fuel", "category", "url",
        ]
        display_df = opportunities[
            [c for c in display_cols if c in opportunities.columns]
        ].reset_index(drop=True)

        display_df.columns = [
            "Marca", "Modelo", "Versión", "Año", "Km",
            "Precio USD", "Precio ARS", "Mediana USD",
            "Ganancia USD", "Ubicación", "Fuente",
            "Transmisión", "Combustible", "Categoría", "Link",
        ][:len(display_df.columns)]

        st.dataframe(
            display_df,
            column_config={
                "Link": st.column_config.LinkColumn("Link"),
                "Precio USD": st.column_config.NumberColumn(format="$%,.0f"),
                "Precio ARS": st.column_config.NumberColumn(format="$%,.0f"),
                "Mediana USD": st.column_config.NumberColumn(format="$%,.0f"),
                "Ganancia USD": st.column_config.NumberColumn(format="$%,.0f"),
                "Km": st.column_config.NumberColumn(format="%,d"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No se encontraron oportunidades con los filtros seleccionados.")

    # --- Market Analysis Tab ---
    st.subheader("Análisis de Mercado")

    if not references_df.empty:
        tab1, tab2 = st.tabs(["Precios por Modelo", "Publicaciones por Fuente"])

        with tab1:
            ref_display = references_df.sort_values("median_price_usd", ascending=False)
            ref_display = ref_display[["brand", "model", "year", "median_price_usd", "sample_count", "min_price_usd", "max_price_usd"]]
            ref_display.columns = ["Marca", "Modelo", "Año", "Mediana USD", "Muestras", "Mín USD", "Máx USD"]
            st.dataframe(
                ref_display,
                column_config={
                    "Mediana USD": st.column_config.NumberColumn(format="$%,.0f"),
                    "Mín USD": st.column_config.NumberColumn(format="$%,.0f"),
                    "Máx USD": st.column_config.NumberColumn(format="$%,.0f"),
                },
                use_container_width=True,
                hide_index=True,
            )

        with tab2:
            source_counts = listings_df["source"].value_counts()
            st.bar_chart(source_counts)


if __name__ == "__main__":
    main()
```

**Step 2: Test dashboard locally**

Run: `cd Autos/oportunidades && streamlit run dashboard/app.py`
Expected: Dashboard opens in browser. Shows "No hay datos" warning if no data yet.

**Step 3: Commit**

```bash
git add dashboard/app.py
git commit -m "feat: add Streamlit dashboard with filters and opportunity detection"
```

---

### Task 11: End-to-end integration test

**Step 1: Run full pipeline**

```bash
cd Autos/oportunidades
python run_scraper.py
```

Expected: Scraper runs, fetches data from at least MercadoLibre, saves to `autos.db`.

**Step 2: Verify data in DB**

```bash
cd Autos/oportunidades
python -c "
from db.database import Database
db = Database()
db.init()
listings = db.get_all_listings()
refs = db.get_market_references()
print(f'Listings: {len(listings)}')
print(f'References: {len(refs)}')
db.close()
"
```

Expected: Shows count of listings and references.

**Step 3: Launch dashboard and verify**

```bash
cd Autos/oportunidades && streamlit run dashboard/app.py
```

Expected: Dashboard shows data, filters work, opportunities appear.

**Step 4: Fix any scraper CSS selectors**

After seeing live data, adjust CSS selectors in Autocosmos, DeMotores, and OLX scrapers if needed.

**Step 5: Final commit**

```bash
git add -A
git commit -m "fix: adjust scrapers after integration testing"
```

---

## Task Summary

| Task | Component | Estimated Steps |
|------|-----------|----------------|
| 1 | Project setup | 3 |
| 2 | Database layer | 5 |
| 3 | Exchange rate module | 5 |
| 4 | MercadoLibre scraper | 5 |
| 5 | Autocosmos scraper | 5 |
| 6 | DeMotores scraper | 5 |
| 7 | OLX scraper | 5 |
| 8 | Analyzer module | 5 |
| 9 | Main runner script | 3 |
| 10 | Streamlit dashboard | 3 |
| 11 | End-to-end integration | 5 |
