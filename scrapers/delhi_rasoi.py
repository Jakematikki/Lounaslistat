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


#
# Sivulla päivämäärä on esimerkiksi:
#
#   Tiistai 24.11.
#
# Vuotta EI ole.
#
DAY_RE = re.compile(
    r"^(maanantai|tiistai|keskiviikko|torstai|"
    r"perjantai|lauantai|sunnuntai)"
    r"\s+"
    r"(\d{1,2})\.(\d{1,2})\.$",
    re.IGNORECASE,
)


#
# Esimerkiksi:
#
#   10:30 – 14:30 14,90 €
#   11:00 – 16:00 17,90 €
#
TIME_PRICE_RE = re.compile(
    r"^(?P<start>\d{1,2}:\d{2})"
    r"\s*[–-]\s*"
    r"(?P<end>\d{1,2}:\d{2})"
    r"\s+"
    r"(?P<price>\d+[,.]\d{2})"
    r"\s*€$"
)


#
# Esimerkiksi:
#
#   Butter Chicken (G, L)
#   Band Gobhi Mattar (G, V)
#   Veg Kofta Korma (G, L, K)
#
DIET_RE = re.compile(
    r"\s*"
    r"\("
    r"(?P<tags>"
    r"[A-ZÅÄÖ]+"
    r"(?:\s*,\s*[A-ZÅÄÖ]+)*"
    r")"
    r"\)"
    r"\s*$",
    re.IGNORECASE,
)


DIET_MAPPING = {
    "G": "G",
    "L": "L",
    "M": "M",
    "VL": "VL",

    #
    # Delhi Rasoi:
    # V = vegaaninen
    #
    "V": "VE",

    #
    # K = kasvis
    #
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


def html_to_lines(
    html: str
) -> list[str]:
    """
    Muuttaa sivun HTML:n tekstiriveiksi.

    Delhi Rasoin oma sivu sisältää lounasdatan
    valmiiksi HTML:ssä, joten JavaScript-renderöintiä
    ei tarvita.
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


def infer_full_date(
    day: int,
    month: int
) -> date:
    """
    Delhi Rasoi ilmoittaa esimerkiksi:

        24.11.

    Päätellään vuosi nykyhetken perusteella.
    Toimii myös vuodenvaihteen ympärillä.
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


def is_meal_name(
    line: str
) -> bool:
    """
    Tunnistaa ruoan otsikkorivin.

    Tavallisissa ruoissa on ruokavaliomerkintä:

        Butter Chicken (G, L)

    Jälkiruoassa merkintää ei välttämättä ole:

        Jälkiruoka Chocolate Cake
    """

    if DIET_RE.search(
        line
    ):
        return True

    if line.lower().startswith(
        "jälkiruoka "
    ):
        return True

    return False


def parse_meal_name(
    line: str
) -> tuple[str, list[str]]:
    """
    Esimerkiksi:

        Band Gobhi Mattar (G, V)

    ->

        Band Gobhi Mattar
        ["G", "VE"]
    """

    match = DIET_RE.search(
        line
    )


    if not match:

        return (
            line,
            []
        )


    source_tags = [
        tag.strip().upper()
        for tag
        in match
        .group("tags")
        .split(",")
    ]


    diets = []


    for source_tag in source_tags:

        mapped = DIET_MAPPING.get(
            source_tag,
            source_tag
        )


        if mapped not in diets:
            diets.append(
                mapped
            )


    name = line[
        :match.start()
    ].strip()


    return (
        name,
        diets
    )


def is_description(
    line: str
) -> bool:
    """
    Tarkistaa, voiko seuraava rivi olla
    ruoan suomenkielinen kuvaus.
    """

    if DAY_RE.match(
        line
    ):
        return False


    if TIME_PRICE_RE.match(
        line
    ):
        return False


    if is_meal_name(
        line
    ):
        return False


    lowered = line.lower()


    if lowered in {
        "tänään",
        "mennyt lounas",
        "delhi rasoi",
    }:
        return False


    return True


def parse_menu(
    lines: list[str]
) -> tuple[
    dict,
    dict,
    list[date],
]:
    """
    Parsii koko viikon lounaslistan.

    Delhi Rasoin rakenne on:

        Tiistai 24.11.
        Tänään
        10:30 – 14:30 14,90 €

        Butter Chicken (G, L)
        Voikanaa

        Lamb Methi (G, L)
        Lammasta sarviapilakastikkeessa
    """

    days = {}

    day_info = {}

    dates = []

    current_day = None

    index = 0


    #
    # Etsitään ensimmäinen oikea päiväotsikko.
    #
    while index < len(lines):

        if DAY_RE.match(
            lines[index]
        ):
            break

        index += 1


    if index >= len(lines):

        raise ValueError(
            "Delhi Rasoi: "
            "no lunch day heading found"
        )


    while index < len(lines):

        line = lines[index]


        #
        # Footer alkaa tästä.
        #
        if (
            current_day is not None
            and
            line == "Delhi Rasoi"
        ):
            break


        #
        # Esimerkiksi:
        #
        # Tiistai 24.11.
        #
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


            if full_date not in dates:
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
                    full_date.isoformat()
            }


            index += 1
            continue


        if current_day is None:
            index += 1
            continue


        #
        # Näitä ei tarvita.
        #
        if line.lower() in {
            "tänään",
            "mennyt lounas",
        }:

            index += 1
            continue


        #
        # Päivän lounasaika ja hinta.
        #
        time_price_match = (
            TIME_PRICE_RE.match(
                line
            )
        )


        if time_price_match:

            price = (
                time_price_match
                .group("price")
                .replace(".", ",")
            )


            day_info[
                current_day
            ].update({
                "start":
                    time_price_match
                    .group("start"),

                "end":
                    time_price_match
                    .group("end"),

                "price":
                    f"{price} €",
            })


            index += 1
            continue


        #
        # Varsinainen ruokalaji.
        #
        if is_meal_name(
            line
        ):

            name, diets = (
                parse_meal_name(
                    line
                )
            )


            description = None


            #
            # Kuvaus on normaalisti seuraava rivi:
            #
            # Butter Chicken (G, L)
            # Voikanaa
            #
            # Maanantain "mennyt lounas" -osiossa
            # kuvaukset voivat puuttua, joten seuraavan
            # rivin tyyppi tarkastetaan ennen käyttöä.
            #
            if index + 1 < len(lines):

                next_line = (
                    lines[
                        index + 1
                    ]
                )


                if is_description(
                    next_line
                ):

                    description = (
                        next_line
                    )


            meal = {
                "name":
                    name,

                "diet":
                    diets,
            }


            if description:

                meal[
                    "description"
                ] = description


            days[
                current_day
            ].append(
                meal
            )


            if description:
                index += 2
            else:
                index += 1

            continue


        index += 1


    #
    # Poistetaan mahdolliset tyhjät päivät.
    #
    days = {
        day: meals
        for day, meals
        in days.items()
        if meals
    }


    if not days:

        raise ValueError(
            "Delhi Rasoi: "
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
    Tekee hinnat esimerkiksi:

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

    Data haetaan suoraan Delhi Rasoin
    omalta Tapiolan lounassivulta.
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
            URL,

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
