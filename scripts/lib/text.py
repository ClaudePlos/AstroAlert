"""Formatowanie liczb i tekstu po polsku."""

from __future__ import annotations

NBSP = " "


def num(value: float, digits: int = 1, lang: str = "pl") -> str:
    """Liczba w konwencji danego jezyka.

    Polski: przecinek dziesietny i spacja co tysiac. Angielski: kropka
    dziesietna i przecinek co tysiac. Jako separatora tysiecy w polskim
    uzywamy spacji niedzielacej, zeby liczba nie zlamala sie na koncu wiersza.
    """
    text = f"{value:,.{digits}f}"
    if lang == "pl":
        return text.replace(",", NBSP).replace(".", ",")
    return text


def fmt(value: float, digits: int = 1) -> dict:
    """Liczba przygotowana dla wszystkich jezykow naraz.

    Zwraca slownik, ktory katalog komunikatow rozwinie osobno dla kazdej
    wersji jezykowej - inaczej angielski tekst dostalby polskie separatory.
    """
    from lib.i18n import LANGS

    return {lang: num(value, digits, lang) for lang in LANGS}


def upper_first(text: str) -> str:
    """Wielka litera na poczatku, bez ruszania reszty (inaczej niz capitalize)."""
    return text[:1].upper() + text[1:] if text else text
