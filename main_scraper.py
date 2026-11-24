from __future__ import annotations

import importlib
import json
import pkgutil

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import scrapers


BASE_DIR = Path(__file__).resolve().parent

OUTPUT_FILE = (
    BASE_DIR
    / "site"
    / "data"
    / "lunch.json"
)


def discover_scrapers():
    """
    Etsii automaattisesti kaikki scrapers-paketissa olevat
    Python-moduulit.

    Jokaisessa scraper-moduulissa pitää olla:

        def fetch():
            ...

    Palauttaa listan:

        [
            ("tapiolan_keilahalli", fetch_function),
            ...
        ]

    sekä mahdolliset moduleiden import-virheet.
    """

    found = []
    failed_imports = []

    modules = sorted(
        pkgutil.iter_modules(scrapers.__path__),
        key=lambda module: module.name
    )

    for module_info in modules:

        module_name = module_info.name

        # Ohitetaan mahdolliset sisäiset moduulit.
        if module_name.startswith("_"):
            continue

        full_module_name = (
            f"scrapers.{module_name}"
        )

        try:
            module = importlib.import_module(
                full_module_name
            )

        except Exception as exc:
            failed_imports.append(
                (
                    module_name,
                    f"Import failed: {exc}"
                )
            )

            print(
                f"ERROR importing {module_name}: "
                f"{exc}"
            )

            continue

        fetch_function = getattr(
            module,
            "fetch",
            None
        )

        if not callable(fetch_function):

            print(
                f"Skipping {module_name}: "
                "no callable fetch() function"
            )

            continue

        found.append(
            (
                module_name,
                fetch_function
            )
        )

    return found, failed_imports


def main():

    restaurants = []

    failed = []

    scraper_modules, import_errors = (
        discover_scrapers()
    )

    failed.extend(
        import_errors
    )

    print(
        f"Found {len(scraper_modules)} scraper(s)"
    )

    print()

    for module_name, fetch_function in scraper_modules:

        try:

            print(
                f"Running {module_name}..."
            )

            restaurant = (
                fetch_function()
            )

            if not isinstance(
                restaurant,
                dict
            ):
                raise TypeError(
                    "Scraper fetch() must return a dict"
                )

            if not restaurant.get("name"):
                raise ValueError(
                    "Scraper result does not contain "
                    "restaurant name"
                )

            restaurants.append(
                restaurant
            )

            print(
                f"OK: {restaurant['name']}"
            )

        except Exception as exc:

            failed.append(
                (
                    module_name,
                    str(exc)
                )
            )

            print(
                f"ERROR: {module_name}: {exc}"
            )

        print()

    #
    # Jos kaikki scraperit epäonnistuvat,
    # ei kirjoiteta tyhjää lunch.json-tiedostoa.
    #
    # Näin edellinen toimiva Pages-julkaisu jää käyttöön.
    #

    if not restaurants:

        raise RuntimeError(
            "All restaurant scrapers failed; "
            "lunch.json was not updated."
        )

    data = {

        "generated_at":
            datetime.now(
                ZoneInfo(
                    "Europe/Helsinki"
                )
            ).isoformat(
                timespec="seconds"
            ),

        "timezone":
            "Europe/Helsinki",

        "restaurants":
            restaurants,
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"Wrote {OUTPUT_FILE}"
    )

    print(
        f"Successful restaurants: "
        f"{len(restaurants)}"
    )

    if failed:

        print()

        print(
            f"Failed scrapers: "
            f"{len(failed)}"
        )

        for name, error in failed:

            print(
                f"  - {name}: {error}"
            )


if __name__ == "__main__":
    main()
