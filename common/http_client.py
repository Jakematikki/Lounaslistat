from __future__ import annotations

import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 60


DEFAULT_HEADERS = {

    "User-Agent": (
        "Lounaslistat/1.0 "
        "(GitHub Pages lunch menu aggregator)"
    ),

    "Accept": (
        "text/html,"
        "application/xhtml+xml,"
        "application/json"
    ),
}


def create_session() -> requests.Session:
    """
    Luo requests.Session-instanssin, jossa on
    yhteinen retry-logiikka kaikille scrapereille.

    Retry suoritetaan esimerkiksi seuraaville:

        429 Too Many Requests
        500 Internal Server Error
        502 Bad Gateway
        503 Service Unavailable
        504 Gateway Timeout

    Myös connection- ja read-timeouteja yritetään
    uudelleen.
    """

    retry = Retry(

        total=4,

        connect=4,

        read=4,

        status=4,

        backoff_factor=2,

        status_forcelist=[
            429,
            500,
            502,
            503,
            504,
        ],

        allowed_methods=frozenset([
            "GET"
        ]),

        respect_retry_after_header=True,

        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry
    )

    session = requests.Session()

    session.mount(
        "https://",
        adapter
    )

    session.mount(
        "http://",
        adapter
    )

    session.headers.update(
        DEFAULT_HEADERS
    )

    return session


def get(
    session: requests.Session,
    url: str,
    *,
    connect_timeout: int = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: int = DEFAULT_READ_TIMEOUT,
    **kwargs
) -> requests.Response:
    """
    Yhteinen GET-apufunktio.

    Käyttö:

        session = create_session()

        response = get(
            session,
            "https://example.com"
        )

    Mahdolliset lisäparametrit välitetään
    requests.Session.get()-funktiolle.
    """

    response = session.get(
        url,
        timeout=(
            connect_timeout,
            read_timeout
        ),
        **kwargs
    )

    response.raise_for_status()

    return response
