import logging
import sys
from core.exchange_rate import get_usd_blue_rate
from core.analyzer import analyze_listings, find_opportunities, categorize
from db.database import Database
from scrapers.mercadolibre import MercadoLibreScraper
from scrapers.autocosmos import AutocosmosScraper
from scrapers.demotores import DeMotoresScraper
from scrapers.olx import OLXScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    db = Database()
    db.init()

    # Step 1: Get exchange rate
    logger.info("Fetching USD blue rate...")
    try:
        usd_rate = get_usd_blue_rate()
        logger.info(f"USD blue rate: ${usd_rate}")
    except Exception as e:
        logger.error(f"Could not fetch USD rate: {e}. Aborting.")
        sys.exit(1)

    # Step 2: Run scrapers
    all_listings = []
    scrapers = [
        ("MercadoLibre", MercadoLibreScraper(usd_rate)),
        ("Autocosmos", AutocosmosScraper(usd_rate)),
        ("DeMotores", DeMotoresScraper(usd_rate)),
        ("OLX", OLXScraper(usd_rate)),
    ]

    for name, scraper in scrapers:
        try:
            listings = scraper.scrape_all()
            all_listings.extend(listings)
        except Exception as e:
            logger.error(f"{name} scraper failed: {e}")

    logger.info(f"Total listings scraped: {len(all_listings)}")

    # Step 2.5: Filter out spam/fake listings with unrealistic prices
    # Any car under USD 2,000 is almost certainly a spam/inquiry listing
    MIN_PRICE_USD = 2000
    before = len(all_listings)
    all_listings = [l for l in all_listings if l.get("price_usd") and l["price_usd"] >= MIN_PRICE_USD]
    logger.info(f"Filtered {before - len(all_listings)} listings below USD {MIN_PRICE_USD} (likely spam)")

    # Step 3: Analyze and calculate references
    references = analyze_listings(all_listings)
    logger.info(f"Market references calculated for {len(references)} model/year combos")

    # Step 4: Assign categories and save to DB
    ref_map = {(r["brand"], r["model"], r["year"]): r for r in references}

    saved = 0
    skipped = 0
    for listing in all_listings:
        if not listing.get("year") or not listing.get("brand") or not listing.get("model"):
            skipped += 1
            continue
        key = (listing["brand"], listing["model"], listing["year"])
        ref = ref_map.get(key)
        if ref:
            listing["category"] = categorize(ref["median_price_usd"])
        db.upsert_listing(listing)
        saved += 1
    logger.info(f"Saved {saved} listings to DB ({skipped} skipped due to missing data)")

    for ref in references:
        db.save_market_reference(ref)

    # Step 5: Report opportunities
    opportunities = find_opportunities(all_listings, references, min_diff_usd=1000)
    logger.info(f"Opportunities found: {len(opportunities)}")
    for opp in opportunities[:10]:
        logger.info(
            f"  {opp['brand']} {opp['model']} {opp['year']} - "
            f"USD {opp['price_usd']:,.0f} (median: USD {opp['median_price_usd']:,.0f}, "
            f"profit: USD {opp['potential_profit_usd']:,.0f}) - {opp['source']}"
        )

    db.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
