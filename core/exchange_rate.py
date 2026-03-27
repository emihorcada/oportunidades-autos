import requests


def get_usd_blue_rate():
    """Get current USD blue sell rate from dolarapi.com."""
    response = requests.get("https://dolarapi.com/v1/dolares/blue", timeout=10)
    response.raise_for_status()
    data = response.json()
    return float(data["venta"])


def convert_ars_to_usd(price_ars, usd_rate):
    """Convert ARS price to USD using given rate."""
    if price_ars is None:
        return None
    return round(price_ars / usd_rate, 2)
