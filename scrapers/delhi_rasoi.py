from __future__ import annotations

import re

from datetime import date, datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from common.http_client import (
    create_session,
    get,
)


URL = "https://delhirasoi.fi/lunch?store=8"


WEEKDAYS = {
    "maanantai": "monday",
    "tiistai": "tuesday",
    "keskiviikko": "wednesday",
    "torstai": "thursday",
    "perjantai": "friday",
    "lauantai": "saturday",
    "sunnuntai": "sunday",
}


DAY_RE = re.compile(
    r"^(maanantai|tiistai|keskiviikko|torstai|"
    r"perjantai|lauantai|sunnuntai)"
    r"\s+"
    r"(\d{1,2})\.(\d{1,2})\.$",
    re.IGNORECASE,
)


TIME_PRICE_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2})"
    r"\s*[–-]\s*"
    r"(?P<end>\d{1,2}:\d{2})"
    r".*?"
    r"(?P<price>\d+[,.]\d{2})"
    r"\s*€",
    re.IGNORECASE,
)


DIET_MAPPING = {
    "G": "G",
    "L": "L",
    "M": "M",
    "VL": "VL",

    # Delhi Rasoi käyttää V = vegaaninen
    "V": "VE",

    # Kasvis
    "K": "K",
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
    Sivulla näkyy esimerkiksi:

        24.11.

    Päätellään oikea vuosi nykyhetken perusteella.
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


def parse_day_title(
    article: Tag
) -> tuple[str, date] | None:
    """
    HTML:

        <h2 class="day-title">
            Tiistai
            <span>24.11.</span>
        </h2>
    """

    title = article.select_one(
        ".day-title"
    )

    if title is None:
        return None

    text = normalize_line(
        title.get_text(
            " ",
            strip=True
        )
    )

    match = DAY_RE.match(
        text
    )

    if not match:
        return None

    finnish_day = (
        match
        .group(1)
        .lower()
    )

    day_key = (
        WEEKDAYS[
            finnish_day
        ]
    )

    day_number = int(
        match.group(2)
    )

    month_number = int(
        match.group(3)
    )

    full_date = infer_full_date(
        day_number,
        month_number
    )

    return (
        day_key,
        full_date
    )


def parse_day_info(
    article: Tag
) -> dict:
    """
    HTML:

        <div class="band-tag tag-day">
            <span>10:30 – 14:30</span>
            <span class="band-price">14,90 €</span>
        </div>
    """

    band = article.select_one(
        ".band-tag.tag-day"
    )

    if band is None:
        return {}

    text = normalize_line(
        band.get_text(
            " ",
            strip=True
        )
    )

    match = TIME_PRICE_RE.search(
        text
    )

    if not match:
        return {}

    price = (
        match
        .group("price")
        .replace(".", ",")
    )

    return {
        "start":
            match.group("start"),

        "end":
            match.group("end"),

        "price":
            f"{price} €",
    }


def parse_diet_tags(
    value: str
) -> list[str]:
    """
    Esimerkiksi:

        (G, L)

    ->

        ["G", "L"]

    ja:

        (G, V)

    ->

        ["G", "VE"]
    """

    value = (
        value
        .strip()
        .strip("()")
    )

    if not value:
        return []

    result = []

    for raw_tag in value.split(","):

        source_tag = (
            raw_tag
            .strip()
            .upper()
        )

        if not source_tag:
            continue

        tag = DIET_MAPPING.get(
            source_tag,
            source_tag
        )

        if tag not in result:
            result.append(
                tag
            )

    return result


def get_dish_name(
    dish_name: Tag
) -> str:
    """
    .dish-name sisältää sekä nimen että tagien span-elementin:

        Butter Chicken
        <span>(G, L)</span>

    Otetaan annoksen nimeen vain span-elementin
    ulkopuolinen teksti.
    """

    parts = []

    for child in dish_name.contents:

        if isinstance(
            child,
            NavigableString
        ):
            parts.append(
                str(child)
            )

        elif (
            isinstance(child, Tag)
            and
            child.name != "span"
        ):
            parts.append(
                child.get_text(
                    " ",
                    strip=True
                )
            )

    name = normalize_line(
        " ".join(parts)
    )

    #
    # Fallback mahdollisia tulevia HTML-muutoksia varten.
    #
    if not name:

        full_text = normalize_line(
            dish_name.get_text(
                " ",
                strip=True
            )
        )

        tag_span = dish_name.find(
            "span"
        )

        if tag_span:

            tag_text = normalize_line(
                tag_span.get_text(
                    " ",
                    strip=True
                )
            )

            if full_text.endswith(
                tag_text
            ):
                full_text = (
                    full_text[
                        :-len(tag_text)
                    ]
                    .strip()
                )

        name = full_text

    return name


def parse_dish(
    dish: Tag
) -> dict | None:
    """
    HTML:

        <div class="dish-item">

            <div class="dish-name">
                Butter Chicken
                <span>(G, L)</span>
            </div>

            <div class="dish-desc">
                Voikanaa
            </div>

        </div>
    """

    dish_name_element = (
        dish.select_one(
            ".dish-name"
        )
    )

    if dish_name_element is None:
        return None

    name = get_dish_name(
        dish_name_element
    )

    if not name:
        return None


    #
    # Ruokavaliomerkinnät
    #
    diets = []

    tag_span = (
        dish_name_element
        .find("span")
    )

    if tag_span:

        diets = parse_diet_tags(
            tag_span.get_text(
                " ",
                strip=True
            )
        )


    #
    # Kuvaus
    #
    description_element = (
        dish.select_one(
            ".dish-desc"
        )
    )

    description = None

    if description_element:

        value = normalize_line(
            description_element
            .get_text(
                " ",
                strip=True
            )
        )

        if value:
            description = value


    result = {
        "name":
            name,

        "diet":
            diets,
    }


    if description:

        result[
            "description"
        ] = description


    return result


def parse_day(
    article: Tag
) -> tuple[
    str,
    list[dict],
    dict,
    date
] | None:
    """
    Parsii yhden:

        <article class="day-card">

    elementin kokonaisuudessaan.
    """

    parsed_title = parse_day_title(
        article
    )

    if parsed_title is None:
        return None


    day_key, full_date = (
        parsed_title
    )


    day_info = parse_day_info(
        article
    )

    day_info[
        "date"
    ] = full_date.isoformat()


    meals = []


    for dish_element in article.select(
        ".dish-list .dish-item"
    ):

        meal = parse_dish(
            dish_element
        )

        if meal:
            meals.append(
                meal
            )


    return (
        day_key,
        meals,
        day_info,
        full_date
    )


def parse_menu(
    html: str
) -> tuple[
    dict,
    dict,
    list[date],
]:
    """
    Parsii kaikki:

        article.day-card

    elementit.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    articles = soup.select(
        "article.day-card"
    )


    if not articles:
        raise ValueError(
            "Delhi Rasoi: "
            "no article.day-card elements found"
        )


    print(
        f"  Found {len(articles)} "
        "day-card element(s)"
    )


    days = {}

    day_info = {}

    dates = []


    for article in articles:

        parsed = parse_day(
            article
        )

        if parsed is None:
            continue


        (
            day_key,
            meals,
            info,
            full_date,
        ) = parsed


        days[
            day_key
        ] = meals


        day_info[
            day_key
        ] = info


        dates.append(
            full_date
        )


        print(
            f"    {day_key}: "
            f"{len(meals)} meal(s)"
        )


    if not days:
        raise ValueError(
            "Delhi Rasoi: "
            "day-card elements were found, "
            "but none could be parsed"
        )


    return (
        days,
        day_info,
        dates
    )


def create_week_label(
    dates: list[date]
) -> str | None:
    """
    Esimerkiksi:

        VIIKKO 48 | 23.-29.11.2026
    """

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
    Ryhmitellään esimerkiksi:

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

        price = (
            day_info
            .get(day, {})
            .get("price")
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

        price = (
            day_info
            .get(day, {})
            .get("price")
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
        "  Fetching Delhi Rasoi Tapiola..."
    )


    response = get(
        session,
        URL,
        headers={
            "Accept":
                "text/html,"
                "application/xhtml+xml",

            "Accept-Language":
                "fi-FI,fi;q=0.9,en;q=0.8",
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


    return {
        "name":
            "Delhi Rasoi Tapiola",

        "address":
            "Länsituuli 5, "
            "02100 Espoo",

        "source":
            URL,

        "source_updated":
            response.headers.get(
                "Last-Modified"
            ),

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
