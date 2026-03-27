"""
Estimador de costo de viaje para buscar autos fuera de CABA/GBA.

Calcula transporte (micro o avión), hotel y nafta para ir a buscar
un auto y manejarlo de vuelta a Buenos Aires.
"""

import unicodedata
import re

DISTANCES = {
    # CABA & GBA - no travel needed
    "capital federal": 0,
    "caba": 0,
    "buenos aires": 0,
    "gba": 0,
    "gran buenos aires": 0,
    "ciudad autonoma de buenos aires": 0,

    # Buenos Aires province (interior)
    "mar del plata": 400,
    "bahia blanca": 650,
    "tandil": 350,
    "olavarria": 350,
    "necochea": 500,
    "junin": 260,
    "pergamino": 220,

    # Other provinces
    "rosario": 300,
    "santa fe": 475,
    "cordoba": 700,
    "mendoza": 1050,
    "san luis": 800,
    "san juan": 1100,
    "tucuman": 1300,
    "salta": 1500,
    "jujuy": 1600,
    "santiago del estero": 1100,
    "catamarca": 1100,
    "la rioja": 1150,
    "entre rios": 350,
    "parana": 500,
    "corrientes": 950,
    "resistencia": 1000,
    "posadas": 1050,
    "misiones": 1050,
    "neuquen": 1150,
    "bariloche": 1600,
    "comodoro rivadavia": 1800,
    "trelew": 1400,
    "rio gallegos": 2600,
    "ushuaia": 3100,
    "la pampa": 600,
    "santa rosa": 600,
    "san rafael": 900,
}

GBA_PARTIDOS = {
    "la matanza", "quilmes", "lomas de zamora", "lanus", "avellaneda",
    "moron", "tres de febrero", "san martin", "vicente lopez", "san isidro",
    "tigre", "pilar", "escobar", "san fernando", "merlo", "moreno",
    "jose c. paz", "malvinas argentinas", "san miguel", "hurlingham",
    "ituzaingo", "ezeiza", "esteban echeverria", "almirante brown",
    "florencio varela", "berazategui", "hudson", "temperley", "adrogue",
    "wilde", "sarandi", "bernal", "don torcuato", "olivos",
}

# Bus costs by distance
BUS_COST_UNDER_500 = 15
BUS_COST_500_1000 = 30
BUS_COST_OVER_1000 = 50

# Plane costs
PLANE_BASE = 60
PLANE_PER_KM_OVER_800 = 0.03
PLANE_THRESHOLD_KM = 800

# Hotel
HOTEL_COST = 35
HOTEL_THRESHOLD_KM = 400

# Fuel
FUEL_CONSUMPTION_L_PER_100KM = 10
FUEL_PRICE_USD_PER_L = 1.0

# Default distance for completely unknown locations
DEFAULT_UNKNOWN_KM = 500

# Default distance for unknown cities inside Buenos Aires province
DEFAULT_BA_INTERIOR_KM = 300


def _normalize(text: str) -> str:
    """Remove accents and convert to lowercase."""
    text = text.lower().strip()
    # Remove accents
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _parse_location(location: str) -> tuple[str, str]:
    """Split 'city, province' and normalize both parts."""
    parts = [_normalize(p) for p in location.split(",")]
    city = parts[0].strip() if len(parts) > 0 else ""
    province = parts[1].strip() if len(parts) > 1 else ""
    return city, province


def _is_caba(city: str, province: str) -> bool:
    """Check if location is in CABA."""
    caba_keywords = ["capital federal", "caba", "ciudad autonoma de buenos aires"]
    return city in caba_keywords or province in caba_keywords


def _is_gba(city: str, province: str) -> bool:
    """Check if city is a GBA partido."""
    return city in GBA_PARTIDOS or province in GBA_PARTIDOS


def _resolve_distance(city: str, province: str) -> int:
    """Determine distance in km from Buenos Aires."""
    # Check city first in DISTANCES
    if city in DISTANCES:
        return DISTANCES[city]

    # Check province in DISTANCES
    if province in DISTANCES:
        dist = DISTANCES[province]
        # Special case: province is "buenos aires" but city is not GBA
        # This means it's BA interior
        if province == "buenos aires" and dist == 0:
            return DEFAULT_BA_INTERIOR_KM
        return dist

    # Partial match: check if any key is contained in city or province
    for key, dist in DISTANCES.items():
        if dist == 0:
            continue
        if key in city or key in province:
            return dist
        if city and city in key:
            return dist

    # Completely unknown
    return DEFAULT_UNKNOWN_KM


def _calc_transport(distance_km: int) -> tuple[float, str]:
    """Calculate transport cost and mode."""
    if distance_km > PLANE_THRESHOLD_KM:
        cost = PLANE_BASE + PLANE_PER_KM_OVER_800 * (distance_km - PLANE_THRESHOLD_KM)
        return round(cost, 2), "avión"
    else:
        if distance_km < 500:
            return float(BUS_COST_UNDER_500), "bus"
        elif distance_km <= 1000:
            return float(BUS_COST_500_1000), "bus"
        else:
            return float(BUS_COST_OVER_1000), "bus"


def _calc_hotel(distance_km: int) -> float:
    """Hotel needed if distance > 400km."""
    return float(HOTEL_COST) if distance_km > HOTEL_THRESHOLD_KM else 0.0


def _calc_fuel(distance_km: int) -> float:
    """Fuel cost to drive the car back."""
    liters = distance_km * FUEL_CONSUMPTION_L_PER_100KM / 100
    return round(liters * FUEL_PRICE_USD_PER_L, 2)


def estimate_travel_cost(location: str) -> dict:
    """
    Estima el costo de viajar a buscar un auto y manejarlo de vuelta a Buenos Aires.

    Args:
        location: Ubicación del auto, ej. "Córdoba, Córdoba" o "Quilmes, Buenos Aires"

    Returns:
        dict con total_usd, transport_usd, transport_mode, hotel_usd, fuel_usd,
        distance_km, detail, needs_travel
    """
    city, province = _parse_location(location)

    # Check if local (CABA/GBA)
    if _is_caba(city, province) or _is_gba(city, province):
        return {
            "total_usd": 0,
            "transport_usd": 0,
            "transport_mode": "ninguno",
            "hotel_usd": 0,
            "fuel_usd": 0,
            "distance_km": 0,
            "detail": "Local (CABA/GBA), sin costo de viaje",
            "needs_travel": False,
        }

    distance_km = _resolve_distance(city, province)

    # If somehow distance resolved to 0 but wasn't caught above
    if distance_km == 0:
        return {
            "total_usd": 0,
            "transport_usd": 0,
            "transport_mode": "ninguno",
            "hotel_usd": 0,
            "fuel_usd": 0,
            "distance_km": 0,
            "detail": "Local (CABA/GBA), sin costo de viaje",
            "needs_travel": False,
        }

    transport_usd, transport_mode = _calc_transport(distance_km)
    hotel_usd = _calc_hotel(distance_km)
    fuel_usd = _calc_fuel(distance_km)
    total_usd = round(transport_usd + hotel_usd + fuel_usd, 2)

    # Build detail string
    transport_label = "Avión" if transport_mode == "avión" else "Micro"
    parts = [f"{transport_label}: USD {transport_usd:.0f}"]
    if hotel_usd > 0:
        parts.append(f"Hotel: USD {hotel_usd:.0f}")
    parts.append(f"Nafta: USD {fuel_usd:.0f}")
    parts.append(f"Total: USD {total_usd:.0f}")
    detail = " | ".join(parts)

    return {
        "total_usd": total_usd,
        "transport_usd": transport_usd,
        "transport_mode": transport_mode,
        "hotel_usd": hotel_usd,
        "fuel_usd": fuel_usd,
        "distance_km": distance_km,
        "detail": detail,
        "needs_travel": True,
    }
