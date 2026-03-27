from unittest.mock import patch, MagicMock
from scrapers.olx import OLXScraper


def test_parse_price_ars():
    scraper = OLXScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("$ 15.000.000")
    assert price == 15000000.0
    assert currency == "ARS"


def test_parse_price_usd():
    scraper = OLXScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("U$S 13.000")
    assert price == 13000.0
    assert currency == "USD"


def test_parse_price_usd_keyword():
    scraper = OLXScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("USD 25.000")
    assert price == 25000.0
    assert currency == "USD"


def test_parse_price_none():
    scraper = OLXScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price(None)
    assert price is None


def test_parse_price_empty():
    scraper = OLXScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("")
    assert price is None


def test_parse_km():
    scraper = OLXScraper(usd_rate=1200.0)
    assert scraper._parse_km("50.000 km") == 50000
    assert scraper._parse_km(None) is None


def test_parse_km_no_unit():
    scraper = OLXScraper(usd_rate=1200.0)
    assert scraper._parse_km("120000") == 120000


def test_scraper_has_scrape_all():
    scraper = OLXScraper(usd_rate=1200.0)
    assert hasattr(scraper, "scrape_all")


def test_parse_listing_element():
    scraper = OLXScraper(usd_rate=1200.0)
    html = """
    <li class="listing-card">
        <a href="https://www.olx.com.ar/item/toyota-corolla-2020-iid-1234">
            <div class="listing-card__title">Toyota Corolla 1.8 XEi CVT 2020</div>
            <div class="listing-card__price">U$S 13.000</div>
            <div class="listing-card__detail">80.000 km</div>
            <div class="listing-card__detail--location">Capital Federal</div>
            <img src="https://img.olx.com.ar/images/12345.jpg" />
        </a>
    </li>
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    element = soup.find("li")
    result = scraper.parse_listing_element(element)
    assert result["source"] == "olx"
    assert result["price_usd"] == 13000.0
    assert result["km"] == 80000
    assert "toyota-corolla" in result["url"].lower()


def test_scrape_page_mock():
    scraper = OLXScraper(usd_rate=1200.0)
    fake_html = """
    <html><body>
    <ul class="listing-list">
        <li class="listing-card">
            <a href="https://www.olx.com.ar/item/ford-focus-2019-iid-5678">
                <div class="listing-card__title">Ford Focus 2.0 SE 2019</div>
                <div class="listing-card__price">$ 12.000.000</div>
                <div class="listing-card__detail">60.000 km</div>
                <div class="listing-card__detail--location">Córdoba</div>
                <img src="https://img.olx.com.ar/images/67890.jpg" />
            </a>
        </li>
    </ul>
    </body></html>
    """
    mock_response = MagicMock()
    mock_response.text = fake_html
    mock_response.raise_for_status = MagicMock()

    with patch.object(scraper.session, "get", return_value=mock_response):
        results = scraper.scrape_page(1)
        assert len(results) == 1
        assert results[0]["source"] == "olx"
        assert results[0]["price_ars"] == 12000000.0
