"""Speicherauswahl Wärmepumpe: WP → zugelassene Speicher → passende E-Heizer (Daten aus der Speichermatrix).

Dieselbe Logik steckt im <script id="logik"> von speicher.html; tests/test_speicher.py vergleicht beide.
Datenbasis: bosch_flow/daten/speicher.json (erzeugt mit tools/speicher_import.py aus der Excel-Matrix).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ORDNER = Path(__file__).parent / "daten"
DATEN = ORDNER / "speicher.json"
STAMMDATEN = ORDNER / "speicher_stammdaten.csv"
BILDER = ORDNER / "speicher" / "bilder"          # Maßbilder aus der IM: <TTNr>.png / .jpg
HEIZER_BILDER = {"led": "heizer_led.jpg", "led_hd": "heizer_handloch.jpg", "flh": "heizer_flh.jpg",
                 "cthk": "heizer_cthk.jpg"}

# Spalten der optionalen Stammdaten-CSV (z. B. aus SAP), Schlüssel ist die TTNr
STAMMDATEN_FELDER = ("ttnr", "volumen_l", "hoehe_mm", "durchmesser_mm", "breite_mm", "tiefe_mm", "kippmass_mm",
                     "gewicht_kg", "waermetauscher_m2", "anschluss_ww", "anschluss_hz", "anschluss_wp",
                     "bemerkung")
STAMMDATEN_TITEL = {"volumen_l": "Volumen (l)", "hoehe_mm": "Höhe (mm)", "durchmesser_mm": "Ø (mm)",
                    "breite_mm": "Breite (mm)", "tiefe_mm": "Tiefe (mm)", "kippmass_mm": "Kippmaß (mm)",
                    "gewicht_kg": "Gewicht (kg)", "waermetauscher_m2": "Wärmetauscher (m²)",
                    "anschluss_ww": "Anschluss WW", "anschluss_hz": "Anschluss HZ", "anschluss_wp": "Anschluss WP",
                    "bemerkung": "Bemerkung"}

DOKU_SUCHE = ("https://bosch-de-de.boschhc-documents.com/td/?query={q}"
              "&sort-type=score&sort-direction=desc&language=de")
WW_HINWEIS = "abweichend bei Wasser-Wasser-Betrieb"


@lru_cache(maxsize=1)
def laden() -> dict:
    return json.loads(DATEN.read_text(encoding="utf-8"))


def normname(name: str) -> str:
    """Speichername vergleichbar machen: „BPU 300-C“ == „BPU 300 C“, „WP 290 EP 1C“ == „WP 290 EP 1 C“."""
    return re.sub(r"[^A-Z0-9]", "", str(name).upper())


def bewertung(code: str) -> tuple[str, str]:
    """Matrix-Eintrag → (Status, Zusatz). Status: ja | bedingt | nein | '' (keine Angabe)."""
    c = re.sub(r"\s+", "", code or "")
    if not c:
        return "", ""
    if "(-)" in c:
        return "bedingt", ("möglich, " if c.startswith("+") else "") + WW_HINWEIS
    if c == "+/++":
        return "ja", "ggf. zwei Speichereinheiten"
    if c == "++":
        return "ja", "zwei Speichereinheiten"
    if c == "+":
        return "ja", ""
    if c == "-":
        return "nein", ""
    return "bedingt", code


def wp_nach_id(wp_id: str, d: dict | None = None) -> dict | None:
    d = d or laden()
    return next((w for w in d["wp"] if w["id"] == wp_id), None)


def speicher_nach_id(sid: str, d: dict | None = None) -> dict | None:
    d = d or laden()
    return next((s for s in d["speicher"] if s["id"] == sid), None)


def speicher_fuer_wp(wp_id: str, alte: bool = True, bedingte: bool = True, katalog: bool = False,
                     d: dict | None = None) -> dict:
    """Alle zugelassenen Speicher einer WP, gruppiert nach Kategorie (Reihenfolge wie in der Matrix).

    katalog=True ergänzt Speicher, die laut Gesamtkatalog freigegeben sind, in der Matrix aber fehlen (quelle "katalog").
    """
    d = d or laden()
    erg = {k: [] for k in d["kategorien"]}
    for s in d["speicher"]:
        if s.get("alt") and not alte:
            continue
        code, quelle = s["kombi"].get(wp_id, ""), "matrix"
        if not code and katalog:
            code, quelle = ((s.get("katalog") or {}).get("kombi") or {}).get(wp_id, ""), "katalog"
        status, zusatz = bewertung(code)
        if status == "ja" or (status == "bedingt" and bedingte):
            erg[s["kategorie"]].append({"id": s["id"], "status": status, "zusatz": zusatz, "code": code,
                                        "notiz": s["notiz"].get(wp_id, ""), "quelle": quelle})
    return erg


def wps_fuer_speicher(sid: str, d: dict | None = None) -> list[dict]:
    """Umkehrung: mit welchen WP ist der Speicher freigegeben? (Matrix, ergänzt um Katalog-Freigaben)"""
    d = d or laden()
    s = speicher_nach_id(sid, d)
    erg = []
    if not s:
        return erg
    kat = (s.get("katalog") or {}).get("kombi") or {}
    for w in d["wp"]:
        code, quelle = s["kombi"].get(w["id"], ""), "matrix"
        if not code:
            code, quelle = kat.get(w["id"], ""), "katalog"
        status, zusatz = bewertung(code)
        if status in ("ja", "bedingt"):
            erg.append({"id": w["id"], "status": status, "zusatz": zusatz, "notiz": s["notiz"].get(w["id"], ""),
                        "quelle": quelle})
    return erg


def abweichungen(sid: str, d: dict | None = None) -> list[dict]:
    """Matrix und Gesamtkatalog widersprechen sich (beide haben einen Eintrag, Bewertung unterschiedlich)."""
    d = d or laden()
    s = speicher_nach_id(sid, d)
    kat = ((s or {}).get("katalog") or {}).get("kombi") or {}
    erg = []
    for w in d["wp"]:
        m, k = s["kombi"].get(w["id"], "") if s else "", kat.get(w["id"], "")
        if m and k and bewertung(m)[0] != bewertung(k)[0]:
            erg.append({"id": w["id"], "matrix": m, "katalog": k})
    return erg


def pakete(wp_id: str | None = None, sid: str | None = None, d: dict | None = None) -> list[dict]:
    """WP-Pakete aus dem Katalog, gefiltert nach Wärmepumpe und/oder Speicher."""
    d = d or laden()
    return [p for p in d.get("pakete", []) if (not wp_id or wp_id in p["wp_ids"])
            and (not sid or sid in p["speicher_ids"])]


def heizer_fuer_speicher(sid: str, d: dict | None = None) -> dict:
    """Passende E-Heizer je Bauart: {typ: [{id, status}]} – status ja | hzg (nur Heizungsunterstützung)."""
    d = d or laden()
    s = speicher_nach_id(sid, d)
    erg = {k: [] for k in d["heizertypen"]}
    eh = (s or {}).get("eheizer") or {}
    for hid, status in eh.get("heizer", {}).items():
        if status in ("ja", "hzg"):
            erg[d["heizer"][hid]["typ"]].append({"id": hid, "status": status})
    for liste in erg.values():
        liste.sort(key=lambda e: (d["heizer"][e["id"]]["leistung_kw"] or 0, d["heizer"][e["id"]]["spannung"]))
    return erg


def suche(text: str, d: dict | None = None) -> list[str]:
    """Speicher nach Name oder TTNr (auch Teilstücke) finden – Ergebnis: Speicher-IDs."""
    d = d or laden()
    q = normname(text)
    if not q:
        return []
    return [s["id"] for s in d["speicher"]
            if q in normname(s["name"]) or any(q in t for t in s["ttnr"])
            or q in normname((s.get("eheizer") or {}).get("name_heizerliste", ""))]


def doku_link(s: dict) -> str:
    q = s["ttnr"][0] if s.get("ttnr") else s["name"]
    return DOKU_SUCHE.format(q=re.sub(r"\s+", "+", q))


def bilder(s: dict) -> list[Path]:
    """Maßbilder: eigene Datei <TTNr>.* (falls abgelegt) vor den Zeichnungen aus dem Gesamtkatalog."""
    if not BILDER.exists():
        return []
    eigene = [p for t in s.get("ttnr", []) + [s["id"]] for p in sorted(BILDER.glob(f"{t}.*"))]
    return eigene[:1] + [BILDER / f"{b}.png" for b in (s.get("katalog") or {}).get("bilder", [])
                         if (BILDER / f"{b}.png").exists()]


def preis_text(wert) -> str:
    """UVP wie im Katalog: 3.073,00 €."""
    if wert is None:
        return ""
    return f"{wert:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
