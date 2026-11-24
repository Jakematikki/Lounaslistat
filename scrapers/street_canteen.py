from __future__ import annotations

import re

from datetime import datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from common.http_client import (
    create_session,
    get,
)


PAGE_URL = "https://www.streetcanteen.fi/menu-1"

DEFAULT_PRICE = "14,30 €"


# =========================================================
# Helper
# =========================================================

def meal(
    name: str,
    diet: list[str] | None = None
) -> dict:
    return {
        "name": name,
        "diet": diet or [],
    }


# =========================================================
# PARITON VIIKKO
# =========================================================

ODD_MENU = {

    "monday": [

        meal(
            "Nasi Goreng Kunyit (kana/tofu) – "
            "saa vegaanisena"
        ),

        meal(
            "Majerin Butter (kana/tofu)"
        ),

        meal(
            "Ayam Masak Kicap (kana)"
        ),

        meal(
            'Mamak Roti (vegaani "kana") & '
            "friteerattu kukkakaali curry mayo",
            ["VE"]
        ),
    ],


    "tuesday": [

        meal(
            "Nasi Goreng Kunyit (kana/tofu) – "
            "saa vegaanisena"
        ),

        meal(
            "Majerin Butter (kana/tofu)"
        ),

        meal(
            "Ayam Masak Kicap (kana)"
        ),

        meal(
            'Mamak Roti (vegaani "kana") & '
            "friteerattu kukkakaali curry mayo",
            ["VE"]
        ),
    ],


    "wednesday": [

        meal(
            "Hakka Mee"
        ),

        meal(
            "Malay Satay (paahdettu kana/tofu) – "
            "saa vegaanisena"
        ),

        meal(
            "Malay Curry Ikan"
        ),

        meal(
            "Johor Laksa keitto (katkarapu)"
        ),
    ],


    "thursday": [

        meal(
            "Hakka Mee"
        ),

        meal(
            "Malay Satay (paahdettu kana/tofu) – "
            "saa vegaanisena"
        ),

        meal(
            "Malay Curry Ikan"
        ),

        meal(
            "Johor Laksa keitto (katkarapu)"
        ),
    ],


    "friday": [

        meal(
            "Nasi Goreng Sambal (katkarapu)"
        ),

        meal(
            "Lemongrass (kana/tofu) – "
            "saa vegaanisena"
        ),

        meal(
            "Rendang (kana/tofu) – "
            "saa vegaanisena"
        ),

        meal(
            'Mamak Roti (vegaani "kana") & '
            "friteerattu kukkakaali curry mayo",
            ["VE"]
        ),
    ],
}


# =========================================================
# PARILLINEN VIIKKO
# =========================================================

EVEN_MENU = {

    "monday": [

        meal(
            "Nasi Goreng Sambal (katkarapu)"
        ),

        meal(
            "Lemongrass (kana/tofu) – "
            "saa vegaanisena"
        ),

        meal(
            "Rendang (kana/tofu) – "
            "saa vegaanisena"
        ),

        meal(
            'Mamak Roti (vegaani "kana") & '
            "friteerattu kukkakaali curry mayo",
            ["VE"]
        ),
    ],


    "tuesday": [

        meal(
            "Mee Goreng (kana/tofu)"
        ),

        meal(
            "Sweet Chili Chicken Bowl"
        ),

        meal(
            "Ayam Masak Kicap (kana)"
        ),

        meal(
            "Kasvis Kari (tofu) – "
            "saa vegaanisena ja gluteenittomana"
        ),
    ],


    "wednesday": [

        meal(
            "Mee Goreng (kana/tofu)"
        ),

        meal(
            "Sweet Chili Chicken Bowl"
        ),

        meal(
            "Ayam Masak Kicap (kana)"
        ),

        meal(
            "Kasvis Kari (tofu) – "
            "saa vegaanisena ja gluteenittomana"
        ),
    ],


    "thursday": [

        meal(
            "Nasi Goreng Tom Yum (kana/tofu) – "
            "saa vegaanisena"
        ),

        meal(
            "Kookos riisiä & curry kana",
            ["G"]
        ),

        meal(
            "Fried Dumplings Creamy "
            "Turmeric kastike (kasvis)"
        ),

        meal(
            "Mee Kari (tofu) – "
            "saa vegaanisena"
        ),
    ],


    "friday": [

        meal(
            "Nasi Goreng Tom Yum (kana/tofu) – "
            "saa vegaanisena"
        ),

        meal(
            "Kookos riisiä & curry kana",
            ["G"]
        ),

        meal(
            "Fried Dumplings Creamy "
            "Turmeric kastike (kasvis)"
        ),

        meal(
            "Mee Kari (tofu) – "
            "saa vegaanisena"
        ),
    ],
}


# =========================================================
# Viikkotiedot
# =========================================================

def get_current_week() -> int:
    """
    Nykyinen ISO-viikkonumero Suomen ajassa.
    """

    now = datetime.now(
        ZoneInfo("Europe/Helsinki")
    )

    return now.isocalendar().week


def get_week_dates():
    """
    Palauttaa kuluvan viikon maanantain
    ja perjantain.
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

    return monday, friday


def create_week_label(
    week_number: int
) -> str:

    monday, friday = (
        get_week_dates()
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


# =========================================================
# Street Canteenin verkkosivun käsittely
# =========================================================

def find_pdf_url(
    html: str,
    even_week: bool
) -> str | None:
    """
    Etsii oikean PDF:n Street Canteenin sivulta.

    Näin PDF:n URL:ää ei tarvitse kovakoodata,
    vaikka Squarespace vaihtaisi sen osoitetta.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    if even_week:
        wanted = "PARILLINEN VIIKKO"
    else:
        wanted = "PARITON VIIKKO"


    for link in soup.find_all(
        "a",
        href=True
    ):

        text = (
            link
            .get_text(
                " ",
                strip=True
            )
            .upper()
        )

        if wanted in text:

            return urljoin(
                PAGE_URL,
                link["href"]
            )

    return None


def find_price(
    html: str
) -> str | None:
    """
    Etsii esimerkiksi:

        14,30 eur

    Street Canteenin sivulta.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    text = soup.get_text(
        " ",
        strip=True
    )

    match = re.search(
        r"(\d+[,.]\d{2})"
        r"\s*"
        r"(?:€|eur)",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    value = (
        match
        .group(1)
        .replace(
            ".",
            ","
        )
    )

    return f"{value} €"


def fetch_site_information(
    even_week: bool
) -> tuple[str | None, str]:
    """
    Yrittää hakea:
      - oikean PDF-linkin
      - tämänhetkisen hinnan

    Jos Street Canteenin sivu ei vastaa,
    scraperi EI epäonnistu.

    Kiinteä ruokalista voidaan silti julkaista.
    """

    pdf_url = None
    price = DEFAULT_PRICE

    try:

        session = create_session()

        response = get(
            session,
            PAGE_URL
        )

        html = response.text

        found_pdf = find_pdf_url(
            html,
            even_week
        )

        if found_pdf:
            pdf_url = found_pdf


        found_price = find_price(
            html
        )

        if found_price:
            price = found_price


    except Exception as exc:

        print(
            "  Street Canteen website "
            f"could not be fetched: {exc}"
        )

        print(
            "  Using embedded menu and "
            f"default price {DEFAULT_PRICE}"
        )


    return (
        pdf_url,
        price
    )


# =========================================================
# Scraper
# =========================================================

def fetch() -> dict:
    """
    Main scraperin kutsuma funktio.
    """

    week_number = (
        get_current_week()
    )

    even_week = (
        week_number % 2 == 0
    )


    if even_week:

        menu = EVEN_MENU

        menu_type = (
            "parillinen"
        )

    else:

        menu = ODD_MENU

        menu_type = (
            "pariton"
        )


    print(
        f"  Week {week_number}: "
        f"{menu_type} week"
    )


    pdf_url, price = (
        fetch_site_information(
            even_week
        )
    )


    return {

        "name":
            "Street Canteen Ainoa",

        "address":
            "Länsituuli 2, "
            "02100 Espoo",

        #
        # Jos oikea PDF löytyi,
        # linkitetään kortti suoraan siihen.
        #
        # Muuten linkki menee lounassivulle.
        #
        "source":
            pdf_url or PAGE_URL,

        "week":
            create_week_label(
                week_number
            ),

        "prices": [
            {
                "label":
                    "Street Lunch",

                "price":
                    price,
            }
        ],

        "days":
            menu,
    }


# =========================================================
# Paikallinen testaus
#
# python -m scrapers.street_canteen
# =========================================================

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
