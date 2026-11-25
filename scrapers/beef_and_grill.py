from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from common.http_client import create_session, get


URL = "https://beefandgrill.fi/"
RESTAURANT_NAME = "Beef & Grill"

DAY_MAP = {
    "maanantai": "monday",
    "tiistai": "tuesday",
    "keskiviikko": "wednesday",
    "torstai": "thursday",
    "perjantai": "friday",
}

PRICE_RE = re.compile(
    r"(?P<price>\d+[,.]\d{2})\s*€?"
)


def clean(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        value.replace("\xa0", " ")
    ).strip()


def format_price(value: str) -> str | None:
    match = PRICE_RE.search(value)

    if not match:
        return None

    return (
        match.group("price")
        .replace(".", ",")
        + " €"
    )


def find_lunch_heading(
    soup: BeautifulSoup
) -> Tag:

    for heading in soup.find_all(
        ["h1", "h2"]
    ):
        if clean(
            heading.get_text(
                " ",
                strip=True
            )
        ).casefold() == "lounas":
            return heading

    raise ValueError(
        "Beef & Grill: Lounas heading not found"
    )


def parse_table_row(
    row: Tag
) -> dict | None:

    cells = row.find_all(
        ["td", "th"]
    )

    if not cells:
        return None

    values = [
        clean(
            cell.get_text(
                " ",
                strip=True
            )
        )
        for cell in cells
    ]

    values = [
        value
        for value in values
        if value
    ]

    if not values:
        return None

    #
    # Etsitään hinta mistä tahansa solusta.
    #
    price = None

    for value in values:
        found = format_price(value)

        if found:
            price = found
            break

    #
    # Nimi muodostetaan soluista,
    # jotka eivät ole pelkkää hintaa.
    #
    name_parts = []

    for value in values:

        stripped = PRICE_RE.sub(
            "",
            value
        )

        stripped = clean(stripped)

        if stripped:
            name_parts.append(
                stripped
            )

    name = clean(
        " ".join(name_parts)
    )

    if not name:
        return None

    meal = {
        "name": name,
        "diet": [],
    }

    if price:
        meal["price"] = price

    return meal


def parse_day(
    day_heading: Tag
) -> list[dict]:

    meals = []

    #
    # Kuljetaan elementtejä eteenpäin,
    # kunnes tulee seuraava päiväotsikko
    # tai seuraava pääotsikko.
    #
    for element in day_heading.find_all_next():

        if element is day_heading:
            continue

        if (
            isinstance(element, Tag)
            and element.name in {
                "h1",
                "h2",
            }
        ):
            break

        #
        # Ruokalista näyttää olevan
        # taulukkomuodossa.
        #
        if (
            isinstance(element, Tag)
            and element.name == "tr"
        ):

            meal = parse_table_row(
                element
            )

            if meal:
                meals.append(meal)

    #
    # Estetään mahdolliset duplikaatit.
    #
    unique = []

    for meal in meals:

        if meal not in unique:
            unique.append(meal)

    return unique


def parse_lunch(
    html: str
) -> dict[str, list[dict]]:

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    lunch_heading = find_lunch_heading(
        soup
    )

    days = {}

    #
    # Etsitään Lounas-otsikon jälkeen
    # Maanantai ... Perjantai.
    #
    for heading in lunch_heading.find_all_next(
        ["h1", "h2"]
    ):

        title = clean(
            heading.get_text(
                " ",
                strip=True
            )
        )

        title_lower = title.casefold()

        #
        # Seuraava H1 päättää lounasosion.
        #
        if (
            heading.name == "h1"
            and title_lower != "lounas"
        ):
            break

        if title_lower not in DAY_MAP:
            continue

        day_key = DAY_MAP[
            title_lower
        ]

        meals = parse_day(
            heading
        )

        if not meals:
            raise ValueError(
                "Beef & Grill: "
                f"no meals found for {title}"
            )

        days[day_key] = meals

        print(
            f"    {day_key}: "
            f"{len(meals)} meal(s)"
        )

    missing = [
        day
        for day in DAY_MAP.values()
        if day not in days
    ]

    if missing:
        raise ValueError(
            "Beef & Grill: missing weekdays: "
            + ", ".join(missing)
        )

    days["saturday"] = []
    days["sunday"] = []

    return days


def create_week_label() -> str:

    today = datetime.now(
        ZoneInfo("Europe/Helsinki")
    ).date()

    monday = (
        today
        - timedelta(
            days=today.weekday()
        )
    )

    friday = (
        monday
        + timedelta(days=4)
    )

    week = monday.isocalendar().week

    if (
        monday.month == friday.month
        and monday.year == friday.year
    ):
        date_range = (
            f"{monday.day}.-"
            f"{friday.day}."
            f"{friday.month}."
            f"{friday.year}"
        )

    else:
        date_range = (
            f"{monday.day}."
            f"{monday.month}."
            "-"
            f"{friday.day}."
            f"{friday.month}."
            f"{friday.year}"
        )

    return (
        f"VIIKKO {week} | "
        f"{date_range}"
    )


def fetch() -> dict:

    print(
        "  Fetching Beef & Grill "
        "weekly menu from beefandgrill.fi..."
    )

    session = create_session()

    response = get(
        session,
        URL,
        read_timeout=90,
        headers={
            "Accept": (
                "text/html,"
                "application/xhtml+xml"
            ),
            "Accept-Language":
                "fi-FI,fi;q=0.9",
        },
    )

    #
    # Pakotetaan UTF-8, ettei sivun
    # ääkkösistä synny mojibakea.
    #
    html = response.content.decode(
        "utf-8",
        errors="replace"
    )

    days = parse_lunch(
        html
    )

    total = sum(
        len(meals)
        for meals in days.values()
    )

    print(
        "  Beef & Grill weekly parsing succeeded"
    )

    print(
        f"  Found {total} meal(s)"
    )

    return {
        "name": RESTAURANT_NAME,

        "address":
            "Länsituuli 10, 02100 Espoo",

        "source":
            "https://beefandgrill.fi/#lunch",

        "week":
            create_week_label(),

        "prices": [
            {
                "label":
                    "Salaattipöytä",

                "price":
                    "13,50 €",
            }
        ],

        "day_info": {
            day: {
                "start": "10:00",
                "end": "15:00",
            }
            for day in DAY_MAP.values()
        },

        "days": days,
    }


if __name__ == "__main__":

    import json

    result = fetch()

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )
