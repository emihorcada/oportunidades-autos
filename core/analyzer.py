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
