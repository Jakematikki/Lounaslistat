from __future__ import annotations

import re

from datetime import date, datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

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
    r"^(?P<start>\d{1,2}:\d{2})"
    r"\s*[–-]\s*"
    r"(?P<end>\d{1,2}:\d{2})"
    r"\s+"
    r"(?P<price>\d+[,.]\d{2})"
    r"\s*€$"
)


#
# Delhi Rasoin käyttämät merkinnät:
#
# G = gluteeniton
# L = laktoositon
# V = vegaaninen
# K = kasvis
#
DIET_RE = re.compile(
    r"\s*"
    r"\("
    r"(?P<tags>"
    r"(?:G|L|V|K)"
    r"(?:\s*,\s*(?:G|L|V|K))*"
    r")"
    r"\)"
    r"\s*$",
    re.IGNORECASE,
)


def normalize_line(
    value: str
) -> str:
    """
    Yhdistää ylimääräiset välilyönnit.
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
    Muuttaa sivun HTML:n siistiksi tekstirivilistaksi.
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


def parse_meal_name(
    line: str
) -> tuple[str, list[str]]:
    """
    Esimerkiksi:

        Butter Chicken (G, L)

    ->

        Butter Chicken
        ["G", "L"]
    """

    match = DIET_RE.search(
        line
    )

    if not match:

        return (
            line,
            []
        )

    tags = [
        tag.strip().upper()
        for tag
        in match
        .group("tags")
        .split(",")
    ]

    name = line[
        :match.start()
    ].strip()

    return (
        name,
        tags
    )


def infer_full_date(
    day: int,
    month: int
) -> date:
    """
    Delhi Rasoin sivulla päivämäärissä ei ole vuotta:

        Tiistai 24.11.

    Valitaan nykyisen päivän ympäriltä lähimpänä oleva
    vastaava päivämäärä. Tämä toimii myös vuodenvaihteen
    ympärillä.
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
            f"Invalid lunch date: "
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


def create_week_label(
    dates: list[date]
) -> str | None:
    """
    Luo esimerkiksi:

        VIIKKO 48 | 23.-29.11.2026
    """

    if not dates:
        return None

    dates = sorted(
        dates
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


def parse_menu(
    lines: list[str]
) -> tuple[
    dict,
    dict,
    list[date],
]:
    """
    Parsii päiväkohtaiset listat.

    Palauttaa:

        days
        day_info
        dates
    """

    days = {}

    day_info = {}

    dates = []

    current_day = None

    #
    # Aloitetaan ensimmäisestä varsinaisesta
    # päiväotsikosta.
    #
    start_index = None

    for index, line in enumerate(
        lines
    ):

        if DAY_RE.match(
            line
        ):

            start_index = index
            break


    if start_index is None:

        raise ValueError(
            "Delhi Rasoi: "
            "no lunch day heading found"
        )


    index = start_index


    while index < len(lines):

        line = lines[index]


        #
        # Footer alkaa tämän jälkeen.
        #
        if line == "Delhi Rasoi":
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

            day_number = int(
                day_match.group(2)
            )

            month_number = int(
                day_match.group(3)
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

            days[
                current_day
            ] = []

            day_info[
                current_day
            ] = {
                "date":
                    full_date.isoformat(),
            }

            index += 1
            continue


        if current_day is None:
            index += 1
            continue


        #
        # "Tänään"-merkintää ei tarvita.
        #
        if line.lower() == "tänään":

            index += 1
            continue


        #
        # Päivän aika ja hinta.
        #
        price_match = (
            TIME_PRICE_RE.match(
                line
            )
        )

        if price_match:

            price = (
                price_match
                .group("price")
                .replace(
                    ".",
                    ","
                )
            )

            day_info[
                current_day
            ].update({
                "start":
                    price_match
                    .group("start"),

                "end":
                    price_match
                    .group("end"),

                "price":
                    f"{price} €",
            })

            index += 1
            continue


        #
        # Jos seuraava rivi on uuden päivän otsikko,
        # tätä ei käsitellä annoksena.
        #
        if DAY_RE.match(
            line
        ):

            continue


        #
        # Ruokalista on HTML:n tekstinä muodossa:
        #
        # Butter Chicken (G, L)
        # Voikanaa
        #
        # Lamb Methi (G, L)
        # Lammasta sarviapilakastikkeessa
        #
        # eli nimi + kuvaus muodostavat parin.
        #

        meal_name = line

        description = None


        if index + 1 < len(lines):

            next_line = lines[
                index + 1
            ]

            #
            # Kuvausrivi ei saa olla:
            # - uuden päivän otsikko
            # - päivän hinta
            # - Tänään
            # - footer
            #
            if (
                not DAY_RE.match(
                    next_line
                )
                and
                not TIME_PRICE_RE.match(
                    next_line
                )
                and
                next_line.lower()
                != "tänään"
                and
                next_line
                != "Delhi Rasoi"
            ):

                description = (
                    next_line
                )


        name, diets = (
            parse_meal_name(
                meal_name
            )
        )


        #
        # Varmistetaan ettei navigaation tai footerin
        # teksti päädy ruokalistaan.
        #
        if name:

            days[
                current_day
            ].append({
                "name":
                    name,

                "description":
                    description,

                "diet":
                    diets,
            })


        if description is not None:
            index += 2
        else:
            index += 1


    if not days:

        raise ValueError(
            "Delhi Rasoi: "
            "no lunch menus found"
        )


    return (
        days,
        day_info,
        dates
    )


def create_prices(
    day_info: dict
) -> list[dict]:
    """
    Nykyinen frontend näyttää ravintolakohtaiset
    hinnat yhteisesti.

    Ryhmitellään siksi saman hintaiset päivät yhteen.

    Tyypillisesti:

        Arkisin 14,90 €
        Viikonloppu 17,90 €
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
            day
        )

        if (
            info
            and
            info.get("price")
        ):

            weekday_prices.append(
                info["price"]
            )


    for day in (
        "saturday",
        "sunday",
    ):

        info = day_info.get(
            day
        )

        if (
            info
            and
            info.get("price")
        ):

            weekend_prices.append(
                info["price"]
            )


    prices = []


    if weekday_prices:

        price = weekday_prices[0]

        prices.append({
            "label":
                "Ma–Pe",

            "price":
                price,
        })


    if weekend_prices:

        price = weekend_prices[0]

        prices.append({
            "label":
                "La–Su",

            "price":
                price,
        })


    return prices


def fetch() -> dict:
    """
    Main scraperin käyttämä julkinen funktio.
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
                "application/xhtml+xml"
        }
    )

    lines = html_to_lines(
        response.text
    )

    (
        days,
        day_info,
        dates,
    ) = parse_menu(
        lines
    )

    prices = create_prices(
        day_info
    )

    week = create_week_label(
        dates
    )

    print(
        "  Delhi Rasoi parsing succeeded"
    )


    return {
        "name":
            "Delhi Rasoi Tapiola",

        "address":
            "Länsituuli 5, "
            "02100 Espoo",

        "source":
            URL,

        "week":
            week,

        "source_updated":
            response.headers.get(
                "Last-Modified"
            ),

        "prices":
            prices,

        #
        # Tätä frontend ei vielä käytä,
        # mutta tieto säilytetään JSON:ssa
        # mahdollista myöhempää käyttöä varten.
        #
        "day_info":
            day_info,

        "days":
            days,
    }


#
# Paikallinen testaus:
#
# python -m scrapers.delhi_rasoi
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
