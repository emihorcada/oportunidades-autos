"""
Database layer — supports both local SQLite and Supabase (REST API).

Set environment variable SUPABASE_URL and SUPABASE_KEY to use Supabase.
If not set, falls back to local SQLite.
"""

import os
import sqlite3
import requests


def get_database():
    """Factory: return the right database backend.

    Checks both os.environ (for CLI usage) and st.secrets (for Streamlit Cloud).
    """
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    # Streamlit Cloud stores secrets in st.secrets, not os.environ
    if not supabase_url:
        try:
            import streamlit as st
            supabase_url = st.secrets.get("SUPABASE_URL")
            supabase_key = st.secrets.get("SUPABASE_KEY")
        except Exception:
            pass

    if supabase_url and supabase_key:
        return SupabaseDatabase(supabase_url, supabase_key)
    return SQLiteDatabase()


class SQLiteDatabase:
    def __init__(self, db_path="autos.db"):
        self.db_path = db_path
        self.conn = None

    def init(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
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
                last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                published_days_ago INTEGER,
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
                category, transmission, fuel, image_url, scraped_at, last_seen_at)
            VALUES (:source, :source_id, :url, :brand, :model, :version,
                :year, :km, :price_ars, :price_usd, :currency_original, :location,
                :category, :transmission, :fuel, :image_url, datetime('now'), datetime('now'))
            ON CONFLICT(source, source_id) DO UPDATE SET
                price_ars = excluded.price_ars,
                price_usd = excluded.price_usd,
                km = excluded.km,
                url = excluded.url,
                image_url = excluded.image_url,
                last_seen_at = datetime('now')
        """, listing)
        self.conn.commit()

    def update_aging(self, source, source_id, published_days_ago):
        self.conn.execute(
            "UPDATE listings SET published_days_ago = ? WHERE source = ? AND source_id = ?",
            (published_days_ago, source, source_id),
        )
        self.conn.commit()

    def get_listing(self, source, source_id):
        """Get a single listing by source + source_id."""
        cursor = self.conn.execute(
            "SELECT * FROM listings WHERE source = ? AND source_id = ?",
            (source, source_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def log_price_change(self, source, source_id, old_usd, new_usd, old_ars, new_ars, change_pct):
        self.conn.execute("""
            INSERT INTO price_history (source, source_id, price_usd_old, price_usd_new,
                price_ars_old, price_ars_new, change_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (source, source_id, old_usd, new_usd, old_ars, new_ars, change_pct))
        self.conn.commit()

    def get_price_history(self, source=None, source_id=None):
        if source and source_id:
            cursor = self.conn.execute(
                "SELECT * FROM price_history WHERE source = ? AND source_id = ? ORDER BY recorded_at DESC",
                (source, source_id),
            )
        else:
            cursor = self.conn.execute("SELECT * FROM price_history ORDER BY recorded_at DESC")
        return [dict(row) for row in cursor.fetchall()]

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


class SupabaseDatabase:
    """Supabase backend using the PostgREST API."""

    def __init__(self, url, key):
        self.base = url.rstrip("/")
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    def init(self):
        pass  # Tables created via SQL Editor in Supabase dashboard

    def _post(self, table, data):
        resp = requests.post(
            f"{self.base}/rest/v1/{table}",
            headers=self.headers,
            json=data,
            timeout=30,
        )
        if resp.status_code not in (200, 201, 204):
            raise Exception(f"Supabase POST {table} failed ({resp.status_code}): {resp.text}")

    def _patch(self, table, match_params, data):
        params = "&".join(f"{k}=eq.{v}" for k, v in match_params.items())
        resp = requests.patch(
            f"{self.base}/rest/v1/{table}?{params}",
            headers=self.headers,
            json=data,
            timeout=30,
        )
        if resp.status_code not in (200, 204):
            raise Exception(f"Supabase PATCH {table} failed ({resp.status_code}): {resp.text}")

    def _get(self, table, select="*", params=None):
        url = f"{self.base}/rest/v1/{table}?select={select}"
        if params:
            url += "&" + "&".join(f"{k}={v}" for k, v in params.items())
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def upsert_listing(self, listing):
        row = {
            "source": listing["source"],
            "source_id": listing["source_id"],
            "url": listing.get("url", ""),
            "brand": listing["brand"],
            "model": listing["model"],
            "version": listing.get("version", ""),
            "year": listing["year"],
            "km": listing.get("km"),
            "price_ars": listing.get("price_ars"),
            "price_usd": listing.get("price_usd"),
            "currency_original": listing.get("currency_original", ""),
            "location": listing.get("location", ""),
            "category": listing.get("category"),
            "transmission": listing.get("transmission", ""),
            "fuel": listing.get("fuel", ""),
            "image_url": listing.get("image_url", ""),
        }
        # Use on_conflict to upsert
        resp = requests.post(
            f"{self.base}/rest/v1/listings?on_conflict=source,source_id",
            headers={
                **self.headers,
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=row,
            timeout=30,
        )
        if resp.status_code not in (200, 201, 204):
            raise Exception(f"Supabase upsert listings failed ({resp.status_code}): {resp.text}")

    def update_aging(self, source, source_id, published_days_ago):
        self._patch(
            "listings",
            {"source": source, "source_id": source_id},
            {"published_days_ago": published_days_ago},
        )

    def get_listing(self, source, source_id):
        rows = self._get("listings", params={
            "source": f"eq.{source}",
            "source_id": f"eq.{source_id}",
            "limit": "1",
        })
        return rows[0] if rows else None

    def log_price_change(self, source, source_id, old_usd, new_usd, old_ars, new_ars, change_pct):
        self._post("price_history", {
            "source": source,
            "source_id": source_id,
            "price_usd_old": old_usd,
            "price_usd_new": new_usd,
            "price_ars_old": old_ars,
            "price_ars_new": new_ars,
            "change_pct": change_pct,
        })

    def get_price_history(self, source=None, source_id=None):
        params = {"order": "recorded_at.desc"}
        if source and source_id:
            params["source"] = f"eq.{source}"
            params["source_id"] = f"eq.{source_id}"
        return self._get("price_history", params=params)

    def get_all_listings(self):
        # Supabase paginates at 1000 rows by default
        all_rows = []
        offset = 0
        while True:
            rows = self._get("listings", params={
                "limit": "1000",
                "offset": str(offset),
            })
            all_rows.extend(rows)
            if len(rows) < 1000:
                break
            offset += 1000
        return all_rows

    def save_market_reference(self, ref):
        row = {
            "brand": ref["brand"],
            "model": ref["model"],
            "year": ref["year"],
            "median_price_usd": ref["median_price_usd"],
            "sample_count": ref["sample_count"],
            "min_price_usd": ref["min_price_usd"],
            "max_price_usd": ref["max_price_usd"],
        }
        resp = requests.post(
            f"{self.base}/rest/v1/market_reference?on_conflict=brand,model,year",
            headers={
                **self.headers,
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=row,
            timeout=30,
        )
        if resp.status_code not in (200, 201, 204):
            raise Exception(f"Supabase upsert market_reference failed ({resp.status_code}): {resp.text}")

    def get_market_references(self):
        return self._get("market_reference")

    def close(self):
        pass  # No persistent connection
