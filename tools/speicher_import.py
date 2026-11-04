"""Speichermatrix (Excel von Matthias Spies) in die Datenbasis der Speicherauswahl übernehmen.

Aufruf:
    python tools/speicher_import.py Speichermatrix_TT.MM.JJJJ.xlsx [--stammdaten SAP.csv]

Schreibt
  * bosch_flow/daten/speicher.json   – Datenbasis für die Streamlit-Seite
  * speicher.html                    – dieselben Daten eingebettet (Block zwischen den DATEN-Markern)

Gelesen werden die Blätter
  1. „NEU_Zusammenfassung Speicher“  – Kombinationsmatrix Wärmepumpe × Speicher (+, ++, -, (-)*, Kommentare, IM-Links)
  2. „Zusammenfassung_E-Heizer“       – passende E-Heizer je Speicher (E-Muffe, Handlochdeckel, Flansch, CTHK)

Optional: CSV mit Stammdaten je TTNr (Spalten siehe bosch_flow/daten/speicher_stammdaten.csv), z. B. aus SAP.
Maßbilder: bosch_flow/daten/speicher/bilder/<TTNr>.png|jpg – werden automatisch zugeordnet.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import sys
import warnings
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
from bosch_flow.speicher import (BILDER, DATEN, HEIZER_BILDER, STAMMDATEN, STAMMDATEN_FELDER,  # noqa: E402
                                 normname)

HTML = WURZEL / "speicher.html"
MARKE_AN, MARKE_AUS = "/*DATEN-ANFANG*/", "/*DATEN-ENDE*/"

KATEGORIEN = {"puffer": "Pufferspeicher", "ww": "WW-Speicher", "biv": "WW-Speicher biv.", "kombi": "Kombispeicher"}


def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


def _kommentar(c) -> str:
    """Excel-Kommentar ohne Autorzeile und ohne den Hinweistext zu Kommentarthreads."""
    if not c.comment:
        return ""
    t = c.comment.text
    if "Kommentar:" in t:
        t = t.split("Kommentar:", 1)[1]
    else:
        zeilen = t.split("\n")
        if zeilen and zeilen[0].rstrip().endswith(":"):
            zeilen = zeilen[1:]
        t = "\n".join(zeilen)
    return _txt(t)


def _ttnrs(v) -> list[str]:
    return re.findall(r"\b\d{10}\b", _txt(v))


def _kategorie(text: str) -> str:
    t = text.lower()
    if "kombi" in t:
        return "kombi"
    if "puffer" in t:
        return "puffer"
    if "biv" in t:
        return "biv"
    return "ww"


# ---------------------------------------------------------------------------------------------- Blatt 1: Matrix
def lese_matrix(ws):
    # Kopf: Zeile 3 = WP-Familie (verbundene Zellen), Zeile 4 = Baugröße
    familie = {}
    for rng in ws.merged_cells.ranges:
        if rng.min_row == 3 and rng.min_col >= 7:
            for c in range(rng.min_col, rng.max_col + 1):
                familie[c] = _txt(ws.cell(3, rng.min_col).value)
    wps = []
    spalten = []
    for c in range(7, ws.max_column + 1):
        groesse = _txt(ws.cell(4, c).value)
        fam = familie.get(c) or _txt(ws.cell(3, c).value)
        if not groesse:
            continue
        name = groesse if groesse.startswith(fam.split()[0]) else f"{fam} {groesse}"
        wps.append({"id": get_column_letter(c), "familie": fam, "groesse": groesse, "name": name})
        spalten.append(c)

    # Kategorie aus Spalte A (verbunden über mehrere Zeilen)
    kat_zeile = {}
    for rng in ws.merged_cells.ranges:
        if rng.min_col == 1 and rng.min_row >= 5:
            k = _kategorie(_txt(ws.cell(rng.min_row, 1).value))
            for r in range(rng.min_row, rng.max_row + 1):
                kat_zeile[r] = k

    speicher = []
    hinweise = []
    for r in range(5, ws.max_row + 1):
        name = _txt(ws.cell(r, 3).value)
        a = _txt(ws.cell(r, 1).value)
        if a.upper().startswith("HINWEIS"):
            break
        if not name:
            continue
        ttnr_roh = _txt(ws.cell(r, 4).value)
        im = ws.cell(r, 6).hyperlink.target if ws.cell(r, 6).hyperlink else ""
        kombi, notiz = {}, {}
        for wp, c in zip(wps, spalten):
            cell = ws.cell(r, c)
            if _txt(cell.value):
                kombi[wp["id"]] = _txt(cell.value)
            k = _kommentar(cell)
            if k:
                notiz[wp["id"]] = k
        speicher.append({
            "name": name,
            "ttnr": _ttnrs(ttnr_roh),
            "ttnr_hinweis": "" if _ttnrs(ttnr_roh) else ttnr_roh,
            "kategorie": kat_zeile.get(r, "ww"),
            "info": _txt(ws.cell(r, 5).value).strip("()"),
            "alt": _txt(ws.cell(r, 2).value).lower() == "alt",
            "im": im,
            "matrix": True,
            "kombi": kombi,
            "notiz": notiz,
        })
    for r in range(1, ws.max_row + 1):
        for c in (1, 3):
            t = _txt(ws.cell(r, c).value)
            if t.startswith("*"):
                hinweise.append(t)
    return wps, speicher, hinweise


# ---------------------------------------------------------------------------------------------- Blatt 2: E-Heizer
def _heizer_kopf(text: str, typ: str) -> dict:
    """Kopfzelle wie „TTNR: 7735502657 E-Heater 2kW/230V Mindesteinbautiefe: 320 mm“ zerlegen."""
    t = _txt(text)
    ttnr = (_ttnrs(t) or [""])[0]
    tiefe = re.search(r"Mindesteinbautiefe:\s*(\d+)", t)
    leistung = re.search(r"(\d+(?:[.,]\d+)?)\s*kW", t, re.I)
    spannung = re.search(r"(3~\s*)?(\d{3})\s*V", t)
    modell = re.search(r"\b(CTHK \d+|FLHU? \d+(?: M)?)\b", t)
    kw = leistung.group(1).replace(",", ".") if leistung else ""
    volt = (("3~" if spannung.group(1) else "") + spannung.group(2) + " V") if spannung else ""
    bez = modell.group(1) if modell else "E-Heater"
    return {"ttnr": ttnr, "typ": typ, "modell": bez,
            "leistung_kw": float(kw) if kw else None, "spannung": volt,
            "einbautiefe_mm": int(tiefe.group(1)) if tiefe else None,
            "name": f"{bez} {kw.replace('.', ',')} kW / {volt}".strip()}


ZEICHEN = {"ü": "ja", "û": "nein"}
RANG = ["ja", "hzg", "nein"]       # beim Zusammenführen gilt die strengere Angabe


def _status(v) -> str:
    t = _txt(v)
    if t in ZEICHEN:
        return ZEICHEN[t]
    if t.startswith("(") and t.endswith(")"):
        return "hzg"            # „(✓)“: nur für Heizungsunterstützung
    return ""


def lese_heizer(ws):
    heizer: dict[str, dict] = {}
    eintraege: list[dict] = []

    def block(kopfzeile, erste, letzte, gruppen, tiefe_spalten, hd_spalte=None):
        for typ, spalten in gruppen.items():
            for c in spalten:
                h = _heizer_kopf(ws.cell(kopfzeile, c).value, typ)
                h["id"] = f"{typ}:{h['ttnr']}"
                heizer.setdefault(h["id"], h)
        familie = ""
        for r in range(erste, letzte + 1):
            fam = _txt(ws.cell(r, 2).value)
            if fam:
                familie = fam
            name = _txt(ws.cell(r, 4).value)
            if not name:
                continue
            e = {"name": name, "ttnr": _ttnrs(ws.cell(r, 3).value), "produktfamilie": familie,
                 "kategorie": _kategorie(familie), "heizer": {}, "hinweis": ""}
            for feld, c in tiefe_spalten.items():
                if isinstance(ws.cell(r, c).value, (int, float)):
                    e[feld] = int(ws.cell(r, c).value)
            if hd_spalte and _ttnrs(ws.cell(r, hd_spalte).value):
                e["handlochdeckel_ttnr"] = _ttnrs(ws.cell(r, hd_spalte).value)[0]
            for typ, spalten in gruppen.items():
                for c in spalten:
                    s = _status(ws.cell(r, c).value)
                    if s:
                        e["heizer"][f"{typ}:{_heizer_kopf(ws.cell(kopfzeile, c).value, typ)['ttnr']}"] = s
            # Freitext-Hinweis in der Zeile (z. B. HR 200/300)
            for c in range(5, 22):
                t = _txt(ws.cell(r, c).value)
                if len(t) > 25 and not _ttnrs(t):
                    e["hinweis"] = t
            eintraege.append(e)

    # Trinkwasser-Speicher: Zeilen 9–60, Kopf in Zeile 7
    block(7, 9, 60, {"led": range(6, 11), "led_hd": range(13, 18), "flh": range(18, 22)},
          {"tiefe_muffe_mm": 5, "tiefe_handloch_mm": 12}, hd_spalte=11)
    # Pufferspeicher: Zeilen 119–160, Kopf in Zeile 118
    block(118, 119, 160, {"led": range(7, 12), "cthk": range(12, 19)},
          {"tiefe_muffe_mm": 5})

    allg = []
    for r in range(60, 70):
        for c in range(4, 12):
            t = _txt(ws.cell(r, c).value)
            if t.startswith("Hinweis"):
                allg.append(t.replace("Hinweis:", "").strip())
    return heizer, eintraege, allg


# ---------------------------------------------------------------------------------------------- Zusammenführen
def zusammenfuehren(speicher: list[dict], eintraege: list[dict]) -> list[dict]:
    nach_ttnr, nach_name = {}, {}
    for s in speicher:
        for t in s["ttnr"]:
            nach_ttnr[t] = s
        nach_name[normname(s["name"])] = s
    for e in eintraege:
        ziele = [nach_ttnr[t] for t in e["ttnr"] if t in nach_ttnr]
        if not ziele and normname(e["name"]) in nach_name:
            ziele = [nach_name[normname(e["name"])]]
        if not ziele:
            s = {"name": e["name"], "ttnr": e["ttnr"], "ttnr_hinweis": "", "kategorie": e["kategorie"],
                 "info": "", "alt": False, "im": "", "matrix": False, "kombi": {}, "notiz": {}}
            speicher.append(s)
            nach_name[normname(s["name"])] = s
            for t in s["ttnr"]:
                nach_ttnr[t] = s
            ziele = [s]
        for s in ziele:
            neu = {k: v for k, v in e.items() if k not in ("name", "ttnr", "kategorie")}
            if normname(e["name"]) != normname(s["name"]):
                neu["name_heizerliste"] = e["name"]
            alt = s.get("eheizer")
            if alt:     # Speicher steht in beiden Blöcken (Trinkwasser und Puffer): zusammenführen, strengere Angabe gilt
                for hid, st in neu.pop("heizer").items():
                    alt["heizer"][hid] = max(st, alt["heizer"].get(hid, st), key=RANG.index)
                for k, v in neu.items():
                    if v and not alt.get(k):
                        alt[k] = v
            else:
                s["eheizer"] = neu
            for t in e["ttnr"]:
                if t not in s["ttnr"] and len(e["ttnr"]) == 1:
                    s["ttnr"].append(t)
    for s in speicher:
        s["id"] = re.sub(r"[^a-z0-9]+", "-", s["name"].lower()).strip("-")
    return speicher


def stammdaten_laden(pfad: Path) -> dict[str, dict]:
    if not pfad.exists():
        return {}
    daten = {}
    with pfad.open(encoding="utf-8-sig", newline="") as f:
        for z in csv.DictReader(f, delimiter=";"):
            t = (z.get("ttnr") or "").strip()
            if t:
                daten[t] = {k: (z.get(k) or "").strip() for k in STAMMDATEN_FELDER if (z.get(k) or "").strip()}
    return daten


def baue(xlsx: Path, stammdaten: Path) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(xlsx)
    blaetter = {ws.title.lower(): ws for ws in wb.worksheets}
    ws1 = next(ws for t, ws in blaetter.items() if "speicher" in t and "heizer" not in t)
    ws2 = next(ws for t, ws in blaetter.items() if "heizer" in t)
    wps, speicher, hinweise = lese_matrix(ws1)
    heizer, eintraege, allg = lese_heizer(ws2)
    speicher = zusammenfuehren(speicher, eintraege)
    sd = stammdaten_laden(stammdaten)
    for s in speicher:
        for t in s["ttnr"]:
            if t in sd:
                s["daten"] = sd[t]
                break
    stand = re.search(r"(\d{2}\.\d{2}\.\d{4})", xlsx.name)
    return {
        "quelle": xlsx.name,
        "stand": stand.group(1) if stand else "",
        "kategorien": KATEGORIEN,
        "wp": wps,
        "speicher": speicher,
        "heizer": heizer,
        "heizertypen": {"led": "E-Heater LED", "led_hd": "E-Heater LED + Handlochdeckel",
                        "flh": "Flanschheizung FLH", "cthk": "CTHK"},
        "hinweise_matrix": hinweise,
        "hinweise_heizer": allg,
    }


def html_einbetten(daten: dict) -> None:
    """Daten und Bilder in speicher.html einsetzen – die Datei läuft dann ohne Server (offline)."""
    bilder = {}
    for typ, datei in HEIZER_BILDER.items():
        p = DATEN.parent / "speicher" / datei
        if p.exists():
            bilder[f"heizer:{typ}"] = "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()
    if BILDER.exists():
        for p in sorted(BILDER.iterdir()):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                mime = "image/png" if p.suffix.lower() == ".png" else (
                    "image/webp" if p.suffix.lower() == ".webp" else "image/jpeg")
                bilder[p.stem] = f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()
    block = (f"{MARKE_AN}\nconst DATEN = {json.dumps(daten, ensure_ascii=False)};\n"
             f"const BILDER = {json.dumps(bilder)};\n{MARKE_AUS}")
    html = HTML.read_text(encoding="utf-8")
    a, b = html.index(MARKE_AN), html.index(MARKE_AUS) + len(MARKE_AUS)
    HTML.write_text(html[:a] + block + html[b:], encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xlsx", type=Path, nargs="?", help="Speichermatrix (.xlsx); ohne Angabe nur HTML neu einbetten")
    ap.add_argument("--stammdaten", type=Path, default=STAMMDATEN)
    a = ap.parse_args()
    if a.xlsx:
        daten = baue(a.xlsx, a.stammdaten)
        DATEN.write_text(json.dumps(daten, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    else:
        daten = json.loads(DATEN.read_text(encoding="utf-8"))
        sd = stammdaten_laden(a.stammdaten)
        for s in daten["speicher"]:
            s.pop("daten", None)
            for t in s["ttnr"]:
                if t in sd:
                    s["daten"] = sd[t]
                    break
        DATEN.write_text(json.dumps(daten, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    html_einbetten(daten)
    n_wp, n_sp = len(daten["wp"]), len(daten["speicher"])
    print(f"{n_wp} Wärmepumpen, {n_sp} Speicher, {len(daten['heizer'])} E-Heizer → {DATEN.name}, {HTML.name}")


if __name__ == "__main__":
    main()
