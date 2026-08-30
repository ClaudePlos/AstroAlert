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


def _parse_kp_forecast(rows: list[list[str]]) -> list[tuple[datetime, float]]:
    out = []
    for row in rows[1:]:  # pierwszy wiersz to naglowki
        try:
            when = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            out.append((when, float(row[1])))
        except (ValueError, IndexError):
            continue
    return out


def collect(now: datetime) -> list[dict]:
    rows = get_json(KP_FORECAST)
    forecast = _parse_kp_forecast(rows)
    if not forecast:
        raise FetchError("SWPC: pusta prognoza Kp")

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
