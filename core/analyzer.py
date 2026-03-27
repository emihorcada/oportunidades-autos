"""
Motor de análisis de oportunidades de compra de autos.

Criterios:
1. Agrupación inteligente: versión > transmisión > modelo (fallback en cascada)
2. Comparación por km: solo contra autos con ±20.000 km
3. Filtro de precios inflados: descarta el 20% más caro antes de calcular
4. Mediana del grupo filtrado como precio de referencia
5. Oportunidad = precio < mediana filtrada por >= USD 1.000
"""

from collections import defaultdict
from statistics import median
import math

KM_RANGE = 20000  # ±20k km for comparison
MIN_PEERS = 3     # minimum peers to form a valid group
TOP_PERCENT_CUT = 0.20  # remove top 20% most expensive


def calculate_median(values):
    return float(median(values))


def categorize(median_price_usd):
    if median_price_usd > 30000:
        return "alta"
    elif median_price_usd >= 10000:
        return "media"
    else:
        return "baja"


def _filter_top_percent(prices, cut_percent):
    """Remove the top cut_percent most expensive prices."""
    if len(prices) <= 2:
        return prices
    sorted_prices = sorted(prices)
    cut_count = max(1, math.ceil(len(sorted_prices) * cut_percent))
    return sorted_prices[:-cut_count]


def _get_km_peers(listings, target_km):
    """Filter listings to those within ±KM_RANGE of target_km."""
    if target_km is None:
        return listings
    return [l for l in listings if l.get("km") is not None
            and abs(l["km"] - target_km) <= KM_RANGE]


def _normalize_version(version):
    """Normalize version string for grouping."""
    if not version:
        return ""
    return version.strip().lower()


def _find_peer_group(listing, all_listings):
    """
    Find the best peer group for a listing using cascading logic:
    1. Same brand + model + year + version, ±20k km (if >= 3 peers)
    2. Same brand + model + year + transmission, ±20k km (if >= 3 peers)
    3. Same brand + model + year, ±20k km (if >= 3 peers)
    4. Same brand + model + year, any km (last resort)

    Returns (peers, group_level) where group_level describes match quality.
    """
    brand = listing.get("brand", "")
    model = listing.get("model", "")
    year = listing.get("year")
    version = _normalize_version(listing.get("version", ""))
    transmission = (listing.get("transmission") or "").strip().lower()
    target_km = listing.get("km")
    source_id = listing.get("source_id", "")

    # Base group: same brand + model + year (excluding self)
    base = [l for l in all_listings
            if l.get("brand") == brand
            and l.get("model") == model
            and l.get("year") == year
            and l.get("price_usd")
            and l.get("source_id") != source_id]

    # Level 1: version + km range
    if version:
        version_peers = [l for l in base
                         if _normalize_version(l.get("version", "")) == version]
        km_filtered = _get_km_peers(version_peers, target_km)
        if len(km_filtered) >= MIN_PEERS:
            return km_filtered, "versión + km"

    # Level 2: transmission + km range
    if transmission:
        trans_peers = [l for l in base
                       if (l.get("transmission") or "").strip().lower() == transmission]
        km_filtered = _get_km_peers(trans_peers, target_km)
        if len(km_filtered) >= MIN_PEERS:
            return km_filtered, "transmisión + km"

    # Level 3: model + year + km range
    km_filtered = _get_km_peers(base, target_km)
    if len(km_filtered) >= MIN_PEERS:
        return km_filtered, "modelo + km"

    # Level 4: model + year (any km, last resort)
    if len(base) >= MIN_PEERS:
        return base, "modelo"

    # Not enough peers
    return base, "insuficiente"


def _calc_reference_price(peers):
    """Calculate reference price: remove top 20%, then median."""
    prices = [p["price_usd"] for p in peers if p.get("price_usd")]
    if not prices:
        return None, []
    filtered = _filter_top_percent(prices, TOP_PERCENT_CUT)
    if not filtered:
        return None, []
    return calculate_median(filtered), filtered


def evaluate_listing(listing, all_listings):
    """
    Evaluate a single listing to determine if it's an opportunity.

    Returns a dict with analysis results, or None if not enough data.
    """
    if not listing.get("price_usd") or not listing.get("brand") or not listing.get("model") or not listing.get("year"):
        return None

    peers, group_level = _find_peer_group(listing, all_listings)

    if len(peers) < 2:
        return None

    ref_price, filtered_prices = _calc_reference_price(peers)
    if ref_price is None:
        return None

    diff = ref_price - listing["price_usd"]

    return {
        "median_price_usd": round(ref_price, 2),
        "potential_profit_usd": round(diff, 2),
        "sample_count": len(peers),
        "group_level": group_level,
        "peer_prices": sorted(filtered_prices),
        "category": categorize(ref_price),
    }


def find_opportunities(listings, min_diff_usd=1000):
    """
    Find all listings that are priced below their peer group median
    by at least min_diff_usd.
    """
    opportunities = []

    for lst in listings:
        result = evaluate_listing(lst, listings)
        if result is None:
            continue

        if result["potential_profit_usd"] >= min_diff_usd:
            opp = dict(lst)
            opp.update(result)
            opportunities.append(opp)

    opportunities.sort(key=lambda x: x["potential_profit_usd"], reverse=True)
    return opportunities


def analyze_listings(listings):
    """
    Generate market reference summary (for the overview table).
    Groups by brand + model + year, applies the top-20% filter.
    """
    groups = defaultdict(list)
    for lst in listings:
        if lst.get("price_usd") and lst.get("brand") and lst.get("model") and lst.get("year"):
            key = (lst["brand"], lst["model"], lst["year"])
            groups[key].append(lst["price_usd"])

    references = []
    for (brand, model, year), prices in groups.items():
        if len(prices) < 2:
            continue
        filtered = _filter_top_percent(prices, TOP_PERCENT_CUT)
        if not filtered:
            continue
        med = calculate_median(filtered)
        references.append({
            "brand": brand,
            "model": model,
            "year": year,
            "median_price_usd": round(med, 2),
            "sample_count": len(prices),
            "min_price_usd": min(prices),
            "max_price_usd": max(prices),
        })
    return references
