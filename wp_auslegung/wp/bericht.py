"""PDF-Ausdruck der Schnellauslegung (A4 hoch) – gleicher Aufbau wie „Drucken / PDF“ in index.html.

Seite 1: Projekt, gewählte Wärmepumpe, Kennzahlen, Herleitung der Heizlast
Seite 2: Heizleistung über der Außentemperatur, passende Wärmepumpen je Baureihe
Seite 3: Anlagenschema (Prinzip), Jahresbilanz, Haftungsausschluss
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fpdf import FPDF

from . import rechnen as R
from . import texte as T

ROT = (226, 0, 21)
BLAU = (0, 86, 145)
INK = (20, 30, 41)
GRAU = (74, 88, 102)
HELL = (120, 136, 154)
LINIE = (201, 211, 220)
GRID = (227, 233, 239)
VL_F, RL_F, WW_F, KW_F = (226, 0, 21), (0, 86, 145), (233, 131, 0), (46, 154, 62)
BAND = [(169, 40, 46), (226, 0, 21), (185, 2, 118), (80, 35, 127), (28, 62, 133), (0, 142, 207), (0, 168, 176),
        (0, 136, 74), (120, 190, 32)]
SCHRIFTEN = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]
ERSATZ = {"θ": "t", "−": "-", "≤": "<=", "≈": "~", "·": "x", "★": "*", "Ø": "O", "²": "2", "³": "3", "–": "-", "„": '"',
          "“": '"', "×": "x", "§": "Par.", "°": " Grad"}


class Ausdruck(FPDF):
    def __init__(self, projekt: str, datum: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.projekt, self.datum = projekt, datum
        self.unicode = False
        for normal, fett in SCHRIFTEN:
            if Path(normal).exists() and Path(fett).exists():
                self.add_font("Text", "", normal)
                self.add_font("Text", "B", fett)
                self.unicode = True
                break
        self.schrift = "Text" if self.unicode else "Helvetica"
        self.set_margins(13, 12, 13)
        self.set_auto_page_break(True, margin=16)
        self.alias_nb_pages()
        self.erste = True

    def t(self, s) -> str:
        s = str(s)
        if self.unicode:
            return s.replace("★", "*")
        for a, b in ERSATZ.items():
            s = s.replace(a, b)
        return s.encode("latin-1", "replace").decode("latin-1")

    def schrift_(self, groesse: float, fett: bool = False, farbe=INK):
        self.set_font(self.schrift, "B" if fett else "", groesse)
        self.set_text_color(*farbe)

    def header(self):
        if self.page_no() == 1:
            return
        self.schrift_(12, True, ROT)
        self.set_xy(13, 11)
        self.cell(40, 6, "BOSCH")
        self.schrift_(7.5, True)
        self.set_xy(110, 10.5)
        self.cell(87, 4, self.t("Wärmepumpen-Schnellauslegung"), align="R")
        self.schrift_(7, False, GRAU)
        self.set_xy(110, 14.5)
        self.cell(87, 4, self.t("Projekt " + self.projekt), align="R")
        self.set_draw_color(*LINIE)
        self.set_line_width(0.2)
        self.line(13, 20, 197, 20)
        self.set_y(25)

    def footer(self):
        self.set_draw_color(*LINIE)
        self.set_line_width(0.2)
        self.line(13, 283, 197, 283)
        self.schrift_(6.8, False, GRAU)
        self.set_xy(13, 284)
        self.cell(80, 4, self.t("© Bosch Thermotechnik GmbH · WP-Schnellauslegung"))
        self.cell(40, 4, self.datum, align="C")
        self.cell(64, 4, f"{self.page_no()} / {{nb}}", align="R")

    def band(self, y: float, h: float = 7):
        b = (self.w - 0) / len(BAND)
        for i, c in enumerate(BAND):
            self.set_fill_color(*c)
            self.rect(i * b, y, b + 0.3, h, style="F")

    def titel(self, s: str):
        self.schrift_(17, False)
        self.cell(0, 9, self.t(s), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def h2(self, s: str):
        self.ln(2)
        self.schrift_(10.5, True)
        self.cell(0, 6, self.t(s), new_x="LMARGIN", new_y="NEXT")

    def box(self, x: float, y: float, w: float, kopf: str, zeilen: list[tuple[str, str]]) -> float:
        self.set_fill_color(215, 221, 227)
        self.set_draw_color(154, 167, 179)
        self.set_line_width(0.25)
        self.rect(x, y, w, 6, style="DF")
        self.schrift_(8.5, True)
        self.set_xy(x + 2.5, y + 1)
        self.cell(w - 5, 4, self.t(kopf))
        yy = y + 8
        for a, b in zeilen:
            self.schrift_(8, False, GRAU)
            self.set_xy(x + 2.5, yy)
            self.cell(w * 0.44, 4.6, self.t(a))
            self.schrift_(8, b.startswith("**"))
            self.set_xy(x + 2.5 + w * 0.44, yy)
            self.cell(w * 0.56 - 5, 4.6, self.t(b.strip("*")))
            yy += 4.8
        self.rect(x, y, w, yy - y + 1.5)
        return yy + 1.5

    def tabelle(self, kopf, zeilen, breiten, rechts=(), fett=lambda z: False):
        self.set_draw_color(*LINIE)
        self.set_line_width(0.15)
        x0 = self.l_margin
        self.set_fill_color(233, 238, 242)
        self.schrift_(7, True, GRAU)
        x = x0
        y = self.get_y()
        for k, b in zip(kopf, breiten):
            self.set_xy(x, y)
            self.cell(b, 6, self.t(k), fill=True, align="R" if kopf.index(k) in rechts else "L")
            x += b
        self.set_y(y + 6)
        for z in zeilen:
            y = self.get_y()
            if y > 270:
                self.add_page()
                y = self.get_y()
            x = x0
            for i, (v, b) in enumerate(zip(z, breiten)):
                self.schrift_(7.6, fett(z))
                self.set_xy(x, y)
                self.cell(b, 5.4, self.t(v), align="R" if i in rechts else "L")
                x += b
            self.line(x0, y + 5.4, x0 + sum(breiten), y + 5.4)
            self.set_y(y + 5.4)


# ------------------------------------------------------------------------------------------------ Diagramm
def diagramm(pdf: Ausdruck, r: dict, daten: dict, x: float, y: float, w: float, h: float):
    k, g = r["kennlinien"], r["gewaehlt"]
    if not k:
        return
    andere = []
    for d in daten["geraete"]:
        if d["serie"] == g["serie"] and d["id"] != g["geraet"]:
            kk = R.kurve_bei_vl(d["max"], r["vl"])
            if kk:
                andere.append((d["kurz"], [g["n"] * kk[0](t) for t in k["t"]]))
    werte = k["last"] + k["max"] + (k["min"] or []) + [q for _, a in andere for q in a]
    import math
    qmax = math.ceil(max(werte) * 1.08 / 2) * 2 or 2
    step = 20 if qmax > 60 else 10 if qmax > 30 else 5 if qmax > 12 else 2
    L, Rr, B = 12, 28, 10
    t0, t1 = k["t"][0], k["t"][-1]
    X = lambda t: x + L + (t - t0) / (t1 - t0) * (w - L - Rr)  # noqa: E731
    Y = lambda q: y + h - B - q / qmax * (h - B - 3)  # noqa: E731
    pdf.set_line_width(0.15)
    pdf.set_draw_color(*GRID)
    pdf.schrift_(6.5, False, GRAU)
    q = 0
    while q <= qmax:
        pdf.line(X(t0), Y(q), X(t1), Y(q))
        pdf.set_xy(x, Y(q) - 2)
        pdf.cell(L - 2, 4, str(q), align="R")
        q += step
    ts = 4 if t1 - t0 > 30 else 2
    t = math.ceil(t0 / ts) * ts
    while t <= t1:
        pdf.line(X(t), Y(0), X(t), Y(qmax))
        pdf.set_xy(X(t) - 5, Y(0) + 1)
        pdf.cell(10, 4, pdf.t(str(t).replace("-", "−")), align="C")
        t += ts
    pdf.set_xy(X(t0), Y(0) + 5)
    pdf.cell(X(t1) - X(t0), 4, pdf.t("Außentemperatur in °C"), align="C")
    with pdf.rotation(90, x + 2, y + (h - B) / 2):
        pdf.set_xy(x + 2 - 20, y + (h - B) / 2 - 2)
        pdf.cell(40, 4, pdf.t("Heizleistung in kW"), align="C")
    # θe
    pdf.set_draw_color(*HELL)
    pdf.set_dash_pattern(0.6, 0.9)
    pdf.line(X(r["nat"]), Y(0), X(r["nat"]), Y(qmax))
    pdf.set_dash_pattern()
    pdf.set_xy(X(r["nat"]) + 1, Y(qmax))
    pdf.cell(25, 3.5, pdf.t("θe " + T.ft(r["nat"]) + " °C"))

    def linie(qs, farbe, breite, strich=None):
        pdf.set_draw_color(*farbe)
        pdf.set_line_width(breite)
        if strich:
            pdf.set_dash_pattern(*strich)
        pdf.polyline([(X(t), Y(v)) for t, v in zip(k["t"], qs)])
        pdf.set_dash_pattern()

    enden = []
    for kurz, qs in andere:
        linie(qs, (150, 160, 172), 0.3, (0.6, 0.9))
        enden.append((qs[-1], kurz, HELL, False))
    if k["min"]:
        linie(k["min"], BLAU, 0.4, (1.6, 1.0))
        enden.append((k["min"][-1], "Min.-Leistung", BLAU, False))
    linie(k["last"], INK, 0.6)
    enden.append((k["last"][-1], "Gebäudekennlinie", INK, True))
    linie(k["max"], BLAU, 0.9)
    enden.append((k["max"][-1], (f"{g['n']}× " if g["n"] > 1 else "") + g["kurz"], BLAU, True))
    yl = -1e9
    for qv, txt, farbe, fett in sorted(enden, key=lambda e: -e[0]):
        yy = max(Y(qv) - 1.6, yl + 3.4)
        yl = yy
        pdf.schrift_(6.5, fett, farbe)
        pdf.set_xy(X(t1) + 1.5, yy)
        pdf.cell(Rr - 2, 3.2, pdf.t(txt))
    pdf.set_line_width(0.3)
    if g["bivalenz_art"] == "punkt":
        qb = R.last(g["bivalenz"], r["qh"] + r["qsperr"], r["qtw"], r["nat"], r["heizgrenze"])
        pdf.set_fill_color(*BLAU)
        pdf.set_draw_color(255, 255, 255)
        pdf.ellipse(X(g["bivalenz"]) - 1.3, Y(qb) - 1.3, 2.6, 2.6, style="DF")
        pdf.schrift_(6.5)
        pdf.set_xy(X(g["bivalenz"]) - 40, Y(qb) + 2)
        pdf.cell(38, 3.5, pdf.t("Bivalenzpunkt " + T.ft(g["bivalenz"]) + " °C"), align="R")
    if g.get("taktgrenze") is not None and r["nat"] < g["taktgrenze"] <= t1:
        qt = R.last(g["taktgrenze"], r["qh"] + r["qsperr"], r["qtw"], r["nat"], r["heizgrenze"])
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(*BLAU)
        pdf.ellipse(X(g["taktgrenze"]) - 1, Y(qt) - 1, 2, 2, style="DF")
        pdf.schrift_(6.5, False, GRAU)
        pdf.set_xy(X(g["taktgrenze"]) - 20, Y(qt) - 5.5)
        pdf.cell(40, 3.5, pdf.t("Taktgrenze ≈ " + T.ft(g["taktgrenze"]) + " °C"), align="C")


# ------------------------------------------------------------------------------------------------ Schema
def schema(pdf: Ausdruck, e: dict, r: dict, ie: dict | None, x: float, y: float, w: float):
    g = r["gewaehlt"]
    kaskade = g["n"] > 1 or g["serie"] == "CS5001"
    integriert = bool(ie and ie.get("speicher") == "integriert")
    puffermodul = bool(ie and "Puffer" in ie.get("art", ""))
    mit_puffer = kaskade or not (integriert or puffermodul)
    mit_ww = e["tww"].get("aktiv", True) and not integriert

    def ln(punkte, farbe, strich=False):
        pdf.set_draw_color(*farbe)
        pdf.set_line_width(0.6)
        if strich:
            pdf.set_dash_pattern(1.2, 0.9)
        pdf.polyline(punkte)
        pdf.set_dash_pattern()

    def kasten(bx, by, bw, bh, t1, t2):
        pdf.set_draw_color(*INK)
        pdf.set_line_width(0.35)
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(bx, by, bw, bh, style="DF", round_corners=True, corner_radius=1.6)
        pdf.schrift_(6.8, True)
        pdf.set_xy(bx - 12, by + bh + 1)
        pdf.cell(bw + 24, 3.2, pdf.t(t1), align="C")
        pdf.schrift_(6.2, False, GRAU)
        pdf.set_xy(bx - 12, by + bh + 4.2)
        pdf.cell(bw + 24, 3.2, pdf.t(t2), align="C")

    # Legende
    for i, (c, txt, s) in enumerate([(VL_F, "Vorlauf Heizung", 0), (RL_F, "Rücklauf Heizung", 1), (WW_F, "Warmwasser", 0), (KW_F, "Kaltwasser", 0)]):
        lx = x + w - 120 + i * 30
        ln([(lx, y + 1.5), (lx + 6, y + 1.5)], c, s)
        pdf.schrift_(6.2, False, GRAU)
        pdf.set_xy(lx + 7, y)
        pdf.cell(22, 3, pdf.t(txt))
    hk = y + 14
    yB, hB = y + 42, 20
    xAE, xIE, xP, xW = x + w - 32, x + w - 76, x + w - 112, x + 14
    ln([(x + w - 76, hk), (x + w - 2, hk)], VL_F)
    ln([(x + w - 76, hk + 4), (x + w - 2, hk + 4)], RL_F, True)
    pdf.schrift_(6.2, False, GRAU)
    pdf.set_xy(x + w - 76, hk + 5)
    pdf.cell(74, 3, pdf.t("Heizkreise (Heizkörper / Fußbodenheizung)"), align="R")
    # Außeneinheit(en)
    for i in range(min(g["n"], 3)):
        pdf.set_draw_color(*INK)
        pdf.set_line_width(0.35)
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(xAE + i * 2, yB - (min(g["n"], 3) - 1) * 3 + i * 3, 26, hB, style="DF", round_corners=True, corner_radius=2)
    pdf.circle(xAE + 13 + (min(g["n"], 3) - 1) * 2, yB + hB / 2, 4.2)
    pdf.schrift_(6.8, True)
    pdf.set_xy(xAE - 10, yB + hB + 1)
    pdf.cell(46, 3.2, pdf.t((f"{g['n']} × " if g["n"] > 1 else "") + "Außeneinheit"), align="C")
    pdf.schrift_(6.2, False, GRAU)
    pdf.set_xy(xAE - 10, yB + hB + 4.2)
    pdf.cell(46, 3.2, pdf.t(g["geraet"]), align="C")
    if kaskade:
        kasten(xIE, yB + 2, 22, 16, ie["typ"] if ie and ie.get("ab_anzahl") else "Wärmepumpenmanager",
               "Kaskadenregelung" if g["n"] > 1 else "HPC 301")
    else:
        kasten(xIE, yB - 3, 22, hB + 6, "Inneneinheit", ie["typ"] if ie else "")
        ln([(xIE + 22, yB + 6), (xAE, yB + 6)], VL_F)
        ln([(xIE + 22, yB + 12), (xAE, yB + 12)], RL_F, True)
        if integriert or puffermodul:
            pdf.schrift_(5.8, False, WW_F if integriert else GRAU)
            pdf.set_xy(xIE, yB + 2)
            pdf.cell(22, 3, pdf.t("WW-Speicher" if integriert else "Puffer"), align="C")
    if mit_puffer:
        kasten(xP, yB - 5, 12, hB + 8, "Trennpufferspeicher" if kaskade else "Pufferspeicher",
               "hydraulische Entkopplung" if kaskade else "Reihen-/Trennpuffer")
        ziel = xAE if kaskade else xIE
        ln([(xP + 12, yB), (ziel, yB)] + ([(ziel, yB + 2)] if kaskade else []), VL_F)
        ln([(xP + 12, yB + 17), (ziel - (2 if kaskade else 0), yB + 17)], RL_F, True)
        ln([(xP + 5, yB - 5), (xP + 5, hk), (x + w - 76, hk)], VL_F)
        ln([(xP + 9, yB - 5), (xP + 9, hk + 4), (x + w - 76, hk + 4)], RL_F, True)
    else:
        ln([(xIE + 7, yB - 3), (xIE + 7, hk)], VL_F)
        ln([(xIE + 15, yB - 3), (xIE + 15, hk + 4)], RL_F, True)
    if mit_ww:
        kasten(xW, yB - 5, 20, hB + 8, "Warmwasserspeicher", "mit WW-Modul / Ladestation" if kaskade else "mit Wärmetauscher")
        pdf.schrift_(14, False)
        pdf.set_xy(xW, yB + 3)
        pdf.cell(20, 8, pdf.t("Σ") if pdf.unicode else "WW", align="C")
        y1, y2 = yB + hB + 11, yB + hB + 13.5
        sx1, sx2 = (xAE - 5, xAE - 8) if kaskade else (xIE + 26, xIE + 29)
        sy1, sy2 = (yB, yB + 17) if kaskade else (yB + 6, yB + 12)
        ln([(sx1, sy1), (sx1, y1), (xW + 25, y1), (xW + 25, yB + 6), (xW + 20, yB + 6)], VL_F)
        ln([(sx2, sy2), (sx2, y2), (xW + 27.5, y2), (xW + 27.5, yB + 14), (xW + 20, yB + 14)], RL_F, True)
        ln([(xW + 5, yB - 5), (xW + 5, hk - 7), (xW + 15, hk - 7)], WW_F)
        pdf.schrift_(6.2, False, GRAU)
        pdf.set_xy(xW + 16, hk - 8.5)
        pdf.cell(20, 3, "Zapfstellen")
        ln([(xW, yB + 18), (xW - 7, yB + 18), (xW - 7, yB + 33)], KW_F)
        pdf.set_xy(xW - 17, yB + 34)
        pdf.cell(20, 3, "Kaltwasser", align="C")
    return yB + hB + 18


# ------------------------------------------------------------------------------------------------ Bericht
def pdf_bytes(e: dict, r: dict, daten: dict, katalog: dict) -> bytes:
    p = e["projekt"]
    datum = ".".join(reversed((p.get("datum") or date.today().isoformat()).split("-")))
    pdf = Ausdruck(p.get("name") or "ohne Namen", datum)
    g = r.get("gewaehlt")
    ie = T.inneneinheit(e, r, katalog)
    kat = katalog["geraete"].get(g["geraet"], {}) if g else {}
    preise = bool(e.get("preise_drucken"))

    # ---- Seite 1
    pdf.add_page()
    pdf.schrift_(19, True)
    pdf.set_xy(13, 14)
    pdf.cell(130, 10, pdf.t("Wärmepumpen-Schnellauslegung"))
    pdf.schrift_(19, True, ROT)
    pdf.cell(54, 10, "BOSCH", align="R")
    pdf.band(29, 8)
    pdf.set_xy(13, 42)
    pdf.schrift_(11, True)
    pdf.cell(130, 6, pdf.t("Projekt: " + (p.get("name") or "ohne Namen")))
    pdf.schrift_(9)
    pdf.cell(54, 6, "Datum: " + datum, align="R")
    links = [("Projekt", p.get("name") or "ohne Namen")]
    if p.get("kunde"):
        links.append(("Kunde", p["kunde"]))
    links += [("PLZ / Ort", " ".join(x for x in (p.get("plz"), p.get("ort")) if x) or "–"),
              ("Norm-Außentemperatur", T.ft(r["nat"]) + " °C"),
              ("Heizgrenze / Innentemp.", T.ft(r["heizgrenze"]) + " / " + T.ft(r["innen"]) + " °C"),
              ("Max. Vorlauftemperatur", T.f(r["vl"], 0) + " °C"), ("Betriebsweise", T.BETRIEBSWEISE[r["kriterium"]])]
    if p.get("bearbeiter"):
        links.append(("Bearbeiter", p["bearbeiter"]))
    if g:
        rechts = [("Außeneinheit", "**" + (f"{g['n']} × " if g["n"] > 1 else "") + g["geraet"]),
                  ("Bestell-Nr.", kat.get("artnr") or "–"), ("Inneneinheit", ie["typ"] if ie else "–")]
        if ie and ie.get("artnr"):
            rechts.append(("Bestell-Nr.", ie["artnr"]))
        rechts += [("Bivalenzpunkt", T.biv_text(g)),
                   ("Abdeckung bei θe", T.f(g["abdeckung"] * 100, 0) + " %" if g["moeglich"] else "–")]
        if preise and kat.get("uvp"):
            summe = kat["uvp"] * g["n"] + ((ie.get("uvp") or 0) * (1 if ie.get("ab_anzahl") else g["n"]) if ie else 0)
            rechts.append(("UVP (netto)", T.euro(summe)))
    else:
        rechts = [("–", "keine Auswahl")]
    y1 = pdf.box(13, 51, 89, "Projekt und Gebäude", links)
    y2 = pdf.box(108, 51, 89, "Gewählte Wärmepumpe", rechts)
    y = max(y1, y2) + 4
    pdf.set_fill_color(*BLAU)
    pdf.rect(13, y, 184, 26, style="F")
    pdf.schrift_(11, True, (255, 255, 255))
    pdf.set_xy(18, y + 3)
    pdf.cell(0, 5, pdf.t("Kennzahlen auf einen Blick"))
    kp = [("Gesamtheizlast QGES", T.f(r["qges"], 2) + " kW")]
    if g and g["moeglich"]:
        kp += [("Bivalenzpunkt", T.biv_text(g)), (f"Leistung bei θe {T.ft(r['nat'])} °C", T.f(g["q_nat"], 2) + " kW"),
               ("WP-Deckungsanteil", T.f(g["deckung"] * 100, 1) + " %")]
    for i, (a, b) in enumerate(kp):
        pdf.schrift_(7, False, (220, 232, 242))
        pdf.set_xy(18 + i * 44, y + 11)
        pdf.cell(42, 4, pdf.t(a))
        pdf.schrift_(13, True, (255, 255, 255))
        pdf.set_xy(18 + i * 44, y + 16)
        pdf.cell(42, 6, pdf.t(b))
    pdf.set_y(y + 30)
    for m in T.meldungen(e, r, katalog):
        pdf.set_fill_color(255, 246, 229)
        pdf.set_draw_color(241, 211, 154)
        pdf.schrift_(7.8, False, (122, 75, 0))
        pdf.multi_cell(184, 4.5, pdf.t(m), border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    pdf.h2("Herleitung der Heizlast")
    for a, b, c in T.herleitung(e, r):
        fett = a.startswith("Gesamt")
        yy = pdf.get_y()
        pdf.schrift_(7.8, fett, INK if fett else GRAU)
        pdf.set_xy(13, yy)
        pdf.cell(62, 5, pdf.t(a))
        pdf.schrift_(7.8, False)
        pdf.set_xy(75, yy)
        pdf.cell(98, 5, pdf.t(b))
        pdf.schrift_(7.8, True)
        pdf.set_xy(173, yy)
        pdf.cell(24, 5, pdf.t(c), align="R")
        pdf.set_y(yy + 5)
    if p.get("notiz"):
        pdf.h2("Notiz")
        pdf.schrift_(8.5)
        pdf.multi_cell(184, 4.5, pdf.t(p["notiz"]), new_x="LMARGIN", new_y="NEXT")

    # ---- Seite 2
    pdf.add_page()
    pdf.titel("Leistungsdaten")
    if r.get("kennlinien"):
        pdf.h2(f"Heizleistung über der Außentemperatur – Vorlauf {T.f(r['vl'], 0)} °C")
        pdf.schrift_(6.8, False, GRAU)
        pdf.cell(0, 4, pdf.t(f"Blau: {(str(g['n']) + ' × ') if g['n'] > 1 else ''}{g['geraet']} (max., gestrichelt Mindestleistung) · "
                             "grau: weitere Größen der Baureihe · schwarz: Gebäudekennlinie"), new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y() + 1
        diagramm(pdf, r, daten, 13, y, 184, 92)
        pdf.set_y(y + 96)
    pdf.h2("Passende Wärmepumpen je Baureihe (kleinste passende Größe) und gewählte Wärmepumpe")
    emp = set(r["empfehlung_je_serie"])
    zeilen = []
    for c in r["kandidaten"]:
        if not ((c["geraet"] + "|" + str(c["n"])) in emp or (g and c["geraet"] == g["geraet"])):
            continue
        k = katalog["geraete"].get(c["geraet"], {})
        z = [("● " if c["ok"] else "○ ") + c["geraet"] + (" ★" if (c["geraet"] + "|" + str(c["n"])) in emp else ""), str(c["n"])]
        if c["moeglich"]:
            z += [T.f(c["q_a7"], 2), T.f(c["q_nat"], 2), T.f(c["abdeckung"] * 100, 0) + " %", T.biv_text(c),
                  T.f(c["heizstab_kw"], 1), T.f(c["deckung"] * 100, 1) + " %"]
        else:
            z += ["–"] * 6
        if preise:
            z.append(T.euro(k["uvp"] * c["n"]) if k.get("uvp") else "–")
        zeilen.append(z)
    kopf = ["Wärmepumpe", "Anz.", f"A-7/W{T.f(r['vl'], 0)}", "bei θe", "Abdeckung", "Bivalenzpunkt", "Heizstab", "Deckung"]
    breiten = [52, 10, 18, 16, 18, 24, 16, 18]
    if preise:
        kopf.append("UVP")
        breiten.append(22)
    gsel = (g["geraet"] if g else "")
    pdf.tabelle(kopf, zeilen, breiten, rechts=tuple(range(1, len(kopf))),
                fett=lambda z: gsel and gsel in z[0])
    rest = len(r["kandidaten"]) - len(zeilen)
    if rest:
        pdf.schrift_(7, False, HELL)
        pdf.cell(0, 5, pdf.t(f"{rest} weitere Größen/Geräte siehe Werkzeug. ● erfüllt das Kriterium, ★ kleinste passende Größe der Baureihe."),
                 new_x="LMARGIN", new_y="NEXT")

    # ---- Seite 3
    pdf.add_page()
    pdf.titel("Anlagenschema und Jahresbilanz")
    if g:
        y = schema(pdf, e, r, ie, 13, pdf.get_y(), 184)
        pdf.set_y(y)
    pdf.schrift_(7, False, HELL)
    pdf.multi_cell(184, 3.8, pdf.t("Prinzipdarstellung – Zubehör, Speicher, Sicherheitstechnik und hydraulischer Abgleich sind in "
                                   "der Systemkonfiguration (SysCon) zu planen."), new_x="LMARGIN", new_y="NEXT")
    en = r.get("energie")
    if en:
        pdf.h2("Jahresbilanz (Schätzung)")
        werte = [("Jahreswärme Heizung + WW", T.f(en["waerme_kwh"], 0) + " kWh/a")]
        if en.get("scop"):
            werte += [("Strom Wärmepumpe", T.f(en["strom_wp_kwh"], 0) + " kWh/a"),
                      ("Strom Heizstab", T.f(en["strom_heizstab_kwh"], 0) + " kWh/a"),
                      ("Umweltwärme", T.f(en["umwelt_kwh"], 0) + " kWh/a")]
        y = pdf.get_y()
        for i, (a, b) in enumerate(werte):
            pdf.set_fill_color(242, 245, 248)
            pdf.set_draw_color(*LINIE)
            pdf.rect(13 + i * 46.5, y, 44, 15, style="DF")
            pdf.schrift_(6.5, False, GRAU)
            pdf.set_xy(15 + i * 46.5, y + 2)
            pdf.cell(40, 3.5, pdf.t(a))
            pdf.schrift_(11, True, BLAU)
            pdf.set_xy(15 + i * 46.5, y + 7)
            pdf.cell(40, 5, pdf.t(b))
        pdf.set_y(y + 17)
        pdf.schrift_(7, False, HELL)
        txt = ("Strom = Wärme · Deckungsanteil / SCOP (EN 14825, mittleres Klima, zwischen 35 und 55 °C interpoliert, "
               f"SCOP ≈ {T.f(en['scop'], 2)})." if en.get("scop") else "Für dieses Gerät ist kein SCOP im Katalog hinterlegt.")
        pdf.multi_cell(184, 3.8, pdf.t(txt), new_x="LMARGIN", new_y="NEXT")
    pdf.h2("Haftungsausschluss")
    pdf.schrift_(7.4, False, GRAU)
    pdf.multi_cell(184, 3.8, pdf.t(T.HAFTUNG + (" Preise: unverbindliche Preisempfehlung ohne MwSt." if preise else "")),
                   align="J", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
