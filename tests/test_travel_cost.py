"""Tests for travel_cost module."""

import pytest
from core.travel_cost import estimate_travel_cost


class TestCABALocations:
    """Cars in CABA should not need travel."""

    def test_capital_federal(self):
        result = estimate_travel_cost("Capital Federal, Capital Federal")
        assert result["needs_travel"] is False
        assert result["total_usd"] == 0

    def test_ciudad_autonoma(self):
        result = estimate_travel_cost("Caballito, Ciudad Autónoma de Buenos Aires")
        assert result["needs_travel"] is False
        assert result["total_usd"] == 0

    def test_caba_simple(self):
        result = estimate_travel_cost("CABA")
        assert result["needs_travel"] is False
        assert result["total_usd"] == 0


class TestGBALocations:
    """Cars in Gran Buenos Aires should not need travel."""

    def test_quilmes(self):
        result = estimate_travel_cost("Quilmes, Buenos Aires")
        assert result["needs_travel"] is False
        assert result["total_usd"] == 0

    def test_la_matanza(self):
        result = estimate_travel_cost("La Matanza, Buenos Aires")
        assert result["needs_travel"] is False
        assert result["total_usd"] == 0

    def test_san_isidro(self):
        result = estimate_travel_cost("San Isidro, Buenos Aires")
        assert result["needs_travel"] is False
        assert result["total_usd"] == 0

    def test_olivos(self):
        result = estimate_travel_cost("Olivos, Buenos Aires")
        assert result["needs_travel"] is False
        assert result["total_usd"] == 0


class TestCordoba:
    """Córdoba is 700km — should use plane (>800? no, 700<800 so bus), needs hotel (>400)."""

    def test_cordoba_needs_travel(self):
        result = estimate_travel_cost("Córdoba, Córdoba")
        assert result["needs_travel"] is True

    def test_cordoba_transport_mode(self):
        # 700km <= 800km, so bus
        result = estimate_travel_cost("Córdoba, Córdoba")
        assert result["transport_mode"] == "bus"

    def test_cordoba_hotel(self):
        # 700km > 400km, so hotel needed
        result = estimate_travel_cost("Córdoba, Córdoba")
        assert result["hotel_usd"] == 35

    def test_cordoba_fuel(self):
        # 700km * 10/100 * 1.0 = 70 USD
        result = estimate_travel_cost("Córdoba, Córdoba")
        assert result["fuel_usd"] == 70.0

    def test_cordoba_distance(self):
        result = estimate_travel_cost("Córdoba, Córdoba")
        assert result["distance_km"] == 700

    def test_cordoba_transport_cost(self):
        # 500-1000km bus = USD 30
        result = estimate_travel_cost("Córdoba, Córdoba")
        assert result["transport_usd"] == 30

    def test_cordoba_total(self):
        # bus 30 + hotel 35 + fuel 70 = 135
        result = estimate_travel_cost("Córdoba, Córdoba")
        assert result["total_usd"] == 135.0


class TestRosario:
    """Rosario is 300km — bus, no hotel."""

    def test_rosario_needs_travel(self):
        result = estimate_travel_cost("Rosario, Santa Fe")
        assert result["needs_travel"] is True

    def test_rosario_transport_mode(self):
        result = estimate_travel_cost("Rosario, Santa Fe")
        assert result["transport_mode"] == "bus"

    def test_rosario_no_hotel(self):
        # 300km <= 400km, no hotel
        result = estimate_travel_cost("Rosario, Santa Fe")
        assert result["hotel_usd"] == 0

    def test_rosario_fuel(self):
        # 300km * 10/100 * 1.0 = 30 USD
        result = estimate_travel_cost("Rosario, Santa Fe")
        assert result["fuel_usd"] == 30.0

    def test_rosario_transport_cost(self):
        # Under 500km bus = USD 15
        result = estimate_travel_cost("Rosario, Santa Fe")
        assert result["transport_usd"] == 15

    def test_rosario_total(self):
        # bus 15 + hotel 0 + fuel 30 = 45
        result = estimate_travel_cost("Rosario, Santa Fe")
        assert result["total_usd"] == 45.0


class TestUshuaia:
    """Ushuaia is 3100km — plane, hotel, lots of fuel."""

    def test_ushuaia_needs_travel(self):
        result = estimate_travel_cost("Ushuaia, Tierra del Fuego")
        assert result["needs_travel"] is True

    def test_ushuaia_transport_mode(self):
        result = estimate_travel_cost("Ushuaia, Tierra del Fuego")
        assert result["transport_mode"] == "avión"

    def test_ushuaia_hotel(self):
        result = estimate_travel_cost("Ushuaia, Tierra del Fuego")
        assert result["hotel_usd"] == 35

    def test_ushuaia_fuel(self):
        # 3100km * 10/100 * 1.0 = 310 USD
        result = estimate_travel_cost("Ushuaia, Tierra del Fuego")
        assert result["fuel_usd"] == 310.0

    def test_ushuaia_distance(self):
        result = estimate_travel_cost("Ushuaia, Tierra del Fuego")
        assert result["distance_km"] == 3100

    def test_ushuaia_transport_cost(self):
        # plane: 60 + 0.03 * (3100 - 800) = 60 + 69 = 129
        result = estimate_travel_cost("Ushuaia, Tierra del Fuego")
        assert result["transport_usd"] == 129.0

    def test_ushuaia_total(self):
        # plane 129 + hotel 35 + fuel 310 = 474
        result = estimate_travel_cost("Ushuaia, Tierra del Fuego")
        assert result["total_usd"] == 474.0


class TestUnknownLocation:
    """Unknown locations should return a default estimate."""

    def test_unknown_needs_travel(self):
        result = estimate_travel_cost("Pueblo Desconocido, La Nada")
        assert result["needs_travel"] is True

    def test_unknown_has_total(self):
        result = estimate_travel_cost("Pueblo Desconocido, La Nada")
        assert result["total_usd"] > 0

    def test_unknown_has_detail(self):
        result = estimate_travel_cost("Pueblo Desconocido, La Nada")
        assert isinstance(result["detail"], str)
        assert len(result["detail"]) > 0


class TestDetailString:
    """The detail string should be a human-readable breakdown in Spanish."""

    def test_detail_contains_total(self):
        result = estimate_travel_cost("Córdoba, Córdoba")
        assert "Total" in result["detail"]
        assert "USD" in result["detail"]

    def test_no_travel_detail(self):
        result = estimate_travel_cost("CABA")
        assert result["detail"] == "Local (CABA/GBA), sin costo de viaje"


class TestBuenosAiresInterior:
    """Cities in Buenos Aires province that are NOT in GBA."""

    def test_mar_del_plata(self):
        result = estimate_travel_cost("Mar del Plata, Buenos Aires")
        assert result["needs_travel"] is True
        assert result["distance_km"] == 400

    def test_bahia_blanca(self):
        result = estimate_travel_cost("Bahía Blanca, Buenos Aires")
        assert result["needs_travel"] is True
        assert result["distance_km"] == 650

    def test_unknown_ba_interior(self):
        """Unknown city in Buenos Aires province defaults to 300km."""
        result = estimate_travel_cost("Pueblo Interior, Buenos Aires")
        assert result["needs_travel"] is True
        assert result["distance_km"] == 300
