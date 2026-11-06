"""Bosch-Gesamtkatalog (Kapitel Speicher, PDF) für die Speicherauswahl auslesen.

Aufruf (mehrere Kataloge: ältester zuerst, spätere Angaben haben Vorrang):
    python tools/katalog_import.py Speicher_..._2026-03_..._Gesamtkatalog.pdf EK_Speicher_..._2026-07_..._Ergaenzungskatalog.pdf
    python tools/speicher_import.py Speichermatrix_TT.MM.JJJJ.xlsx      # führt Matrix und Katalog zusammen

Schreibt
  * bosch_flow/daten/speicher_katalog.json  – je Produktfamilie: Produkte (TTNr, Preis), technische Daten,
                                              Anschlüsse, Kombinationstabellen, Zubehör, Fußnoten, Seite
  * bosch_flow/daten/speicher/bilder/<familie>.png – Maßzeichnung aus „Abmessungen und Technische Daten“

Benötigt PyMuPDF (requirements-dev.txt). Gelesen wird über die Wortpositionen, nicht über Fließtext:
Tabellenspalten werden an den Kopfzeilen (Typbezeichnungen) ausgerichtet.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
from bosch_flow.speicher import BILDER, ORDNER, normname  # noqa: E402

AUSGABE = ORDNER / "speicher_katalog.json"
TTNR = re.compile(r"^\d{10}$")
PREIS = re.compile(r"^\d{1,3}(\.\d{3})*,(––|--|\d{2})$")
SYMBOL = re.compile(r"^[+\-–()/ *\d)]+$")
KOPF_Y, FUSS_Y = 45, 790        # Seitenkopf (Titel) und -fuß (Seitenzahl) ausblenden


# Offensichtliche Tippfehler im Katalogtext (für die Anzeige korrigiert, im Abgleich gemeldet)
TIPPFEHLER = {"Folienmantell": "Folienmantel", "Ernergieverbrauch": "Energieverbrauch",
              "Magensiumschutzanode": "Magnesiumschutzanode", "Prüfsöffnung": "Prüföffnung",
              "Betriebtemperatur": "Betriebstemperatur", "Wärmdämmung": "Wärmedämmung", "‚(750/1000": "(750/1000"}


def zeilen(page) -> list[tuple[float, list[list]]]:
    """Wörter zu Zeilen (Mitte weicht < 3,5 pt ab) und Zeilen zu Zellen (Abstand < 5 pt) zusammenfassen."""
    woerter = sorted(((*w[:4], TIPPFEHLER.get(w[4], re.sub(r"[\uf000-\uf8ff]", "•", w[4])))
                      for w in page.get_text("words")),
                     key=lambda w: (w[1] + w[3]) / 2)
    reihen: list[list] = []
    for w in woerter:
        m = (w[1] + w[3]) / 2
        if reihen and abs(m - reihen[-1][0]) < 3.5:
            reihen[-1][1].append(w)
        else:
            reihen.append([m, [w]])
    aus = []
    for _, ws in reihen:
        ws = sorted(ws, key=lambda w: w[0])
        zellen, cur = [], None
        for w in ws:
            if cur and w[0] - cur[2] < 5:
                cur = [cur[0], min(cur[1], w[1]), w[2], max(cur[3], w[3]), cur[4] + " " + w[4]]
            else:
                if cur:
                    zellen.append(cur)
                cur = list(w[:5])
        zellen.append(cur)
        aus.append((min(w[1] for w in ws), zellen))
    return aus


SPEICHERNAME = re.compile(r"^\(?(B|BH|BS|BSH|BP|BPS|BPU|BST|BTHC|BBS|CST|HR|SP|SW|SWDP|W|WH|WP|WPS|WS|WST)\s?\d")


def kopf_zellen(zellen: list[list]) -> list[list]:
    """Kopfzellen trennen, in denen zwei Typbezeichnungen zusammengerückt sind („B 1000-6 M 1 B B 1300-6 M 1 B“)."""
    aus = []
    for c in zellen:
        teile = re.split(r"\s(?=(?:B|BH|BS|BSH|BP|BPU|W|WH|WP|WPS|WS|SW|SWDP|CST|HR|SP)\s?\d{2,})", c[4].strip())
        if len(teile) == 1:
            aus.append(c)
            continue
        breite, x = c[2] - c[0], c[0]
        gesamt = sum(len(t) for t in teile) + len(teile) - 1
        for t in teile:
            b = breite * len(t) / gesamt
            aus.append([x, c[1], x + b, c[3], t])
            x += b + breite / gesamt
    return aus


def titel(page) -> str:
    for y, z in zeilen(page):
        if y < 28 and "Gesamtkatalog" not in " ".join(c[4] for c in z):
            return " ".join(c[4] for c in z).strip()
    return ""


def zahl(t: str):
    t = t.strip()
    if re.fullmatch(r"-?\d+(\.\d{3})*(,\d+)?", t):
        return float(t.replace(".", "").replace(",", "."))
    return None


# ---------------------------------------------------------------------------------------------- Abschnitte
def abschnitte(doc) -> list[dict]:
    """Aufeinanderfolgende Seiten mit gleichem Kopftitel bilden eine Produktfamilie."""
    teile: list[dict] = []
    for i, page in enumerate(doc):
        t = titel(page)
        if not t or t.startswith("Warmwasser-, Kombi") or t in ("Allgemeines Zubehör",):
            continue
        if teile and teile[-1]["titel"] == t:
            teile[-1]["seiten"].append(i)
        else:
            teile.append({"titel": t, "seiten": [i]})
    return teile


def preiszeilen(z: list[tuple[float, list]], von: float = 0, bis: float = 1e9):
    """Bestelltabellen: Zeilen mit 10-stelliger Bestell-Nr. und Preis; Typ/Beschreibung aus Nachbarzeilen."""
    treffer = []
    for y, zellen in z:
        if not (von <= y <= bis):
            continue
        nr = [c for c in zellen if TTNR.match(c[4].strip())]
        pr = [c for c in zellen if PREIS.match(c[4].strip())]
        if nr and pr:
            treffer.append({"y": y, "x_nr": nr[0][0], "ttnr": nr[0][4].strip(), "preis": zahl(pr[0][4].replace("––", "00").replace("--", "00")),
                            "typ": [], "text": []})
    if not treffer:
        return []
    x_nr = treffer[0]["x_nr"]
    # Spalte „Typ“ beginnt am Kopf „Typ“ (sonst: linkeste Zelle der Preiszeilen)
    x_typ = next((c[0] for y, zs in z for c in zs if c[4].strip() == "Typ"), None)
    x_text = next((c[0] for y, zs in z for c in zs if c[4].strip() in ("Beschreibung", "Bezeichnung")), None)
    if x_typ is None or x_text is None:
        return []
    for y, zellen in z:
        if not (von <= y <= bis) or y < min(t["y"] for t in treffer) - 40:
            continue
        nah = min(treffer, key=lambda t: abs(t["y"] - y))
        if abs(nah["y"] - y) > 40:
            continue
        for c in zellen:
            t = c[4].strip()
            if TTNR.match(t) or PREIS.match(t) or t in ("Typ", "Beschreibung", "Bezeichnung", "Bestell-Nr.", "€"):
                continue
            if x_typ - 6 <= c[0] < x_text - 4:
                nah["typ"].append((y, t))
            elif x_text - 4 <= c[0] < x_nr - 4:
                nah["text"].append((y, t))
    # Zeilen zwischen zwei Positionen gehören zur näheren – Typ steht oft mittig zur Beschreibung
    for t in treffer:
        t["typ"] = " ".join(x for _, x in sorted(t["typ"]))
        t["text"] = " ".join(x for _, x in sorted(t["text"]))
        t.pop("x_nr")
    return treffer


def tabellen(z: list[tuple[float, list]], produkte: list[dict]) -> list[dict]:
    """Spaltentabellen, deren Kopfzeile Typbezeichnungen der Familie enthält (techn. Daten, Kombinationen)."""
    namen = {normname(p["typ"]): p for p in produkte if p.get("typ")}

    def passt(text: str) -> list[str]:
        n = normname(text)
        if len(n) < 4:
            return []
        return [p["ttnr"] for k, p in namen.items() if k.startswith(n) or n.startswith(k)]

    aus: list[dict] = []
    tab = None
    letzte_ohne_wert = ""
    for y, zellen in z:
        if y < KOPF_Y or y > FUSS_Y:
            continue
        kopf = [(c, passt(c[4])) for c in kopf_zellen([c for c in zellen if c[0] > 200])]
        if kopf and any(t for _, t in kopf) and all(t or SPEICHERNAME.match(c[4].strip()) for c, t in kopf) \
                and not any(TTNR.match(c[4]) for c in zellen) \
                and all(not re.search(r"\d", c[4]) for c in zellen if c[0] < 200):
            tab = {"y": y, "spalten": [{"mitte": (c[0] + c[2]) / 2, "name": c[4].strip(), "ttnr": t} for c, t in kopf],
                   "zeilen": []}
            aus.append(tab)
            letzte_ohne_wert, gruppe = "", ""
            continue
        if not tab:
            continue
        werte, rest = {}, []
        for c in zellen:
            m = (c[0] + c[2]) / 2
            sp = min(range(len(tab["spalten"])), key=lambda i: abs(tab["spalten"][i]["mitte"] - m))
            if abs(tab["spalten"][sp]["mitte"] - m) < 42 and c[0] > 240:
                werte[sp] = c[4].strip()
            else:
                rest.append(c)
        label = " ".join(c[4] for c in rest if c[0] < 225).strip()
        einheit = " ".join(c[4] for c in rest if c[0] >= 225).strip()
        if not werte:
            if re.match(r"^(\d\)|\*)", label) or label.startswith(("Zubehör", "Typ ")):
                tab = None              # Fußnoten oder nächste Tabelle: Ende
                continue
            letzte_ohne_wert = label
            if label and not einheit:
                tab.setdefault("gruppen", []).append(label)
            continue
        if not label and letzte_ohne_wert:
            label = letzte_ohne_wert
        # Anschlussbuchstabe (A–O) als eigenes Feld, wenn neben der Einheit
        buchst = ""
        m = re.match(r"^([A-Z]{1,2})\s+(.+)$", einheit)
        if m:
            buchst, einheit = m.group(1), m.group(2)
        elif re.fullmatch(r"[A-Z]{1,2}", einheit):
            buchst, einheit = einheit, ""
        tab["zeilen"].append({"label": label, "kz": buchst, "einheit": einheit,
                              "gruppe": (tab.get("gruppen") or [""])[-1],
                              "werte": {tab["spalten"][i]["name"]: v for i, v in werte.items()}})
        letzte_ohne_wert = ""
    for t in aus:
        t["art"] = "kombination" if t["zeilen"] and all(
            all(SYMBOL.match(v) for v in r["werte"].values()) for r in t["zeilen"]) and \
            any("+" in v for r in t["zeilen"] for v in r["werte"].values()) else "daten"
        t.pop("gruppen", None)
    return [t for t in aus if t["zeilen"]]


def texte(z, von: float, bis: float) -> list[str]:
    """Freitext (Produktbeschreibung, Hinweise) spaltenweise lesen."""
    spalten: dict[int, list] = {}
    for y, zellen in z:
        if von < y < bis:
            for c in zellen:
                spalten.setdefault(0 if c[0] < 220 else (1 if c[0] < 395 else 2), []).append((y, c[4].strip()))
    return [" ".join(t for _, t in sorted(v)) for k, v in sorted(spalten.items())]


def fussnoten(z) -> list[str]:
    aus, cur = [], None
    for y, zellen in z:
        if y > FUSS_Y:
            continue
        t = " ".join(c[4] for c in zellen).strip()
        if re.match(r"^(\d\)|\*)\s*\S", t) and zellen[0][0] < 80:
            cur = t
            aus.append(cur)
        elif cur and zellen[0][0] < 80 and not re.match(r"^(Zubehör|Typ|Unverbindliche|Deutschland)", t) and len(t) > 3 \
                and not any(TTNR.match(c[4]) for c in zellen):
            aus[-1] = cur = cur + " " + t
        else:
            cur = None
    return [h for h in aus if len(h) > 12]


ENDE_BILD = ("Produktabmessungen", "Kombinationsmöglichkeiten", "Zubehör", "Speicherzubehör", "Typ", "Legende")


def massbild(page, z, tabellen_y: list[float], ziel: Path) -> bool:
    """Maßzeichnung oberhalb der ersten Tabelle als PNG speichern (nur wenn dort echte Zeichnung mit Bögen ist)."""
    oben = next((y + 19 for y, c in z if any("Abmessungen und Technische Daten" in x[4] for x in c)), KOPF_Y + 4)
    marken = [y for y, c in z if y > oben and c[0][4].strip().startswith(ENDE_BILD) and c[0][0] < 160]
    unten = min([y for y in tabellen_y if y > oben] + marken + [FUSS_Y])
    if unten - oben < 120:
        return False
    # ganze Seitenbreite bis direkt an die Tabelle – ohne die Kapitelmarke („12“) am linken/rechten Seitenrand
    links, rechts = 15, page.rect.width - 5
    for b_ in page.get_text("dict")["blocks"]:
        r = pymupdf.Rect(b_["bbox"])
        if b_["type"] == 1 and r.width < 50 and r.height > 600:
            if r.x0 < 60:
                links = max(links, r.x1 + 2)
            else:
                rechts = min(rechts, r.x0 - 2)
    for _, c in z:      # Kapitelnummer als Text im Randstreifen
        for x in c:
            if re.fullmatch(r"\d{1,2}", x[4].strip()) and (x[0] > page.rect.width - 60 or x[2] < 60) and 200 < x[1] < 760:
                if x[0] > page.rect.width - 60:
                    rechts = min(rechts, x[0] - 2)
                else:
                    links = max(links, x[2] + 2)
    clip = pymupdf.Rect(links, oben, rechts, unten - 0.5)
    pfade = [it[0] for d in page.get_drawings() if clip.intersects(d["rect"]) for it in d["items"]]
    rasterbild = any(pymupdf.Rect(b["bbox"]).intersect(clip).get_area() > 30000
                     for b in page.get_text("dict")["blocks"] if b["type"] == 1)
    if pfade.count("c") < 25 and pfade.count("l") < 400 and not rasterbild:
        return False
    pix = page.get_pixmap(clip=clip, dpi=150, colorspace=pymupdf.csGRAY)
    im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    rahmen = ImageChops.difference(im, Image.new("L", im.size, 255)).point(lambda p: 255 if p > 20 else 0).getbbox()
    if rahmen:
        im = im.crop((max(0, rahmen[0] - 8), max(0, rahmen[1] - 8), min(im.width, rahmen[2] + 8), min(im.height, rahmen[3] + 8)))
    if im.height < 150:
        return False
    im = im.quantize(colors=16)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    im.save(ziel, optimize=True)
    return True


def familie_slug(titel_: str) -> str:
    return "kat-" + re.sub(r"[^a-z0-9]+", "-", titel_.lower().replace("stora ", "").replace("storacell ", "")).strip("-")


def katalog_stand(pdf: Path) -> str:
    """„…_2026-07_…“ im Dateinamen → „07/2026“."""
    m = re.search(r"(20\d{2})-(\d{2})", pdf.name)
    return f"{m.group(2)}/{m.group(1)}" if m else ""


def neuheiten(doc) -> set[str]:
    """Im Kapitel-Inhaltsverzeichnis als „NEU“ markierte Produktfamilien (normalisierte Namen)."""
    neu = set()
    for page in doc:
        if titel(page).startswith("Warmwasser-, Kombi"):
            z = zeilen(page)
            for y, zellen in z:
                if "NEU" not in [c[4].strip() for c in zellen]:
                    continue
                # „NEU“ steht manchmal ein paar Punkt neben der Zeile mit dem Namen
                for _, nachbar in sorted(z, key=lambda e: abs(e[0] - y)):
                    name = next((c[4].strip() for c in nachbar if SPEICHERNAME.match(c[4].strip())), "")
                    if name:
                        neu.add(normname(name))
                        break
    return neu


def lesen(pdf: Path, bilder: bool = True, vergeben: set | None = None) -> dict:
    doc = pymupdf.open(pdf)
    familien = []
    stand = katalog_stand(pdf)
    neu = neuheiten(doc)
    vergeben = vergeben if vergeben is not None else set()
    for teil in abschnitte(doc):
        seiten = [doc[i] for i in teil["seiten"]]
        z_seiten = [zeilen(p) for p in seiten]
        fam = {"titel": teil["titel"], "seite": doc[teil["seiten"][0]].get_label() or str(teil["seiten"][0] + 1),
               "produkte": [], "zubehoer": [], "tabellen": [], "hinweise": [], "beschreibung": [], "bild": "",
               "quelle": pdf.name, "stand": stand, "verfuegbar_ab": "",
               "neu": normname(re.sub(r"^(Stora|Storacell|Dimplex)\s+", "", teil["titel"])) in neu}
        zubehoer = False
        for p, z in zip(seiten, z_seiten):
            # „Zubehör“-Überschrift trennt Produkt- und Zubehörtabellen
            y_zub = next((y for y, c in z if c[0][4].strip() in ("Zubehör", "Speicherzubehör") and c[0][0] < 60
                          and len(c) == 1 and KOPF_Y < y), None)
            if not zubehoer:
                for t in preiszeilen(z, 0, y_zub or 1e9):
                    fam["produkte"].append(t)
                if fam["produkte"] and not fam["beschreibung"]:
                    y_typ = next((y for y, c in z if any(x[4].strip() == "Typ" for x in c)), None)
                    if y_typ:
                        fam["beschreibung"] = [t for t in texte(z, 65, y_typ - 4) if t]
            if y_zub is not None or zubehoer:
                fam["zubehoer"] += preiszeilen(z, y_zub or 0, 1e9)
                zubehoer = True
            fam["hinweise"] += [h for h in fussnoten(z) if h not in fam["hinweise"]]
            m = re.search(r"Verfügbar\s+ab\s+(\d{2}/\d{4})", p.get_text())       # Störer neben der Bestelltabelle
            if m and not fam["verfuegbar_ab"]:
                fam["verfuegbar_ab"] = m.group(1)
        fam["bilder"] = []
        for i, (p, z) in enumerate(zip(seiten, z_seiten)):
            tabs = tabellen(z, fam["produkte"])
            fam["tabellen"] += tabs
            if bilder and i > 0 and len(fam["bilder"]) < 3:
                slug = f'{familie_slug(teil["titel"])}{"-" + str(len(fam["bilder"]) + 1) if fam["bilder"] else ""}'
                if slug in vergeben:          # gleiche Familie in einem zweiten Katalog
                    slug += "-" + stand.replace("/", "-")
                if massbild(p, z, [t["y"] for t in tabs], BILDER / f"{slug}.png"):
                    fam["bilder"].append(slug)
                    vergeben.add(slug)
        fam["bild"] = fam["bilder"][0] if fam["bilder"] else ""
        for t in fam["produkte"] + fam["zubehoer"]:
            t.pop("y", None)
        # nur Speicherfamilien (der Elektrokatalog enthält auch Wärmepumpen, Klimageräte …)
        if any(SPEICHERNAME.match(p_["typ"]) for p_ in fam["produkte"]):
            familien.append(fam)
        else:
            for b_ in fam["bilder"]:
                (BILDER / f"{b_}.png").unlink(missing_ok=True)
                vergeben.discard(b_)
    return {"quelle": pdf.name, "stand": stand, "familien": familien}


def pakete(pdf: Path) -> list[dict]:
    """WP-Pakete (z. B. „CS3800iAW Pakete …“): je Paket WP-Variante, enthaltene Speicher, Bestell-Nr., Preis."""
    doc = pymupdf.open(pdf)
    aus = []
    for page in doc:
        t = page.get_text()
        if "Paketinhalt" not in t:
            continue
        titel_ = re.sub(r"\s+", " ", t.split("Paketinhalt")[0].split("Mehrwertsteuer.")[-1]).strip()
        speicher = re.findall(r"–\s*(?:Puffer|Kombi|Warmwasser)speicher\s+([^\n]+)", t)
        for m in re.finditer(r"(CS\w+)\s+(\d+)\s*\n\s*(O[A-Z]?-[ST])\s*\n(?:.*\n){0,6}?\s*(\d{10})\s*\n\s*([\d.]+,(?:––|\d{2}))", t):
            aus.append({"titel": titel_, "wp": f"{m.group(1)} {m.group(2)} {m.group(3)}",
                        "speicher": [x.strip() for x in speicher], "ttnr": m.group(4),
                        "preis": zahl(m.group(5).replace("––", "00")), "quelle": pdf.name,
                        "seite": page.get_label() or str(page.number + 1)})
    return aus


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path, nargs="+", help="Kataloge, ältester zuerst (spätere haben Vorrang)")
    ap.add_argument("--ohne-bilder", action="store_true")
    a = ap.parse_args()
    if not a.ohne_bilder and BILDER.exists():
        for alt in BILDER.glob("kat-*.png"):
            alt.unlink()
    vergeben: set = set()
    teile = [lesen(pdf, not a.ohne_bilder, vergeben) for pdf in a.pdf]
    # Familien, die ein weiterer Katalog unverändert wiederholt (z. B. Elektro-Ergänzungskatalog), nur einmal führen
    familien, gesehen = [], {}
    for t in teile:
        for f in t["familien"]:
            sig = (f["titel"], tuple(sorted((p["ttnr"], p["preis"]) for p in f["produkte"])), f["stand"])
            if sig in gesehen:
                gesehen[sig].setdefault("auch_in", []).append(f["quelle"])
                for b_ in f["bilder"]:
                    (BILDER / f"{b_}.png").unlink(missing_ok=True)
                continue
            gesehen[sig] = f
            familien.append(f)
    daten = {"quellen": [{"quelle": t["quelle"], "stand": t["stand"]} for t in teile],
             "familien": familien,
             "pakete": [pk for pdf in a.pdf for pk in pakete(pdf)]}
    genutzt = {b for f in daten["familien"] for b in f["bilder"]}
    for bild in BILDER.glob("kat-*.png"):
        if bild.stem not in genutzt:
            bild.unlink()            # Seiten ohne Bestelltabelle (z. B. „Produktinformationen“)
    AUSGABE.write_text(json.dumps(daten, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n_p = sum(len(f["produkte"]) for f in daten["familien"])
    n_b = sum(1 for f in daten["familien"] if f["bild"])
    print(f"{len(daten['familien'])} Produktfamilien, {n_p} Speicher, {n_b} Maßbilder → {AUSGABE.name}")


if __name__ == "__main__":
    main()
