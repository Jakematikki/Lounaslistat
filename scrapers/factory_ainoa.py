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


def calculate_diet_tags(
    groups: list[set[str]]
) -> list[str]:
    """
    Laskee koko annosriville turvallisesti pätevät merkinnät.

    Esimerkkejä:

        (L+G) + (VE+G)
            -> L, G

        (M+G+VS) + (VE+G)
            -> M, G, VS

        (VL+VS) + (L+G)
            -> VL, VS

    Merkintöjen merkitys:

        G   = gluteeniton
        VE  = vegaaninen
        M   = maidoton
        L   = laktoositon
        VL  = vähälaktoosinen
        VS  = sisältää valkosipulia
    """

    if not groups:
        return []

    #
    # Jos rivillä on vain yksi merkintäryhmä,
    # voidaan käyttää sitä sellaisenaan.
    #
    if len(groups) == 1:
        preferred_order = [
            "VE",
            "M",
            "L",
            "VL",
            "G",
            "VS",
        ]

        return [
            tag
            for tag in preferred_order
            if tag in groups[0]
        ]

    result = []


    #
    # Vegaaninen vain jos kaikki annoksen osat
    # ovat vegaanisia.
    #
    if all(
        "VE" in group
        for group in groups
    ):
        result.append("VE")


    #
    # Maidoton:
    #
    # VE on luonnollisesti myös maidoton.
    #
    elif all(
        bool(
            group
            & {
                "M",
                "VE",
            }
        )
        for group in groups
    ):
        result.append("M")


    #
    # Laktoositon:
    #
    # M ja VE ovat myös laktoosittomia.
    #
    elif all(
        bool(
            group
            & {
                "L",
                "M",
                "VE",
            }
        )
        for group in groups
    ):
        result.append("L")


    #
    # Vähälaktoosinen:
    #
    # L, M ja VE täyttävät myös VL-vaatimuksen.
    #
    elif all(
        bool(
            group
            & {
                "VL",
                "L",
                "M",
                "VE",
            }
        )
        for group in groups
    ):
        result.append("VL")


    #
    # Gluteeniton vain jos kaikki annoksen osat
    # on merkitty gluteenittomiksi.
    #
    if all(
        "G" in group
        for group in groups
    ):
        result.append("G")


    #
    # VS tarkoittaa "sisältää valkosipulia".
    #
    # Tähän riittää, että yksikin annoksen osa
    # sisältää valkosipulia.
    #
    if any(
        "VS" in group
        for group in groups
    ):
        result.append("VS")


    return result


def parse_meal(
    line: str
) -> dict:
    """
    Parsii Factoryn ruokarivin.

    Esimerkiksi:

        Paahdettua lohta ... (L+G)
        yrttiperunat (VE+G)

    muuttuu muotoon:

        {
            "name":
                "Paahdettua lohta ... yrttiperunat",

            "diet": [
                "L",
                "G"
            ]
        }
    """

    matches = list(
        DIET_GROUP_RE.finditer(
            line
        )
    )

    if not matches:

        return {
            "name": line,
            "diet": [],
        }


    groups = []

    for match in matches:

        tags = {
            tag.strip().upper()
            for tag
            in match
            .group("tags")
            .split("+")
        }

        groups.append(
            tags
        )


    #
    # Poistetaan itse (L+G), (VE+G) jne.
    # näkyvästä ruoan nimestä.
    #
    name = DIET_GROUP_RE.sub(
        "",
        line
    )

    name = normalize_line(
        name
    )


    return {
        "name": name,
        "diet": calculate_diet_tags(
            groups
        ),
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
