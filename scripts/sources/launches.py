"""Nadchodzace starty rakiet - The Space Devs / Launch Library 2 (bez klucza API)."""

from __future__ import annotations

from datetime import datetime

from lib.http import FetchError, get_json

#: tryb "list" oszczedza transfer, ale gubi operatora, kosmodrom i opis misji,
#: wiec pobieramy pelne rekordy - jedno zapytanie na dobe zmiesci sie w limitach
ENDPOINTS = (
    "https://ll.thespacedevs.com/2.3.0/launches/upcoming/?limit=30&hide_recent_previous=true",
    "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=30&hide_recent_previous=true",
)

#: slowa kluczowe podbijajace wage startu
HIGHLIGHTS = {
    "crew": ("załoga", 5), "starship": ("Starship", 5), "artemis": ("Artemis", 5),
    "europa": ("sonda", 5), "james webb": ("teleskop", 5), "vulcan": ("nowa rakieta", 4),
    "new glenn": ("nowa rakieta", 4), "ariane 6": ("nowa rakieta", 4),
    "axiom": ("załoga", 4), "dragon": ("Dragon", 4), "soyuz ms": ("załoga", 4),
    "starliner": ("załoga", 5), "lunar": ("Księżyc", 4), "moon": ("Księżyc", 4),
    "mars": ("Mars", 5), "telescope": ("teleskop", 4), "rover": ("łazik", 5),
}

STATUS_PL = {
    "Go": "potwierdzony", "TBD": "termin wstępny", "TBC": "termin do potwierdzenia",
    "Hold": "wstrzymany", "Success": "zakończony sukcesem", "Failure": "nieudany",
    "Go for Launch": "potwierdzony", "To Be Determined": "termin wstępny",
    "To Be Confirmed": "termin do potwierdzenia",
}


def _score(name: str, mission_type: str) -> tuple[int, list[str]]:
    text = f"{name} {mission_type}".lower()
    score, tags = 2, []
    for key, (tag, weight) in HIGHLIGHTS.items():
        if key in text:
            score = max(score, weight)
            if tag not in tags:
                tags.append(tag)
    if "starlink" in text:
        score = 1  # rutynowe, kilkadziesiat razy w roku
    return score, tags


def _first(*values):
    for v in values:
        if v:
            return v
    return None


def collect(now: datetime, limit: int = 25) -> list[dict]:
    data = None
    errors = []
    for url in ENDPOINTS:
        try:
            data = get_json(url)
            break
        except FetchError as exc:
            errors.append(str(exc))
    if data is None:
        raise FetchError("; ".join(errors))

    events = []
    for item in (data.get("results") or [])[:limit]:
        net = item.get("net") or item.get("window_start")
        if not net:
            continue
        name = item.get("name") or "Start rakiety"
        lsp = item.get("launch_service_provider")
        provider = _first(
            lsp.get("name") if isinstance(lsp, dict) else None,
            lsp if isinstance(lsp, str) else None,
        )
        pad = item.get("pad") or {}
        location = _first(
            (pad.get("location") or {}).get("name") if isinstance(pad, dict) else None,
            pad.get("name") if isinstance(pad, dict) else None,
            item.get("pad_location"),
        )
        mission = item.get("mission") or {}
        mission_desc = mission.get("description") if isinstance(mission, dict) else None
        mission_type = (mission.get("type") if isinstance(mission, dict) else None) or ""
        status = item.get("status") or {}
        status_name = status.get("name") if isinstance(status, dict) else str(status)
        status_pl = STATUS_PL.get(status_name, status_name or "nieznany")

        score, tags = _score(name, mission_type)
        rocket = item.get("rocket") or {}
        rocket_name = (rocket.get("configuration") or {}).get("full_name") if isinstance(rocket, dict) else None

        rocket_txt = f"rakiety {rocket_name}" if rocket_name else "rakiety"
        parts = [
            f"Start {rocket_txt} – {provider}." if provider else f"Start {rocket_txt}."
        ]
        if location:
            parts.append(f"Miejsce: {location}.")
        parts.append(f"Status terminu: {status_pl}.")
        if mission_desc:
            parts.append(f"Misja: {mission_desc.strip()}")
        elif mission_type:
            parts.append(f"Typ misji: {mission_type}.")
        parts.append(
            "Terminy startów zmieniają się często – przed obserwacją transmisji warto "
            "sprawdzić aktualny status."
        )

        links = [{"label": "Szczegóły misji", "url": item.get("url", "").replace("ll.thespacedevs.com", "thespacedevs.com")}]
        for key, label in (("vid_urls", "Transmisja na żywo"), ("info_urls", "Informacje")):
            for u in (item.get(key) or [])[:1]:
                url = u.get("url") if isinstance(u, dict) else u
                if url:
                    links.append({"label": label, "url": url})
        links.append({"label": "Kalendarz startów – Space Launch Now", "url": "https://spacelaunchnow.me/"})
        links = [l for l in links if l.get("url")]

        tags = ["start rakiety"] + ([provider] if provider else []) + tags
        events.append(
            {
                "uid": f"ll2-{item.get('id')}" if item.get("id") else None,
                "title": name,
                "starts_at": net.replace("+00:00", "Z"),
                "category": "launch",
                "subcategory": "rocket",
                "importance": score,
                "summary": " ".join(parts),
                "tags": tags,
                "location": location,
                "links": links,
                "source": "The Space Devs (Launch Library 2)",
                "source_id": "launchlibrary",
                "extra": {"status": status_pl},
            }
        )
    return events
