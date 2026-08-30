"""Astronomiczne zdjecie dnia (APOD) - uzywane jako ilustracja portalu."""

from __future__ import annotations

from datetime import datetime

from lib.http import get_json

URL = "https://api.nasa.gov/planetary/apod?api_key={key}&thumbs=true"


def collect(api_key: str = "DEMO_KEY") -> dict | None:
    data = get_json(URL.format(key=api_key))
    if isinstance(data, list):
        data = data[0] if data else None
    if not data:
        return None
    image = data.get("url") if data.get("media_type") == "image" else data.get("thumbnail_url")
    return {
        "title": data.get("title"),
        "date": data.get("date"),
        "image": image,
        "hdimage": data.get("hdurl"),
        "credit": data.get("copyright", "NASA/domena publiczna").strip(),
        "explanation": data.get("explanation"),
        "link": f"https://apod.nasa.gov/apod/ap{(data.get('date') or '')[2:].replace('-', '')}.html",
    }
