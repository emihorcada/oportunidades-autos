from unittest.mock import patch, MagicMock
from core.exchange_rate import get_usd_blue_rate, convert_ars_to_usd


def test_get_usd_blue_rate():
    mock_response = MagicMock()
    mock_response.json.return_value = {"venta": 1200.0, "compra": 1180.0}
    mock_response.raise_for_status = MagicMock()

    with patch("core.exchange_rate.requests.get", return_value=mock_response):
        rate = get_usd_blue_rate()
        assert rate == 1200.0


def test_convert_ars_to_usd():
    assert convert_ars_to_usd(12000000, 1200.0) == 10000.0
    assert convert_ars_to_usd(0, 1200.0) == 0.0


def test_convert_ars_to_usd_none_price():
    assert convert_ars_to_usd(None, 1200.0) is None
