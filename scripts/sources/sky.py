"""Zjawiska na niebie liczone lokalnie - bez internetu i bez kluczy API.

Wyznaczamy: fazy Ksiezyca (z superpelniami), koniunkcje planet i Ksiezyca,
maksymalne elongacje Merkurego i Wenus, opozycje planet zewnetrznych,
rownonoce i przesilenia, peryhelium/aphelium Ziemi, roje meteorow (dane
statyczne) oraz zacmienia (dane statyczne, redagowane recznie).

Kazdy opis powstaje od razu we wszystkich jezykach portalu - teksty siedza
w katalogu komunikatow (data/locales/), a tutaj zostaje sama astronomia.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ephem
from ephem import day_number, from_day_number, rev180
from lib.i18n import LANGS, join, literal, render
from lib.text import fmt, upper_first

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "static"

#: (kat fazy, klucz tytulu, klucz nazwy fazy, waga)
PHASES = (
    (0.0, "moon.title.new", "moon.phase.new", 2),
    (90.0, "moon.title.first_quarter", "moon.phase.first_quarter", 1),
    (180.0, "moon.title.full", "moon.phase.full", 2),
    (270.0, "moon.title.last_quarter", "moon.phase.last_quarter", 1),
)

#: maksymalna interesujaca separacja przy koniunkcjach
PLANET_PAIRS_MAX_SEP = 4.0
MOON_PAIR_MAX_SEP = 3.0
#: ponizej tej elongacji zjawisko tonie w blasku Slonca
MIN_ELONGATION = 12.0

SUPERMOON_KM = 360_000
MICROMOON_KM = 405_000


# --- pomocnicze ------------------------------------------------------------


def _iso(d: float) -> str:
    """Znacznik czasu zaokraglony do pelnej minuty.

    Metody numeryczne trafiaja w moment zjawiska z dokladnoscia do sekund,
    a siatka probkowania zalezy od chwili uruchomienia skryptu. Bez
    zaokraglenia ten sam nów dostawalby codziennie inna sekunde i wygladal
    jak wydarzenie o zmienionym terminie.
    """
    exact = from_day_number(d)
    t = exact.replace(second=0, microsecond=0)
    if exact.second >= 30:
        t += timedelta(minutes=1)
    return t.isoformat().replace("+00:00", "Z")


def _name(body: str) -> dict:
    return render(f"planet.{body.lower()}")


def _gen(body: str) -> dict:
    """Nazwa w formie wymaganej przez zdanie (w polskim - dopelniacz)."""
    return render(f"planet.{body.lower()}.gen")


def _blurb(body: str) -> dict:
    return render(f"planet.{body.lower()}.blurb")


def _zodiac(lon: float) -> dict:
    return render(f"zodiac.{ephem.zodiac_index(lon)}")


def _cap(text: dict) -> dict:
    """Wielka litera na poczatku w kazdej wersji jezykowej."""
    return {lang: upper_first(value) for lang, value in text.items()}


def _link(label_key: str, url) -> dict:
    return {"label": render(label_key), "url": url}


def _sky_links(*extra: dict) -> list[dict]:
    return list(extra) + [
        _link("link.stellarium", "https://stellarium-web.org/"),
        _link("link.inthesky", "https://in-the-sky.org/newscal.php"),
    ]


def _separation_text(sep_deg: float) -> dict:
    """Separacja w stopniach albo minutach luku, zaleznie od wielkosci."""
    if sep_deg >= 1:
        return {lang: f"{value}°" for lang, value in fmt(sep_deg, 1).items()}
    return {lang: f"{value}′" for lang, value in fmt(sep_deg * 60, 0).items()}


def _evening(body_lon: float, d: float) -> bool:
    """Czy cialo widac wieczorem (na wschod od Slonca)?"""
    return rev180(body_lon - ephem.sun(d)["lon"]) > 0


# --- fazy Ksiezyca ----------------------------------------------------------


def moon_phases(d0: float, d1: float) -> list[dict]:
    events = []
    step = 0.5
    d = d0
    while d < d1:
        nxt = d + step
        for target, title_key, phase_key, importance in PHASES:
            def f(x, angle=target):
                return rev180(ephem.moon_phase_angle(x) - angle)

            if f(d) < 0 <= f(nxt) and abs(f(nxt) - f(d)) < 90:
                events.append(_phase_event(ephem.find_root(f, d, nxt), target,
                                           title_key, phase_key, importance))
        d = nxt
    return events


def _phase_event(t: float, target: float, title_key: str, phase_key: str,
                 importance: int) -> dict:
    m = ephem.moon(t)
    dist = m["dist_km"]
    extra_tag = None
    if target == 180.0 and dist < SUPERMOON_KM:
        title_key, importance, extra_tag = "moon.title.supermoon", 3, "moon.tag.supermoon"
    elif target == 180.0 and dist > MICROMOON_KM:
        title_key, extra_tag = "moon.title.micromoon", "moon.tag.micromoon"

    tags = [render("planet.moon"), render(title_key)]
    if extra_tag:
        tags.append(render(extra_tag))

    summary = render("moon.summary", phase=render(phase_key),
                     zodiac=_zodiac(m["lon"]), dist=fmt(dist, 0))
    if title_key == "moon.title.supermoon":
        summary = join(summary, render("moon.summary.supermoon"))
    elif target == 0.0:
        summary = join(summary, render("moon.summary.new"))

    return {
        "title": render(title_key),
        "starts_at": _iso(t),
        "category": "sky",
        "subcategory": "moon",
        "importance": importance,
        "summary": summary,
        "tags": tags,
        "links": _sky_links(_link("link.moonphases",
                                  "https://www.timeanddate.com/moon/phases/")),
    }


# --- koniunkcje -------------------------------------------------------------


def _pair_events(a: str, b: str, d0: float, d1: float, max_sep: float,
                 step: float) -> list[dict]:
    events = []

    def sep(x):
        return ephem.separation(ephem.body(a, x), ephem.body(b, x))

    d = d0
    s_prev, s_cur = sep(d), sep(d + step)
    while d + 2 * step < d1:
        s_next = sep(d + 2 * step)
        if s_cur < s_prev and s_cur < s_next:
            t, value = ephem.find_extremum(lambda x: -sep(x), d, d + 2 * step, tol=1e-4)
            value = -value
            if value <= max_sep and ephem.elongation(a, t) >= MIN_ELONGATION:
                events.append(_conjunction_event(a, b, t, value))
        d += step
        s_prev, s_cur = s_cur, s_next
    return events


def _conjunction_event(a: str, b: str, t: float, sep_deg: float) -> dict:
    pa, pb = ephem.body(a, t), ephem.body(b, t)
    visibility = render("visibility.evening" if _evening(pa["lon"], t)
                        else "visibility.morning")
    sep_text = _separation_text(sep_deg)

    if a == "Moon":
        return {
            "title": render("conj.moon.title", body=_gen(b)),
            "starts_at": _iso(t),
            "category": "sky",
            "subcategory": "conjunction",
            "importance": 2,
            "summary": render("conj.moon.summary", sep=sep_text, body=_gen(b),
                              visibility=visibility, zodiac=_zodiac(pb["lon"]),
                              blurb=_cap(_blurb(b))),
            "tags": [_name(a), _name(b), render("tag.conjunction")],
            "links": _sky_links(),
            "extra": {"separation_deg": round(sep_deg, 2), "bodies": [a, b]},
        }

    return {
        "title": render("conj.planets.title", a=_gen(a), b=_gen(b)),
        "starts_at": _iso(t),
        "category": "sky",
        "subcategory": "conjunction",
        "importance": 4 if sep_deg < 1.0 else 3,
        "summary": render("conj.planets.summary", sep=sep_text, visibility=visibility,
                          zodiac=_zodiac(pa["lon"]),
                          elong=fmt(ephem.elongation(a, t), 0)),
        "tags": [_name(a), _name(b), render("tag.conjunction")],
        "links": _sky_links(),
        "extra": {"separation_deg": round(sep_deg, 2), "bodies": [a, b]},
    }


def conjunctions(d0: float, d1: float) -> list[dict]:
    events = []
    naked = list(ephem.NAKED_EYE)
    for i, a in enumerate(naked):
        for b in naked[i + 1:]:
            events += _pair_events(a, b, d0, d1, PLANET_PAIRS_MAX_SEP, 1.0)
    for b in ("Venus", "Mars", "Jupiter", "Saturn"):
        events += _pair_events("Moon", b, d0, d1, MOON_PAIR_MAX_SEP, 0.25)
    return events


# --- elongacje i opozycje ---------------------------------------------------


def elongations(d0: float, d1: float) -> list[dict]:
    events = []
    for name in ("Mercury", "Venus"):
        step = 2.0
        d = d0
        e_prev, e_cur = ephem.elongation(name, d), ephem.elongation(name, d + step)
        while d + 2 * step < d1:
            e_next = ephem.elongation(name, d + 2 * step)
            if e_cur > e_prev and e_cur > e_next:
                t, value = ephem.find_extremum(
                    lambda x: ephem.elongation(name, x), d, d + 2 * step, tol=1e-4)
                evening = _evening(ephem.body(name, t)["lon"], t)
                events.append(
                    {
                        "title": render("elongation.title", body=_gen(name),
                                        direction=render("elongation.east" if evening
                                                         else "elongation.west"),
                                        value=fmt(value, 0)),
                        "starts_at": _iso(t),
                        "category": "sky",
                        "subcategory": "elongation",
                        "importance": 4 if name == "Mercury" else 3,
                        "summary": render(
                            "elongation.summary", body=_name(name), value=fmt(value, 0),
                            when=render("elongation.when.evening" if evening
                                        else "elongation.when.morning"),
                            blurb=_cap(_blurb(name)),
                            horizon=render("horizon.west" if evening else "horizon.east"),
                        ),
                        "tags": [_name(name), render("tag.elongation")],
                        "links": _sky_links(),
                        "extra": {"elongation_deg": round(value, 1), "body": name},
                    }
                )
            d += step
            e_prev, e_cur = e_cur, e_next
    return events


def oppositions(d0: float, d1: float) -> list[dict]:
    """Opozycje planet zewnetrznych.

    Opozycja to moment, w ktorym dlugosc ekliptyczna planety rozni sie od
    dlugosci Slonca dokladnie o 180 stopni (elongacja bywa nieco mniejsza,
    bo planeta ma wlasna szerokosc ekliptyczna).
    """
    events = []
    for name in ("Mars", "Jupiter", "Saturn", "Uranus", "Neptune"):
        def diff(x, n=name):
            return rev180(ephem.body(n, x)["lon"] - ephem.sun(x)["lon"] - 180.0)

        step = 2.0
        d = d0
        while d + step < d1:
            a, b = diff(d), diff(d + step)
            # Slonce porusza sie szybciej niz planeta zewnetrzna, wiec roznica
            # maleje - przejscie przez zero lapiemy w obie strony
            if (a < 0) != (b < 0) and abs(b - a) < 90:
                t = ephem.find_root(diff, d, d + step)
                p = ephem.body(name, t)
                dist_km = p["dist_au"] * ephem.AU_KM
                events.append(
                    {
                        "title": render("opposition.title", body=_gen(name)),
                        "starts_at": _iso(t),
                        "category": "sky",
                        "subcategory": "opposition",
                        "importance": 5 if name in ("Mars", "Jupiter", "Saturn") else 3,
                        "summary": render(
                            "opposition.summary", body=_name(name),
                            au=fmt(p["dist_au"], 2), mln=fmt(dist_km / 1e6, 0),
                            minutes=fmt(dist_km / 17_987_547.48, 0),
                            zodiac=_zodiac(p["lon"]), blurb=_cap(_blurb(name)),
                        ),
                        "tags": [_name(name), render("tag.opposition")],
                        "links": _sky_links(),
                        "extra": {"distance_au": round(p["dist_au"], 3), "body": name},
                    }
                )
            d += step
    return events


# --- Slonce: rownonoce, przesilenia, peryhelium ------------------------------

SEASONS = (
    (0.0, "season.march"), (90.0, "season.june"),
    (180.0, "season.september"), (270.0, "season.december"),
)


def seasons(d0: float, d1: float) -> list[dict]:
    events = []
    d = d0
    while d < d1:
        nxt = min(d + 1.0, d1)
        for target, key in SEASONS:
            def f(x, angle=target):
                return rev180(ephem.sun(x)["lon"] - angle)

            if f(d) < 0 <= f(nxt) and abs(f(nxt) - f(d)) < 90:
                events.append(
                    {
                        "title": render(f"{key}.title"),
                        "starts_at": _iso(ephem.find_root(f, d, nxt)),
                        "category": "sky",
                        "subcategory": "season",
                        "importance": 3,
                        "summary": render(f"{key}.summary"),
                        "tags": [render("tag.sun"), render("tag.seasons")],
                        "links": _sky_links(),
                    }
                )
        d = nxt
    return events


def apsides(d0: float, d1: float) -> list[dict]:
    """Peryhelium i aphelium Ziemi."""
    events = []
    step = 5.0
    d = d0
    r_prev, r_cur = ephem.sun(d)["dist_au"], ephem.sun(d + step)["dist_au"]
    while d + 2 * step < d1:
        r_next = ephem.sun(d + 2 * step)["dist_au"]
        for is_max, key in ((True, "apsis.aphelion"), (False, "apsis.perihelion")):
            hit = (r_cur > r_prev and r_cur > r_next) if is_max \
                else (r_cur < r_prev and r_cur < r_next)
            if hit:
                sign = 1 if is_max else -1
                t, value = ephem.find_extremum(
                    lambda x: sign * ephem.sun(x)["dist_au"], d, d + 2 * step, tol=1e-4)
                value *= sign
                events.append(
                    {
                        "title": render(f"{key}.title"),
                        "starts_at": _iso(t),
                        "category": "sky",
                        "subcategory": "season",
                        "importance": 2,
                        "summary": render(f"{key}.summary",
                                          mln=fmt(value * ephem.AU_KM / 1e6, 1)),
                        "tags": [render("tag.earth"), render("tag.sun")],
                        "links": _sky_links(),
                    }
                )
        d += step
        r_prev, r_cur = r_cur, r_next
    return events


# --- dane statyczne: roje meteorow i zacmienia ------------------------------


def _load(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _moon_note(illum: float) -> dict:
    if illum < 0.25:
        return render("meteor.moon.excellent")
    key = "meteor.moon.some" if illum < 0.6 else "meteor.moon.bad"
    return render(key, illum=fmt(illum * 100, 0))


def meteor_showers(d0: float, d1: float) -> list[dict]:
    events = []
    start_year = from_day_number(d0).year
    for year in (start_year, start_year + 1, start_year + 2):
        for sh in _load("meteor_showers.json"):
            try:
                peak = datetime(year, sh["peak_month"], sh["peak_day"], 2, 0,
                                tzinfo=timezone.utc)
            except ValueError:
                continue
            t = day_number(peak)
            if not (d0 <= t <= d1):
                continue
            illum = ephem.moon_illumination(t)
            events.append(
                {
                    "title": render("meteor.title", name=sh["name"]),
                    "starts_at": peak.isoformat().replace("+00:00", "Z"),
                    "category": "sky",
                    "subcategory": "meteors",
                    "importance": 5 if sh["zhr"] >= 80 else (4 if sh["zhr"] >= 20 else 3),
                    "summary": render("meteor.summary", description=sh["description"],
                                      zhr=sh["zhr"], radiant=sh["radiant"],
                                      moon=_moon_note(illum)),
                    "tags": [render("tag.meteors"), sh["name"]],
                    "links": _sky_links(
                        _link("link.imo", "https://www.imo.net/resources/calendar/"),
                        _link("link.shower_info", sh.get("url")),
                    ),
                    "extra": {"zhr": sh["zhr"], "moon_illumination": round(illum, 2),
                              "radiant_ra": sh.get("radiant_ra"),
                              "radiant_dec": sh.get("radiant_dec")},
                }
            )
    return events


def eclipses(d0: float, d1: float) -> list[dict]:
    events = []
    for ec in _load("eclipses.json"):
        when = datetime.fromisoformat(ec["utc"].replace("Z", "+00:00"))
        if not (d0 <= day_number(when) <= d1):
            continue
        solar = ec["kind"].startswith("s")
        summary = ec["description"]
        if solar:
            summary = join(summary, render("eclipse.solar_warning"))
        extra_link = [_link("link.eclipse_details", ec["url"])] if ec.get("url") else []
        events.append(
            {
                "title": ec["title"],
                "starts_at": ec["utc"],
                "category": "sky",
                "subcategory": "eclipse",
                "importance": ec.get("importance", 5),
                "summary": summary,
                "tags": [render("tag.eclipse"),
                         render("tag.sun") if solar else render("planet.moon")],
                "links": _sky_links(
                    _link("link.nasa_eclipse", "https://eclipse.gsfc.nasa.gov/eclipse.html"),
                    *extra_link,
                ),
                "location": ec.get("visibility"),
                "extra": {"poland": bool(ec.get("poland"))},
            }
        )
    return events


# --- wejscie ----------------------------------------------------------------


def collect(now: datetime, days_ahead: int = 400, days_back: int = 3) -> list[dict]:
    # siatke probkowania kotwiczymy w pelnej dobie, zeby kolejne przebiegi
    # tego samego dnia dawaly identyczne wyniki
    d0 = math.floor(day_number(now)) - days_back
    d1 = math.floor(day_number(now)) + days_ahead
    events: list[dict] = []
    events += moon_phases(d0, d1)
    events += conjunctions(d0, d1)
    events += elongations(d0, d1)
    events += oppositions(d0, d1)
    events += seasons(d0, d1)
    events += apsides(d0, d1)
    events += meteor_showers(d0, d1)
    events += eclipses(d0, d1)
    for e in events:
        e.setdefault("source", render("attribution.sky"))
        e.setdefault("source_id", "sky")
    return events
