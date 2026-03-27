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


SAMPLE_HTML = (
    '<html><script>_n.ctx.r={"total":5,"other":"data",'
    '"items":[{"id":"POLYCARD","state":"VISIBLE",'
    '"polycard":{"unique_id":"abc123","metadata":{"id":"MLA9999999999",'
    '"url":"auto.mercadolibre.com.ar/MLA-9999999999-toyota-corolla-_JM",'
    '"category_id":"MLA1744","domain_id":"MLA-CARS_AND_VANS","item_position":"1"},'
    '"pictures":{"pictures":[{"id":"123456-MLA00000000000_012025"}]},'
    '"components":['
    '{"type":"title","id":"title","title":{"text":"Toyota Corolla 1.8 Xei Cvt Pack"}},'
    '{"type":"price","id":"price","price":{"current_price":{"value":15000000,"currency":"ARS"}}},'
    '{"type":"attributes_list","id":"attributes_list","attributes_list":{"separator":"|","texts":["2020","50.000 Km"]}},'
    '{"type":"location","id":"location","location":{"text":"Capital Federal - Capital Federal"}}'
    ']}}]};</script></html>'
)


def test_fetch_page():
    mock_response = MagicMock()
    mock_response.text = SAMPLE_HTML
    mock_response.raise_for_status = MagicMock()

    scraper = MercadoLibreScraper(usd_rate=1200.0)
    with patch.object(scraper.session, "get", return_value=mock_response):
        results, total = scraper.fetch_page(offset=0)
        assert len(results) == 1
        assert total == 5
        assert results[0]["brand"] == "Toyota"
        assert results[0]["source_id"] == "MLA9999999999"
        assert results[0]["year"] == 2020
        assert results[0]["km"] == 50000
        assert results[0]["price_ars"] == 15000000
        assert results[0]["price_usd"] == 12500.0
        assert "Capital Federal" in results[0]["location"]
