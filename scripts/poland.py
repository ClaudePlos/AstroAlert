"""Ocena, czy wydarzenie jest ciekawe z perspektywy Polski.

Dla zjawisk na niebie odpowiedz da sie policzyc: sprawdzamy, czy obiekt
wznosi sie dostatecznie wysoko nad horyzontem w czasie, gdy jest juz
wystarczajaco ciemno. Punktem odniesienia jest srodek Polski - roznice
miedzy Szczecinem a Rzeszowem to dla wysokosci pojedyncze stopnie.

Reszta kategorii ma wlasne kryteria: zacmienia biora flage z danych
redagowanych recznie, zorze wymagaja burzy zdolnej zejsc nad Polske,
a starty rakiet licza sie wtedy, gdy jest w nich polski watek.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import ephem
from lib.i18n import render
from lib.text import fmt

#: ponizej tej wysokosci Slonca niebo jest dosc ciemne dla danego obiektu.
#: Wenus (-4 mag) i Merkury widac jeszcze w jasnym zmierzchu, slabsze
#: obiekty wymagaja nocy astronomicznej
TWILIGHT_LIMIT = {"Mercury": -2.0, "Venus": -2.0, "Moon": -6.0}
DEFAULT_TWILIGHT_LIMIT = -12.0

#: minimalna wysokosc nad horyzontem, przy ktorej obserwacja ma sens -
#: dla jasnych planet wystarczy odslonięty horyzont, reszta musi wyjsc wyzej
MIN_ALTITUDE = {"Mercury": 2.0, "Venus": 2.0, "Moon": 5.0}
DEFAULT_MIN_ALTITUDE = 10.0

#: od tego indeksu Kp zorza bywa widoczna z Polski (skala G2 i wyzej)
AURORA_KP = 6.0

#: polskie watki w startach rakiet - nazwy misji, firm i ladunkow
POLISH_LAUNCH_KEYWORDS = (
    "poland", "polish", "polska", "uznański", "uznanski", "pw-sat",
    "intuition-1", "eagleeye", "creotech", "satrev", "iceye", "scanway",
    "ax-4", "ignis",
)

#: krok probkowania nocy (doba ulamkowa) - 10 minut
STEP = 10.0 / 1440.0


def _night_window(day_start: float) -> tuple[float, float]:
    """Przedzial doby, w ktorym szukamy okazji: od poludnia do poludnia."""
    return day_start + 0.5, day_start + 1.5


def best_observation(ra: float, dec: float, day_start: float,
                     twilight: float, min_altitude: float) -> dict | None:
    """Najlepszy moment obserwacji obiektu w nocy wokol zadanej doby.

    Zwraca slownik z maksymalna wysokoscia i chwila jej osiagniecia albo
    None, jesli obiekt nie wychodzi wtedy dostatecznie wysoko nad horyzont
    przy dostatecznie ciemnym niebie.
    """
    start, end = _night_window(day_start)
    best_alt, best_t = -90.0, None
    t = start
    while t <= end:
        if ephem.altitude("Sun", t) < twilight:
            alt = ephem.altitude_of(ra, dec, t)
            if alt > best_alt:
                best_alt, best_t = alt, t
        t += STEP
    if best_t is None or best_alt < min_altitude:
        return None
    return {"max_altitude": round(best_alt, 1), "best_time": best_t}


def _body_observation(name: str, when: datetime) -> dict | None:
    day_start = math.floor(ephem.day_number(when))
    twilight = TWILIGHT_LIMIT.get(name, DEFAULT_TWILIGHT_LIMIT)
    minimum = MIN_ALTITUDE.get(name, DEFAULT_MIN_ALTITUDE)
    # wspolrzedne bierzemy z polnocy - w ciagu jednej nocy zmieniaja sie
    # na tyle wolno, ze nie wplywa to na ocene widocznosci
    ra, dec = ephem.equatorial(ephem.body(name, day_start + 1.0), day_start + 1.0)
    return best_observation(ra, dec, day_start, twilight, minimum)


def _iso(d: float) -> str:
    return ephem.from_day_number(d).replace(second=0, microsecond=0) \
        .isoformat().replace("+00:00", "Z")


def _visible(reason_key: str, observation: dict | None = None) -> dict:
    """Buduje ocene wraz z opisem; nieuzyte pola szablon po prostu pomija."""
    alt = fmt(observation["max_altitude"], 0) if observation else ""
    out = {"visible": True, "note": render(reason_key, alt=alt)}
    if observation:
        out["max_altitude"] = observation["max_altitude"]
        out["best_time"] = _iso(observation["best_time"])
    return out


NOT_VISIBLE = {"visible": False}


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate(event: dict) -> dict:
    """Ocena pojedynczego wydarzenia."""
    when = _parse(event["starts_at"])
    sub = event.get("subcategory")
    extra = event.get("extra") or {}

    if event["category"] == "spaceweather":
        kp = extra.get("kp", 0)
        return _visible("poland.aurora") if kp >= AURORA_KP else NOT_VISIBLE

    if event["category"] == "launch":
        text = " ".join([
            event["title"].get("en", ""), event["summary"].get("en", ""),
            " ".join(t.get("en", "") for t in event.get("tags", [])),
        ]).lower()
        if any(word in text for word in POLISH_LAUNCH_KEYWORDS):
            return _visible("poland.launch")
        return NOT_VISIBLE

    if event["category"] == "asteroid":
        return NOT_VISIBLE  # bez teleskopu i tak nic nie zobaczymy

    if sub == "eclipse":
        return _visible("poland.eclipse") if extra.get("poland") else NOT_VISIBLE

    if sub == "meteors":
        radiant = extra.get("radiant_ra"), extra.get("radiant_dec")
        if None in radiant:
            return NOT_VISIBLE
        observation = best_observation(radiant[0], radiant[1],
                                       math.floor(ephem.day_number(when)),
                                       DEFAULT_TWILIGHT_LIMIT, 15.0)
        return _visible("poland.meteors", observation) if observation else NOT_VISIBLE

    if sub == "season":
        return _visible("poland.season")  # równonoce i przesilenia dotyczą nas wprost

    if sub == "moon":
        observation = _body_observation("Moon", when)
        if "Nów" in event["title"].get("pl", ""):
            return _visible("poland.new_moon")
        return _visible("poland.moon", observation) if observation else NOT_VISIBLE

    body = extra.get("body") or (extra.get("bodies") or [None])[0]
    if body:
        observation = _body_observation(body, when)
        if not observation:
            return NOT_VISIBLE
        key = {"conjunction": "poland.conjunction", "opposition": "poland.opposition",
               "elongation": "poland.elongation"}.get(sub, "poland.sky")
        return _visible(key, observation)

    return NOT_VISIBLE


def annotate(events: list[dict]) -> list[dict]:
    """Dopisuje do kazdego wydarzenia ocene widocznosci z Polski."""
    for event in events:
        try:
            event["poland"] = evaluate(event)
        except Exception:  # ocena widocznosci nie moze wywrocic przebiegu
            event["poland"] = NOT_VISIBLE
    return events
