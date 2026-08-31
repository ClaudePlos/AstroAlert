"""Katalog komunikatow - jedno zrodlo tekstow dla wszystkich jezykow portalu.

Wpisy w kalendarzu powstaja od razu w obu jezykach: kolektor uruchamiany jest
raz na dobe, wiec taniej wygenerowac obie wersje niz tlumaczyc cokolwiek
w przegladarce. Dzieki temu portal dziala bez zadnego API tlumaczacego,
a teksty sa pisane recznie, nie maszynowo.

Uzycie:

    from lib.i18n import render

    render("moon.summary", phase=PHASE_NAMES["full"], zodiac=zodiac(lon), dist=fmt(km, 0))
    # -> {"pl": "Księżyc wchodzi w fazę pełnia…", "en": "The Moon reaches full…"}

Parametry moga byc zwyklymi wartosciami albo slownikami {"pl": …, "en": …} -
te drugie sa rozwijane osobno dla kazdego jezyka, co pozwala odmieniac nazwy
(„koniunkcja Marsa i Jowisza" kontra „conjunction of Mars and Jupiter").
"""

from __future__ import annotations

import json
from pathlib import Path

#: kolejnosc ma znaczenie - pierwszy jezyk jest domyslny
LANGS = ("pl", "en")

LOCALES_DIR = Path(__file__).resolve().parents[2] / "data" / "locales"

_CATALOGS: dict[str, dict[str, str]] = {}


class MissingMessage(KeyError):
    """Brak klucza w katalogu - lepiej wywalic sie glosno niz pokazac pusty tekst."""


def catalog(lang: str) -> dict[str, str]:
    if lang not in _CATALOGS:
        path = LOCALES_DIR / f"{lang}.json"
        _CATALOGS[lang] = json.loads(path.read_text(encoding="utf-8"))
    return _CATALOGS[lang]


def pick(value, lang: str):
    """Rozwija slownik {"pl": …, "en": …} do wartosci dla danego jezyka."""
    if isinstance(value, dict) and set(value) & set(LANGS):
        return value.get(lang, value.get(LANGS[0], ""))
    return value


def t(key: str, lang: str, **params) -> str:
    """Pojedynczy komunikat w jednym jezyku."""
    try:
        template = catalog(lang)[key]
    except KeyError as exc:
        raise MissingMessage(f"brak klucza {key!r} w katalogu {lang!r}") from exc
    if not params:
        return template
    return template.format(**{k: pick(v, lang) for k, v in params.items()})


def render(key: str, **params) -> dict[str, str]:
    """Komunikat we wszystkich jezykach naraz."""
    return {lang: t(key, lang, **params) for lang in LANGS}


def join(*parts: dict[str, str], separator: str = " ") -> dict[str, str]:
    """Skleja kilka wielojezycznych fragmentow w jeden."""
    return {
        lang: separator.join(p[lang] for p in parts if p.get(lang))
        for lang in LANGS
    }


def literal(value: str) -> dict[str, str]:
    """Ten sam tekst w kazdym jezyku (nazwy własne, oznaczenia katalogowe)."""
    return {lang: value for lang in LANGS}


def multi(**by_lang: str) -> dict[str, str]:
    """Jawnie podane warianty, np. multi(pl="Marsa", en="Mars")."""
    return {lang: by_lang.get(lang, "") for lang in LANGS}
