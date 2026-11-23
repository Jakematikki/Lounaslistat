import json
from pathlib import Path
from datetime import datetime


OUTPUT_FILE = Path("data/lunch.json")


def fetch_test_restaurant():
    """
    Ensimmäinen testiversio.
    Myöhemmin tämän tilalle tulee oikea HTTP-haku ravintolan sivulta/API:sta.
    """
    return {
        "name": "Testiravintola",
        "source": "https://example.com",
        "meals": [
            {
                "name": "Lihapullat ja perunamuusi",
                "price": "12,90 €",
                "diet": ["L"]
            },
            {
                "name": "Kasviscurry",
                "price": "11,90 €",
                "diet": ["VEG", "G"]
            }
        ]
    }


def main():
    restaurants = []

    # Lisää ravintolat tähän
    restaurants.append(fetch_test_restaurant())

    data = {
        "updated": datetime.now().astimezone().isoformat(),
        "restaurants": restaurants
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"Wrote {OUTPUT_FILE}")
    print(f"Restaurants: {len(restaurants)}")


if __name__ == "__main__":
    main()