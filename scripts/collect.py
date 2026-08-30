#!/usr/bin/env python3
"""AstroAlert - zbieranie wydarzen kosmicznych i budowa danych dla portalu.

Uruchamiany raz dziennie przez GitHub Actions. Kazde zrodlo jest odpytywane
niezaleznie: jesli ktores padnie (limit API, awaria, brak sieci), portal
zbuduje sie z pozostalych, a wpisy z niedostepnego zrodla zostana zachowane
z poprzedniego przebiegu.

Uzycie:
    python scripts/collect.py                 # pelny przebieg
    python scripts/collect.py --offline       # tylko obliczenia astronomiczne
    python scripts/collect.py --days 400      # horyzont czasowy
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from sources import apod, launches, neo, sky, spaceweather  # noqa: E402

DATA = ROOT / "data"
EVENTS_FILE = DATA / "events.json"
ARCHIVE_DIR = DATA / "archive"
CUSTOM_FILE = DATA / "custom_events.json"
FEED_FILE = ROOT / "feed.xml"

SITE_URL = os.environ.get("SITE_URL", "https://claudeplos.github.io/AstroAlert")
SITE_TITLE = "AstroAlert – co ciekawego dzieje się w kosmosie"

#: jak dlugo trzymamy minione wydarzenia w glownym pliku
KEEP_PAST_DAYS = 60

#: o ile musi przesunac sie termin, zeby uznac to za realna zmiane, a nie szum
RESCHEDULE_THRESHOLD = timedelta(minutes=10)

CATEGORY_LABELS = {
    "sky": "Niebo nad nami",
    "launch": "Starty rakiet",
    "spaceweather": "Pogoda kosmiczna",
    "asteroid": "Planetoidy",
    "mission": "Misje kosmiczne",
}


# --- narzedzia --------------------------------------------------------------


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


#: jedyne polskie litery bez rozkladu NFKD - trzeba je zamienic recznie
_TRANSLIT = str.maketrans({"ł": "l", "Ł": "L"})


def slugify(text: str) -> str:
    """Zamienia tytul na czesc identyfikatora w URL-u."""
    text = unicodedata.normalize("NFKD", text.translate(_TRANSLIT))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:60] or "wydarzenie"


def event_id(ev: dict) -> str:
    if ev.get("uid"):
        return slugify(ev["uid"])
    day = (ev.get("starts_at") or "")[:10]
    base = f"{ev.get('source_id', 'x')}|{ev.get('title', '')}|{day}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"{slugify(ev.get('title', ''))}-{day}-{digest}"


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[uwaga] nie udało się wczytać {path.name}: {exc}", file=sys.stderr)
        return default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
        encoding="utf-8",
    )


# --- zbieranie --------------------------------------------------------------


def gather(now: datetime, days: int, offline: bool, nasa_key: str) -> tuple[list[dict], list[dict], dict | None]:
    """Zwraca (wydarzenia, raport ze zrodel, APOD)."""
    report: list[dict] = []
    events: list[dict] = []

    def run(source_id: str, name: str, fn):
        if offline and source_id != "sky":
            report.append({"id": source_id, "name": name, "status": "skipped",
                           "count": 0, "error": "tryb offline"})
            return
        try:
            got = fn() or []
            events.extend(got)
            report.append({"id": source_id, "name": name, "status": "ok", "count": len(got)})
            print(f"  [ok]   {name}: {len(got)} wpisów")
        except Exception as exc:  # zrodlo nie moze wywrocic calego przebiegu
            report.append({"id": source_id, "name": name, "status": "error",
                           "count": 0, "error": f"{type(exc).__name__}: {exc}"[:300]})
            print(f"  [błąd] {name}: {exc}", file=sys.stderr)

    print("Zbieranie danych…")
    run("sky", "Obliczenia astronomiczne", lambda: sky.collect(now, days_ahead=days))
    run("launchlibrary", "Starty rakiet (The Space Devs)", lambda: launches.collect(now))
    run("swpc", "Pogoda kosmiczna (NOAA SWPC)", lambda: spaceweather.collect(now))
    run("neows", "Planetoidy (NASA NeoWs)", lambda: neo.collect(now, api_key=nasa_key))

    picture = None
    if not offline:
        try:
            picture = apod.collect(nasa_key)
            print("  [ok]   Zdjęcie dnia NASA APOD")
        except Exception as exc:
            print(f"  [błąd] APOD: {exc}", file=sys.stderr)

    custom = load_json(CUSTOM_FILE, [])
    for ev in custom:
        ev.setdefault("source", "wpis redakcyjny")
        ev.setdefault("source_id", "custom")
        ev.setdefault("category", "mission")
        ev.setdefault("importance", 3)
    if custom:
        events.extend(custom)
        report.append({"id": "custom", "name": "Wpisy własne", "status": "ok", "count": len(custom)})

    return events, report, picture


def normalize(ev: dict, today: str) -> dict | None:
    starts = parse_dt(ev.get("starts_at"))
    if not starts:
        return None
    out = {
        "id": event_id(ev),
        "title": (ev.get("title") or "Wydarzenie").strip(),
        "starts_at": starts.isoformat().replace("+00:00", "Z"),
        "category": ev.get("category", "sky"),
        "subcategory": ev.get("subcategory"),
        "importance": max(1, min(5, int(ev.get("importance", 3)))),
        "summary": (ev.get("summary") or "").strip(),
        "tags": [t for t in (ev.get("tags") or []) if t][:6],
        "links": [l for l in (ev.get("links") or []) if l.get("url")][:5],
        "location": ev.get("location"),
        "source": ev.get("source", "AstroAlert"),
        "source_id": ev.get("source_id", "sky"),
        "added_on": ev.get("added_on") or today,
        "extra": ev.get("extra") or {},
    }
    if ev.get("ephemeral"):
        out["ephemeral"] = True
    return out


def is_rescheduled(old: dict, new: dict) -> bool:
    """Czy termin wydarzenia realnie sie przesunal?

    Dotyczy wydarzen z zewnetrznych zrodel - przede wszystkim startow rakiet,
    ktore przekladane sa niemal codziennie. Zjawisk liczonych z efemeryd nikt
    nie przeklada, wiec ewentualna roznica jest tam tylko szumem numerycznym.
    """
    if new.get("source_id") == "sky":
        return False
    before, after = parse_dt(old.get("starts_at", "")), parse_dt(new["starts_at"])
    if not before or not after:
        return False
    return abs(after - before) >= RESCHEDULE_THRESHOLD


def merge(previous: list[dict], fresh: list[dict], report: list[dict], today: str) -> list[dict]:
    """Laczy nowe dane ze starymi, zachowujac date dodania wpisu.

    Wpisy ze zrodel, ktore w tym przebiegu padly, zostaja z poprzedniej wersji -
    dzieki temu chwilowa awaria API nie kasuje polowy portalu.
    """
    failed = {r["id"] for r in report if r["status"] in ("error", "skipped")}
    old_by_id = {e["id"]: e for e in previous if e.get("id")}

    merged: dict[str, dict] = {}
    for ev in previous:
        if not ev.get("id"):
            continue
        if ev.get("source_id") in failed and not ev.get("ephemeral"):
            merged[ev["id"]] = ev  # ratujemy dane z niedostepnego zrodla

    for raw in fresh:
        ev = normalize(raw, today)
        if not ev:
            continue
        old = old_by_id.get(ev["id"])
        if old:
            ev["added_on"] = old.get("added_on", ev["added_on"])
            if is_rescheduled(old, ev):
                ev["rescheduled_from"] = old["starts_at"]
                ev["updated_on"] = today
        merged[ev["id"]] = ev

    return sorted(merged.values(), key=lambda e: e["starts_at"])


def prune(events: list[dict], now: datetime) -> tuple[list[dict], list[dict]]:
    """Dzieli wydarzenia na aktualne i te do archiwum."""
    cutoff = now - timedelta(days=KEEP_PAST_DAYS)
    keep, archived = [], []
    for ev in events:
        start = parse_dt(ev["starts_at"])
        if start and start < cutoff:
            if not ev.get("ephemeral"):
                archived.append(ev)
        else:
            keep.append(ev)
    return keep, archived


def update_archive(archived: list[dict]) -> None:
    by_year: dict[str, list[dict]] = {}
    for ev in archived:
        by_year.setdefault(ev["starts_at"][:4], []).append(ev)
    for year, items in by_year.items():
        path = ARCHIVE_DIR / f"{year}.json"
        existing = {e["id"]: e for e in load_json(path, [])}
        for ev in items:
            existing[ev["id"]] = ev
        write_json(path, sorted(existing.values(), key=lambda e: e["starts_at"]))
        print(f"  archiwum {year}: {len(existing)} wpisów")


# --- kanal RSS --------------------------------------------------------------


def escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_feed(events: list[dict], generated: datetime) -> str:
    recent = sorted(events, key=lambda e: (e.get("added_on", ""), e["starts_at"]), reverse=True)[:40]
    items = []
    for ev in recent:
        start = parse_dt(ev["starts_at"])
        when = start.strftime("%d.%m.%Y, %H:%M UTC") if start else ""
        links = "".join(
            f'<p><a href="{escape(l["url"])}">{escape(l["label"])}</a></p>' for l in ev.get("links", [])
        )
        body = f"<p><strong>{escape(when)}</strong></p><p>{escape(ev['summary'])}</p>{links}"
        pub = parse_dt(ev.get("added_on", "") + "T09:00:00Z") or generated
        items.append(
            "  <item>\n"
            f"    <title>{escape(ev['title'])}</title>\n"
            f"    <link>{SITE_URL}/#{escape(ev['id'])}</link>\n"
            f"    <guid isPermaLink=\"false\">{escape(ev['id'])}</guid>\n"
            f"    <pubDate>{pub.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>\n"
            f"    <category>{escape(CATEGORY_LABELS.get(ev['category'], ev['category']))}</category>\n"
            f"    <description>{escape(body)}</description>\n"
            "  </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>\n'
        f"  <title>{escape(SITE_TITLE)}</title>\n"
        f"  <link>{SITE_URL}</link>\n"
        "  <description>Codziennie aktualizowany przegląd wydarzeń astronomicznych "
        "i kosmicznych: zaćmienia, koniunkcje, roje meteorów, starty rakiet, zorze polarne "
        "i bliskie przeloty planetoid.</description>\n"
        "  <language>pl-PL</language>\n"
        f"  <lastBuildDate>{generated.strftime('%a, %d %b %Y %H:%M:%S +0000')}</lastBuildDate>\n"
        + "\n".join(items)
        + "\n</channel></rss>\n"
    )


# --- main -------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Zbiera wydarzenia kosmiczne dla portalu AstroAlert.")
    ap.add_argument("--days", type=int, default=400, help="horyzont w dniach (domyślnie 400)")
    ap.add_argument("--offline", action="store_true", help="tylko obliczenia astronomiczne")
    ap.add_argument("--dry-run", action="store_true", help="nie zapisuj plików")
    args = ap.parse_args()

    now = now_utc()
    today = now.date().isoformat()
    nasa_key = os.environ.get("NASA_API_KEY", "DEMO_KEY").strip() or "DEMO_KEY"

    fresh, report, picture = gather(now, args.days, args.offline, nasa_key)

    prev_doc = load_json(EVENTS_FILE, {})
    previous = prev_doc.get("events", []) if isinstance(prev_doc, dict) else []

    events = merge(previous, fresh, report, today)
    events, archived = prune(events, now)

    if picture is None and isinstance(prev_doc, dict):
        picture = prev_doc.get("apod")

    upcoming = [e for e in events if (parse_dt(e["starts_at"]) or now) >= now]
    doc = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "site": {"title": SITE_TITLE, "url": SITE_URL},
        "sources": report,
        "apod": picture,
        "stats": {
            "total": len(events),
            "upcoming": len(upcoming),
            "new_today": sum(1 for e in events if e.get("added_on") == today),
            "by_category": {
                key: sum(1 for e in upcoming if e["category"] == key) for key in CATEGORY_LABELS
            },
        },
        "categories": CATEGORY_LABELS,
        "events": events,
    }

    print(
        f"\nRazem: {len(events)} wydarzeń ({len(upcoming)} nadchodzących, "
        f"{doc['stats']['new_today']} dodanych dzisiaj), {len(archived)} do archiwum."
    )

    if args.dry_run:
        print("[dry-run] nic nie zapisano")
        return 0

    write_json(EVENTS_FILE, doc)
    update_archive(archived)
    FEED_FILE.write_text(build_feed(events, now), encoding="utf-8")
    print(f"Zapisano {EVENTS_FILE.relative_to(ROOT)} i {FEED_FILE.relative_to(ROOT)}")

    if all(r["status"] != "ok" for r in report):
        print("Żadne źródło nie odpowiedziało!", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
