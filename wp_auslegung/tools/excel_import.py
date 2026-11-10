"""Übernimmt Leistungskurven und Klimadaten aus dem Excel-Werkzeug „WP-Auslegung_S“ (Stand 2.8.3).

    python wp_auslegung/tools/excel_import.py  PFAD/WP-Auslegung_S_2.8.3.xlsm

Schreibt wp_auslegung/daten/geraete.json und wp_auslegung/daten/klima.json und bettet beide (zusammen mit
dem von Hand gepflegten daten/katalog.json) in wp_auslegung/index.html ein (Block zwischen /*DATEN-START*/ und /*DATEN-ENDE*/). Die Excel-Datei selbst
wird nicht eingecheckt.

Je Gerät und Vorlauftemperatur werden die maximale (und, wo vorhanden, minimale) Heizleistung über der
Außentemperatur übernommen. Leere Zellen und Nullwerte gelten als „nicht erfasst“.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string as CI

HIER = Path(__file__).resolve().parent.parent
DATEN = HIER / "daten"

# --------------------------------------------------------------------------------- Serien (Stammdaten)
SERIEN = [
    # Luft/Wasser – Kaskaden wie Navigation im Excel-Werkzeug: CS3800 und CS7400 nicht kaskadierbar
    {"id": "CS3800", "name": "Compress 3800i AW", "quelle": "luft", "bauart": "Monoblock", "kaeltemittel": "R290",
     "eheizer_kw": 9, "kaskade_max": 1,
     "hinweis": "Nicht kaskadierbar. 10 O-T und 13 O-T: Kurven aus dem Excel-Werkzeug, Katalogdaten noch offen."},
    {"id": "CS5800", "name": "Compress 5800i / 6800i AW", "quelle": "luft", "bauart": "Monoblock", "kaeltemittel": "R290",
     "eheizer_kw": 9, "kaskade_max": 2, "hinweis": "E-Heizer bis 9 kW, 2er-Kaskade."},
    {"id": "CS8800", "name": "Compress 8800i AW", "quelle": "luft", "bauart": "Monoblock", "kaeltemittel": "R290",
     "eheizer_kw": 9, "kaskade_max": 2, "hinweis": "E-Heizer bis 9 kW, 2er-Kaskade."},
    {"id": "CS5001", "name": "Compress 5000 AW (CS5001AW)", "quelle": "luft", "bauart": "Monoblock (Großanlage)",
     "kaeltemittel": "R290", "eheizer_kw": None, "kaskade_max": 14,
     "hinweis": "Großanlage, Kaskade bis 14 Geräte mit HPC 301 C. Zweiter Wärmeerzeuger/Heizstab bauseits."},
    {"id": "CS7000", "name": "Compress 7000i AW", "quelle": "luft", "bauart": "Monoblock", "kaeltemittel": "R410A",
     "eheizer_kw": None, "kaskade_max": 2, "hinweis": "2er-Kaskade."},
    {"id": "CS7400", "name": "Compress 7400i AW", "quelle": "luft", "bauart": "Monoblock", "kaeltemittel": "R32",
     "eheizer_kw": None, "kaskade_max": 1, "hinweis": "Nicht kaskadierbar."},
    # Sole/Wasser – aus dem Gesamtkatalog März 2026 (nicht im Excel-Werkzeug)
    {"id": "CS7800LW", "name": "Compress 7800i LW", "quelle": "sole", "bauart": "Sole/Wasser, Innenaufstellung",
     "kaeltemittel": "R410A", "eheizer_kw": 9, "kaskade_max": 1,
     "hinweis": "Max. Heizleistung B0/W35 laut Katalog; bei 55 °C Nennwärmeleistung (ErP) angesetzt. "
                "Ausführungen M (mit WW-Speicher), MB und F siehe Katalog."},
    {"id": "SupraecoT", "name": "Supraeco T (T-2)", "quelle": "sole", "bauart": "Sole/Wasser, 2 Verdichter",
     "kaeltemittel": "R410A", "eheizer_kw": None, "kaskade_max": 1,
     "hinweis": "Heizleistung B0/W35 und B0/W45 nach EN 14511 (2 Verdichter); bei 55 °C Nennwärmeleistung (ErP). "
                "Zuheizer EZH 42 als Zubehör."},
]

# Sole/Wasser: Heizleistung praktisch unabhängig von der Außentemperatur (Sole ca. 0 °C) – konstante Kurven.
# (Gerät, Serie, {Vorlauf: max. kW}, min. kW (Modulation) oder None)
SOLE = [
    ("CS7800iLW 6", "CS7800LW", {35: 6.0, 55: 5.0}, 2.0), ("CS7800iLW 8", "CS7800LW", {35: 8.0, 55: 7.0}, 2.0),
    ("CS7800iLW 12", "CS7800LW", {35: 12.0, 55: 11.0}, 3.0), ("CS7800iLW 16", "CS7800LW", {35: 15.0, 55: 14.0}, 4.0),
    ("Supraeco T 220-2", "SupraecoT", {35: 22.9, 45: 23.05, 55: 21.0}, 11.83),
    ("Supraeco T 280-2", "SupraecoT", {35: 29.3, 45: 29.25, 55: 29.0}, 15.21),
    ("Supraeco T 380-2", "SupraecoT", {35: 38.7, 45: 38.53, 55: 38.0}, 20.48),
    ("Supraeco T 480-2", "SupraecoT", {35: 47.37, 45: 47.27, 55: 47.0}, 25.28),
]


def sole_geraete() -> list[dict]:
    out = []
    for gid, serie, q, qmin in SOLE:
        g = {"id": gid, "serie": serie, "kurz": gid.split()[-1],
             "max": {str(v): [[-25.0, kw], [40.0, kw]] for v, kw in q.items()},
             "min": {str(v): [[-25.0, qmin], [40.0, qmin]] for v in q} if qmin else None}
        out.append(g)
    return out


# Blöcke: (Blatt, Spalte Außentemperatur, erste Zeile, letzte Zeile, Vorlauf, {Spalte: (Serie, Gerät, max|min)})
# Bei „min“ ist Gerät eine Liste: die Mindestleistung gilt für alle genannten Geräte.
S38S = ["CS3800iAW 4 O-S", "CS3800iAW 6 O-S", "CS3800iAW 7 O-S"]
S38T = ["CS3800iAW 10 O-T", "CS3800iAW 13 O-T"]
S58S = ["CS5800/6800iAW 4 OR-S", "CS5800/6800iAW 5 OR-S", "CS5800/6800iAW 7 OR-S"]
S58T = ["CS5800/6800iAW 10 OR-T", "CS5800/6800iAW 12 OR-T"]
S88 = ["CS8800iAW 11 O-T", "CS8800iAW 13 O-T", "CS8800iAW 15 O-T"]
S70 = ["CS7000iAW 5", "CS7000iAW 7", "CS7000iAW 9", "CS7000iAW 13", "CS7000iAW 17"]
S74 = ["CS7400iAW 5", "CS7400iAW 7"]


def _mx(serie, namen, spalten):
    return {s: (serie, n, "max") for s, n in zip(spalten, namen)}


BLOECKE = []
# CS8800 (Blatt LWP_Propan)
BLOECKE.append(("LWP_Propan", "BX", 10, 45, 35, {**_mx("CS8800", S88[:2], ["BY", "BZ"])}))
BLOECKE.append(("LWP_Propan", "CJ", 10, 45, 35, {"CK": ("CS8800", S88[2], "max"), "CL": ("CS8800", S88, "min")}))
for vl, (r0, r1) in {45: (71, 106), 55: (130, 165), 65: (178, 213)}.items():
    BLOECKE.append(("LWP_Propan", "BX", r0, r1, vl,
                    {**_mx("CS8800", S88, ["BY", "BZ", "CA"]), "CB": ("CS8800", S88, "min")}))
# CS5001 (Blatt LWP_Propan, ab -22 °C)
for i, vl in enumerate((35, 45, 55, 65)):
    c = lambda s: openpyxl.utils.get_column_letter(CI(s) + i)  # noqa: E731
    BLOECKE.append(("LWP_Propan", "BX", 406, 468, vl, {
        c("CC"): ("CS5001", "CS5001 AW22", "max"), c("CG"): ("CS5001", ["CS5001 AW22"], "min"),
        c("CK"): ("CS5001", "CS5001 AW42", "max"), c("CO"): ("CS5001", ["CS5001 AW42"], "min")}))
# CS5800/6800 (Blatt LWP_Propan_2)
BLOECKE.append(("LWP_Propan_2", "BX", 10, 45, 35, {**_mx("CS5800", S58S[:2], ["BY", "BZ"]),
                                                    "CH": ("CS5800", S58S, "min")}))
BLOECKE.append(("LWP_Propan_2", "CJ", 10, 45, 35, {**_mx("CS5800", [S58S[2]] + S58T, ["CK", "CL", "CM"]),
                                                    "CO": ("CS5800", S58T, "min")}))
for vl, (r0, r1) in {45: (71, 106), 55: (130, 165)}.items():
    BLOECKE.append(("LWP_Propan_2", "BX", r0, r1, vl, {**_mx("CS5800", S58S + S58T, ["BY", "BZ", "CA", "CB", "CC"]),
                                                       "CD": ("CS5800", S58S, "min"), "CE": ("CS5800", S58T, "min")}))
# CS3800 (Blatt LWP_Propan_2, ab -22 °C)
for vl, (r0, r1) in {35: (232, 274), 45: (287, 329), 55: (344, 386)}.items():
    BLOECKE.append(("LWP_Propan_2", "BX", r0, r1, vl, {**_mx("CS3800", S38S, ["BY", "BZ", "CA"]),
                                                       "CB": ("CS3800", S38S, "min"),
                                                       **_mx("CS3800", S38T, ["CC", "CD"]),
                                                       "CE": ("CS3800", S38T, "min")}))
# CS7400 / CS7000 (Blatt LWP, ab -20 °C)
BLOECKE.append(("LWP", "BX", 10, 45, 35, _mx("CS7400", S74, ["BY", "BZ"])))
BLOECKE.append(("LWP", "CJ", 10, 45, 35, _mx("CS7000", S70, ["CK", "CL", "CM", "CN", "CO"])))
for vl, (r0, r1) in {45: (71, 106), 55: (130, 165)}.items():
    BLOECKE.append(("LWP", "BX", r0, r1, vl, _mx("CS7000", S70, ["BY", "BZ", "CA", "CB", "CC"])))
    BLOECKE.append(("LWP", "CN", r0, r1, vl, _mx("CS7400", S74, ["CO", "CP"])))

def _kurz(name: str) -> str:
    """„CS3800iAW 7 O-S“ -> „7 O-S“, „CS5001 AW22“ -> „AW 22“."""
    if name.startswith("CS5001"):
        return "AW " + name.split("AW", 1)[1]
    return name.split("AW", 1)[1].strip()


def _zahl(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def lese(pfad: Path) -> tuple[dict, dict]:
    wb = openpyxl.load_workbook(pfad, read_only=True, data_only=True)
    blaetter: dict[str, dict] = {}

    def zelle(blatt: str, spalte: str, zeile: int):
        if blatt not in blaetter:
            g = {}
            for row in wb[blatt].iter_rows(min_row=1, max_row=480, min_col=CI("BX"), max_col=CI("ER")):
                for c in row:
                    if getattr(c, "value", None) is not None:
                        g[(c.row, c.column)] = c.value
            blaetter[blatt] = g
        return blaetter[blatt].get((zeile, CI(spalte)))

    geraete: dict[str, dict] = {}
    for blatt, tsp, r0, r1, vl, spalten in BLOECKE:
        for sp, (serie, name, art) in spalten.items():
            punkte = []
            for r in range(r0, r1 + 1):
                t, q = zelle(blatt, tsp, r), _zahl(zelle(blatt, sp, r))
                if isinstance(t, (int, float)) and q is not None:
                    punkte.append([float(t), round(q, 4)])
            if not punkte:
                continue
            for n in (name if isinstance(name, list) else [name]):
                g = geraete.setdefault(n, {"id": n, "serie": serie, "max": {}, "min": {}})
                if art == "max" and isinstance(name, str):
                    g["max"][str(vl)] = punkte
                elif art == "min":
                    g["min"][str(vl)] = punkte

    # VDI 4650 (Blatt LWP_Propan, ED7:EF87): Leistungsanteil % -> Deckungsanteil Luft/Wasser parallel
    vdi, vdi_sole = [], []
    for row in wb["LWP_Propan"].iter_rows(min_row=7, max_row=87, min_col=CI("ED"), max_col=CI("EF"), values_only=True):
        if isinstance(row[0], (int, float)):
            vdi.append([int(row[0]), round(float(row[2]), 4)])
            vdi_sole.append([int(row[0]), round(float(row[1]), 4)])
    vdi.sort()
    vdi_sole.sort()

    # Klimadaten: PLZ -> Ort, Norm-Außentemperatur
    plz = {}
    for row in wb["Klimadaten"].iter_rows(min_row=4, max_col=3, values_only=True):
        p, ort, t = row
        if isinstance(p, (int, float)) and p > 0 and isinstance(t, (int, float)):
            plz.setdefault(f"{int(p):05d}", [str(ort or "").strip(), float(t)])

    geraete_liste = []
    reihenfolge = {s["id"]: i for i, s in enumerate(SERIEN)}
    for g in geraete.values():
        if not g["max"]:
            continue
        g["kurz"] = _kurz(g["id"])
        g["min"] = g["min"] or None
        geraete_liste.append(g)
    geraete_liste.sort(key=lambda g: (reihenfolge[g["serie"]], _nenn(g)))
    geraete_liste += sole_geraete()

    stand = date.today().isoformat()
    daten = {"quelle": f"Excel-Werkzeug {pfad.name}", "stand": stand, "serien": SERIEN,
             "geraete": geraete_liste, "vdi4650_luft_parallel": vdi, "vdi4650_sole_parallel": vdi_sole}
    klima = {"quelle": f"{pfad.name}, Blatt Klimadaten", "stand": stand, "plz": dict(sorted(plz.items()))}
    return daten, klima


def _nenn(g) -> float:
    """Sortierschlüssel: Heizleistung bei A-7 und höchstem gemeinsamen Vorlauf."""
    kurve = g["max"].get("55") or next(iter(g["max"].values()))
    return min(kurve, key=lambda p: abs(p[0] + 7))[1]


def einbetten(daten: dict, klima: dict) -> None:
    html = HIER / "index.html"
    if not html.exists():
        return
    text = html.read_text(encoding="utf-8")
    a, b = "/*DATEN-START*/", "/*DATEN-ENDE*/"
    i, j = text.index(a) + len(a), text.index(b)
    block = ("\nconst GERAETE_DATEN = " + json.dumps(daten, ensure_ascii=False, separators=(",", ":")) +
             ";\nconst KATALOG_DATEN = " + json.dumps(_katalog(), ensure_ascii=False, separators=(",", ":")) +
             ";\nconst KLIMA_DATEN = " + json.dumps(klima, ensure_ascii=False, separators=(",", ":")) + ";\n")
    html.write_text(text[:i] + block + text[j:], encoding="utf-8")


def _katalog() -> dict:
    """Katalogdaten (Bestell-Nr., UVP, technische Daten) – von Hand gepflegt in daten/katalog.json."""
    return json.loads((DATEN / "katalog.json").read_text(encoding="utf-8"))


def schreibe(daten: dict, klima: dict) -> None:
    DATEN.mkdir(exist_ok=True)
    (DATEN / "geraete.json").write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATEN / "klima.json").write_text(json.dumps(klima, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    einbetten(daten, klima)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--nur-einbetten":   # z. B. nach Änderung von katalog.json
        einbetten(json.loads((DATEN / "geraete.json").read_text(encoding="utf-8")),
                  json.loads((DATEN / "klima.json").read_text(encoding="utf-8")))
        sys.exit(0)
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    d, k = lese(Path(sys.argv[1]))
    schreibe(d, k)
    print(f"{len(d['geraete'])} Geräte, {len(k['plz'])} PLZ übernommen.")
