"""Zjawiska na niebie liczone lokalnie - bez internetu i bez kluczy API.

Wyznaczamy: fazy Ksiezyca (z superpelniami), koniunkcje planet i Ksiezyca,
maksymalne elongacje Merkurego i Wenus, opozycje planet zewnetrznych,
rownonoce i przesilenia, peryhelium/aphelium Ziemi, roje meteorow (dane
statyczne) oraz zacmienia (dane statyczne, redagowane recznie).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ephem
from ephem import day_number, from_day_number, rev180
from lib.text import num, upper_first

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "static"

PHASES = (
    (0.0, "Nów", "nów", 2),
    (90.0, "Pierwsza kwadra", "pierwsza kwadra", 1),
    (180.0, "Pełnia Księżyca", "pełnia", 2),
    (270.0, "Ostatnia kwadra", "ostatnia kwadra", 1),
)

#: pary cial, dla ktorych szukamy koniunkcji, i maksymalna interesujaca separacja
PLANET_PAIRS_MAX_SEP = 4.0
MOON_PAIR_MAX_SEP = 3.0

BODY_BLURB = {
    "Merkury": "najtrudniejsza do złapania planeta – trzyma się blisko Słońca",
    "Wenus": "najjaśniejszy punkt nieba po Słońcu i Księżycu",
    "Mars": "wyraźnie pomarańczowy punkt",
    "Jowisz": "przez lornetkę widać cztery księżyce galileuszowe",
    "Saturn": "nawet mały teleskop pokaże pierścienie",
    "Uran": "na granicy widoczności gołym okiem, łatwy przez lornetkę",
    "Neptun": "wyłącznie przez teleskop",
    "Księżyc": "nasz naturalny satelita",
}


def _iso(d: float) -> str:
    """Znacznik czasu zaokraglony do pelnej minuty.

    Metody numeryczne trafiaja w moment zjawiska z dokladnoscia do sekund,
    a siatka probkowania zalezy od chwili uruchomienia skryptu. Bez
    zaokraglenia ten sam nów dostawalby codziennie inna sekunde i wygladal
    jak wydarzenie o zmienionym terminie.
    """
    t = from_day_number(d).replace(second=0, microsecond=0)
    if from_day_number(d).second >= 30:
        t += timedelta(minutes=1)
    return t.isoformat().replace("+00:00", "Z")


def _link(label: str, url: str) -> dict:
    return {"label": label, "url": url}


def _sky_links(*extra: dict) -> list[dict]:
    return list(extra) + [
        _link("Mapa nieba na dziś (Stellarium Web)", "https://stellarium-web.org/"),
        _link("Kalendarium – In-The-Sky.org", "https://in-the-sky.org/newscal.php"),
    ]


# --- fazy Ksiezyca ----------------------------------------------------------


def moon_phases(d0: float, d1: float) -> list[dict]:
    events = []
    step = 0.5
    d = d0
    prev = ephem.moon_phase_angle(d)
    while d < d1:
        nxt = d + step
        cur = ephem.moon_phase_angle(nxt)
        for target, title, short, importance in PHASES:
            # przejscie przez zadany kat fazy (uwzgledniamy przewiniecie 360 -> 0)
            def f(x, t=target):
                return rev180(ephem.moon_phase_angle(x) - t)

            if f(d) < 0 <= f(nxt) and abs(f(nxt) - f(d)) < 90:
                t = ephem.find_root(f, d, nxt)
                m = ephem.moon(t)
                dist = m["dist_km"]
                extra_tag = None
                if target == 180.0 and dist < 360_000:
                    title = "Superpełnia Księżyca"
                    extra_tag = "superpełnia"
                    importance = 3
                elif target == 180.0 and dist > 405_000:
                    title = "Pełnia w apogeum (mikropełnia)"
                    extra_tag = "mikropełnia"
                desc = (
                    f"Księżyc wchodzi w fazę {short} w gwiazdozbiorze "
                    f"{ephem.zodiac_area(m['lon'])}. Odległość od Ziemi: "
                    f"{num(dist, 0)} km."
                )
                if extra_tag == "superpełnia":
                    desc += (
                        " To superpełnia – tarcza jest o kilka procent większa i wyraźnie "
                        "jaśniejsza niż zwykle. Najefektowniej wygląda tuż po wschodzie, "
                        "nisko nad horyzontem."
                    )
                elif target == 0.0:
                    desc += (
                        " Bezksiężycowe noce wokół tej daty to najlepszy moment w miesiącu "
                        "na obserwacje galaktyk, mgławic i Drogi Mlecznej."
                    )
                events.append(
                    {
                        "title": title,
                        "starts_at": _iso(t),
                        "category": "sky",
                        "subcategory": "moon",
                        "importance": importance,
                        "summary": desc,
                        "tags": ["Księżyc", short] + ([extra_tag] if extra_tag else []),
                        "links": _sky_links(
                            _link("Fazy Księżyca – kalendarz", "https://www.timeanddate.com/moon/phases/")
                        ),
                    }
                )
        d, prev = nxt, cur
    return events


# --- koniunkcje -------------------------------------------------------------


def _pair_events(a: str, b: str, d0: float, d1: float, max_sep: float, step: float) -> list[dict]:
    events = []

    def sep(x):
        return ephem.separation(ephem.body(a, x), ephem.body(b, x))

    d = d0
    s_prev, s_cur = sep(d), sep(d + step)
    while d + 2 * step < d1:
        s_next = sep(d + 2 * step)
        if s_cur < s_prev and s_cur < s_next:
            # lokalne minimum separacji - dopasowanie przez zloty podzial
            t, val = ephem.find_extremum(lambda x: -sep(x), d, d + 2 * step, tol=1e-4)
            val = -val
            if val <= max_sep:
                elong = ephem.elongation(a, t)
                if elong >= 12.0:  # pomijamy zjawiska utopione w blasku Slonca
                    events.append(_conjunction_event(a, b, t, val, elong))
        d += step
        s_prev, s_cur = s_cur, s_next
    return events


def _conjunction_event(a: str, b: str, t: float, sep_deg: float, elong: float) -> dict:
    pa, pb = ephem.body(a, t), ephem.body(b, t)
    visible = "wieczorem, po zachodzie Słońca" if rev180(pa["lon"] - ephem.sun(t)["lon"]) > 0 \
        else "nad ranem, przed wschodem Słońca"
    with_moon = "Księżyc" in (a, b)
    other = b if a == "Księżyc" else a
    sep_txt = f"{num(sep_deg, 1)}°" if sep_deg >= 1 else f"{num(sep_deg * 60, 0)}′"
    if with_moon:
        title = f"Zbliżenie Księżyca i {_gen(other)}"
        summary = (
            f"Księżyc przechodzi w odległości zaledwie {sep_txt} od {_gen(other)} – parę widać "
            f"{visible}, w gwiazdozbiorze {ephem.zodiac_area(pb['lon'])}. "
            f"{upper_first(BODY_BLURB.get(other, 'Ładna para na niebie'))}. Efektowny widok gołym "
            f"okiem i wdzięczny temat na zdjęcie z krótkim teleobiektywem."
        )
        importance = 2
    else:
        title = f"Koniunkcja {_gen(a)} i {_gen(b)}"
        summary = (
            f"Dwie planety dzieli na niebie zaledwie {sep_txt} – to mniej niż szerokość "
            f"palca wyciągniętej ręki. Zjawisko widoczne {visible}, w gwiazdozbiorze "
            f"{ephem.zodiac_area(pa['lon'])}. Odległość od Słońca na niebie: {num(elong, 0)}°."
        )
        importance = 4 if sep_deg < 1.0 else 3
    return {
        "title": title,
        "starts_at": _iso(t),
        "category": "sky",
        "subcategory": "conjunction",
        "importance": importance,
        "summary": summary,
        "tags": [a, b, "koniunkcja"],
        "links": _sky_links(),
        "extra": {"separation_deg": round(sep_deg, 2)},
    }


_GEN = {
    "Merkury": "Merkurego", "Wenus": "Wenus", "Mars": "Marsa", "Jowisz": "Jowisza",
    "Saturn": "Saturna", "Uran": "Urana", "Neptun": "Neptuna", "Księżyc": "Księżyca",
}


def _gen(name: str) -> str:
    return _GEN.get(name, name)


def conjunctions(d0: float, d1: float) -> list[dict]:
    events = []
    naked = ["Merkury", "Wenus", "Mars", "Jowisz", "Saturn"]
    for i, a in enumerate(naked):
        for b in naked[i + 1:]:
            events += _pair_events(a, b, d0, d1, PLANET_PAIRS_MAX_SEP, 1.0)
    for b in ["Wenus", "Mars", "Jowisz", "Saturn"]:
        events += _pair_events("Księżyc", b, d0, d1, MOON_PAIR_MAX_SEP, 0.25)
    return events


# --- elongacje i opozycje ---------------------------------------------------


def elongations(d0: float, d1: float) -> list[dict]:
    events = []
    for name in ("Merkury", "Wenus"):
        step = 2.0
        d = d0
        e_prev, e_cur = ephem.elongation(name, d), ephem.elongation(name, d + step)
        while d + 2 * step < d1:
            e_next = ephem.elongation(name, d + 2 * step)
            if e_cur > e_prev and e_cur > e_next:
                t, val = ephem.find_extremum(lambda x: ephem.elongation(name, x), d, d + 2 * step, tol=1e-4)
                p = ephem.body(name, t)
                evening = rev180(p["lon"] - ephem.sun(t)["lon"]) > 0
                events.append(
                    {
                        "title": f"Maksymalna elongacja {_gen(name)} "
                                 f"({'wschodnia' if evening else 'zachodnia'}, {num(val, 0)}°)",
                        "starts_at": _iso(t),
                        "category": "sky",
                        "subcategory": "elongation",
                        "importance": 4 if name == "Merkury" else 3,
                        "summary": (
                            f"{name} odsuwa się od Słońca na {num(val, 0)}° – to najlepszy w tym "
                            f"sezonie moment na obserwację tej planety "
                            f"{'wieczorem, tuż po zachodzie Słońca' if evening else 'nad ranem, tuż przed wschodem Słońca'}. "
                            f"{upper_first(BODY_BLURB[name])}. Szukaj nisko nad horyzontem, "
                            f"{'zachodnim' if evening else 'wschodnim'}, w czasie zmierzchu."
                        ),
                        "tags": [name, "elongacja"],
                        "links": _sky_links(),
                        "extra": {"elongation_deg": round(val, 1)},
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
    for name in ("Mars", "Jowisz", "Saturn", "Uran", "Neptun"):
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
                light_min = dist_km / 17_987_547.48
                events.append(
                    {
                        "title": f"Opozycja {_gen(name)}",
                        "starts_at": _iso(t),
                        "category": "sky",
                        "subcategory": "opposition",
                        "importance": 5 if name in ("Mars", "Jowisz", "Saturn") else 3,
                        "summary": (
                            f"{name} znajduje się naprzeciw Słońca – wschodzi o zachodzie Słońca, "
                            f"góruje około północy i świeci najjaśniej w całym sezonie. "
                            f"Odległość od Ziemi: {num(p['dist_au'], 2)} au ({num(dist_km / 1e6, 0)} mln km, "
                            f"światło leci stamtąd {num(light_min, 0)} minut). Planeta jest w gwiazdozbiorze "
                            f"{ephem.zodiac_area(p['lon'])}. {upper_first(BODY_BLURB[name])}."
                        ),
                        "tags": [name, "opozycja"],
                        "links": _sky_links(),
                        "extra": {"distance_au": round(p["dist_au"], 3)},
                    }
                )
            d += step
    return events


# --- Slonce: rownonoce, przesilenia, peryhelium ------------------------------

SEASONS = (
    (0.0, "Równonoc wiosenna", "Słońce przechodzi przez punkt Barana. Dzień i noc mają"
                               " zbliżoną długość, na półkuli północnej zaczyna się astronomiczna wiosna."),
    (90.0, "Przesilenie letnie", "Najdłuższy dzień roku na półkuli północnej – Słońce osiąga"
                                 " najwyższe położenie na niebie. Początek astronomicznego lata."),
    (180.0, "Równonoc jesienna", "Słońce przechodzi przez punkt Wagi. Początek astronomicznej"
                                 " jesieni i sezonu na zorze polarne – w okolicach równonocy"
                                 " burze geomagnetyczne zdarzają się statystycznie częściej."),
    (270.0, "Przesilenie zimowe", "Najkrótszy dzień roku na półkuli północnej. Od tego momentu"
                                  " dnia zaczyna przybywać – początek astronomicznej zimy."),
)


def seasons(d0: float, d1: float) -> list[dict]:
    events = []
    d = d0
    while d < d1:
        nxt = min(d + 1.0, d1)
        for target, title, desc in SEASONS:
            def f(x, t=target):
                return rev180(ephem.sun(x)["lon"] - t)

            if f(d) < 0 <= f(nxt) and abs(f(nxt) - f(d)) < 90:
                t = ephem.find_root(f, d, nxt)
                events.append(
                    {
                        "title": title,
                        "starts_at": _iso(t),
                        "category": "sky",
                        "subcategory": "season",
                        "importance": 3,
                        "summary": desc,
                        "tags": ["Słońce", "pory roku"],
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
        for is_max, title in ((True, "Aphelium Ziemi"), (False, "Peryhelium Ziemi")):
            hit = (r_cur > r_prev and r_cur > r_next) if is_max else (r_cur < r_prev and r_cur < r_next)
            if hit:
                sign = 1 if is_max else -1
                t, val = ephem.find_extremum(lambda x: sign * ephem.sun(x)["dist_au"], d, d + 2 * step, tol=1e-4)
                val = sign * val
                events.append(
                    {
                        "title": title,
                        "starts_at": _iso(t),
                        "category": "sky",
                        "subcategory": "season",
                        "importance": 2,
                        "summary": (
                            f"Ziemia jest {'najdalej od' if is_max else 'najbliżej'} Słońca w tym roku: "
                            f"{num(val * ephem.AU_KM / 1e6, 1)} mln km. Różnica między peryhelium a aphelium "
                            f"to około 5 mln km – to nie ona odpowiada za pory roku, tylko nachylenie "
                            f"osi obrotu Ziemi."
                        ),
                        "tags": ["Ziemia", "Słońce"],
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


def meteor_showers(d0: float, d1: float) -> list[dict]:
    events = []
    start_year = from_day_number(d0).year
    for year in (start_year, start_year + 1, start_year + 2):
        for sh in _load("meteor_showers.json"):
            try:
                peak = datetime(year, sh["peak_month"], sh["peak_day"], 2, 0, tzinfo=timezone.utc)
            except ValueError:
                continue
            t = day_number(peak)
            if not (d0 <= t <= d1):
                continue
            illum = ephem.moon_illumination(t)
            if illum < 0.25:
                moon_note = "Warunki są znakomite – Księżyc praktycznie nie przeszkadza."
            elif illum < 0.6:
                moon_note = f"Księżyc oświetlony w {num(illum * 100, 0)}% nieco rozjaśni niebo."
            else:
                moon_note = (f"Niestety Księżyc będzie oświetlony w {num(illum * 100, 0)}% "
                             f"i zagłuszy słabsze meteory – warto obserwować po jego zachodzie.")
            events.append(
                {
                    "title": f"Maksimum roju {sh['name']}",
                    "starts_at": peak.isoformat().replace("+00:00", "Z"),
                    "category": "sky",
                    "subcategory": "meteors",
                    "importance": 5 if sh["zhr"] >= 80 else (4 if sh["zhr"] >= 20 else 3),
                    "summary": (
                        f"{sh['description']} W maksimum teoretycznie do {sh['zhr']} meteorów na godzinę "
                        f"(ZHR – przy idealnie ciemnym niebie i radiancie w zenicie; realnie zwykle "
                        f"kilka razy mniej). Radiant w gwiazdozbiorze {sh['radiant']}. {moon_note} "
                        f"Nie potrzeba żadnego sprzętu – wystarczy leżak, ciepłe ubranie i dala od "
                        f"miejskich świateł."
                    ),
                    "tags": ["meteory", sh["name"]],
                    "links": _sky_links(
                        _link("Kalendarz rojów IMO", "https://www.imo.net/resources/calendar/"),
                        _link("O roju – Wikipedia", sh.get("url", "https://pl.wikipedia.org/wiki/Rój_meteorów")),
                    ),
                    "extra": {"zhr": sh["zhr"], "moon_illumination": round(illum, 2)},
                }
            )
    return events


def eclipses(d0: float, d1: float) -> list[dict]:
    events = []
    for ec in _load("eclipses.json"):
        when = datetime.fromisoformat(ec["utc"].replace("Z", "+00:00"))
        t = day_number(when)
        if not (d0 <= t <= d1):
            continue
        solar = ec["kind"].startswith("s")
        events.append(
            {
                "title": ec["title"],
                "starts_at": ec["utc"],
                "category": "sky",
                "subcategory": "eclipse",
                "importance": ec.get("importance", 5),
                "summary": ec["description"] + (
                    " UWAGA: Słońce wolno obserwować wyłącznie przez atestowane filtry "
                    "słoneczne – zwykłe okulary przeciwsłoneczne czy klisza NIE chronią wzroku."
                    if solar else ""
                ),
                "tags": ["zaćmienie", "Słońce" if solar else "Księżyc"],
                "links": _sky_links(
                    _link("Szczegóły i mapa widoczności (NASA)",
                          "https://eclipse.gsfc.nasa.gov/eclipse.html"),
                    *( [_link("Szczegóły zjawiska", ec["url"])] if ec.get("url") else [] ),
                ),
                "location": ec.get("visibility"),
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
        e.setdefault("source", "obliczenia własne (efemerydy)")
        e.setdefault("source_id", "sky")
    return events
