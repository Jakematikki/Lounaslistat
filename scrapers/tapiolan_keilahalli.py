from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup


API_URL = "https://tapiolankeilahalli.fi/wp-json/wp/v2/posts/286"
SOURCE_URL = "https://tapiolankeilahalli.fi/keittio/#lounas"

WEEKDAYS = {
    "MAANANTAI": "monday",
    "TIISTAI": "tuesday",
    "KESKIVIIKKO": "wednesday",
    "TORSTAI": "thursday",
    "PERJANTAI": "friday",
}

PRICE_LABELS = {
    "LOUNASPÖYTÄ": "Lounaspöytä",
    "KEITTOLOUNAS": "Keittolounas",
    "SALAATTILOUNAS": "Salaattilounas",
}

# Yleisimmät suomalaiset ruokavaliomerkinnät.
DIET_TAG = r"(?:VL|VEG|VE|L|G|M|V)"
DIET_RE = re.compile(
    rf"\s+(?P<tags>{DIET_TAG}(?:\s*,\s*{DIET_TAG})*)\s*$",
    re.IGNORECASE,
)


def _normalize_line(value: str) -> str:
    """Poistaa ylimääräiset välilyönnit yhdeltä tekstiriviltä."""
    return re.sub(r"\s+", " ", value).strip()


def _split_meal_and_diets(line: str) -> dict:
    """
    Muuttaa esimerkiksi:
        'Lohikeitto L,G'
    muotoon:
        {'name': 'Lohikeitto', 'diet': ['L', 'G']}
    """
    match = DIET_RE.search(line)

    if not match:
        return {
            "name": line,
            "diet": [],
        }

    tags = [
        tag.strip().upper()
        for tag in match.group("tags").split(",")
    ]

    name = line[: match.start()].strip()

    return {
        "name": name,
        "diet": tags,
    }


def _parse_price(line: str) -> dict | None:
    upper = line.upper()

    for prefix, label in PRICE_LABELS.items():
        if upper.startswith(prefix):
            price = line[len(prefix):].strip()

            # Muotoillaan esim. "14,00€" -> "14,00 €"
            price = re.sub(r"\s*€", " €", price)

            return {
                "label": label,
                "price": price,
            }

    return None


def fetch_tapiolan_keilahalli() -> dict:
    response = requests.get(
        API_URL,
        timeout=20,
        headers={
            "User-Agent": "Lounaslistat/1.0 (+GitHub Pages lunch menu aggregator)"
        },
    )
    response.raise_for_status()

    wordpress_data = response.json()

    try:
        html = wordpress_data["content"]["rendered"]
    except (KeyError, TypeError) as exc:
        raise ValueError("WordPress response did not contain content.rendered") from exc

    soup = BeautifulSoup(html, "html.parser")

    # get_text("\n") säilyttää HTML-elementtien väliset rajat riveinä.
    raw_text = soup.get_text("\n", strip=True)

    lines = [
        _normalize_line(line)
        for line in raw_text.splitlines()
        if _normalize_line(line)
    ]

    week_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(r"^VIIKKO\s+\d+", line, re.IGNORECASE)
        ),
        None,
    )

    if week_index is None:
        raise ValueError("Could not find week heading from Tapiolan Keilahalli menu")

    # Kaikki lounasdata alkaa VIIKKO-rivistä.
    menu_lines = lines[week_index:]

    # Lopetetaan ennen ravintolan yleistä allergeeni-/footer-tekstiä.
    allergen_index = next(
        (
            index
            for index, line in enumerate(menu_lines)
            if line.lower().startswith("lisätietoja allergeeneista")
        ),
        len(menu_lines),
    )
    menu_lines = menu_lines[:allergen_index]

    week = menu_lines[0]
    prices = []
    days = {}
    current_day = None

    for line in menu_lines[1:]:
        normalized = line.upper().strip()

        if normalized in WEEKDAYS:
            current_day = WEEKDAYS[normalized]
            days[current_day] = []
            continue

        # Ennen ensimmäistä viikonpäivää olevat rivit ovat hintoja.
        if current_day is None:
            price = _parse_price(line)
            if price:
                prices.append(price)
            continue

        days[current_day].append(_split_meal_and_diets(line))

    if not days:
        raise ValueError("No weekday menus were found from Tapiolan Keilahalli")

    return {
        "name": "Tapiolan Keilahalli",
        "address": "Kauppamiehentie 6, 02100 Espoo",
        "source": SOURCE_URL,
        "week": week,
        "source_updated": wordpress_data.get("modified"),
        "prices": prices,
        "days": days,
    }
