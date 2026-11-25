from __future__ import annotations

import re
import unicodedata

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from common.http_client import (
    create_session,
    get,
)


DATA_URL = "https://lounas.online/espoo/alue/tapiola"
SOURCE_URL = "https://lounas.online/espoo/beef-grill"

RESTAURANT_NAME = "Beef & Grill"

WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
]


TIME_RE = re.compile(
    r"^"
    r"(?P<start_h>\d{1,2})"
    r"[.:]"
    r"(?P<start_m>\d{2})"
    r"\s*[-–—]\s*"
    r"(?P<end_h>\d{1,2})"
    r"[.:]"
    r"(?P<end_m>\d{2})"
    r"$"
)


PRICE_RE = re.compile(
    r"^(?P<price>\d+[,.]\d{2})\s*€$"
)


def normalize_line(value: str) -> str:
    """
    Normalisoi lounas.online-sivun tekstiä.

    Sivulla esiintyy mm. näkymättömiä Unicode-merkkejä
    kellonaikojen ympärillä, esimerkiksi:

        10.00⁠-⁠15.00

    Unicode-luokan Cf merkit poistetaan kokonaan.
    """

    value = "".join(
        char
        for char in value
        if unicodedata.category(char) != "Cf"
    )

    value = (
        value
        .replace("\xa0", " ")
        .replace("\u202f", " ")
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def extract_page_lines(
    html: str
) -> list[str]:
    """
    Muuttaa koko sivun HTML:n yksittäisiksi tekstiriveiksi.
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

        if not line:
            continue

        #
        # Poistetaan vain peräkkäiset täysin
        # identtiset rivit.
        #
        if (
            lines
            and
            lines[-1] == line
        ):
            continue

        lines.append(line)

    return lines


def extract_restaurant_lines(
    html: str
) -> list[str]:
    """
    Rajaa Tapiolan alue-sivulta Beef & Grillin osuuden.

    Sivun rakenne tekstinä on suunnilleen:

        Näytä ravintolan Beef & Grill koko viikon lounaslista
        Beef & Grill
        Piilota
        ...
        Ei lounasta sunnuntaina
        Näytä ravintolan Xin Long koko viikon lounaslista

    Emme siis ole riippuvaisia tietystä div/class-rakenteesta.
    """

    lines = extract_page_lines(
        html
    )

    start_index = None

    #
    # Etsitään varsinainen ravintolan otsikko,
    # ei "Näytä ravintolan Beef & Grill..." -linkkiä.
    #
    for index, line in enumerate(lines):

        if line == RESTAURANT_NAME:
            start_index = index + 1
            break

    if start_index is None:
        raise ValueError(
            "Beef & Grill heading was not found"
        )

    restaurant_lines = []

    for line in lines[start_index:]:

        #
        # Seuraavan ravintolan osio alkaa tästä.
        #
        if (
            line.startswith("Näytä ravintolan ")
            and
            "koko viikon lounaslista"
            in line
        ):
            break

        restaurant_lines.append(
            line
        )

    if not restaurant_lines:
        raise ValueError(
            "Beef & Grill section was empty"
        )

    return restaurant_lines


def is_time(
    line: str
) -> bool:

    line = normalize_line(
        line
    )

    return TIME_RE.fullmatch(
        line
    ) is not None


def parse_time(
    line: str
) -> tuple[str, str]:

    line = normalize_line(
        line
    )

    match = TIME_RE.fullmatch(
        line
    )

    if not match:
        raise ValueError(
            f"Invalid lunch time: {line!r}"
        )

    start = (
        f"{int(match.group('start_h')):02d}:"
        f"{match.group('start_m')}"
    )

    end = (
        f"{int(match.group('end_h')):02d}:"
        f"{match.group('end_m')}"
    )

    return start, end


def is_price(
    line: str
) -> bool:

    return PRICE_RE.fullmatch(
        normalize_line(line)
    ) is not None


def format_price(
    line: str
) -> str:

    line = normalize_line(
        line
    )

    match = PRICE_RE.fullmatch(
        line
    )

    if not match:
        raise ValueError(
            f"Invalid price: {line!r}"
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
    Tekstit, joita ei haluta tulkita ruoiksi.
    """

    line = normalize_line(
        line
    )

    lowered = line.lower()

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
        "katso lista ravintolan"
    ):
        return True

    if lowered.startswith(
        "listat päivitetty"
    ):
        return True

    if lowered.startswith(
        "ravintola voi muuttaa"
    ):
        return True

    if lowered.startswith(
        "ei lounasta "
    ):
        return True

    #
    # Osoiterivi.
    #
    if "länsituuli 10" in lowered:
        return True

    #
    # lounas.online näyttää joistakin ruoista ensin
    # lyhennetyn preview-rivin:
    #
    # Black Angus Burger…
    #
    # ja heti perään oikean rivin.
    #
    if line.endswith("…"):
        return True

    return False


def split_day_sections(
    lines: list[str]
) -> list[tuple[str, list[str]]]:
    """
    Jakaa Beef & Grillin osuuden viiteen arkipäivään.

    Jokainen päivä alkaa omalla kellonaikarivillä:

        10.00-15.00

    Sivun alussa on lisäksi yhteenvetorivi:

        10.00-15.00 · 10.00-15.00 · ...

    mutta koska se ei ole pelkkä kellonaika,
    is_time() ei hyväksy sitä.
    """

    sections = []

    current_time = None
    current_lines = []

    for raw_line in lines:

        line = normalize_line(
            raw_line
        )

        #
        # Viikonlopun teksti merkitsee samalla
        # arkipäivälistan loppua.
        #
        if lowered_startswith(
            line,
            "ei lounasta lauantaina"
        ):
            break

        if is_time(line):

            if current_time is not None:

                sections.append(
                    (
                        current_time,
                        current_lines,
                    )
                )

            current_time = line
            current_lines = []

            continue

        if current_time is None:
            continue

        current_lines.append(
            line
        )

    if current_time is not None:

        sections.append(
            (
                current_time,
                current_lines,
            )
        )

    if len(sections) < 5:

        #
        # Debug-tieto auttaa heti, jos sivusto
        # muuttaa rakennetta myöhemmin.
        #
        candidates = [
            line
            for line in lines
            if (
                "10.00" in line
                or "15.00" in line
            )
        ]

        raise ValueError(
            "Beef & Grill: expected at least "
            f"5 weekday sections, found {len(sections)}. "
            f"Time candidates: {candidates!r}"
        )

    return sections[:5]


def lowered_startswith(
    value: str,
    prefix: str
) -> bool:

    return (
        normalize_line(value)
        .casefold()
        .startswith(
            prefix.casefold()
        )
    )


def add_meal(
    meals: list[dict],
    name: str,
    price: str | None
) -> None:

    name = normalize_line(
        name
    )

    if not name:
        return

    if is_ui_text(name):
        return

    meal = {
        "name": name,
        "diet": [],
    }

    if price:
        meal["price"] = price

    #
    # Poistetaan peräkkäinen identtinen duplikaatti.
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


def parse_day_meals(
    lines: list[str]
) -> list[dict]:
    """
    Parsii yhden päivän ruoat ja hinnat.

    Tavallisin rakenne:

        19,30 €
        Metsästäjänhärkä (200g)

        19,30 €
        Entrecote (200g)

    Sivulla esimerkiksi Black Angus Burgerin kohdalla
    järjestys saattaa kuitenkin olla:

        Black Angus Burger
        16,30 €

    joten parseri tukee molempia järjestyksiä.
    """

    meals = []

    pending_price = None
    pending_name = None

    for raw_line in lines:

        line = normalize_line(
            raw_line
        )

        if not line:
            continue

        if is_ui_text(line):
            continue

        if is_time(line):
            continue

        #
        # HINTA
        #
        if is_price(line):

            price = format_price(
                line
            )

            #
            # Jos nimi tuli ennen hintaa:
            #
            # Black Angus Burger
            # 16,30 €
            #
            if pending_name is not None:

                add_meal(
                    meals,
                    pending_name,
                    price,
                )

                pending_name = None
                pending_price = None

            else:

                pending_price = price

            continue

        #
        # NIMI
        #
        if pending_price is not None:

            #
            # Normaali:
            #
            # 19,30 €
            # Metsästäjänhärkä
            #
            add_meal(
                meals,
                line,
                pending_price,
            )

            pending_price = None
            pending_name = None

            continue

        #
        # Meillä oli jo hinnaton nimi odottamassa,
        # mutta tuli toinen nimi ennen hintaa.
        #
        # Säilytetään ensimmäinen hinnattomana.
        #
        if pending_name is not None:

            add_meal(
                meals,
                pending_name,
                None,
            )

        pending_name = line

    #
    # Mahdollinen viimeinen hinnaton ruoka.
    #
    if pending_name is not None:

        add_meal(
            meals,
            pending_name,
            None,
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
    Suomen paikallisessa ajassa.
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

    elif monday.year == friday.year:

        date_range = (
            f"{monday.day}."
            f"{monday.month}.-"
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
    lounaslistan yhdellä HTTP-pyynnöllä.
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
            "Accept": (
                "text/html,"
                "application/xhtml+xml"
            ),
            "Accept-Language": (
                "fi-FI,fi;q=0.9,en;q=0.8"
            ),
        },
    )

    restaurant_lines = (
        extract_restaurant_lines(
            response.text
        )
    )

    sections = split_day_sections(
        restaurant_lines
    )

    days = {}
    day_info = {}

    for index, (
        time_line,
        section_lines,
    ) in enumerate(sections):

        day_key = WEEKDAYS[index]

        start, end = parse_time(
            time_line
        )

        meals = parse_day_meals(
            section_lines
        )

        days[day_key] = meals

        day_info[day_key] = {
            "start": start,
            "end": end,
        }

        print(
            f"    {day_key}: "
            f"{len(meals)} meal(s)"
        )

    #
    # Beef & Grillillä ei ole viikonloppulounasta.
    #
    days["saturday"] = []
    days["sunday"] = []

    total_meals = sum(
        len(meals)
        for meals in days.values()
    )

    print(
        "  Beef & Grill weekly parsing succeeded"
    )

    print(
        f"  Found {total_meals} meal(s)"
    )

    return {
        "name": RESTAURANT_NAME,

        "address": (
            "Länsituuli 10, "
            "02100 Espoo"
        ),

        "source": SOURCE_URL,

        "data_source": DATA_URL,

        "week": create_week_label(),

        #
        # Beef & Grillillä hinnat ovat
        # annoskohtaisia.
        #
        "prices": [],

        "day_info": day_info,

        "days": days,
    }


if __name__ == "__main__":

    import json

    result = fetch()

    print()

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )
