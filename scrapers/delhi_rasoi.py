from __future__ import annotations

import re

from datetime import date, datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from common.http_client import (
    create_session,
    get,
)


DATA_URL = (
    "https://lunchmenu.fi/en/lunch-lists/"
    "espoo/delhi-rasoi-tapiola"
)

OFFICIAL_URL = (
    "https://delhirasoi.fi/lunch?store=8"
)


WEEKDAYS = {
    "monday": "monday",
    "tuesday": "tuesday",
    "wednesday": "wednesday",
    "thursday": "thursday",
    "friday": "friday",
    "saturday": "saturday",
    "sunday": "sunday",
}


#
# Esimerkiksi:
#
# Monday 23.11.
#
# Today Tuesday 24.11.10:30-14:30
#
# Wednesday 25.11.10:30-14:30
#
DAY_RE = re.compile(
    r"^(?:Today\s+)?"
    r"(Monday|Tuesday|Wednesday|Thursday|"
    r"Friday|Saturday|Sunday)"
    r"\s+"
    r"(\d{1,2})\.(\d{1,2})\."
    r"(?:\s*"
    r"(\d{1,2}:\d{2})"
    r"\s*[–-]\s*"
    r"(\d{1,2}:\d{2})"
    r")?"
    r"$",
    re.IGNORECASE,
)


#
# Esimerkiksi:
#
# Butter Chicken G L 14.90€
#
# Band Gobhi Mattar G Vgn 14.90€
#
MEAL_PRICE_RE = re.compile(
    r"^(?P<body>.+?)"
    r"\s+"
    r"(?P<price>\d+[,.]\d{2})"
    r"\s*€$",
    re.IGNORECASE,
)


#
# Lunchmenu.fi:n käyttämät ruokavaliokoodit,
# joita voidaan löytää annoksen nimen lopusta.
#
KNOWN_SOURCE_TAGS = {
    "G",
    "L",
    "M",
    "VL",
    "VGN",
    "VG",
    "VEG",
    "K",
    "VS",
    "P",
    "N",
    "SO",
    "C",
    "A",
}


#
# Muutetaan Lunchmenu.fi:n merkinnät
# meidän käyttämään muotoon.
#
DIET_MAPPING = {
    "G": "G",
    "L": "L",
    "M": "M",
    "VL": "VL",

    # vegan
    "VGN": "VE",

    # vegetarian
    "VG": "K",
    "VEG": "K",
    "K": "K",

    # garlic
    "VS": "VS",

    # hyödyllisiä allergeenimerkintöjä
    "N": "N",
    "SO": "SO",
}


def normalize_line(
    value: str
) -> str:
    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def infer_full_date(
    day: int,
    month: int
) -> date:
    """
    Lunchmenu.fi näyttää esimerkiksi:

        24.11.

    mutta ei vuotta.

    Valitaan nykyhetkeä lähimpänä oleva
    kyseinen päivämäärä.
    """

    today = datetime.now(
        ZoneInfo("Europe/Helsinki")
    ).date()

    candidates = []

    for year in (
        today.year - 1,
        today.year,
        today.year + 1,
    ):

        try:
            candidate = date(
                year,
                month,
                day
            )

        except ValueError:
            continue

        candidates.append(
            candidate
        )


    if not candidates:
        raise ValueError(
            f"Invalid Delhi Rasoi date: "
            f"{day}.{month}."
        )


    return min(
        candidates,
        key=lambda candidate:
            abs(
                (
                    candidate
                    - today
                ).days
            )
    )


def parse_meal_text(
    text: str
) -> dict | None:
    """
    Esimerkiksi:

        Butter Chicken G L 14.90€

    muuttuu:

        {
            "name": "Butter Chicken",
            "diet": ["G", "L"],
            "price": "14,90 €"
        }


    Ja esimerkiksi:

        Shahi Mattar Paneer:
        Cottage cheese and peas in cashew cream sauce
        G Vg N 14.90€

    muuttuu:

        {
            "name": "Shahi Mattar Paneer",
            "description":
                "Cottage cheese and peas in cashew cream sauce",
            "diet": ["G", "K", "N"],
            "price": "14,90 €"
        }
    """

    text = normalize_line(
        text
    )


    price_match = MEAL_PRICE_RE.match(
        text
    )


    if not price_match:
        return None


    body = normalize_line(
        price_match.group(
            "body"
        )
    )


    price = (
        price_match
        .group("price")
        .replace(".", ",")
    )

    price = f"{price} €"


    #
    # Ruokavaliomerkinnät sijaitsevat
    # annoksen lopussa ennen hintaa.
    #
    parts = body.split()

    source_tags = []


    while parts:

        candidate = (
            parts[-1]
            .strip()
            .upper()
        )


        if candidate not in KNOWN_SOURCE_TAGS:
            break


        source_tags.insert(
            0,
            candidate
        )

        parts.pop()


    meal_text = " ".join(
        parts
    ).strip()


    if not meal_text:
        return None


    diets = []


    for source_tag in source_tags:

        mapped = DIET_MAPPING.get(
            source_tag
        )


        if (
            mapped
            and
            mapped not in diets
        ):
            diets.append(
                mapped
            )


    #
    # Lunchmenu.fi käyttää joissakin annoksissa:
    #
    # Shahi Mattar Paneer:
    # Cottage cheese and peas ...
    #
    description = None
    name = meal_text


    if ":" in meal_text:

        possible_name, possible_description = (
            meal_text.split(
                ":",
                1
            )
        )


        possible_name = (
            possible_name.strip()
        )

        possible_description = (
            possible_description.strip()
        )


        if (
            possible_name
            and
            possible_description
        ):
            name = possible_name
            description = (
                possible_description
            )


    result = {
        "name":
            name,

        "diet":
            diets,

        "price":
            price,
    }


    if description:
        result[
            "description"
        ] = description


    return result


def get_day_headings(
    soup: BeautifulSoup
) -> list[tuple[Tag, re.Match]]:
    """
    Etsii kaikki tämän viikon päiväotsikot.
    """

    headings = []


    for heading in soup.find_all(
        ["h2", "h3"]
    ):

        text = normalize_line(
            heading.get_text(
                " ",
                strip=True
            )
        )


        match = DAY_RE.match(
            text
        )


        if match:
            headings.append(
                (
                    heading,
                    match
                )
            )


    return headings


def get_meals_after_heading(
    heading: Tag
) -> list[dict]:
    """
    Etsii päiväotsikon jälkeen kaikki <li>-annokset
    seuraavaan päivä-/osio-otsikkoon asti.

    Tämä ratkaisee aiemman ongelman:
    annoksen nimi, tagit ja hinta voivat olla HTML:ssä
    eri span-elementeissä, mutta li.get_text(" ")
    yhdistää ne takaisin samaksi annokseksi.
    """

    meals = []


    for element in heading.find_all_next(
        ["h2", "h3", "li"]
    ):

        if element is heading:
            continue


        #
        # Seuraava otsikko lopettaa tämän päivän.
        #
        if element.name in {
            "h2",
            "h3",
        }:
            break


        if element.name != "li":
            continue


        text = normalize_line(
            element.get_text(
                " ",
                strip=True
            )
        )


        meal = parse_meal_text(
            text
        )


        if meal:
            meals.append(
                meal
            )


    return meals


def parse_menu(
    html: str
) -> tuple[
    dict,
    dict,
    list[date],
]:
    """
    Parsii koko viikon lounaslistan suoraan
    sivun DOM-rakenteesta.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    day_headings = (
        get_day_headings(
            soup
        )
    )


    if not day_headings:
        raise ValueError(
            "Delhi Rasoi: "
            "no lunch day headings found"
        )


    days = {}

    day_info = {}

    dates = []


    for heading, match in day_headings:

        english_day = (
            match
            .group(1)
            .lower()
        )


        current_day = (
            WEEKDAYS[
                english_day
            ]
        )


        day_number = int(
            match.group(2)
        )

        month_number = int(
            match.group(3)
        )


        full_date = (
            infer_full_date(
                day_number,
                month_number
            )
        )


        dates.append(
            full_date
        )


        meals = (
            get_meals_after_heading(
                heading
            )
        )


        if not meals:

            print(
                f"  WARNING: "
                f"{current_day}: "
                "day found but no meals parsed"
            )

            continue


        days[
            current_day
        ] = meals


        info = {
            "date":
                full_date.isoformat()
        }


        if (
            match.group(4)
            and
            match.group(5)
        ):

            info[
                "start"
            ] = match.group(4)

            info[
                "end"
            ] = match.group(5)


        #
        # Delhi Rasoilla päivän annoksilla
        # on sama buffet-hinta.
        #
        first_price = meals[
            0
        ].get(
            "price"
        )


        if first_price:
            info[
                "price"
            ] = first_price


        day_info[
            current_day
        ] = info


    if not days:

        raise ValueError(
            "Delhi Rasoi: "
            "day headings were found but "
            "no meals could be parsed"
        )


    return (
        days,
        day_info,
        dates
    )


def create_week_label(
    dates: list[date]
) -> str | None:

    if not dates:
        return None


    dates = sorted(
        set(dates)
    )


    first = dates[0]
    last = dates[-1]


    week_number = (
        first
        .isocalendar()
        .week
    )


    if (
        first.month == last.month
        and
        first.year == last.year
    ):

        date_range = (
            f"{first.day}.-"
            f"{last.day}."
            f"{last.month}."
            f"{last.year}"
        )

    else:

        date_range = (
            f"{first.day}."
            f"{first.month}."
            f"{first.year}"
            " - "
            f"{last.day}."
            f"{last.month}."
            f"{last.year}"
        )


    return (
        f"VIIKKO {week_number} | "
        f"{date_range}"
    )


def create_prices(
    day_info: dict
) -> list[dict]:
    """
    Ryhmitellään hinnat frontendille:

        Ma–Pe 14,90 €
        La–Su 17,90 €
    """

    weekday_prices = []

    weekend_prices = []


    for day in (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
    ):

        info = day_info.get(
            day,
            {}
        )

        price = info.get(
            "price"
        )


        if (
            price
            and
            price not in weekday_prices
        ):

            weekday_prices.append(
                price
            )


    for day in (
        "saturday",
        "sunday",
    ):

        info = day_info.get(
            day,
            {}
        )

        price = info.get(
            "price"
        )


        if (
            price
            and
            price not in weekend_prices
        ):

            weekend_prices.append(
                price
            )


    prices = []


    if len(weekday_prices) == 1:

        prices.append({
            "label":
                "Ma–Pe",

            "price":
                weekday_prices[0],
        })


    if len(weekend_prices) == 1:

        prices.append({
            "label":
                "La–Su",

            "price":
                weekend_prices[0],
        })


    return prices


def fetch() -> dict:
    """
    Main scraperin kutsuma funktio.
    """

    session = create_session()


    print(
        "  Fetching Delhi Rasoi Tapiola "
        "from lunchmenu.fi..."
    )


    response = get(
        session,
        DATA_URL,
        headers={
            "Accept":
                "text/html,"
                "application/xhtml+xml",

            "Accept-Language":
                "en-US,en;q=0.9",
        }
    )


    (
        days,
        day_info,
        dates,
    ) = parse_menu(
        response.text
    )


    prices = create_prices(
        day_info
    )


    week = create_week_label(
        dates
    )


    meal_count = sum(
        len(meals)
        for meals
        in days.values()
    )


    print(
        "  Delhi Rasoi parsing succeeded"
    )

    print(
        f"  Found {len(days)} day(s), "
        f"{meal_count} meal(s)"
    )


    for day, meals in days.items():

        print(
            f"    {day}: "
            f"{len(meals)} meal(s)"
        )


    return {
        "name":
            "Delhi Rasoi Tapiola",

        "address":
            "Länsituuli 5, "
            "02100 Espoo",

        "source":
            OFFICIAL_URL,

        "data_source":
            DATA_URL,

        "week":
            week,

        "prices":
            prices,

        "day_info":
            day_info,

        "days":
            days,
    }


if __name__ == "__main__":

    import json

    result = fetch()

    print()

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )
    )
