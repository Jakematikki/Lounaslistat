from __future__ import annotations

import re

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from common.http_client import (
    create_session,
    get,
)


DATA_URL = "https://common-api.lounaat.info/tapiola"

#
# Käyttäjälle näytettävä lähde.
# Beef & Grillin oma sivu on jätetty tarkoituksella pois,
# koska se vastaa hyvin epäluotettavasti.
#
SOURCE_URL = "https://lounas.online/espoo/beef-grill"


RESTAURANT_NAME = "Beef & Grill"


WEEKDAY_KEYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


PRICE_RE = re.compile(
    r"^(?:Hinta:\s*)?"
    r"(?P<price>\d+[,.]\d{2})"
    r"\s*(?:€|e)$",
    re.IGNORECASE,
)


TIME_RE = re.compile(
    r"^\d{1,2}(?::\d{2})?"
    r"\s*[-–]\s*"
    r"\d{1,2}(?::\d{2})?$"
)


DISTANCE_RE = re.compile(
    r"^\d+(?:[,.]\d+)?\s*(?:m|km)$",
    re.IGNORECASE,
)


RATING_RE = re.compile(
    r"^(?:\d+(?:[,.]\d+)?/5(?:\.0)?|/5(?:\.0)?)$",
    re.IGNORECASE,
)


def normalize_line(
    value: str
) -> str:
    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def format_price(
    value: str
) -> str:
    """
    19,30e -> 19,30 €
    """

    match = PRICE_RE.match(
        normalize_line(value)
    )

    if not match:
        raise ValueError(
            f"Invalid price: {value}"
        )

    price = (
        match
        .group("price")
        .replace(".", ",")
    )

    return f"{price} €"


def find_restaurant_heading(
    soup: BeautifulSoup
) -> Tag:
    """
    Etsii Beef & Grill -otsikon.

    Lounaat.info käyttää tällä hetkellä h3-otsikoita,
    mutta sallitaan myös h2 tulevien muutosten varalta.
    """

    for heading in soup.find_all(
        ["h2", "h3", "h4"]
    ):

        text = normalize_line(
            heading.get_text(
                " ",
                strip=True
            )
        )

        if text == RESTAURANT_NAME:
            return heading

    raise ValueError(
        "Beef & Grill heading was not found "
        "from lounaat.info"
    )


def extract_restaurant_lines(
    html: str
) -> list[str]:
    """
    Kerää vain Beef & Grillin oman osuuden.

    Käsittely lopetetaan seuraavaan ravintolaotsikkoon,
    joten muiden Tapiolan ravintoloiden ruokia ei voi
    vahingossa päätyä tähän listaan.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    heading = find_restaurant_heading(
        soup
    )

    lines = []


    for element in heading.next_elements:

        #
        # Seuraava ravintolaotsikko lopettaa osion.
        #
        if (
            isinstance(element, Tag)
            and
            element is not heading
            and
            element.name
            in {"h2", "h3", "h4"}
        ):
            break


        if not isinstance(
            element,
            NavigableString
        ):
            continue


        line = normalize_line(
            str(element)
        )

        if not line:
            continue


        #
        # Sama tekstisolmu voi joskus tulla useampaan
        # kertaan DOM-rakenteen vuoksi.
        #
        if (
            lines
            and
            lines[-1] == line
        ):
            continue


        lines.append(
            line
        )


    return lines


def is_metadata(
    line: str
) -> bool:
    """
    Poistaa ravintolaosion metatiedot kuten:
      /5.0
      10-15
      240m
    """

    if RATING_RE.match(
        line
    ):
        return True

    if TIME_RE.match(
        line
    ):
        return True

    if DISTANCE_RE.match(
        line
    ):
        return True

    return False


def parse_meals(
    lines: list[str]
) -> list[dict]:
    """
    Lounaat.info näyttää Beef & Grillin tiedot muodossa:

        19,30e
        Metsästäjänhärkä 200g

        19,30e
        Entrecote 200g

    Joillakin riveillä hinta voi puuttua lähdedatasta.
    Tällainen ruoka otetaan silti mukaan.
    """

    meals = []

    pending_price = None


    for raw_line in lines:

        line = normalize_line(
            raw_line
        )


        if not line:
            continue


        if is_metadata(
            line
        ):
            continue


        price_match = PRICE_RE.match(
            line
        )


        if price_match:

            pending_price = (
                format_price(
                    line
                )
            )

            continue


        #
        # Mahdolliset käyttöliittymän ylimääräiset tekstit.
        #
        lowered = line.lower()

        if lowered in {
            "beef & grill",
            "näytä lisää",
            "piilota",
        }:
            continue


        meal = {
            "name":
                line,

            "diet":
                [],
        }


        if pending_price:

            meal["price"] = (
                pending_price
            )


        meals.append(
            meal
        )

        pending_price = None


    if not meals:
        raise ValueError(
            "No Beef & Grill meals were found"
        )


    return meals


def get_current_day_key() -> str:
    """
    Suomen paikallinen viikonpäivä.
    """

    now = datetime.now(
        ZoneInfo("Europe/Helsinki")
    )

    return WEEKDAY_KEYS[
        now.weekday()
    ]


def create_week_label() -> str:
    """
    Esimerkiksi:

        VIIKKO 48 | 23.-27.11.2026
    """

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

    week_number = (
        monday
        .isocalendar()
        .week
    )


    if (
        monday.month == friday.month
        and
        monday.year == friday.year
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
            f"{monday.year}"
            " - "
            f"{friday.day}."
            f"{friday.month}."
            f"{friday.year}"
        )


    return (
        f"VIIKKO {week_number} | "
        f"{date_range}"
    )


def fetch() -> dict:
    """
    Main scraperin kutsuma julkinen funktio.

    Beef & Grillin omaa verkkosivua ei kutsuta lainkaan.
    """

    current_day = (
        get_current_day_key()
    )


    #
    # Lauantaina ja sunnuntaina ei normaalisti
    # ole Beef & Grillin lounasta.
    #
    if current_day in {
        "saturday",
        "sunday",
    }:

        return {
            "name":
                RESTAURANT_NAME,

            "address":
                "Länsituuli 10, "
                "02100 Espoo",

            "source":
                SOURCE_URL,

            "week":
                create_week_label(),

            "prices":
                [],

            "days": {
                current_day: [],
            },
        }


    session = create_session()


    print(
        "  Fetching Beef & Grill "
        "from lounaat.info..."
    )


    response = get(
        session,
        DATA_URL,
        headers={
            "Accept":
                "text/html,"
                "application/xhtml+xml"
        }
    )


    lines = extract_restaurant_lines(
        response.text
    )


    meals = parse_meals(
        lines
    )


    print(
        f"  Beef & Grill: "
        f"{len(meals)} meal(s) found"
    )


    #
    # lounaat.info:n Tapiola-näkymä antaa
    # kuluvan päivän lounaat.
    #
    days = {
        current_day:
            meals
    }


    return {
        "name":
            RESTAURANT_NAME,

        "address":
            "Länsituuli 10, "
            "02100 Espoo",

        "source":
            SOURCE_URL,

        "week":
            create_week_label(),

        #
        # Beef & Grillillä ei ole yhtä yhteistä
        # lounashintaa, vaan hinnat ovat annoskohtaisia.
        #
        "prices":
            [],

        "days":
            days,
    }


#
# Paikallinen testaus:
#
# python -m scrapers.beef_and_grill
#
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
