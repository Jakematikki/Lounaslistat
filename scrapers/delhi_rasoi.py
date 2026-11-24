from __future__ import annotations

import re

from datetime import date, datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

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
# Mahdollisia muotoja:
#
# Monday 23.11.
#
# Today Tuesday 24.11.
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
# Band Gobhi Mattar G Vgn P 14.90€
#
# Veg Kofta Korma G L Vg 14.90€
#
MEAL_PRICE_RE = re.compile(
    r"^(?P<body>.+?)"
    r"\s+"
    r"(?P<price>\d+[,.]\d{2})"
    r"\s*€$",
    re.IGNORECASE,
)


#
# Lunchmenu.fi käyttää hieman eri
# ruokavaliomerkintöjä kuin Delhi Rasoi.
#
# Muutetaan ne meidän yhtenäiseen muotoon.
#
DIET_MAPPING = {
    "G": "G",
    "L": "L",
    "M": "M",
    "VL": "VL",

    #
    # Vegan
    #
    "VGN": "V",

    #
    # Vegetarian
    #
    "VG": "K",
}


KNOWN_SOURCE_TAGS = {
    "G",
    "L",
    "M",
    "VL",
    "VGN",
    "VG",

    #
    # Lunchmenu voi käyttää myös näitä.
    # Niitä ei tällä hetkellä näytetä meidän
    # ruokavaliotageina.
    #
    "P",
    "N",
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
    Muuttaa HTML:n tekstiriveiksi.
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
    Lähde ilmoittaa päivämäärän esimerkiksi:

        24.11.

    Valitaan lähimpänä nykyhetkeä oleva vuosi.
    Tämä toimii myös vuodenvaihteessa.
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
            f"Invalid date: "
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


def parse_meal_line(
    line: str
) -> dict | None:
    """
    Parsii esimerkiksi:

        Butter Chicken G L 14.90€

    muotoon:

        {
            "name": "Butter Chicken",
            "diet": ["G", "L"],
            "price": "14,90 €"
        }

    Jos nimessä on kaksoispiste:

        Shahi Mattar Paneer: Cottage cheese ...

    jälkimmäinen osa tallennetaan description-kenttään.
    """

    match = MEAL_PRICE_RE.match(
        line
    )

    if not match:
        return None


    body = normalize_line(
        match.group("body")
    )


    price = (
        match
        .group("price")
        .replace(".", ",")
    )

    price = f"{price} €"


    #
    # Puretaan ruokavaliotagit lopusta.
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


    name = " ".join(
        parts
    ).strip()


    if not name:
        return None


    #
    # Muutetaan tagit meidän käyttämään muotoon.
    #
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
    # Joillakin riveillä Lunchmenu sisältää
    # kuvauksen samassa kentässä:
    #
    # Shahi Mattar Paneer: Cottage cheese...
    #
    description = None


    if ":" in name:

        meal_name, possible_description = (
            name.split(
                ":",
                1
            )
        )

        meal_name = (
            meal_name.strip()
        )

        possible_description = (
            possible_description.strip()
        )


        if (
            meal_name
            and
            possible_description
        ):

            name = meal_name

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


def parse_menu(
    lines: list[str]
) -> tuple[
    dict,
    dict,
    list[date],
]:
    """
    Parsii koko viikon lounaslistan.

    Palauttaa:

        days
        day_info
        dates
    """

    days = {}

    day_info = {}

    dates = []

    current_day = None


    for line in lines:

        #
        # Esimerkiksi:
        #
        # Today Tuesday 24.11.10:30-14:30
        #
        day_match = DAY_RE.match(
            line
        )


        if day_match:

            english_day = (
                day_match
                .group(1)
                .lower()
            )

            current_day = (
                WEEKDAYS[
                    english_day
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


            if current_day not in days:

                days[
                    current_day
                ] = []


            day_info[
                current_day
            ] = {
                "date":
                    full_date
                    .isoformat()
            }


            #
            # Jos kellonajat olivat samalla
            # otsikkorivillä.
            #
            if (
                day_match.group(4)
                and
                day_match.group(5)
            ):

                day_info[
                    current_day
                ][
                    "start"
                ] = day_match.group(4)

                day_info[
                    current_day
                ][
                    "end"
                ] = day_match.group(5)


            continue


        if current_day is None:
            continue


        #
        # Sivun alaosan tieto alkaa tästä.
        #
        lowered = line.lower()


        if lowered in {
            "basic info",
            "address",
            "website",
            "phone",
        }:

            current_day = None

            continue


        #
        # Parsitaan ruoka.
        #
        meal = parse_meal_line(
            line
        )


        if meal:

            days[
                current_day
            ].append(
                meal
            )


            #
            # Päivän hinta voidaan päätellä
            # mistä tahansa päivän annoksesta.
            #
            if (
                "price"
                not in
                day_info[
                    current_day
                ]
            ):

                day_info[
                    current_day
                ][
                    "price"
                ] = meal[
                    "price"
                ]


    if not days:

        raise ValueError(
            "Delhi Rasoi: "
            "no lunch days found "
            "from lunchmenu.fi"
        )


    #
    # Varmistetaan ettei tyhjät,
    # väärin parsitut päivät jää mukaan.
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
            "days were found but "
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
    Tekee nykyiselle frontendille:

        Ma–Pe 14,90 €
        La–Su 17,90 €

    jos hinnat löytyvät.
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

    Delhi Rasoin oma lounassivu käyttää
    selaimessa renderöityvää sisältöä.

    Siksi varsinainen data haetaan
    server-renderöidystä lunchmenu.fi:stä.
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


    return {
        "name":
            "Delhi Rasoi Tapiola",

        "address":
            "Länsituuli 5, "
            "02100 Espoo",

        #
        # Käyttäjälle linkitetään edelleen
        # alkuperäisen ravintolan lista.
        #
        "source":
            OFFICIAL_URL,

        #
        # Tämä kertoo JSON:ssa,
        # mistä scraperi oikeasti haki datan.
        #
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
