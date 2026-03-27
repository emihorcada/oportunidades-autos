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
