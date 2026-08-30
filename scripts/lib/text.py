"""Formatowanie liczb i tekstu po polsku."""

from __future__ import annotations

NBSP = " "


def num(value: float, digits: int = 1) -> str:
    """Liczba w zapisie polskim: przecinek dziesietny, spacja co tysiac.

    Jako separatora tysiecy uzywamy spacji niedzielacej, zeby liczba nie
    zlamala sie w polowie na koncu wiersza.
    """
    text = f"{value:,.{digits}f}"
    return text.replace(",", NBSP).replace(".", ",")


def upper_first(text: str) -> str:
    """Wielka litera na poczatku, bez ruszania reszty (inaczej niz capitalize)."""
    return text[:1].upper() + text[1:] if text else text
