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
