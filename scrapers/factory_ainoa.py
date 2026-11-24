from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from common.http_client import (
    create_session,
    get,
)


URL = (
    "https://ravintolafactory.com/"
    "ainoa/factory-ainoa-lounas/"
)

SOURCE_URL = URL


WEEKDAYS = {
    "maanantai": "monday",
    "tiistai": "tuesday",
    "keskiviikko": "wednesday",
    "torstai": "thursday",
    "perjantai": "friday",
}


#
# Esimerkiksi:
#
#   Maanantai 23.11.2026
#
DAY_RE = re.compile(
    r"^(maanantai|tiistai|keskiviikko|torstai|perjantai)"
    r"\s+"
    r"(\d{1,2}\.\d{1,2}\.\d{4})$",
    re.IGNORECASE,
)


#
# Factory käyttää merkintöjä esimerkiksi:
#
#   (L+G)
#   (VE+G+VS)
#   (VL+VS)
#
DIET_GROUP_RE = re.compile(
    r"\("
    r"(?P<tags>"
    r"(?:L|VL|G|VE|M|VS)"
    r"(?:\+(?:L|VL|G|VE|M|VS))*"
    r")"
    r"\)",
    re.IGNORECASE,
)


PRICE_RE = re.compile(
    r"\bLounasbuffet\s+"
    r"(?P<price>\d+[,.]\d{2})"
    r"\s*€",
    re.IGNORECASE,
)


def normalize_line(
    value: str
) -> str:
    """
    Poistaa ylimääräiset välilyönnit.
    """

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def html_to_lines(
    html: str
) -> list[str]:
    """
    Muuttaa HTML:n siisteiksi tekstiriveiksi.
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

    for raw_line in text.splitlines():

        line = normalize_line(
            raw_line
        )

        if line:
            lines.append(
                line
            )

    return lines


def parse_meal(
    line: str
) -> dict:
    """
    Factoryn yksi rivi voi sisältää useita ruokalajin
    osia eri ruokavaliomerkinnöillä.

    Esimerkiksi:

        Paahdettua lohta ... (L+G)
        yrttiperunat (VE+G)

    Tällaista riviä ei ole turvallista merkitä kokonaan
    vegaaniseksi vain siksi, että lisuke on VE.

    Siksi ruokavaliot erotetaan omiksi tageiksi vain,
    jos rivillä on yksi ainoa ruokavalioryhmä ja se on
    aivan rivin lopussa.

    Muissa tapauksissa Factoryn alkuperäiset merkinnät
    jätetään näkyviin annoksen nimeen.
    """

    matches = list(
        DIET_GROUP_RE.finditer(
            line
        )
    )

    if len(matches) != 1:

        return {
            "name": line,
            "diet": [],
        }

    match = matches[0]

    #
    # Ruokavalioryhmän pitää olla rivin lopussa.
    #
    if match.end() != len(line):

        return {
            "name": line,
            "diet": [],
        }

    tags = [
        tag.strip().upper()
        for tag
        in match.group("tags").split("+")
    ]

    name = line[
        :match.start()
    ].strip()

    return {
        "name": name,
        "diet": tags,
    }


def parse_price(
    lines: list[str]
) -> list[dict]:
    """
    Etsii varsinaisen lounasbuffetin hinnan.

    Esimerkiksi sivulla:

        Lounasbuffet 13,70€
    """

    for line in lines:

        match = PRICE_RE.search(
            line
        )

        if not match:
            continue

        price = (
            match
            .group("price")
            .replace(".", ",")
        )

        return [
            {
                "label": "Lounasbuffet",
                "price": f"{price} €",
            }
        ]

    return []


def parse_menu(
    lines: list[str]
) -> dict:
    """
    Parsii suomenkielisen maanantai-perjantai-listan.
    """

    start_index = None

    for index, line in enumerate(
        lines
    ):

        match = DAY_RE.match(
            line
        )

        if not match:
            continue

        if (
            match
            .group(1)
            .lower()
            == "maanantai"
        ):

            start_index = index
            break


    if start_index is None:

        raise ValueError(
            "Factory Ainoa: "
            "Monday lunch heading was not found"
        )


    days = {}

    dates = {}

    current_day = None


    for line in lines[
        start_index:
    ]:

        #
        # Suomenkielisen listan jälkeen sivulla alkaa
        # englanninkielinen versio.
        #
        if re.match(
            r"^Monday\s+\d",
            line,
            re.IGNORECASE
        ):
            break


        #
        # Toinen hyvä lopetuskohta on allergeeniteksti.
        #
        if line.lower().startswith(
            "henkilökuntamme auttaa"
        ):
            break


        day_match = DAY_RE.match(
            line
        )

        if day_match:

            finnish_day = (
                day_match
                .group(1)
                .lower()
            )

            current_day = (
                WEEKDAYS[
                    finnish_day
                ]
            )

            date_string = (
                day_match
                .group(2)
            )

            days[
                current_day
            ] = []

            dates[
                current_day
            ] = date_string

            continue


        if current_day is None:
            continue


        meal = parse_meal(
            line
        )

        days[
            current_day
        ].append(
            meal
        )


    if not days:

        raise ValueError(
            "Factory Ainoa: "
            "no lunch days were found"
        )


    return {
        "days": days,
        "dates": dates,
    }


def create_week_label(
    dates: dict
) -> str | None:
    """
    Luo esimerkiksi:

        VIIKKO 48 | 23.-27.11.2026
    """

    if not dates:
        return None


    parsed_dates = []

    for value in dates.values():

        try:

            parsed_dates.append(
                datetime.strptime(
                    value,
                    "%d.%m.%Y"
                )
            )

        except ValueError:
            continue


    if not parsed_dates:
        return None


    parsed_dates.sort()

    first = parsed_dates[0]
    last = parsed_dates[-1]

    week_number = (
        first
        .isocalendar()
        .week
    )


    #
    # Jos alku- ja loppupäivä ovat samassa kuussa.
    #
    if (
        first.month == last.month
        and first.year == last.year
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


def fetch() -> dict:
    """
    Main scraperin kutsuma julkinen funktio.
    """

    session = create_session()

    print(
        "  Fetching Factory Ainoa HTML page..."
    )

    response = get(
        session,
        URL,
        headers={
            "Accept": (
                "text/html,"
                "application/xhtml+xml"
            )
        }
    )

    lines = html_to_lines(
        response.text
    )


    menu = parse_menu(
        lines
    )


    prices = parse_price(
        lines
    )


    week = create_week_label(
        menu["dates"]
    )


    print(
        "  Factory Ainoa HTML parsing succeeded"
    )


    return {
        "name":
            "Factory Ainoa",

        "address":
            "Länsituuli 5, 02100 Espoo",

        "source":
            SOURCE_URL,

        "week":
            week,

        "source_updated":
            response.headers.get(
                "Last-Modified"
            ),

        "prices":
            prices,

        "days":
            menu["days"],
    }


#
# Mahdollistaa scraperin testaamisen yksin:
#
# python -m scrapers.factory_ainoa
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
