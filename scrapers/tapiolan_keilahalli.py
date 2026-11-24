from __future__ import annotations

import re

import requests

from bs4 import BeautifulSoup

from common.http_client import (
    create_session,
    get,
)


API_URL = (
    "https://tapiolankeilahalli.fi/"
    "wp-json/wp/v2/posts/286"
)

PAGE_URL = (
    "https://tapiolankeilahalli.fi/"
    "keittio/"
)

SOURCE_URL = (
    "https://tapiolankeilahalli.fi/"
    "keittio/#lounas"
)


WEEKDAYS = {

    "MAANANTAI":
        "monday",

    "TIISTAI":
        "tuesday",

    "KESKIVIIKKO":
        "wednesday",

    "TORSTAI":
        "thursday",

    "PERJANTAI":
        "friday",
}


PRICE_LABELS = {

    "LOUNASPÖYTÄ":
        "Lounaspöytä",

    "KEITTOLOUNAS":
        "Keittolounas",

    "SALAATTILOUNAS":
        "Salaattilounas",
}


#
# Yleisimmät ruokavaliomerkinnät.
#
# Järjestyksessä pidemmät ensin, jotta esimerkiksi
# VEG ei tulkita vahingossa pelkäksi V:ksi.
#

DIET_TAG = (
    r"(?:VEG|VL|VE|L|G|M|V)"
)


DIET_RE = re.compile(

    rf"\s+"
    rf"(?P<tags>"
    rf"{DIET_TAG}"
    rf"(?:\s*,\s*{DIET_TAG})*"
    rf")"
    rf"\s*$",

    re.IGNORECASE,
)


def normalize_line(
    value: str
) -> str:
    """
    Yhdistää peräkkäiset välilyönnit yhdeksi.
    """

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def split_meal_and_diets(
    line: str
) -> dict:
    """
    Esimerkiksi:

        Lohikeitto L,G

    muutetaan muotoon:

        {
            "name": "Lohikeitto",
            "diet": [
                "L",
                "G"
            ]
        }
    """

    match = DIET_RE.search(
        line
    )

    if not match:

        return {
            "name": line,
            "diet": [],
        }

    tags = [

        tag
        .strip()
        .upper()

        for tag
        in match
        .group("tags")
        .split(",")

    ]

    name = line[
        :match.start()
    ].strip()

    return {

        "name":
            name,

        "diet":
            tags,
    }


def parse_price(
    line: str
) -> dict | None:
    """
    Esimerkiksi:

        LOUNASPÖYTÄ 14,00€

    muutetaan muotoon:

        {
            "label": "Lounaspöytä",
            "price": "14,00 €"
        }
    """

    upper = line.upper()

    for prefix, label in (
        PRICE_LABELS.items()
    ):

        if not upper.startswith(
            prefix
        ):
            continue

        price = line[
            len(prefix):
        ].strip()

        #
        # 14,00€ -> 14,00 €
        #

        price = re.sub(
            r"\s*€",
            " €",
            price
        )

        return {

            "label":
                label,

            "price":
                price,
        }

    return None


def html_to_lines(
    html: str
) -> list[str]:
    """
    Muuntaa HTML:n tekstiriveiksi.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    text = soup.get_text(
        "\n",
        strip=True
    )

    lines = []

    for raw_line in (
        text.splitlines()
    ):

        line = normalize_line(
            raw_line
        )

        if not line:
            continue

        lines.append(
            line
        )

    return lines


def extract_menu(
    lines: list[str]
) -> dict:
    """
    Etsii lounaslistan tekstiriveistä.

    Odotettu rakenne:

        VIIKKO 48 | ...
        LOUNASPÖYTÄ ...
        KEITTOLOUNAS ...

        MAANANTAI
        ...
        TIISTAI
        ...
    """

    week_index = next(

        (
            index

            for index, line
            in enumerate(lines)

            if re.match(
                r"^VIIKKO\s+\d+",
                line,
                re.IGNORECASE
            )
        ),

        None,
    )

    if week_index is None:

        raise ValueError(
            "Could not find VIIKKO heading "
            "from lunch menu"
        )

    menu_lines = lines[
        week_index:
    ]

    #
    # Lopetetaan esimerkiksi sivun
    # allergeeniselityksen kohdalla.
    #

    end_index = next(

        (
            index

            for index, line
            in enumerate(menu_lines)

            if line.lower().startswith(
                "lisätietoja allergeeneista"
            )
        ),

        len(menu_lines),
    )

    menu_lines = menu_lines[
        :end_index
    ]

    if not menu_lines:

        raise ValueError(
            "Lunch menu was empty"
        )

    week = menu_lines[0]

    prices = []

    days = {}

    current_day = None


    for line in menu_lines[1:]:

        normalized = (
            line
            .upper()
            .strip()
        )

        #
        # Viikonpäivä
        #

        if normalized in WEEKDAYS:

            current_day = (
                WEEKDAYS[
                    normalized
                ]
            )

            days[
                current_day
            ] = []

            continue


        #
        # Ennen ensimmäistä viikonpäivää
        # etsitään hinnat.
        #

        if current_day is None:

            price = parse_price(
                line
            )

            if price:

                prices.append(
                    price
                )

            continue


        #
        # Varsinainen ruokalaji.
        #

        meal = (
            split_meal_and_diets(
                line
            )
        )

        days[
            current_day
        ].append(
            meal
        )


    if not days:

        raise ValueError(
            "No weekday menus found"
        )


    return {

        "week":
            week,

        "prices":
            prices,

        "days":
            days,
    }


def fetch_from_api(
    session: requests.Session
) -> tuple[dict, str | None]:
    """
    Ensisijainen lähde:
    WordPress REST API.
    """

    print(
        "  Fetching WordPress API..."
    )

    response = get(

        session,

        API_URL,

        headers={
            "Accept":
                "application/json"
        },
    )

    data = response.json()

    try:

        html = (
            data[
                "content"
            ][
                "rendered"
            ]
        )

    except (
        KeyError,
        TypeError
    ) as exc:

        raise ValueError(
            "WordPress response did not "
            "contain content.rendered"
        ) from exc


    lines = html_to_lines(
        html
    )

    menu = extract_menu(
        lines
    )


    return (
        menu,
        data.get("modified")
    )


def fetch_from_page(
    session: requests.Session
) -> tuple[dict, None]:
    """
    Fallback-lähde:
    Tapiolan Keilahallin varsinainen
    keittiösivu.
    """

    print(
        "  Fetching HTML page..."
    )

    response = get(

        session,

        PAGE_URL,

        headers={
            "Accept":
                "text/html,"
                "application/xhtml+xml"
        },
    )

    lines = html_to_lines(
        response.text
    )

    menu = extract_menu(
        lines
    )

    return (
        menu,
        None
    )


def fetch() -> dict:
    """
    Main scraperin käyttämä julkinen funktio.

    Ensin käytetään WordPress REST API:a.

    Jos API epäonnistuu, yritetään
    varsinaista HTML-sivua.
    """

    session = create_session()

    source_updated = None


    try:

        menu, source_updated = (
            fetch_from_api(
                session
            )
        )

        print(
            "  WordPress API succeeded"
        )


    except (
        requests.RequestException,
        ValueError
    ) as api_error:

        print(
            "  WordPress API failed:"
        )

        print(
            f"    {api_error}"
        )

        print(
            "  Trying HTML fallback..."
        )


        try:

            menu, source_updated = (
                fetch_from_page(
                    session
                )
            )

            print(
                "  HTML fallback succeeded"
            )


        except (
            requests.RequestException,
            ValueError
        ) as page_error:

            raise RuntimeError(

                "Tapiolan Keilahalli failed "
                "from both API and HTML page. "

                f"API error: {api_error}. "

                f"HTML error: {page_error}"

            ) from page_error


    return {

        "name":
            "Tapiolan Keilahalli",

        "address":
            "Kauppamiehentie 6, "
            "02100 Espoo",

        "source":
            SOURCE_URL,

        "week":
            menu["week"],

        "source_updated":
            source_updated,

        "prices":
            menu["prices"],

        "days":
            menu["days"],
    }


#
# Mahdollistaa myös tämän scraperin
# testaamisen yksin:
#
# python -m scrapers.tapiolan_keilahalli
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
