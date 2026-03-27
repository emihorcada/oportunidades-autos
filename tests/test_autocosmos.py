from scrapers.autocosmos import AutocosmosScraper


def test_parse_price_ars():
    scraper = AutocosmosScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("$ 15.000.000")
    assert price == 15000000.0
    assert currency == "ARS"


def test_parse_price_usd():
    scraper = AutocosmosScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("U$S 13.000")
    assert price == 13000.0
    assert currency == "USD"


def test_parse_price_usd_alt():
    scraper = AutocosmosScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("USD 25.000")
    assert price == 25000.0
    assert currency == "USD"


def test_parse_price_none():
    scraper = AutocosmosScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price(None)
    assert price is None


def test_parse_price_empty():
    scraper = AutocosmosScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("")
    assert price is None


def test_parse_km():
    scraper = AutocosmosScraper(usd_rate=1200.0)
    assert scraper._parse_km("50.000 km") == 50000
    assert scraper._parse_km(None) is None


def test_parse_km_no_unit():
    scraper = AutocosmosScraper(usd_rate=1200.0)
    assert scraper._parse_km("120.000") == 120000


def test_scraper_has_scrape_all():
    scraper = AutocosmosScraper(usd_rate=1200.0)
    assert hasattr(scraper, "scrape_all")


def test_scraper_has_expected_methods():
    scraper = AutocosmosScraper(usd_rate=1200.0)
    assert hasattr(scraper, "scrape_page")
    assert hasattr(scraper, "parse_listing_element")
    assert hasattr(scraper, "_parse_price")
    assert hasattr(scraper, "_parse_km")


def test_scraper_session_created():
    scraper = AutocosmosScraper(usd_rate=1200.0)
    assert scraper.session is not None
    assert scraper.usd_rate == 1200.0
