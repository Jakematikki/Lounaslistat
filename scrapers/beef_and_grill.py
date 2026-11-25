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


DATA_URL = (
    "https://lounas.online/"
    "espoo/alue/tapiola"
)

SOURCE_URL = (
    "https://lounas.online/"
    "espoo/beef-grill"
)

RESTAURANT_NAME = "Beef & Grill"


WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
]


#
# Esimerkiksi:
#
# 10.00-15.00
# 10.00 – 15.00
#
TIME_RE = re.compile(
    r"^(?P<start>\d{1,2}[.:]\d{2})"
    r"\s*[–-]\s*"
    r"(?P<end>\d{1,2}[.:]\d{2})$"
)


#
# Esimerkiksi:
#
# 19,30 €
# 14.00 €
#
PRICE_RE = re.compile(
    r"^(?P<price>\d+[,.]\d{2})"
    r"\s*€$"
)


def normalize_line(
    value: str
) -> str:
    """
    Siivoaa lounas.online-sivulla esiintyvät
    erikoisvälilyönnit ja word joiner -merkit.
    """

    value = (
        value
        .replace("\u2060", "")
        .replace("\xa0", " ")
        .replace("\u200b", "")
    )

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def find_restaurant_heading(
    soup: BeautifulSoup
) -> Tag:
    """
    Etsii Tapiolan sivulta juuri Beef & Grill
    -ravintolan otsikon.
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
        "Beef & Grill heading was not found"
    )


def extract_restaurant_lines(
    html: str
) -> list[str]:
    """
    Kerää vain Beef & Grillin oman HTML-osion
    seuraavaan ravintola-/osio-otsikkoon asti.
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
        # Seuraava heading lopettaa Beef & Grillin
        # oman osion.
        #
        if (
            isinstance(element, Tag)
            and
            element is not heading
            and
            element.name in {
                "h2",
                "h3",
                "h4",
            }
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
        # Estetään peräkkäiset duplikaatit.
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


    if not lines:
        raise ValueError(
            "Beef & Grill section was empty"
        )


    return lines


def is_time(
    line: str
) -> bool:
    return TIME_RE.match(
        normalize_line(line)
    ) is not None


def parse_time(
    line: str
) -> tuple[str, str]:
    match = TIME_RE.match(
        normalize_line(line)
    )

    if not match:
        raise ValueError(
            f"Invalid lunch time: {line}"
        )

    start = (
        match
        .group("start")
        .replace(".", ":")
    )

    end = (
        match
        .group("end")
        .replace(".", ":")
    )

    return (
        start,
        end,
    )


def is_price(
    line: str
) -> bool:
    return PRICE_RE.match(
        normalize_line(line)
    ) is not None


def format_price(
    line: str
) -> str:
    match = PRICE_RE.match(
        normalize_line(line)
    )

    if not match:
        raise ValueError(
            f"Invalid price: {line}"
        )

    price = (
        match
        .group("price")
        .replace(".", ",")
    )

    return f"{price} €"


def is_ui_text(
    line: str
) -> bool:
    """
    Sivulla on myös käyttöliittymätekstejä,
    joita ei haluta ruokalistaan.
    """

    normalized = normalize_line(
        line
    )

    lowered = normalized.lower()


    if lowered in {
        "piilota",
        "beef & grill",
    }:
        return True


    if lowered.startswith(
        "näytä ravintolan"
    ):
        return True


    if lowered.startswith(
        "ei lounasta "
    ):
        return True


    if lowered.startswith(
        "katso lista ravintolan"
    ):
        return True


    #
    # Sivun lyhennetty preview voi sisältää
    # esimerkiksi:
    #
    # Black Angus Burger…
    #
    # jonka jälkeen tulee varsinainen teksti.
    #
    if normalized.endswith(
        "…"
    ):
        return True


    #
    # Ravintolan osoite/metatieto.
    #
    if (
        "Länsituuli 10"
        in normalized
    ):
        return True


    return False


def split_day_sections(
    lines: list[str]
) -> list[
    tuple[str, list[str]]
]:
    """
    Tapiolan alue-sivulla jokainen Beef & Grillin
    arkipäivä alkaa omalla:

        10.00-15.00

    rivillään.

    Tällä erotellaan maanantai-perjantai toisistaan.
    """

    sections = []

    current_time = None
    current_lines = []


    for line in lines:

        line = normalize_line(
            line
        )


        #
        # Yläosan metatietorivillä voi olla kaikki
        # viisi kellonaikaa samalla rivillä.
        #
        # Se EI täsmää TIME_RE:hen, koska siinä on
        # muutakin tekstiä.
        #
        if is_time(
            line
        ):

            if current_time is not None:

                sections.append(
                    (
                        current_time,
                        current_lines
                    )
                )


            current_time = line
            current_lines = []

            continue


        if current_time is None:
            continue


        if line.lower().startswith(
            "ei lounasta lauantaina"
        ):
            break


        current_lines.append(
            line
        )


    if current_time is not None:

        sections.append(
            (
                current_time,
                current_lines
            )
        )


    #
    # Beef & Grillillä pitäisi olla viisi
    # arkipäivän osiota.
    #
    if len(sections) < 5:

        raise ValueError(
            "Beef & Grill: expected at least "
            f"5 weekday sections, found {len(sections)}"
        )


    return sections[:5]


def parse_day_meals(
    lines: list[str]
) -> list[dict]:
    """
    Parsii yhden päivän annokset.

    Tavallinen järjestys on:

        19,30 €
        Metsästäjänhärkä (200g)

        19,30 €
        Entrecote (200g)

    Parseri sallii myös käänteisen tilanteen:

        Black Angus Burger
        16,30 €

    jos HTML:n rakenne joskus tuottaa tekstin
    tässä järjestyksessä.
    """

    meals = []

    pending_price = None
    pending_name = None


    def add_meal(
        name: str,
        price: str | None
    ) -> None:

        name = normalize_line(
            name
        )


        if not name:
            return


        meal = {
            "name":
                name,

            "diet":
                [],
        }


        if price:

            meal[
                "price"
            ] = price


        #
        # Estetään identtiset duplikaatit.
        #
        if meals:

            previous = meals[-1]

            if (
                previous.get("name")
                == meal.get("name")
                and
                previous.get("price")
                == meal.get("price")
            ):
                return


        meals.append(
            meal
        )


    for raw_line in lines:

        line = normalize_line(
            raw_line
        )


        if not line:
            continue


        if is_ui_text(
            line
        ):
            continue


        if is_time(
            line
        ):
            continue


        #
        # Hinta
        #
        if is_price(
            line
        ):

            price = format_price(
                line
            )


            #
            # Jos nimi tuli HTML:ssä ennen hintaa.
            #
            if pending_name:

                add_meal(
                    pending_name,
                    price
                )

                pending_name = None
                pending_price = None

            else:

                pending_price = price


            continue


        #
        # Normaali tapa:
        #
        # hinta -> nimi
        #
        if pending_price:

            add_meal(
                line,
                pending_price
            )

            pending_price = None
            pending_name = None

            continue


        #
        # Jos nimi tulee ennen hintaa,
        # odotetaan seuraavaa tokenia.
        #
        if pending_name:

            #
            # Edelliselle nimelle ei löytynyt hintaa.
            # Säilytetään se silti.
            #
            add_meal(
                pending_name,
                None
            )


        pending_name = line


    #
    # Viimeinen mahdollinen hinnaton ruoka.
    #
    if pending_name:

        add_meal(
            pending_name,
            None
        )


    if not meals:

        raise ValueError(
            "Beef & Grill: no meals found "
            "from weekday section"
        )


    return meals


def get_week_dates():
    """
    Kuluvan viikon maanantai-perjantai
    Suomen ajassa.
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


    return [
        monday
        + timedelta(days=index)

        for index in range(5)
    ]


def create_week_label() -> str:
    """
    Esimerkiksi:

        VIIKKO 48 | 23.-27.11.2026
    """

    dates = get_week_dates()

    monday = dates[0]
    friday = dates[-1]

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
    Hakee Beef & Grillin koko viikon
    lounaslistan yhdellä ajolla.
    """

    session = create_session()


    print(
        "  Fetching Beef & Grill "
        "weekly menu from lounas.online..."
    )


    response = get(
        session,
        DATA_URL,
        headers={
            "Accept":
                "text/html,"
                "application/xhtml+xml",

            "Accept-Language":
                "fi-FI,fi;q=0.9,en;q=0.8",
        }
    )


    lines = extract_restaurant_lines(
        response.text
    )


    sections = split_day_sections(
        lines
    )


    days = {}

    day_info = {}


    for index, (
        time_line,
        section_lines,
    ) in enumerate(
        sections
    ):

        day_key = (
            WEEKDAYS[
                index
            ]
        )


        start, end = parse_time(
            time_line
        )


        meals = parse_day_meals(
            section_lines
        )


        days[
            day_key
        ] = meals


        day_info[
            day_key
        ] = {
            "start":
                start,

            "end":
                end,
        }


        print(
            f"    {day_key}: "
            f"{len(meals)} meal(s)"
        )


    #
    # Viikonloppuna ei ole lounasta.
    #
    days[
        "saturday"
    ] = []

    days[
        "sunday"
    ] = []


    meal_count = sum(
        len(meals)
        for meals
        in days.values()
    )


    print(
        "  Beef & Grill weekly parsing succeeded"
    )

    print(
        f"  Found {meal_count} meal(s)"
    )


    return {
        "name":
            RESTAURANT_NAME,

        "address":
            "Länsituuli 10, "
            "02100 Espoo",

        "source":
            SOURCE_URL,

        "data_source":
            DATA_URL,

        "week":
            create_week_label(),

        #
        # Beef & Grillillä ei ole yhtä yhteistä
        # lounashintaa. Hinta on jokaisessa
        # meal-objektissa erikseen.
        #
        "prices":
            [],

        "day_info":
            day_info,

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
