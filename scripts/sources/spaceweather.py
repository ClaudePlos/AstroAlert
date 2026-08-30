"""Pogoda kosmiczna - prognozy NOAA SWPC (dane publiczne, bez klucza API)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lib.http import FetchError, get_json
from lib.text import num

KP_FORECAST = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
ALERTS = "https://services.swpc.noaa.gov/products/alerts.json"

#: skala burz geomagnetycznych NOAA
G_SCALE = {
    5: ("G1", "słaba burza geomagnetyczna", 3,
        "Zorza polarna możliwa nad Skandynawią, Szkocją i Islandią; z Polski raczej nic nie zobaczymy."),
    6: ("G2", "umiarkowana burza geomagnetyczna", 4,
        "Zorzę widać zwykle z południowej Skandynawii i Szkocji, a przy sprzyjających warunkach "
        "jako łuna nad północnym horyzontem z północy Polski."),
    7: ("G3", "silna burza geomagnetyczna", 5,
        "Realna szansa na zorzę polarną z terenu Polski – szukaj czystego nieba i ciemnego miejsca "
        "z odsłoniętym północnym horyzontem. Aparat na statywie zarejestruje ją nawet wtedy, gdy "
        "gołym okiem widać tylko szarą łunę."),
    8: ("G4", "bardzo silna burza geomagnetyczna", 5,
        "Zorza polarna może być widoczna z całej Polski, także wysoko nad horyzontem. Takie burze "
        "zdarzają się kilka razy w cyklu słonecznym – warto rzucić wszystko i wyjść na dwór."),
    9: ("G5", "ekstremalna burza geomagnetyczna", 5,
        "Zjawisko klasy tych z października 1989 czy maja 2024 – zorza widoczna nawet z południa "
        "Europy, możliwe zakłócenia w sieciach energetycznych, GPS i łączności radiowej."),
}


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
        code, label, importance, advice = G_SCALE[min(level, 9)]
        events.append(
            {
                "title": f"Burza geomagnetyczna {code} – szansa na zorzę polarną",
                "starts_at": when.isoformat().replace("+00:00", "Z"),
                "category": "spaceweather",
                "subcategory": "aurora",
                "importance": importance,
                "summary": (
                    f"NOAA prognozuje na ten dzień indeks Kp = {num(kp, 0)}, czyli {label} ({code}). "
                    f"{advice} Prognozy pogody kosmicznej sprawdzają się na 1–3 dni do przodu i "
                    f"potrafią się zmienić z godziny na godzinę."
                ),
                "tags": ["zorza polarna", "pogoda kosmiczna", code],
                "links": [
                    {"label": "Prognoza zorzy NOAA (30 min)",
                     "url": "https://www.swpc.noaa.gov/products/aurora-30-minute-forecast"},
                    {"label": "Aktualny indeks Kp",
                     "url": "https://www.swpc.noaa.gov/products/planetary-k-index"},
                    {"label": "SpaceWeatherLive – zorze na żywo",
                     "url": "https://www.spaceweatherlive.com/pl.html"},
                ],
                "source": "NOAA Space Weather Prediction Center",
                "source_id": "swpc",
                "extra": {"kp": kp},
                "ephemeral": True,  # prognoza krotkoterminowa - nie archiwizujemy jej na stale
            }
        )
    return events
