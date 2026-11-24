from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scrapers.tapiolan_keilahalli import fetch_tapiolan_keilahalli


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "site" / "data" / "lunch.json"

# Lisää uudet scraperit tähän listaan.
SCRAPERS = [
    fetch_tapiolan_keilahalli,
]


def main() -> None:
    restaurants = []
    failed = []

    for scraper in SCRAPERS:
        try:
            print(f"Running {scraper.__name__}...")
            restaurant = scraper()
            restaurants.append(restaurant)
            print(f"OK: {restaurant['name']}")
        except Exception as exc:
            # Yhden ravintolan virhe ei estä muiden päivittämistä.
            failed.append((scraper.__name__, str(exc)))
            print(f"ERROR: {scraper.__name__}: {exc}")

    # Jos kaikki scraperit epäonnistuvat, keskeytetään ajo.
    # Näin GitHub Pagesiin ei julkaista vahingossa täysin tyhjää listaa.
    if not restaurants:
        raise RuntimeError("All restaurant scrapers failed; lunch.json was not updated.")

    data = {
        "generated_at": datetime.now(ZoneInfo("Europe/Helsinki")).isoformat(timespec="seconds"),
        "timezone": "Europe/Helsinki",
        "restaurants": restaurants,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUTPUT_FILE}")
    print(f"Restaurants: {len(restaurants)}")

    if failed:
        print(f"Failed scrapers: {len(failed)}")
        for name, error in failed:
            print(f"  - {name}: {error}")


if __name__ == "__main__":
    main()
