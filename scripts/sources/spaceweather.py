"""Pogoda kosmiczna - prognozy NOAA SWPC (dane publiczne, bez klucza API)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lib.http import FetchError, get_json
from lib.i18n import render
from lib.text import fmt

KP_FORECAST = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
ALERTS = "https://services.swpc.noaa.gov/products/alerts.json"

#: skala burz geomagnetycznych NOAA: indeks Kp -> (kod, waga)
G_SCALE = {5: ("G1", 3), 6: ("G2", 4), 7: ("G3", 5), 8: ("G4", 5), 9: ("G5", 5)}


TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: str) -> datetime | None:
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            continue
    return None


def _row_values(row) -> tuple[str, str] | None:
    """Wyciaga (czas, Kp) z wiersza niezaleznie od postaci odpowiedzi.

    SWPC podaje ten produkt jako tablice tablic z wierszem naglowkow, ale
    bywa serwowany takze jako lista obiektow - obslugujemy oba warianty,
    zeby zmiana po stronie NOAA nie wygaszala calego zrodla.
    """
    if isinstance(row, dict):
        time_key = next((k for k in ("time_tag", "model_prediction_time", "date") if k in row), None)
        kp_key = next((k for k in ("kp", "kp_index", "estimated_kp", "k_index") if k in row), None)
        if time_key and kp_key:
            return str(row[time_key]), str(row[kp_key])
        return None
    if isinstance(row, (list, tuple)) and len(row) >= 2:
        return str(row[0]), str(row[1])
    return None


def _parse_kp_forecast(rows) -> list[tuple[datetime, float]]:
    if not isinstance(rows, list):
        raise FetchError(f"SWPC: nieoczekiwana odpowiedź typu {type(rows).__name__}")
    out = []
    for row in rows:
        values = _row_values(row)
        if not values:
            continue
        when = _parse_time(values[0])          # wiersz naglowkowy odpadnie tutaj
        if when is None:
            continue
        try:
            out.append((when, float(values[1])))
        except ValueError:
            continue
    return out


def collect(now: datetime) -> list[dict]:
    rows = get_json(KP_FORECAST)
    forecast = _parse_kp_forecast(rows)
    if not forecast:
        shape = rows[:2] if isinstance(rows, list) else rows
        raise FetchError(f"SWPC: nie rozpoznano formatu prognozy Kp, początek odpowiedzi: {str(shape)[:160]}")

    # grupujemy po dobie i bierzemy dzienne maksimum
    by_day: dict[str, tuple[float, datetime]] = {}
    for when, kp in forecast:
        if when < now - timedelta(hours=6):
            continue
        day = when.date().isoformat()
        if day not in by_day or kp > by_day[day][0]:
            by_day[day] = (kp, when)

    events = []
    for day, (kp, when) in sorted(by_day.items()):
        level = int(kp)
        if level < 5:
            continue
        code, importance = G_SCALE[min(level, 9)]
        events.append(
            {
                "title": render("sw.title", code=code),
                "starts_at": when.isoformat().replace("+00:00", "Z"),
                "category": "spaceweather",
                "subcategory": "aurora",
                "importance": importance,
                "summary": render("sw.summary", kp=fmt(kp, 0), code=code,
                                  label=render(f"sw.{code}.label"),
                                  advice=render(f"sw.{code}.advice")),
                "tags": [render("tag.aurora"), render("tag.spaceweather"),
                         {"pl": code, "en": code}],
                "links": [
                    {"label": render("link.aurora"),
                     "url": "https://www.swpc.noaa.gov/products/aurora-30-minute-forecast"},
                    {"label": render("link.kp"),
                     "url": "https://www.swpc.noaa.gov/products/planetary-k-index"},
                    {"label": render("link.spaceweatherlive"),
                     "url": {"pl": "https://www.spaceweatherlive.com/pl.html",
                             "en": "https://www.spaceweatherlive.com/en.html"}},
                ],
                "source": render("attribution.swpc"),
                "source_id": "swpc",
                "extra": {"kp": kp},
                "ephemeral": True,  # prognoza krotkoterminowa - nie archiwizujemy jej na stale
            }
        )
    return events
