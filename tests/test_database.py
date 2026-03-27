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
