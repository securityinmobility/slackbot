"""Today's Mensa Ingolstadt menu from werkswelt.de, the Studierendenwerk's own page, in German and English.

The page has no feed: one HTML page per language, all meals in a single <div>, separated by <br>.
"""
import html
import re
import sys
from datetime import date, datetime

import requests

URL = "https://www.werkswelt.de/index.php"
LOCATION_ID = "ingo"

_BR = r"<br\s*/?>"
# "Speiseplan <br><h4>Dienstag 24.11.2026</h4> ...meals... <form" (the form holds the day navigation buttons)
_MENU = re.compile(r"Speiseplan\s*" + _BR + r"\s*<h4[^>]*>[^<]*?(\d{2}\.\d{2}\.\d{4})\s*</h4>(.*?)(?:<form|</div>)", re.S | re.I)
_PRICES = re.compile(r"(\d+,\d{2})\D*?\(Stud\.\).*?(\d+,\d{2})\D*?\(Bed\.\)", re.S)
_ICON = re.compile(r"infomax-food-icon\s+([\w-]+)", re.I)


def _text(fragment: str) -> str:
    """Visible text of an HTML fragment without allergen marks like <sup><b>[Wz,Mi]</b></sup>."""
    fragment = re.sub(r"<sup\b.*?</sup>", "", fragment, flags=re.S | re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return " ".join(html.unescape(fragment).split())


def parse_menu(page: str):
    """Return (day, meals) of a werkswelt menu page. Each meal: name, prices (student/employee), flags."""
    match = _MENU.search(page)
    if not match:
        raise ValueError("menu section not found on the werkswelt page")
    day = datetime.strptime(match.group(1), "%d.%m.%Y").date()
    meals = []
    for block in re.split(rf"(?:{_BR}\s*){{2,}}", match.group(2), flags=re.I):
        without_details = re.sub(r"<details\b.*?</details>", "", block, flags=re.S | re.I)
        lines = [_text(line) for line in re.split(_BR, without_details, flags=re.I)]
        # Block: label ("Suppe", "Essen 1"), name, prices, icons, optional extras ("Optional: Reis").
        price_index = next((i for i, line in enumerate(lines) if _PRICES.search(line)), None)
        if price_index is None or price_index < 2:
            continue
        name = " ".join(line for line in lines[1:price_index] if line)
        if not name:
            continue
        student, employee = (float(p.replace(",", ".")) for p in _PRICES.search(lines[price_index]).groups())
        meals.append({
            "name": name,
            "prices": {"student": student, "employee": employee},
            "flags": _ICON.findall(block),
        })
    return day, meals


def _fetch(lang: str) -> str:
    response = requests.get(URL, params={"id": LOCATION_ID, "setlang": lang}, timeout=30)
    response.raise_for_status()
    if "charset" not in response.headers.get("Content-Type", "").lower():
        response.encoding = response.apparent_encoding
    return response.text


def mensa_meals(today: date):
    """Today's meals with German and English names. Raises if the German page can't be used."""
    day, german = parse_menu(_fetch("de"))
    if day != today:
        raise ValueError(f"werkswelt shows {day.isoformat()}, not {today.isoformat()}")
    if not german:
        raise ValueError("no meals found on the werkswelt page")
    try:
        day_en, english = parse_menu(_fetch("en"))
        # Both pages list the same meals in the same order; prices tie them together.
        if day_en != day or [m["prices"] for m in english] != [m["prices"] for m in german]:
            raise ValueError("English page doesn't match the German one")
    except Exception as error:
        print(f"Warning: werkswelt English names unavailable: {error}", file=sys.stderr)
        english = german
    return [
        {"name": {"de": de["name"], "en": en["name"]}, "prices": de["prices"], "flags": de["flags"]}
        for de, en in zip(german, english)
    ]
