"""Lekkie efemerydy w czystym Pythonie (bez zaleznosci zewnetrznych).

Algorytmy oparte na klasycznych, niskoprecyzyjnych formulach orbitalnych
(Paul Schlyter, "Computing planetary positions"; perturbacje wg Meeusa).
Dokladnosc pozycji: ok. 1-2' dla Slonca i Ksiezyca, do ~0.2 stopnia dla
planet zewnetrznych. To w zupelnosci wystarcza, by wyznaczyc DATY zjawisk
(fazy Ksiezyca, koniunkcje, opozycje, elongacje, rownonoce) z dokladnoscia
do minut/godzin, a o to nam tutaj chodzi.

Wszystkie katy w stopniach, czas w UTC.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

# --- pomocnicze funkcje trygonometryczne w stopniach ------------------------

_D2R = math.pi / 180.0
_R2D = 180.0 / math.pi

EARTH_RADIUS_KM = 6378.14
AU_KM = 149_597_870.7


def sind(x: float) -> float:
    return math.sin(x * _D2R)


def cosd(x: float) -> float:
    return math.cos(x * _D2R)


def atan2d(y: float, x: float) -> float:
    return math.atan2(y, x) * _R2D


def acosd(x: float) -> float:
    return math.acos(max(-1.0, min(1.0, x))) * _R2D


def rev(x: float) -> float:
    """Normalizacja kata do przedzialu [0, 360)."""
    return x % 360.0


def rev180(x: float) -> float:
    """Normalizacja kata do przedzialu (-180, 180]."""
    x = (x + 180.0) % 360.0 - 180.0
    return x + 360.0 if x <= -180.0 else x


# --- czas -------------------------------------------------------------------


def day_number(dt: datetime) -> float:
    """Dzien "d" liczony od 2000-01-00 00:00 UT (konwencja Schlytera)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    y, m, day = dt.year, dt.month, dt.day
    d = 367 * y - (7 * (y + ((m + 9) // 12))) // 4 + (275 * m) // 9 + day - 730530
    frac = (dt.hour + dt.minute / 60.0 + (dt.second + dt.microsecond / 1e6) / 3600.0) / 24.0
    return d + frac


def from_day_number(d: float) -> datetime:
    """Odwrotnosc day_number()."""
    epoch = datetime(1999, 12, 31, 0, 0, 0, tzinfo=timezone.utc)
    return epoch + timedelta(days=d)


def obliquity(d: float) -> float:
    """Nachylenie ekliptyki."""
    return 23.4393 - 3.563e-7 * d


# --- rozwiazanie rownania Keplera ------------------------------------------


def _eccentric_anomaly(M: float, e: float) -> float:
    """Anomalia mimosrodowa (stopnie), iteracyjnie."""
    E = M + _R2D * e * sind(M) * (1.0 + e * cosd(M))
    for _ in range(12):
        dE = (E - _R2D * e * sind(E) - M) / (1.0 - e * cosd(E))
        E -= dE
        if abs(dE) < 1e-9:
            break
    return E


# --- Slonce -----------------------------------------------------------------


def sun(d: float) -> dict:
    """Pozycja geocentryczna Slonca."""
    w = 282.9404 + 4.70935e-5 * d
    e = 0.016709 - 1.151e-9 * d
    M = rev(356.0470 + 0.9856002585 * d)
    E = _eccentric_anomaly(M, e)
    x = cosd(E) - e
    y = math.sqrt(1.0 - e * e) * sind(E)
    r = math.hypot(x, y)
    v = atan2d(y, x)
    lon = rev(v + w)
    return {
        "name": "Sun",
        "lon": lon,
        "lat": 0.0,
        "dist_au": r,
        "M": M,
        "w": w,
        "L": rev(M + w),
        "x": r * cosd(lon),
        "y": r * sind(lon),
        "z": 0.0,
    }


# --- Ksiezyc ----------------------------------------------------------------


def moon(d: float) -> dict:
    """Pozycja geocentryczna Ksiezyca z glownymi perturbacjami."""
    N = rev(125.1228 - 0.0529538083 * d)
    i = 5.1454
    w = rev(318.0634 + 0.1643573223 * d)
    a = 60.2666  # promienie Ziemi
    e = 0.054900
    M = rev(115.3654 + 13.0649929509 * d)

    E = _eccentric_anomaly(M, e)
    xv = a * (cosd(E) - e)
    yv = a * (math.sqrt(1.0 - e * e) * sind(E))
    v = atan2d(yv, xv)
    r = math.hypot(xv, yv)

    xh = r * (cosd(N) * cosd(v + w) - sind(N) * sind(v + w) * cosd(i))
    yh = r * (sind(N) * cosd(v + w) + cosd(N) * sind(v + w) * cosd(i))
    zh = r * (sind(v + w) * sind(i))

    lon = rev(atan2d(yh, xh))
    lat = atan2d(zh, math.hypot(xh, yh))

    s = sun(d)
    Ms, Mm = s["M"], M
    Ls, Lm = s["L"], rev(N + w + M)
    D = rev(Lm - Ls)
    F = rev(Lm - N)

    lon += (
        -1.274 * sind(Mm - 2 * D)
        + 0.658 * sind(2 * D)
        - 0.186 * sind(Ms)
        - 0.059 * sind(2 * Mm - 2 * D)
        - 0.057 * sind(Mm - 2 * D + Ms)
        + 0.053 * sind(Mm + 2 * D)
        + 0.046 * sind(2 * D - Ms)
        + 0.041 * sind(Mm - Ms)
        - 0.035 * sind(D)
        - 0.031 * sind(Mm + Ms)
        - 0.015 * sind(2 * F - 2 * D)
        + 0.011 * sind(Mm - 4 * D)
    )
    lat += (
        -0.173 * sind(F - 2 * D)
        - 0.055 * sind(Mm - F - 2 * D)
        - 0.046 * sind(Mm + F - 2 * D)
        + 0.033 * sind(F + 2 * D)
        + 0.017 * sind(2 * Mm + F)
    )
    r += -0.58 * cosd(Mm - 2 * D) - 0.46 * cosd(2 * D)

    lon = rev(lon)
    return {
        "name": "Moon",
        "lon": lon,
        "lat": lat,
        "dist_km": r * EARTH_RADIUS_KM,
        "dist_au": r * EARTH_RADIUS_KM / AU_KM,
        "node": N,
        "arg_lat": F,
        "elong_mean": D,
    }


# --- planety ----------------------------------------------------------------

#: identyfikatory cial sa neutralne jezykowo - nazwy do wyswietlenia
#: pochodza z katalogu komunikatow (data/locales/)
_ELEMENTS = {
    # nazwa: (N, i, w, a, e, M) jako pary (wyraz stały, wspolczynnik * d)
    "Mercury": ((48.3313, 3.24587e-5), (7.0047, 5.00e-8), (29.1241, 1.01444e-5),
                (0.387098, 0.0), (0.205635, 5.59e-10), (168.6562, 4.0923344368)),
    "Venus": ((76.6799, 2.46590e-5), (3.3946, 2.75e-8), (54.8910, 1.38374e-5),
              (0.723330, 0.0), (0.006773, -1.302e-9), (48.0052, 1.6021302244)),
    "Mars": ((49.5574, 2.11081e-5), (1.8497, -1.78e-8), (286.5016, 2.92961e-5),
             (1.523688, 0.0), (0.093405, 2.516e-9), (18.6021, 0.5240207766)),
    "Jupiter": ((100.4542, 2.76854e-5), (1.3030, -1.557e-7), (273.8777, 1.64505e-5),
               (5.20256, 0.0), (0.048498, 4.469e-9), (19.8950, 0.0830853001)),
    "Saturn": ((113.6634, 2.38980e-5), (2.4886, -1.081e-7), (339.3939, 2.97661e-5),
               (9.55475, 0.0), (0.055546, -9.499e-9), (316.9670, 0.0334442282)),
    "Uranus": ((74.0005, 1.3978e-5), (0.7733, 1.9e-8), (96.6612, 3.0565e-5),
             (19.18171, -1.55e-8), (0.047318, 7.45e-9), (142.5905, 0.011725806)),
    "Neptune": ((131.7806, 3.0173e-5), (1.7700, -2.55e-7), (272.8461, -6.027e-6),
               (30.05826, 3.313e-8), (0.008606, 2.15e-9), (260.2471, 0.005995147)),
}

PLANETS = tuple(_ELEMENTS.keys())
#: planety realnie widoczne golym okiem - tylko dla nich generujemy wpisy
NAKED_EYE = ("Mercury", "Venus", "Mars", "Jupiter", "Saturn")


def _heliocentric(name: str, d: float) -> tuple[float, float, float, float]:
    (N0, N1), (i0, i1), (w0, w1), (a0, a1), (e0, e1), (M0, M1) = _ELEMENTS[name]
    N = rev(N0 + N1 * d)
    i = i0 + i1 * d
    w = rev(w0 + w1 * d)
    a = a0 + a1 * d
    e = e0 + e1 * d
    M = rev(M0 + M1 * d)

    E = _eccentric_anomaly(M, e)
    xv = a * (cosd(E) - e)
    yv = a * (math.sqrt(1.0 - e * e) * sind(E))
    v = atan2d(yv, xv)
    r = math.hypot(xv, yv)

    xh = r * (cosd(N) * cosd(v + w) - sind(N) * sind(v + w) * cosd(i))
    yh = r * (sind(N) * cosd(v + w) + cosd(N) * sind(v + w) * cosd(i))
    zh = r * (sind(v + w) * sind(i))

    lon = rev(atan2d(yh, xh))
    lat = atan2d(zh, math.hypot(xh, yh))
    return lon, lat, r, M


def _giant_perturbations(name: str, d: float, lon: float, lat: float) -> tuple[float, float]:
    """Perturbacje Jowisza/Saturna/Urana (Meeus, wersja skrocona)."""
    if name not in ("Jupiter", "Saturn", "Uranus"):
        return lon, lat
    Mj = rev(19.8950 + 0.0830853001 * d)
    Ms = rev(316.9670 + 0.0334442282 * d)
    Mu = rev(142.5905 + 0.011725806 * d)
    if name == "Jupiter":
        lon += (
            -0.332 * sind(2 * Mj - 5 * Ms - 67.6)
            - 0.056 * sind(2 * Mj - 2 * Ms + 21)
            + 0.042 * sind(3 * Mj - 5 * Ms + 21)
            - 0.036 * sind(Mj - 2 * Ms)
            + 0.022 * cosd(Mj - Ms)
            + 0.023 * sind(2 * Mj - 3 * Ms + 52)
            - 0.016 * sind(Mj - 5 * Ms - 69)
        )
    elif name == "Saturn":
        lon += (
            0.812 * sind(2 * Mj - 5 * Ms - 67.6)
            - 0.229 * cosd(2 * Mj - 4 * Ms - 2)
            + 0.119 * sind(Mj - 2 * Ms - 3)
            + 0.046 * sind(2 * Mj - 6 * Ms - 69)
            + 0.014 * sind(Mj - 3 * Ms + 32)
        )
        lat += -0.020 * cosd(2 * Mj - 4 * Ms - 2) + 0.018 * sind(2 * Mj - 6 * Ms - 49)
    else:
        lon += (
            0.040 * sind(Ms - 2 * Mu + 6)
            + 0.035 * sind(Ms - 3 * Mu + 33)
            - 0.015 * sind(Mj - Mu + 20)
        )
    return rev(lon), lat


def planet(name: str, d: float) -> dict:
    """Pozycja geocentryczna planety (dlugosc/szerokosc ekliptyczna)."""
    lon_h, lat_h, r, M = _heliocentric(name, d)
    lon_h, lat_h = _giant_perturbations(name, d, lon_h, lat_h)

    xh = r * cosd(lon_h) * cosd(lat_h)
    yh = r * sind(lon_h) * cosd(lat_h)
    zh = r * sind(lat_h)

    s = sun(d)
    xg = xh + s["x"]
    yg = yh + s["y"]
    zg = zh

    lon = rev(atan2d(yg, xg))
    lat = atan2d(zg, math.hypot(xg, yg))
    dist = math.sqrt(xg * xg + yg * yg + zg * zg)
    return {
        "name": name,
        "lon": lon,
        "lat": lat,
        "dist_au": dist,
        "sun_dist_au": r,
        "helio_lon": lon_h,
    }


#: polskie nazwy przyjmowane jako aliasy - ulatwiaja prace w konsoli
ALIASES = {
    "Słońce": "Sun", "Slonce": "Sun", "Księżyc": "Moon", "Ksiezyc": "Moon",
    "Merkury": "Mercury", "Wenus": "Venus", "Jowisz": "Jupiter",
    "Uran": "Uranus", "Neptun": "Neptune",
}


def body(name: str, d: float) -> dict:
    """Pozycja geocentryczna dowolnego ciala po nazwie."""
    name = ALIASES.get(name, name)
    if name == "Sun":
        return sun(d)
    if name == "Moon":
        return moon(d)
    return planet(name, d)


# --- geometria --------------------------------------------------------------


def separation(a: dict, b: dict) -> float:
    """Odleglosc katowa miedzy dwoma cialami (stopnie)."""
    return acosd(
        sind(a["lat"]) * sind(b["lat"])
        + cosd(a["lat"]) * cosd(b["lat"]) * cosd(a["lon"] - b["lon"])
    )


def elongation(name: str, d: float) -> float:
    """Elongacja ciala od Slonca (stopnie, 0-180)."""
    return separation(body(name, d), sun(d))


def moon_phase_angle(d: float) -> float:
    """Roznica dlugosci ekliptycznej Ksiezyc - Slonce (0-360).

    0 = nów, 90 = pierwsza kwadra, 180 = pelnia, 270 = ostatnia kwadra.
    """
    return rev(moon(d)["lon"] - sun(d)["lon"])


def moon_illumination(d: float) -> float:
    """Ulamek oswietlonej tarczy Ksiezyca (0-1)."""
    return (1.0 - cosd(moon_phase_angle(d))) / 2.0


def equatorial(b: dict, d: float) -> tuple[float, float]:
    """Zamiana wspolrzednych ekliptycznych na rownikowe: (RA w godzinach, dec)."""
    ecl = obliquity(d)
    r = b.get("dist_au", 1.0)
    x = r * cosd(b["lon"]) * cosd(b["lat"])
    y = r * sind(b["lon"]) * cosd(b["lat"])
    z = r * sind(b["lat"])
    xe = x
    ye = y * cosd(ecl) - z * sind(ecl)
    ze = y * sind(ecl) + z * cosd(ecl)
    ra = rev(atan2d(ye, xe)) / 15.0
    dec = atan2d(ze, math.hypot(xe, ye))
    return ra, dec


def zodiac_index(lon: float) -> int:
    """Numer sektora zodiaku (0-11), w ktorym lezy dana dlugosc ekliptyczna.

    To uproszczenie: dzielimy ekliptyke na 12 rownych sektorow po 30 stopni,
    a nie uzywamy rzeczywistych granic gwiazdozbiorow IAU. Nazwy sektorow
    trzyma katalog komunikatow, bo roznia sie miedzy jezykami.
    """
    return int(rev(lon) // 30) % 12


# --- numeryka: zera i ekstrema ---------------------------------------------


def find_root(f, lo: float, hi: float, tol: float = 1e-5) -> float:
    """Bisekcja na przedziale, w ktorym f zmienia znak."""
    flo = f(lo)
    for _ in range(80):
        mid = (lo + hi) / 2.0
        fmid = f(mid)
        if hi - lo < tol:
            return mid
        if (flo < 0) == (fmid < 0):
            lo, flo = mid, fmid
        else:
            hi = mid
    return (lo + hi) / 2.0


def find_extremum(f, lo: float, hi: float, tol: float = 1e-4) -> tuple[float, float]:
    """Zloty podzial - szuka MAKSIMUM f na [lo, hi]. Zwraca (x, f(x))."""
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c = b - phi * (b - a)
    dd = a + phi * (b - a)
    fc, fd = f(c), f(dd)
    while b - a > tol:
        if fc > fd:
            b, dd, fd = dd, c, fc
            c = b - phi * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, dd, fd
            dd = a + phi * (b - a)
            fd = f(dd)
    x = (a + b) / 2.0
    return x, f(x)
