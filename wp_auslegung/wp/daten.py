"""Gerätedaten (Leistungskurven), Katalogdaten und Klimadaten (PLZ → Norm-Außentemperatur)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATEN = Path(__file__).resolve().parent.parent / "daten"


@lru_cache(maxsize=None)
def geraete() -> dict:
    return json.loads((DATEN / "geraete.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def katalog() -> dict:
    return json.loads((DATEN / "katalog.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def klima() -> dict:
    return json.loads((DATEN / "klima.json").read_text(encoding="utf-8"))


def plz_suche(plz: str) -> tuple[str, float] | None:
    """(Ort, Norm-Außentemperatur) zur fünfstelligen PLZ oder None."""
    p = "".join(c for c in str(plz) if c.isdigit())
    if len(p) == 4:
        p = "0" + p
    t = klima()["plz"].get(p)
    return (t[0], float(t[1])) if t else None


@lru_cache(maxsize=None)
def bild_uri(name: str | None) -> str | None:
    """Produktbild als data-URI (für Tabellen in Streamlit)."""
    import base64
    if not name:
        return None
    datei = DATEN / "bilder" / f"{name}.jpg"
    return "data:image/jpeg;base64," + base64.b64encode(datei.read_bytes()).decode() if datei.exists() else None


def geraet(gid: str) -> dict | None:
    return next((g for g in geraete()["geraete"] if g["id"] == gid), None)


def serie(sid: str) -> dict | None:
    return next((s for s in geraete()["serien"] if s["id"] == sid), None)
