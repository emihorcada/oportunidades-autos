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
