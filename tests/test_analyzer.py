from core.analyzer import (
    calculate_median, categorize, analyze_listings,
    find_opportunities, evaluate_listing, _filter_top_percent,
    _get_km_peers,
)


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


def test_filter_top_percent():
    result = _filter_top_percent([10, 20, 30, 40, 50], 0.20)
    assert result == [10, 20, 30, 40]


def test_filter_top_percent_small_list():
    result = _filter_top_percent([10, 20], 0.20)
    assert result == [10, 20]


def test_get_km_peers():
    listings = [
        {"km": 30000, "price_usd": 10000},
        {"km": 50000, "price_usd": 11000},
        {"km": 80000, "price_usd": 9000},
        {"km": 120000, "price_usd": 8000},
    ]
    peers = _get_km_peers(listings, 50000)
    assert len(peers) == 2


def _make(brand, model, year, price, km=50000, version="", transmission="", source_id=None):
    return {
        "brand": brand, "model": model, "year": year,
        "price_usd": price, "km": km, "version": version,
        "transmission": transmission,
        "source_id": source_id or f"{brand}-{model}-{price}-{km}",
    }


def test_find_opportunities_basic():
    listings = [
        _make("Toyota", "Corolla", 2020, 12000, km=50000),
        _make("Toyota", "Corolla", 2020, 14000, km=55000),
        _make("Toyota", "Corolla", 2020, 15000, km=45000),
        _make("Toyota", "Corolla", 2020, 16000, km=60000),
    ]
    opps = find_opportunities(listings, min_diff_usd=1000)
    assert len(opps) >= 1
    assert opps[0]["price_usd"] == 12000


def test_find_opportunities_no_match():
    listings = [
        _make("Toyota", "Corolla", 2020, 13500, km=50000),
        _make("Toyota", "Corolla", 2020, 14000, km=55000),
        _make("Toyota", "Corolla", 2020, 14500, km=45000),
    ]
    opps = find_opportunities(listings, min_diff_usd=1000)
    assert len(opps) == 0


def test_find_opportunities_respects_km_range():
    listings = [
        _make("Toyota", "Corolla", 2020, 8000, km=150000),
        _make("Toyota", "Corolla", 2020, 14000, km=50000),
        _make("Toyota", "Corolla", 2020, 15000, km=55000),
        _make("Toyota", "Corolla", 2020, 16000, km=45000),
        _make("Toyota", "Corolla", 2020, 17000, km=60000),
    ]
    opps = find_opportunities(listings, min_diff_usd=1000)
    for opp in opps:
        if opp["price_usd"] == 8000:
            assert opp["group_level"] in ("modelo", "insuficiente", "modelo + km")


def test_evaluate_listing_version_grouping():
    listings = [
        _make("Toyota", "Corolla", 2020, 12000, km=50000, version="XEI 1.8 CVT"),
        _make("Toyota", "Corolla", 2020, 18000, km=55000, version="XEI 1.8 CVT"),
        _make("Toyota", "Corolla", 2020, 19000, km=45000, version="XEI 1.8 CVT"),
        _make("Toyota", "Corolla", 2020, 20000, km=60000, version="XEI 1.8 CVT"),
        _make("Toyota", "Corolla", 2020, 10000, km=50000, version="XLI 1.6"),
        _make("Toyota", "Corolla", 2020, 11000, km=55000, version="XLI 1.6"),
        _make("Toyota", "Corolla", 2020, 12000, km=45000, version="XLI 1.6"),
    ]
    result = evaluate_listing(listings[0], listings)
    assert result is not None
    assert result["group_level"] == "versión + km"
    assert result["median_price_usd"] == 18500.0


def test_evaluate_listing_transmission_fallback():
    listings = [
        _make("Toyota", "Corolla", 2020, 12000, km=50000, version="A", transmission="automática"),
        _make("Toyota", "Corolla", 2020, 18000, km=55000, version="B", transmission="automática"),
        _make("Toyota", "Corolla", 2020, 19000, km=45000, version="C", transmission="automática"),
        _make("Toyota", "Corolla", 2020, 20000, km=60000, version="D", transmission="automática"),
    ]
    result = evaluate_listing(listings[0], listings)
    assert result is not None
    assert result["group_level"] == "transmisión + km"


def test_analyze_listings_filters_top():
    listings = [
        _make("Toyota", "Corolla", 2020, 12000),
        _make("Toyota", "Corolla", 2020, 14000),
        _make("Toyota", "Corolla", 2020, 15000),
        _make("Toyota", "Corolla", 2020, 16000),
        _make("Toyota", "Corolla", 2020, 50000),
    ]
    refs = analyze_listings(listings)
    corolla = next(r for r in refs if r["model"] == "Corolla")
    assert corolla["median_price_usd"] == 14500.0
