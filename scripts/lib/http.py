"""Minimalny klient HTTP na bibliotece standardowej (bez zaleznosci)."""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = (
    "AstroAlert/1.0 (+https://github.com/ClaudePlos/AstroAlert) "
    "portal wydarzen kosmicznych"
)


class FetchError(RuntimeError):
    """Nie udalo sie pobrac danych ze zrodla."""


def get_json(url: str, timeout: int = 30, retries: int = 3, backoff: float = 3.0) -> Any:
    """Pobiera i parsuje JSON, z ponowieniami i wykladniczym odczekaniem.

    Rzuca FetchError zamiast przerywac caly proces - kazde zrodlo moze paść,
    a portal ma sie zbudowac z tego, co akurat dziala.
    """
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:  # 4xx/5xx
            last = exc
            if exc.code in (400, 401, 403, 404):
                break  # ponawianie nic nie da
        except Exception as exc:  # timeout, DNS, blad parsowania
            last = exc
        if attempt < retries - 1:
            time.sleep(backoff * (2 ** attempt))
    raise FetchError(f"{url}: {last}") from last
