"""Bliskie przeloty planetoid - NASA NeoWs (dziala z DEMO_KEY, lepiej z wlasnym kluczem)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lib.http import get_json
from lib.i18n import literal, render
from lib.text import fmt

FEED = "https://api.nasa.gov/neo/rest/v1/feed?start_date={start}&end_date={end}&api_key={key}"
MOON_DISTANCE_KM = 384_400.0

#: przelot uznajemy za "bliski" ponizej tylu odleglosci Ziemia-Ksiezyc
CLOSE_LD = 5.0
#: ile najciekawszych dalszych przelotow pokazac poza tymi naprawde bliskimi
MAX_RANKED = 5
#: ponizej tej srednicy dalszy przelot nie jest juz ciekawy
MIN_DIAMETER_M = 150.0


def _clean_name(name: str) -> str:
    """Katalogowe nazwy bywaja w nawiasach: "(2012 DF61)" -> "2012 DF61"."""
    name = (name or "").strip()
    if name.startswith("(") and name.endswith(")"):
        name = name[1:-1].strip()
    return name


def _size_note(dmin: float, dmax: float) -> dict:
    """Porownanie rozmiaru do czegos wyobrazalnego."""
    avg = (dmin + dmax) / 2.0
    if avg < 20:
        key = "neo.size.tiny"
    elif avg < 60:
        key = "neo.size.tunguska"
    elif avg < 150:
        key = "neo.size.building"
    elif avg < 500:
        key = "neo.size.hill"
    else:
        key = "neo.size.major"
    return render(key)


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

                if lunar > CLOSE_LD and dmax < MIN_DIAMETER_M:
                    continue  # mala skala daleko od Ziemi to nie jest wydarzenie

                speed = float(approach["relative_velocity"]["kilometers_per_second"])
                when = datetime.strptime(
                    approach["close_approach_date_full"], "%Y-%b-%d %H:%M"
                ).replace(tzinfo=timezone.utc)

                close = lunar <= CLOSE_LD
                if lunar < 1:
                    importance = 5
                elif lunar < 3:
                    importance = 4
                elif close or dmax >= 500:
                    importance = 3
                else:
                    importance = 2

                events.append(
                    {
                        "uid": f"neo-{obj.get('id')}-{approach.get('close_approach_date')}",
                        "title": render("neo.title.close" if close else "neo.title.far",
                                        name=literal(_clean_name(obj.get("name")))),
                        "starts_at": when.isoformat().replace("+00:00", "Z"),
                        "category": "asteroid",
                        "subcategory": "close-approach",
                        "importance": importance,
                        "summary": render(
                            "neo.summary", dmin=fmt(dmin, 0), dmax=fmt(dmax, 0),
                            mln=fmt(miss_km / 1e6, 2), ld=fmt(lunar, 1), speed=fmt(speed, 1),
                            size=_size_note(dmin, dmax),
                            context=render("neo.context.close" if close else "neo.context.far"),
                            hazard=render("neo.hazard.yes" if hazardous else "neo.hazard.no"),
                        ),
                        "tags": [render("tag.asteroid"), render("tag.neo")]
                                + ([render("tag.pha")] if hazardous else []),
                        "links": [
                            {"label": render("link.jpl"),
                             "url": obj.get("nasa_jpl_url", "https://cneos.jpl.nasa.gov/ca/")},
                            {"label": render("link.cneos"), "url": "https://cneos.jpl.nasa.gov/ca/"},
                        ],
                        "source": render("attribution.neows"),
                        "source_id": "neows",
                        "extra": {
                            "miss_distance_km": round(miss_km),
                            "lunar_distances": round(lunar, 2),
                            "diameter_m": [round(dmin), round(dmax)],
                            "hazardous": hazardous,
                        },
                    }
                )
    return _select(events)


def _select(events: list[dict]) -> list[dict]:
    """Zostawia przeloty naprawde bliskie oraz kilka najciekawszych dalszych.

    W typowym tygodniu katalog nie zawiera zadnego zblizenia ponizej pieciu
    odleglosci ksiezycowych, za to kilkanascie duzych obiektow mija Ziemie
    kilkadziesiat razy dalej. Sztywny prog dawalby wiec albo pusta kategorie,
    albo kilkanascie prawie identycznych wpisow - dlatego dalsze przeloty
    porzadkujemy wedlug tego, jak duzy jest obiekt w stosunku do dystansu.
    """
    close = [e for e in events if e["extra"]["lunar_distances"] <= CLOSE_LD]
    far = [e for e in events if e["extra"]["lunar_distances"] > CLOSE_LD]
    far.sort(key=lambda e: e["extra"]["diameter_m"][1] / max(e["extra"]["lunar_distances"], 1.0),
             reverse=True)
    return sorted(close + far[:MAX_RANKED], key=lambda e: e["starts_at"])
