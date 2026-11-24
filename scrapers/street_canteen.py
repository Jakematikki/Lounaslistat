from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from common.http_client import create_session, get


PAGE_URL = "https://www.streetcanteen.fi/menu-1"
DEFAULT_PRICE = "14,30 €"


def meal(
    name: str,
    description: str | None = None,
    diet: list[str] | None = None,
) -> dict:
    return {
        "name": name,
        "description": description,
        "diet": diet or [],
    }


ODD_MENU = {
    "monday": [
        meal(
            "Nasi Goreng Kunyit (kana/tofu)",
            "Paistettua riisiä, kanaa tai tofua, kananmunaa ja vihanneksia "
            "kurkuma-currykastikkeessa. Saatavana vegaanisena.",
        ),
        meal(
            "Majerin Butter (kana/tofu)",
            "Kana tai tofu kermaisessa voikastikkeessa paistettujen "
            "currylehtien ja riisin kanssa.",
        ),
        meal(
            "Ayam Masak Kicap (kana)",
            "Kanaa talon soijakastikkeessa, riisiä ja kasviksia.",
        ),
        meal(
            'Mamak Roti (vegaani "kana") & friteerattu kukkakaali curry mayo',
            "Rapea roti-leipä, salaattisekoitus, paistettua sipulia, "
            "chilimajoneesia, teriyakikastiketta ja limeä sekä friteerattua "
            "kukkakaalia currymajoneesilla.",
            ["VE"],
        ),
    ],
    "tuesday": [
        meal(
            "Nasi Goreng Kunyit (kana/tofu)",
            "Paistettua riisiä, kanaa tai tofua, kananmunaa ja vihanneksia "
            "kurkuma-currykastikkeessa. Saatavana vegaanisena.",
        ),
        meal(
            "Majerin Butter (kana/tofu)",
            "Kana tai tofu kermaisessa voikastikkeessa paistettujen "
            "currylehtien ja riisin kanssa.",
        ),
        meal(
            "Ayam Masak Kicap (kana)",
            "Kanaa talon soijakastikkeessa, riisiä ja kasviksia.",
        ),
        meal(
            'Mamak Roti (vegaani "kana") & friteerattu kukkakaali curry mayo',
            "Rapea roti-leipä, salaattisekoitus, paistettua sipulia, "
            "chilimajoneesia, teriyakikastiketta ja limeä sekä friteerattua "
            "kukkakaalia currymajoneesilla.",
            ["VE"],
        ),
    ],
    "wednesday": [
        meal(
            "Hakka Mee",
            "Nuudelit talon soijakastikkeessa Hakka-tyylisen "
            "broilerijauhelihan, paistetun kananmunan ja kasvisten kanssa.",
        ),
        meal(
            "Malay Satay (paahdettu kana/tofu)",
            "Paahdettua kanaa tai tofua aromaattisessa "
            "satay-pähkinäcurrykastikkeessa riisin kanssa. Saatavana vegaanisena.",
        ),
        meal(
            "Malay Curry Ikan",
            "Paneroitua kalaa currykastikkeessa kasvisten ja riisin kanssa.",
        ),
        meal(
            "Johor Laksa -keitto (katkarapu)",
            "Nuudeleita laksa-currykeitossa, kananmunaa, tofua, limeä, "
            "kevätsipulia, kasviksia, chiliä ja paahdettua sipulia.",
        ),
    ],
    "thursday": [
        meal(
            "Hakka Mee",
            "Nuudelit talon soijakastikkeessa Hakka-tyylisen "
            "broilerijauhelihan, paistetun kananmunan ja kasvisten kanssa.",
        ),
        meal(
            "Malay Satay (paahdettu kana/tofu)",
            "Paahdettua kanaa tai tofua aromaattisessa "
            "satay-pähkinäcurrykastikkeessa riisin kanssa. Saatavana vegaanisena.",
        ),
        meal(
            "Malay Curry Ikan",
            "Paneroitua kalaa currykastikkeessa kasvisten ja riisin kanssa.",
        ),
        meal(
            "Johor Laksa -keitto (katkarapu)",
            "Nuudeleita laksa-currykeitossa, kananmunaa, tofua, limeä, "
            "kevätsipulia, kasviksia, chiliä ja paahdettua sipulia.",
        ),
    ],
    "friday": [
        meal(
            "Nasi Goreng Sambal (katkarapu)",
            "Paistettua riisiä, kananmunaa, katkarapuja ja vihanneksia "
            "sambal-kastikkeessa.",
        ),
        meal(
            "Lemongrass (kana/tofu)",
            "Paneroitua kanaa tai tofua limen ja chilin maustamassa "
            "aromaattisessa sitruunaruohokastikkeessa riisin kanssa. "
            "Saatavana vegaanisena.",
        ),
        meal(
            "Rendang (kana/tofu)",
            "Kanaa tai tofua aromaattisessa rendang-kookoscurryssa riisin "
            "kanssa. Saatavana vegaanisena.",
        ),
        meal(
            'Mamak Roti (vegaani "kana") & friteerattu kukkakaali curry mayo',
            "Rapea roti-leipä, salaattisekoitus, paistettua sipulia, "
            "chilimajoneesia, teriyakikastiketta ja limeä sekä friteerattua "
            "kukkakaalia currymajoneesilla.",
            ["VE"],
        ),
    ],
}


EVEN_MENU = {
    "monday": [
        meal(
            "Nasi Goreng Sambal (katkarapu)",
            "Paistettua riisiä, kananmunaa, katkarapuja ja vihanneksia "
            "sambal-kastikkeessa.",
        ),
        meal(
            "Lemongrass (kana/tofu)",
            "Paneroitua kanaa tai tofua limen ja chilin maustamassa "
            "aromaattisessa sitruunaruohokastikkeessa riisin kanssa. "
            "Saatavana vegaanisena.",
        ),
        meal(
            "Rendang (kana/tofu)",
            "Kanaa tai tofua aromaattisessa rendang-kookoscurryssa riisin "
            "kanssa. Saatavana vegaanisena.",
        ),
        meal(
            'Mamak Roti (vegaani "kana") & friteerattu kukkakaali curry mayo',
            "Rapea roti-leipä, salaattisekoitus, paistettua sipulia, "
            "chilimajoneesia, teriyakikastiketta ja limeä sekä friteerattua "
            "kukkakaalia currymajoneesilla.",
            ["VE"],
        ),
    ],
    "tuesday": [
        meal(
            "Mee Goreng (kana/tofu)",
            "Paistettuja kananmunanuudeleita talon soijakastikkeessa "
            "kasvisten kanssa.",
        ),
        meal(
            "Sweet Chili Chicken Bowl",
            "Paneroitua kanaa makeassa chilikastikkeessa, vihanneksia ja riisiä.",
        ),
        meal(
            "Ayam Masak Kicap (kana)",
            "Kanaa talon soijakastikkeessa, riisiä ja kasviksia.",
        ),
        meal(
            "Kasvis Kari (tofu)",
            "Tofua kasvis-kookoscurryssa riisin kanssa. Saatavana vegaanisena "
            "ja gluteenittomana.",
        ),
    ],
    "wednesday": [
        meal(
            "Mee Goreng (kana/tofu)",
            "Paistettuja kananmunanuudeleita talon soijakastikkeessa "
            "kasvisten kanssa.",
        ),
        meal(
            "Sweet Chili Chicken Bowl",
            "Paneroitua kanaa makeassa chilikastikkeessa, vihanneksia ja riisiä.",
        ),
        meal(
            "Ayam Masak Kicap (kana)",
            "Kanaa talon soijakastikkeessa, riisiä ja kasviksia.",
        ),
        meal(
            "Kasvis Kari (tofu)",
            "Tofua kasvis-kookoscurryssa riisin kanssa. Saatavana vegaanisena "
            "ja gluteenittomana.",
        ),
    ],
    "thursday": [
        meal(
            "Nasi Goreng Tom Yum (kana/tofu)",
            "Paistettua riisiä, kananmunaa ja vihanneksia Tom Yum -kastikkeessa. "
            "Saatavana vegaanisena.",
        ),
        meal(
            "Kookosriisiä & curry-kanaa",
            "Aromaattista kanacurrya talon kookosriisin kanssa.",
            ["G"],
        ),
        meal(
            "Fried Dumplings Creamy Turmeric (kasvis)",
            "Kahdeksan friteerattua dumpling-nyyttiä kermaisessa "
            "kurkumakastikkeessa kasvisten kanssa.",
        ),
        meal(
            "Mee Kari (tofu)",
            "Nuudeleita tulisessa currypohjaisessa keitossa, kookosmaitoa, "
            "tofua, munakoisoa, kasviksia, limeä, chiliä ja paahdettua sipulia. "
            "Saatavana vegaanisena.",
        ),
    ],
    "friday": [
        meal(
            "Nasi Goreng Tom Yum (kana/tofu)",
            "Paistettua riisiä, kananmunaa ja vihanneksia Tom Yum -kastikkeessa. "
            "Saatavana vegaanisena.",
        ),
        meal(
            "Kookosriisiä & curry-kanaa",
            "Aromaattista kanacurrya talon kookosriisin kanssa.",
            ["G"],
        ),
        meal(
            "Fried Dumplings Creamy Turmeric (kasvis)",
            "Kahdeksan friteerattua dumpling-nyyttiä kermaisessa "
            "kurkumakastikkeessa kasvisten kanssa.",
        ),
        meal(
            "Mee Kari (tofu)",
            "Nuudeleita tulisessa currypohjaisessa keitossa, kookosmaitoa, "
            "tofua, munakoisoa, kasviksia, limeä, chiliä ja paahdettua sipulia. "
            "Saatavana vegaanisena.",
        ),
    ],
}


def get_current_week() -> int:
    now = datetime.now(ZoneInfo("Europe/Helsinki"))
    return now.isocalendar().week


def get_week_dates():
    today = datetime.now(ZoneInfo("Europe/Helsinki")).date()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def create_week_label(week_number: int) -> str:
    monday, friday = get_week_dates()

    if monday.month == friday.month and monday.year == friday.year:
        date_range = (
            f"{monday.day}.-{friday.day}."
            f"{friday.month}.{friday.year}"
        )
    else:
        date_range = (
            f"{monday.day}.{monday.month}.{monday.year} - "
            f"{friday.day}.{friday.month}.{friday.year}"
        )

    return f"VIIKKO {week_number} | {date_range}"


def find_pdf_url(html: str, even_week: bool) -> str | None:
    soup = BeautifulSoup(html, "html.parser")

    wanted = "PARILLINEN VIIKKO" if even_week else "PARITON VIIKKO"

    for link in soup.find_all("a", href=True):
        text = link.get_text(" ", strip=True).upper()

        if wanted in text:
            return urljoin(PAGE_URL, link["href"])

    return None


def find_price(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    match = re.search(
        r"(\d+[,.]\d{2})\s*(?:€|eur)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    value = match.group(1).replace(".", ",")
    return f"{value} €"


def fetch_site_information(
    even_week: bool,
) -> tuple[str | None, str]:
    """
    Sivuston väliaikainen virhe ei estä kiinteän lounaslistan
    julkaisemista.
    """
    pdf_url = None
    price = DEFAULT_PRICE

    try:
        session = create_session()
        response = get(session, PAGE_URL)

        found_pdf = find_pdf_url(
            response.text,
            even_week,
        )

        if found_pdf:
            pdf_url = found_pdf

        found_price = find_price(
            response.text
        )

        if found_price:
            price = found_price

    except Exception as exc:
        print(
            f"  Street Canteen website could not be fetched: {exc}"
        )
        print(
            f"  Using embedded menu and default price {DEFAULT_PRICE}"
        )

    return pdf_url, price


def fetch() -> dict:
    week_number = get_current_week()
    even_week = week_number % 2 == 0

    if even_week:
        menu = EVEN_MENU
        menu_type = "parillinen"
    else:
        menu = ODD_MENU
        menu_type = "pariton"

    print(
        f"  Week {week_number}: {menu_type} week"
    )

    pdf_url, price = fetch_site_information(
        even_week
    )

    return {
        "name": "Street Canteen Ainoa",
        "address": "Länsituuli 2, 02100 Espoo",
        "source": pdf_url or PAGE_URL,
        "week": create_week_label(week_number),
        "prices": [
            {
                "label": "Street Lunch",
                "price": price,
            }
        ],
        "days": menu,
    }


if __name__ == "__main__":
    import json

    print(
        json.dumps(
            fetch(),
            ensure_ascii=False,
            indent=2,
        )
    )
