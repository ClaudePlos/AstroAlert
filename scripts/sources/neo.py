"""Bliskie przeloty planetoid - NASA NeoWs (dziala z DEMO_KEY, lepiej z wlasnym kluczem)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lib.http import get_json
from lib.text import num

FEED = "https://api.nasa.gov/neo/rest/v1/feed?start_date={start}&end_date={end}&api_key={key}"
MOON_DISTANCE_KM = 384_400.0


def _size_note(dmin: float, dmax: float) -> str:
    avg = (dmin + dmax) / 2.0
    if avg < 20:
        return "obiekt tej wielkości spłonąłby w atmosferze jako jasny bolid"
    if avg < 60:
        return "rozmiarami przypomina obiekt tunguski z 1908 roku"
    if avg < 150:
        return "wielkości sporego bloku mieszkalnego"
    if avg < 500:
        return "wielkości niewielkiego wzgórza"
    return "obiekt tej skali to już poważny gracz w katalogu planetoid bliskich Ziemi"


def collect(now: datetime, api_key: str = "DEMO_KEY", days: int = 7) -> list[dict]:
    start = now.date()
    end = start + timedelta(days=min(days, 7))  # API pozwala na maksymalnie 7 dni
    data = get_json(FEED.format(start=start.isoformat(), end=end.isoformat(), key=api_key))

    events = []
    for day, objects in (data.get("near_earth_objects") or {}).items():
        for obj in objects:
            for approach in obj.get("close_approach_data", []):
                miss_km = float(approach["miss_distance"]["kilometers"])
                lunar = miss_km / MOON_DISTANCE_KM
                est = obj["estimated_diameter"]["meters"]
                dmin, dmax = est["estimated_diameter_min"], est["estimated_diameter_max"]
                hazardous = obj.get("is_potentially_hazardous_asteroid", False)

                # filtrujemy szum: interesuja nas bliskie przeloty albo duze obiekty
                if lunar > 5 and dmax < 300 and not hazardous:
                    continue

                speed = float(approach["relative_velocity"]["kilometers_per_second"])
                when = datetime.strptime(
                    approach["close_approach_date_full"], "%Y-%b-%d %H:%M"
                ).replace(tzinfo=timezone.utc)

                importance = 2
                if lunar < 1:
                    importance = 5
                elif lunar < 3:
                    importance = 4
                elif hazardous and dmax > 300:
                    importance = 3

                events.append(
                    {
                        "uid": f"neo-{obj.get('id')}-{approach.get('close_approach_date')}",
                        "title": f"Bliski przelot planetoidy {obj['name'].strip('()')}",
                        "starts_at": when.isoformat().replace("+00:00", "Z"),
                        "category": "asteroid",
                        "subcategory": "close-approach",
                        "importance": importance,
                        "summary": (
                            f"Planetoida o średnicy szacowanej na {num(dmin, 0)}–{num(dmax, 0)} m minie "
                            f"Ziemię w odległości {num(miss_km / 1e6, 2)} mln km, czyli {num(lunar, 1)} "
                            f"odległości Ziemia–Księżyc, z prędkością {num(speed, 1)} km/s. Dla skali: "
                            f"{_size_note(dmin, dmax)}. "
                            + (
                                "NASA klasyfikuje ją jako „potencjalnie niebezpieczną” – to jednak "
                                "wyłącznie techniczna kategoria dla obiektów większych niż ok. 140 m, "
                                "które zbliżają się do orbity Ziemi. Żaden znany obiekt nie zagraża "
                                "nam w przewidywalnej przyszłości."
                                if hazardous else
                                "Przelot jest całkowicie bezpieczny – takie zbliżenia zdarzają się "
                                "regularnie i są rutynowo śledzone."
                            )
                        ),
                        "tags": ["planetoida", "NEO"] + (["potencjalnie niebezpieczna"] if hazardous else []),
                        "links": [
                            {"label": "Karta obiektu w bazie JPL",
                             "url": obj.get("nasa_jpl_url", "https://cneos.jpl.nasa.gov/ca/")},
                            {"label": "Najbliższe przeloty – CNEOS",
                             "url": "https://cneos.jpl.nasa.gov/ca/"},
                        ],
                        "source": "NASA NeoWs / CNEOS",
                        "source_id": "neows",
                        "extra": {
                            "miss_distance_km": round(miss_km),
                            "lunar_distances": round(lunar, 2),
                            "diameter_m": [round(dmin), round(dmax)],
                            "hazardous": hazardous,
                        },
                    }
                )
    return events
