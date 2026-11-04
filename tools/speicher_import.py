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


# ---------------------------------------------------------------------------------------------- Katalog
KATALOG = DATEN.parent / "speicher_katalog.json"
KERN = [("volumen_l", ("Speichervolumen", "Speicherinhalt gesamt", "Nenninhalt", "Nutzinhalt", "Inhalt")),
        ("hoehe_mm", ("Höhe", "Höhe mit Isolierung", "Höhe inkl. Isolierung")),
        ("durchmesser_mm", ("Durchmesser, mit Wärmedämmung", "Durchmesser mit Isolierung", "Durchmesser",
                            "Durchmesser inkl. Isolierung")),
        ("kippmass_mm", ("Kippmaß", "Kipphöhe")),
        ("gewicht_kg", ("Nettogewicht", "Gewicht (leer)", "Gewicht leer", "Leergewicht", "Gewicht"))]


def wp_zuordnen(gruppe: str, label: str, wps: list[dict]) -> list[str]:
    """WP-Bezeichnung aus dem Katalog („AW 7 OR-S (CS6800i AW 12 E/MB)“) → Spalten-IDs der Matrix."""
    t = re.sub(r"\d\)|\*", "", f"{label}").replace("…", "...")
    g = re.sub(r"\d\)|\*", "", gruppe)
    nach = {(w["familie"], str(w["groesse"]).strip()): w["id"] for w in wps}

    def fam(teil: str) -> str:
        return next((w["familie"] for w in wps if teil in w["familie"].replace(" ", "")), "")

    m = re.search(r"CS8800iAW (\d+)", t)
    if m:
        return [nach.get((fam("CS8800iAW"), f"{m.group(1)} O-T"))]
    m = re.search(r"^AW (\d+) OR-([ST])", t)
    if m and re.search(r"[56]800", g + t):
        return [nach.get((fam("CS58/6800i"), f"{m.group(1)} OR-{m.group(2)}"))]
    m = re.search(r"CS3800iAW (\d+) O-([ST])", t)
    if m:
        return [nach.get((fam("CS3800iAW"), f"{m.group(1)} O-{m.group(2)}"))]
    m = re.search(r"CS ?7\.\.\.i ?AW (\d+) ORE", t)
    if m:
        return [nach.get((fam("CS7...iAW".replace("...", "…")), m.group(1)))]
    m = re.search(r"CS5001 ?AW (\d+)", t)
    if m:
        return [nach.get((fam("CS5001AW"), m.group(1)))]
    m = re.search(r"CS5000 ?AW (\d+)", t)
    if m:
        return [nach.get((fam("CS5000AW"), "22 O" if m.group(1) == "22" else "38 OR"))]
    m = re.search(r"CS780[01]i ?L?W (\d+)", t)
    if m:     # Matrix führt 13/17, der Katalog 12/16
        groesse = {"12": "13", "16": "17"}.get(m.group(1), m.group(1))
        return [nach.get((fam("CS7801iLW"), groesse))]
    m = re.search(r"(?:STM/)?STE (\d+)-1", t)
    if m:
        return [nach.get((fam("STM/STE"), f"{m.group(1)}-1"))]
    m = re.search(r"^T (\d+)-2", t)
    if m:
        return [nach.get(("T", f"T {m.group(1)}-2"))]
    return []


def katalog_code(code: str) -> str:
    """Fußnotenzeichen entfernen, „(-)“-Fußnote als „(-)*“ wie in der Matrix."""
    c = re.sub(r"\s+", "", code)
    c = re.sub(r"(\(-\))\d\)", r"\1*", c)
    c = re.sub(r"\d\)$", "", c).rstrip("*") if "(-)" not in c else c
    return c


def _kategorie_katalog(titel: str, name: str) -> str:
    n = name.upper()
    if re.match(r"^(CST|BPU|SP )", n):
        return "kombi"
    if re.match(r"^(B|BH|BS|BSH|BP|BST|BTHC|BBS)\s?\d", n):
        return "puffer"
    if re.match(r"^(WS|WPS)\s?\d", n):
        return "biv"
    return "ww"


def katalog_einbinden(daten: dict, pfad: Path = KATALOG) -> None:
    """Katalogdaten (tools/katalog_import.py) je TTNr an die Speicher hängen; fehlende Speicher ergänzen."""
    daten["speicher"] = [s for s in daten["speicher"] if not s.get("nur_katalog")]
    for s in daten["speicher"]:
        s.pop("katalog", None)
    daten.pop("katalog_quelle", None)
    if not pfad.exists():
        return
    kat = json.loads(pfad.read_text(encoding="utf-8"))
    quellen = kat.get("quellen") or [{"quelle": kat["quelle"], "stand": ""}]
    daten["katalog_quelle"] = " + ".join(q["quelle"] for q in quellen)
    nach_ttnr = {t: s for s in daten["speicher"] for t in s["ttnr"]}
    preise = {}
    for fam in kat["familien"]:                  # Reihenfolge: ältester Katalog zuerst → neuester Preis gewinnt
        for z in fam["zubehoer"]:
            preise[z["ttnr"]] = z["preis"]
    for h in daten["heizer"].values():
        h["preis"] = preise.get(h["ttnr"])
    for fam in kat["familien"]:
        for p in fam["produkte"]:
            werte, konflikte, kombi = [], [], {}
            for tab in fam["tabellen"]:
                spalten = [sp["name"] for sp in tab["spalten"] if p["ttnr"] in sp["ttnr"]]
                if not spalten:
                    continue
                # CS7801i vor CS7800i (die Matrix führt die 7801i-Reihe)
                for z in sorted(tab["zeilen"], key=lambda z: "7800i" in z["label"].replace(" ", "")):
                    v = z["werte"].get(spalten[0])
                    if v is None:
                        continue
                    if tab["art"] == "kombination":
                        for wid in wp_zuordnen(z["gruppe"], z["label"], daten["wp"]):
                            if wid:
                                kombi.setdefault(wid, katalog_code(v))
                        continue
                    if v in ("-", "–"):
                        continue
                    alt = next((w for w in werte if (w["label"], w["einheit"]) == (z["label"], z["einheit"])
                                and (w["kz"] == z["kz"] or not (w["kz"] and z["kz"]))), None)
                    if alt and alt["wert"] == v:
                        continue
                    if alt and any(z["label"] in namen for _, namen in KERN):
                        konflikte.append(f'{z["label"]}: {alt["wert"]} bzw. {v} {z["einheit"]}'.strip())
                        continue
                    werte.append({"label": z["label"], "kz": z["kz"], "einheit": z["einheit"], "wert": v})
            kern = {}
            for feld, namen in KERN:
                for n in namen:
                    w = next((w for w in werte if w["label"] == n and w["wert"]), None)
                    if w:
                        kern[feld] = w["wert"]
                        break
            info = {"typ": p["typ"], "familie": fam["titel"], "seite": fam["seite"], "preis": p["preis"],
                    "quelle": fam.get("quelle", kat.get("quelle", "")), "stand": fam.get("stand", ""),
                    "neu": fam.get("neu", False), "verfuegbar_ab": fam.get("verfuegbar_ab", ""),
                    "text": p["text"], "beschreibung": fam["beschreibung"], "bilder": fam.get("bilder", []), "kern": kern,
                    "werte": werte, "konflikte": konflikte, "kombi": kombi, "hinweise": fam["hinweise"],
                    "zubehoer": [{k: z[k] for k in ("typ", "text", "ttnr", "preis")} for z in fam["zubehoer"]]}
            s = nach_ttnr.get(p["ttnr"])
            if not s:
                s = {"id": re.sub(r"[^a-z0-9]+", "-", p["typ"].lower()).strip("-"), "name": p["typ"],
                     "ttnr": [p["ttnr"]], "ttnr_hinweis": "", "kategorie": _kategorie_katalog(fam["titel"], p["typ"]),
                     "info": "", "alt": False, "im": "", "matrix": False, "nur_katalog": True, "kombi": {}, "notiz": {}}
                daten["speicher"].append(s)
                nach_ttnr[p["ttnr"]] = s
            vorher = s.get("katalog")
            if vorher:                      # neuerer Katalog: Angaben ersetzen, alten Preis merken
                if vorher["preis"] != info["preis"]:
                    info["preis_vorher"] = {"preis": vorher["preis"], "stand": vorher["stand"]}
                info["bilder"] = info["bilder"] or vorher["bilder"]
                for k in ("kombi", "hinweise"):
                    info[k] = info[k] or vorher[k]
            s["katalog"] = info
    # Zubehörpreise im Speicher auf den neuesten Stand
    for s in daten["speicher"]:
        for z in (s.get("katalog") or {}).get("zubehoer", []):
            z["preis"] = preise.get(z["ttnr"], z["preis"])
    # E-Heizer aus dem Katalog-Zubehör, wo die E-Heizer-Liste nichts sagt (z. B. neue BP ...-7)
    typ_nach_ttnr = {}
    for hid, h in daten["heizer"].items():
        if h["typ"] != "led_hd":
            typ_nach_ttnr.setdefault(h["ttnr"], hid)
    for s in daten["speicher"]:
        if s.get("eheizer") or not s.get("katalog"):
            continue
        hz = {typ_nach_ttnr[z["ttnr"]]: "ja" for z in s["katalog"]["zubehoer"] if z["ttnr"] in typ_nach_ttnr}
        if hz:
            s["eheizer"] = {"heizer": hz, "quelle": "katalog", "hinweis":
                            "Nicht in der E-Heizer-Liste – E-Heizer aus dem Katalog-Zubehör übernommen. "
                            "Einbautiefe und Muffe am Speicher prüfen."}



# ---------------------------------------------------------------------------------------------- Nachbearbeitung
TIPPFEHLER_EXCEL = {"je anch Verwendung": "je nach Verwendung"}

# Neue Speichergeneration (-7): Vorgänger → Nachfolger. Zuordnung über die im Katalog wortgleichen
# Produktbeschreibungen (z. B. BH …-6 ERZ und BP …-7 ERZ: „Schichtladeeinheit mit 2 Rücklaufanschlüssen,
# Diffusorstab … 1 Trennblech“).
NACHFOLGER = [(r"^BH (\d+)-6 ERZ", "BP {}-7 ERZ 1"), (r"^BSH (\d+)-6 ERZ", "BPS {}-7 ERZ 1"),
              (r"^B (\d+)-6 ER\b", "BP {}-7 EMR 1"), (r"^BS (500)-6 ER\b", "BPS {}-7 ER 1"),
              (r"^BH (\d+)-6 (?:PN6 )?1 B", "BP {}-7 EM 1"),
              # laut M. Spies: WP … EP 1C sind die Nachfolger der WH … LP 1 B (bis auf ca. 2 cm / 3–4 l identisch)
              (r"^WH (290|370) LP 1 B", "WP {} EP 1C")]
NAHEZU_GLEICH = "laut Matthias Spies bis auf ca. 2 cm und 3–4 l identisch"

# Erklärungen zu Begriffen aus den Matrix-Kommentaren (Schlüssel = Textstück im Kommentar)
ERKLAERUNGEN = {
    "4-Punkt": "4-Punkt-Anbindung (Trennpuffer): Der Puffer hat vier Anschlüsse, zwei für den Wärmepumpenkreis "
               "(Vor- und Rücklauf) und zwei für den Heizkreis. Er entkoppelt beide Kreise hydraulisch, ähnlich wie "
               "eine hydraulische Weiche. Jeder Kreis braucht dann eine eigene Pumpe.",
    "Pendelpuffer": "Pendelpuffer bzw. Reihenpuffer (2-Punkt): Der Puffer liegt nur in einer Leitung, meist im "
                    "Rücklauf, und das Wasser „pendelt“ durch. Er vergrößert das Anlagenvolumen, trennt die Kreise "
                    "aber nicht. Der BST 50 ist so ein Speicher.",
}

# Bestätigte Regeln zur Matrix (Rückmeldung Matthias Spies)
HINWEISE_FREIGABE = [
    "Leere Matrixzelle: nicht geprüft und nicht freigegeben.",
    "Generation -7: Freigaben von Matthias Spies und Michael aus Planererfahrung angepasst – "
    "Abweichungen zur Vorgängergeneration -6 sind gewollt.",
]


def nachbearbeiten(daten: dict) -> None:
    """Namen nach Katalog, Tippfehler, Nachfolger (-7) und WP-Pakete."""
    # PF solar: laut Matthias Spies nicht betrachten (nicht mehr im Programm)
    daten["speicher"] = [s for s in daten["speicher"] if not re.match(r"^PF \d+ solar", s.get("name_excel") or s["name"])]
    sp = daten["speicher"]
    for s in sp:
        s["info"] = TIPPFEHLER_EXCEL.get(s.get("info", ""), s.get("info", ""))
        s["name"] = s.pop("name_excel", s["name"])      # wiederholbar: Ausgangsname aus der Excel
        k = s.get("katalog")
        # offizieller Name aus der Bestelltabelle, wenn die Excel nur anders schreibt (gleiche TTNr)
        if k and len(s["ttnr"]) == 1 and normname(k["typ"]) != normname(s["name"]):
            s["name_excel"], s["name"] = s["name"], k["typ"]
    nach_name = {normname(s["name"]): s for s in sp}
    for s in sp:
        s.pop("nachfolger", None)
        s.pop("vorgaenger", None)
    for s in sp:
        for muster, ziel in NACHFOLGER:
            m = re.match(muster, s.get("name_excel") or s["name"])
            neu = m and nach_name.get(normname(ziel.format(m.group(1))))
            if neu:
                s["nachfolger"] = neu["id"]
                neu.setdefault("vorgaenger", []).append(s["id"])
                break
    # Nachfolger ohne Katalogdaten (WP 290/370 EP 1C): Maße, Zeichnung und E-Heizer vom Vorgänger
    for s in sp:
        if s.get("katalog") or not s.get("vorgaenger"):
            continue
        alt = next((a for a in sp if a["id"] in s["vorgaenger"] and a.get("katalog")), None)
        if alt:
            s["katalog"] = {**alt["katalog"], "preis": None, "kombi": {}, "konflikte": [], "zubehoer": [],
                            "von_vorgaenger": alt["name"], "von_vorgaenger_hinweis": NAHEZU_GLEICH}
            s["katalog"].pop("preis_vorher", None)
            if not s.get("eheizer") and alt.get("eheizer"):
                s["eheizer"] = {**alt["eheizer"], "quelle": "vorgaenger",
                                "hinweis": f"E-Heizer vom Vorgänger {alt['name']} übernommen ({NAHEZU_GLEICH})."}
    # Daten aus Installationsanleitungen (bosch_flow/daten/speicher_im.json)
    im_pfad = DATEN.parent / "speicher_im.json"
    if im_pfad.exists():
        im = json.loads(im_pfad.read_text(encoding="utf-8"))
        nach_typ = {p_["typ"]: p_ for p_ in im["produkte"]}
        for s in sp:
            s.pop("name_im", None)
            ziel = im["matrix_alias"].get(s.get("name_excel") or s["name"])
            treffer = nach_typ.get(ziel) if ziel else next(
                (p_ for p_ in im["produkte"] if p_["ttnr"] in s["ttnr"] or p_["ttnr_ippc"] in s["ttnr"]), None)
            if not treffer:
                continue
            s["name_im"] = treffer["typ"]
            s["im"] = s.get("im") or im["link"]
            if ziel:      # Matrix-Speicher ohne Katalogdaten: Daten, Maßbild und TTNr aus der IM
                s["ttnr"], s["ttnr_hinweis"] = [treffer["ttnr"], treffer["ttnr_ippc"]], ""
                s["katalog"] = {"typ": treffer["typ"], "familie": im["titel"], "seite": im["seite"], "preis": None,
                                "quelle": im["quelle"], "stand": im["stand"], "neu": False, "verfuegbar_ab": "",
                                "text": "", "beschreibung": im["beschreibung"], "bilder": [im["bild"]],
                                "kern": treffer["kern"], "werte": treffer["werte"], "konflikte": [], "kombi": {},
                                "hinweise": im["hinweise"], "zubehoer": [], "aus_im": True}
    # E-Heizer-Ergänzungen von Matthias Spies (bosch_flow/daten/speicher_eheizer_ergaenzung.json)
    eh_pfad = DATEN.parent / "speicher_eheizer_ergaenzung.json"
    if eh_pfad.exists():
        eh = json.loads(eh_pfad.read_text(encoding="utf-8"))
        for regel in eh["regeln"]:
            for s in sp:
                m = re.match(regel["muster"], s["name"])
                if not m:
                    continue
                vol = m.group(1)
                s["eheizer"] = {"heizer": {h: (st if isinstance(st, str) else st.get(vol, "nein"))
                                           for h, st in regel["heizer"].items()},
                                "tiefe_muffe_mm": regel["tiefe_muffe_mm"][vol], "quelle": "spies",
                                "hinweis": regel["hinweis"], "herkunft": eh["quelle"]}
        daten["hinweise_eheizer_ergaenzung"] = eh.get("abweichungen", [])
    # Plausibilität: freigegebener Heizer länger als die max. Eintauchtiefe?
    for s in sp:
        e = s.get("eheizer") or {}
        e.pop("zu_lang", None)
        for hid, st in e.get("heizer", {}).items():
            h = daten["heizer"].get(hid)
            grenze = e.get("tiefe_handloch_mm") if h and h["typ"] == "led_hd" else e.get("tiefe_muffe_mm")
            if st in ("ja", "hzg") and h and h["typ"] in ("led", "led_hd", "cthk") and grenze and h["einbautiefe_mm"] > grenze:
                e.setdefault("zu_lang", []).append(hid)
    # Kommentare „… bei allen Leistungen“ gelten für die ganze Baureihe (nicht nur die kommentierte Zelle)
    familie = {w["id"]: w["familie"] for w in daten["wp"]}
    for s in sp:
        for wid in s.pop("notiz_baureihe", []):         # wiederholbar: übertragene Kommentare zuerst entfernen
            s["notiz"].pop(wid, None)
        for wid, text in list(s.get("notiz", {}).items()):
            if "allen Leistungen" not in text:
                continue
            for w in daten["wp"]:
                if familie[w["id"]] == familie[wid] and w["id"] not in s["notiz"] and s["kombi"].get(w["id"]):
                    s["notiz"][w["id"]] = text
                    s.setdefault("notiz_baureihe", []).append(w["id"])
    daten["erklaerungen"] = ERKLAERUNGEN
    daten["erklaerung_einleitung"] = "Die Kommentare „4-Punkt-Anbindung“ und „Pendelpuffer“ in der Matrix beschreiben, wie der Pufferspeicher hydraulisch eingebunden wird:"
    daten["hinweise_freigabe"] = HINWEISE_FREIGABE
    for s in sp:
        s.pop("hinweis_matrix", None)
        if s.get("matrix") and re.search(r"-7\b", s["name"]):
            s["hinweis_matrix"] = HINWEISE_FREIGABE[1]
    # WP-Pakete aus dem Katalog
    daten["pakete"] = []
    if KATALOG.exists():
        for pk in json.loads(KATALOG.read_text(encoding="utf-8")).get("pakete", []):
            wp = re.sub(r"O[A-Z]-([ST])$", r"O-\1", pk["wp"])
            wids = [w for w in wp_zuordnen("", wp, daten["wp"]) if w]
            sids = []
            for name in pk["speicher"]:
                n = normname(name)
                treffer = [s["id"] for s in sp if normname(s["name"]) == n] or \
                          [s["id"] for s in sp if normname(s["name"]).startswith(n) and not s.get("alt")]
                if treffer:
                    sids.append(treffer[0])
            daten["pakete"].append({**pk, "wp_ids": wids, "speicher_ids": sids})

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
    katalog_einbinden(daten)
    nachbearbeiten(daten)
    DATEN.write_text(json.dumps(daten, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    html_einbetten(daten)
    n_wp, n_sp = len(daten["wp"]), len(daten["speicher"])
    print(f"{n_wp} Wärmepumpen, {n_sp} Speicher, {len(daten['heizer'])} E-Heizer → {DATEN.name}, {HTML.name}")


if __name__ == "__main__":
    main()
