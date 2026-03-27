from unittest.mock import patch, MagicMock
from scrapers.demotores import DeMotoresScraper


def test_parse_price_ars():
    scraper = DeMotoresScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("$ 15.000.000")
    assert price == 15000000.0
    assert currency == "ARS"


def test_parse_price_usd():
    scraper = DeMotoresScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("U$S 13.000")
    assert price == 13000.0
    assert currency == "USD"


def test_parse_price_usd_keyword():
    scraper = DeMotoresScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("USD 25.000")
    assert price == 25000.0
    assert currency == "USD"


def test_parse_price_none():
    scraper = DeMotoresScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price(None)
    assert price is None
    assert currency is None


def test_parse_price_empty():
    scraper = DeMotoresScraper(usd_rate=1200.0)
    price, currency = scraper._parse_price("")
    assert price is None
    assert currency is None


def test_parse_km():
    scraper = DeMotoresScraper(usd_rate=1200.0)
    assert scraper._parse_km("50.000 km") == 50000


def test_parse_km_none():
    scraper = DeMotoresScraper(usd_rate=1200.0)
    assert scraper._parse_km(None) is None


def test_parse_km_empty():
    scraper = DeMotoresScraper(usd_rate=1200.0)
    assert scraper._parse_km("") is None


def test_scraper_has_scrape_all():
    scraper = DeMotoresScraper(usd_rate=1200.0)
    assert hasattr(scraper, "scrape_all")


def test_scraper_has_scrape_page():
    scraper = DeMotoresScraper(usd_rate=1200.0)
    assert hasattr(scraper, "scrape_page")


def test_scraper_has_parse_listing_element():
    scraper = DeMotoresScraper(usd_rate=1200.0)
    assert hasattr(scraper, "parse_listing_element")


def test_parse_listing_element():
    """Test parsing a simulated listing HTML element."""
    from bs4 import BeautifulSoup

    html = """
    <div class="listing-card">
        <a class="listing-card__link" href="/auto/toyota-corolla-123">
            <img class="listing-card__image" src="https://img.demotores.com/123.jpg" />
        </a>
        <h2 class="listing-card__title">Toyota Corolla 1.8 XEi CVT</h2>
        <span class="listing-card__price">$ 15.000.000</span>
        <span class="listing-card__year">2020</span>
        <span class="listing-card__km">50.000 km</span>
        <span class="listing-card__location">Capital Federal</span>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    element = soup.find("div", class_="listing-card")

    scraper = DeMotoresScraper(usd_rate=1200.0)
    result = scraper.parse_listing_element(element)

    assert result is not None
    assert result["source"] == "demotores"
    assert result["price_ars"] == 15000000.0
    assert result["price_usd"] == 12500.0
    assert result["year"] == 2020
    assert result["km"] == 50000
    assert result["location"] == "Capital Federal"


def test_parse_listing_element_usd_price():
    """Test parsing a listing with USD price."""
    from bs4 import BeautifulSoup

    html = """
    <div class="listing-card">
        <a class="listing-card__link" href="/auto/ford-ranger-456">
            <img class="listing-card__image" src="https://img.demotores.com/456.jpg" />
        </a>
        <h2 class="listing-card__title">Ford Ranger 3.2 XLT</h2>
        <span class="listing-card__price">U$S 25.000</span>
        <span class="listing-card__year">2021</span>
        <span class="listing-card__km">30.000 km</span>
        <span class="listing-card__location">Córdoba</span>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    element = soup.find("div", class_="listing-card")

    scraper = DeMotoresScraper(usd_rate=1200.0)
    result = scraper.parse_listing_element(element)

    assert result is not None
    assert result["price_usd"] == 25000.0
    assert result["price_ars"] == 30000000.0
    assert result["currency_original"] == "USD"


def test_scrape_page_mock():
    """Test scrape_page with mocked HTTP response."""
    html_page = """
    <html><body>
    <div class="listing-card">
        <a class="listing-card__link" href="/auto/vw-golf-789">
            <img class="listing-card__image" src="https://img.demotores.com/789.jpg" />
        </a>
        <h2 class="listing-card__title">Volkswagen Golf 1.4 TSI</h2>
        <span class="listing-card__price">$ 12.000.000</span>
        <span class="listing-card__year">2019</span>
        <span class="listing-card__km">60.000 km</span>
        <span class="listing-card__location">Rosario</span>
    </div>
    </body></html>
    """
    mock_response = MagicMock()
    mock_response.text = html_page
    mock_response.url = "https://www.demotores.com.ar/autos/usados"
    mock_response.raise_for_status = MagicMock()

    scraper = DeMotoresScraper(usd_rate=1200.0)
    with patch.object(scraper.session, "get", return_value=mock_response):
        results = scraper.scrape_page(1)
        assert len(results) == 1
        assert results[0]["source"] == "demotores"
        assert results[0]["price_ars"] == 12000000.0


def test_scrape_page_detects_shutdown():
    """Test that scraper detects site shutdown (redirect to soloautos.mx)."""
    closure_html = """
    <html><body>
    <div class="container closingPage">
        <h1>Aviso de Cierre</h1>
    </div>
    </body></html>
    """
    mock_response = MagicMock()
    mock_response.text = closure_html
    mock_response.url = "https://soloautos.mx/mxclose"
    mock_response.raise_for_status = MagicMock()

    scraper = DeMotoresScraper(usd_rate=1200.0)
    with patch.object(scraper.session, "get", return_value=mock_response):
        results = scraper.scrape_page(1)
        assert results == []
