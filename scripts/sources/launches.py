"""Nadchodzace starty rakiet - The Space Devs / Launch Library 2 (bez klucza API)."""

from __future__ import annotations

from datetime import datetime

from lib.http import FetchError, get_json
from lib.i18n import join, literal, render

#: tryb "list" oszczedza transfer, ale gubi operatora, kosmodrom i opis misji,
#: wiec pobieramy pelne rekordy - jedno zapytanie na dobe zmiesci sie w limitach
ENDPOINTS = (
    "https://ll.thespacedevs.com/2.3.0/launches/upcoming/?limit=30&hide_recent_previous=true",
    "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=30&hide_recent_previous=true",
)

#: slowa kluczowe podbijajace wage startu -> (klucz tagu, waga)
HIGHLIGHTS = {
    "crew": ("tag.crew", 5), "starship": ("tag.new_rocket", 5),
    "artemis": ("tag.moon", 5), "europa": ("tag.probe", 5),
    "james webb": ("tag.telescope", 5), "vulcan": ("tag.new_rocket", 4),
    "new glenn": ("tag.new_rocket", 4), "ariane 6": ("tag.new_rocket", 4),
    "axiom": ("tag.crew", 4), "dragon": ("tag.crew", 4), "soyuz ms": ("tag.crew", 4),
    "starliner": ("tag.crew", 5), "lunar": ("tag.moon", 4), "moon": ("tag.moon", 4),
    "mars": ("tag.mars", 5), "telescope": ("tag.telescope", 4), "rover": ("tag.rover", 5),
}

STATUS_KEYS = {
    "Go": "go", "Go for Launch": "go", "TBD": "tbd", "To Be Determined": "tbd",
    "TBC": "tbc", "To Be Confirmed": "tbc", "Hold": "hold",
    "Success": "success", "Failure": "failure",
}


def _score(name: str, mission_type: str) -> tuple[int, list[dict]]:
    text = f"{name} {mission_type}".lower()
    score, keys = 2, []
    for needle, (tag_key, weight) in HIGHLIGHTS.items():
        if needle in text:
            score = max(score, weight)
            if tag_key not in keys:
                keys.append(tag_key)
    if "starlink" in text:
        score = 1  # rutynowe, kilkadziesiat razy w roku
    return score, [render(k) for k in keys]


def _first(*values):
    for value in values:
        if value:
            return value
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

        lsp = item.get("launch_service_provider")
        provider = _first(lsp.get("name") if isinstance(lsp, dict) else None,
                          lsp if isinstance(lsp, str) else None)
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
        rocket = item.get("rocket") or {}
        rocket_name = (rocket.get("configuration") or {}).get("full_name") \
            if isinstance(rocket, dict) else None

        name = item.get("name") or "Launch"
        score, extra_tags = _score(name, mission_type)

        # opis budujemy ze zdan - kazde w obu jezykach naraz
        if rocket_name and provider:
            parts = [render("launch.sentence.rocket_provider",
                            rocket=literal(rocket_name), provider=literal(provider))]
        elif rocket_name:
            parts = [render("launch.sentence.rocket", rocket=literal(rocket_name))]
        elif provider:
            parts = [render("launch.sentence.provider", provider=literal(provider))]
        else:
            parts = [render("launch.sentence.generic")]

        if location:
            parts.append(render("launch.place", place=literal(location)))
        parts.append(render("launch.status",
                            status=render(f"launch.status.{STATUS_KEYS.get(status_name, 'unknown')}")))
        # opisy misji przychodza z API tylko po angielsku - zostawiamy je bez zmian
        if mission_desc:
            parts.append(render("launch.mission", description=literal(mission_desc.strip())))
        elif mission_type:
            parts.append(render("launch.mission_type", type=literal(mission_type)))
        parts.append(render("launch.note"))

        links = [{"label": render("link.launch_details"),
                  "url": item.get("url", "").replace("ll.thespacedevs.com", "thespacedevs.com")}]
        for key, label_key in (("vid_urls", "link.webcast"), ("info_urls", "link.launch_info")):
            for entry in (item.get(key) or [])[:1]:
                url = entry.get("url") if isinstance(entry, dict) else entry
                if url:
                    links.append({"label": render(label_key), "url": url})
        links.append({"label": render("link.launch_calendar"), "url": "https://spacelaunchnow.me/"})

        tags = [render("tag.launch")] + ([literal(provider)] if provider else []) + extra_tags
        events.append(
            {
                "uid": f"ll2-{item.get('id')}" if item.get("id") else None,
                "title": literal(name),
                "starts_at": net.replace("+00:00", "Z"),
                "category": "launch",
                "subcategory": "rocket",
                "importance": score,
                "summary": join(*parts),
                "tags": tags,
                "location": literal(location) if location else None,
                "links": [l for l in links if l.get("url")],
                "source": render("attribution.launchlibrary"),
                "source_id": "launchlibrary",
                "extra": {"status": status_name},
            }
        )
    return events
