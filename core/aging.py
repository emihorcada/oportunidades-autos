"""
Obtiene la antigüedad de publicación desde la página individual del listing.

Solo funciona con MercadoLibre (muestra "Publicado hace X días/meses/año").
Para otras fuentes devuelve None.
"""

import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}

# Pattern: "Publicado hace 25 días" or "1 mes" or "1 año"
_AGING_RE = re.compile(r'Publicado hace\s+(\d+)\s+(día|días|mes|meses|año|años)')


def _parse_aging_text(text):
    """Convert 'Publicado hace X días/meses/año' to days."""
    match = _AGING_RE.search(text)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if "día" in unit:
        return value
    elif "mes" in unit:
        return value * 30
    elif "año" in unit:
        return value * 365
    return None


def fetch_aging_days(url, source="mercadolibre"):
    """Fetch how many days ago a listing was published.

    Returns number of days, or None if unavailable.
    """
    if source != "mercadolibre" or not url:
        return None
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        return _parse_aging_text(resp.text)
    except Exception as e:
        logger.debug(f"Could not fetch aging for {url}: {e}")
        return None


def fetch_aging_batch(listings, delay=1.5):
    """Fetch aging for a list of listing dicts. Updates each dict in place.

    Only fetches for MercadoLibre listings. Autocosmos gets None.
    Adds 'published_days_ago' key to each dict.
    """
    total = len(listings)
    fetched = 0
    for i, lst in enumerate(listings):
        source = lst.get("source", "")
        url = lst.get("url", "")
        if source == "mercadolibre" and url:
            days = fetch_aging_days(url, source)
            lst["published_days_ago"] = days
            fetched += 1
            if (i + 1) % 20 == 0:
                logger.info(f"  Aging: {i + 1}/{total} processed ({fetched} fetched)")
            time.sleep(delay)
        else:
            lst["published_days_ago"] = None
    logger.info(f"Aging: done. {fetched} fetched out of {total}")
