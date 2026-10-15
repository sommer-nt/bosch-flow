"""PDF-Auslegungsbericht (A4 quer) – Inhalt wie „Planung als PDF exportieren“ der HTML-Version V54.

Deckblatt mit Eingabeparametern und Gesamt-Kennzahlen, je Strang Netzschema und Steigstrang-Tabelle,
Gesamtübersicht mit Netztopologie (Position der Wärmezentrale), Diagramme, Anlagenschema,
Auslegungstabelle, Wärmezentrale, DLE-Auslegungshilfe und Hinweise.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

from . import report as RP
from . import schemata as SC
from . import katalog as KA
from . import varianten as VA
from .calc import Inputs, din18015, dle_table, gesamt_anlage, gz, project_headline, puffer_produkt, seg, topologie
from .data import MATNAME, WAERMEQUELLEN
from .zeichnung import in_pdf

BOSCH_ROT = (226, 0, 21)
BOSCH_BLAU = (0, 86, 145)
GRAU = (90, 98, 108)
VERSION = "Rechenkern V54"
ENTWICKLER = "Entwickelt von Daniel Sommer · HC/SDE3-PSD"

SCHRIFTEN = [  # (normal, fett) – erste vorhandene wird genutzt
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]
ERSATZ = {"→": "->", "≈": "~", "Δ": "d", "–": "-", "−": "-", "“": '"', "„": '"', "×": "x", "Σ": "S", "≤": "<=",
          "◆": "*", "●": "*", "▶": ">", "⚡": "", "◄": "<", "✓": "OK", "⚠": "!", "V̇": "V", "̇": "", "·": "-",
          "²": "2", "³": "3", "°": " Grad"}


class Bericht(FPDF):
    def __init__(self, projekt: str = ""):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.projekt = projekt
        self.unicode = False
        for normal, fett in SCHRIFTEN:
            if Path(normal).exists() and Path(fett).exists():
                self.add_font("Text", "", normal)
                self.add_font("Text", "B", fett)
                self.unicode = True
                break
        self.schrift = "Text" if self.unicode else "Helvetica"
        self.set_auto_page_break(True, margin=14)
        self.set_margins(12, 12, 12)
        self.alias_nb_pages()

    def t(self, s) -> str:
        s = str(s)
        if not self.unicode:
            for a, b in ERSATZ.items():
                s = s.replace(a, b)
            return s.encode("latin-1", "replace").decode("latin-1")
        for a in ("⚡", "◄"):            # nicht in DejaVu Sans enthalten
            s = s.replace(a, ERSATZ[a])
        return s

    def header(self):
        self.set_font(self.schrift, "B", 15)
        self.set_text_color(*BOSCH_ROT)
        self.cell(self.get_string_width("BOSCH") + 1, 8, "BOSCH")
        self.set_text_color(*BOSCH_BLAU)
        self.cell(0, 8, self.t(" Flow · Netz- & Anlagenrechner – Auslegungsbericht"), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*BOSCH_ROT)
        self.set_line_width(0.6)
        self.line(12, self.get_y(), self.w - 12, self.get_y())
        self.ln(3)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-10)
        self.set_font(self.schrift, "", 7)
        self.set_text_color(*GRAU)
        self.cell(0, 5, self.t(f"Bosch Flow · {VERSION} · {self.projekt or 'Projekt'} · {ENTWICKLER} · "
                               f"Seite {self.page_no()}/{{nb}}"), align="C")

    def abschnitt(self, titel: str, neue_seite: bool = False, platz: float = 40):
        if neue_seite or self.get_y() > self.h - platz:
            self.add_page()
        self.ln(2)
        self.set_font(self.schrift, "B", 11)
        self.set_text_color(*BOSCH_BLAU)
        self.cell(0, 7, self.t(titel), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def absatz(self, s: str, groesse: float = 8.5, farbe=(0, 0, 0)):
        self.set_font(self.schrift, "", groesse)
        self.set_text_color(*farbe)
        self.multi_cell(0, 4.4, self.t(s.replace("**", "")), align="L", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def tabelle(self, kopf: list[str], zeilen: list[list], breiten: list[float] | None = None,
                fett_wenn=None):
        self.set_font(self.schrift, "", 7.5)
        self.set_fill_color(240, 244, 248)      # Zeichnungen hinterlassen sonst ihre letzte Füllfarbe
        self.set_draw_color(205, 213, 221)
        self.set_line_width(0.2)
        self.set_text_color(0, 0, 0)
        kopfstil = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=BOSCH_BLAU)
        with self.table(col_widths=breiten, headings_style=kopfstil, line_height=4.6, text_align="LEFT",
                        first_row_as_headings=True, cell_fill_color=(240, 244, 248), cell_fill_mode="ROWS") as tab:
            tab.row([self.t(k) for k in kopf])
            for z in zeilen:
                stil = FontFace(emphasis="BOLD", color=BOSCH_BLAU) if fett_wenn and fett_wenn(z) else None
                tab.row([self.t(x) for x in z], style=stil)
        self.ln(1)

    def szene(self, s, hoehe_max: float | None = None, breite: float | None = None):
        w = breite or (self.w - self.l_margin - self.r_margin)
        h = s.hoehe * w / s.breite
        if hoehe_max and h > hoehe_max:
            w, h = s.breite * hoehe_max / s.hoehe, hoehe_max
        if self.get_y() + h > self.h - 16:
            self.add_page()
        x = self.l_margin + ((self.w - self.l_margin - self.r_margin) - w) / 2
        in_pdf(self, s, x, self.get_y(), w)
        self.set_y(self.get_y() + h + 2)

    def _platz(self, hoehe: float):
        if self.get_y() + hoehe > self.h - 16:
            self.add_page()

    def kacheln(self, werte: list[tuple[str, str]]):
        self._platz(20)
        self.set_auto_page_break(False)
        n = len(werte)
        gap = 4
        w = (self.w - self.l_margin - self.r_margin - gap * (n - 1)) / n
        y = self.get_y()
        for i, (k, v) in enumerate(werte):
            x = self.l_margin + i * (w + gap)
            self.set_fill_color(247, 249, 251)
            self.set_draw_color(211, 220, 229)
            self.set_line_width(0.2)
            self.rect(x, y, w, 17, style="DF")
            self.set_fill_color(*BOSCH_BLAU)
            self.rect(x, y, w, 1, style="F")
            self.set_xy(x + 2.5, y + 2.5)
            self.set_font(self.schrift, "", 7.5)
            self.set_text_color(*GRAU)
            self.cell(w - 5, 4, self.t(k))
            self.set_xy(x + 2.5, y + 7.5)
            self.set_font(self.schrift, "B", 13)
            self.set_text_color(20, 30, 41)
            self.cell(w - 5, 7, self.t(v))
        self.set_text_color(0, 0, 0)
        self.set_y(y + 20)
        self.set_auto_page_break(True, margin=14)

    def parameter(self, werte: list[tuple[str, str]], spalten: int = 3):
        w = (self.w - self.l_margin - self.r_margin) / spalten
        self.set_auto_page_break(False)
        for i in range(0, len(werte), spalten):
            self._platz(12)
            y = self.get_y()
            for j, (k, v) in enumerate(werte[i:i + spalten]):
                x = self.l_margin + j * w
                self.set_fill_color(*BOSCH_BLAU)
                self.rect(x, y, 0.8, 9, style="F")
                self.set_xy(x + 2.5, y)
                self.set_font(self.schrift, "", 6.5)
                self.set_text_color(*GRAU)
                self.cell(w - 6, 3.5, self.t(k.upper()))
                self.set_xy(x + 2.5, y + 3.8)
                self.set_font(self.schrift, "B", 9)
                self.set_text_color(20, 30, 41)
                self.cell(w - 6, 5, self.t(v))
            self.set_y(y + 11.5)
        self.set_text_color(0, 0, 0)
        self.set_auto_page_break(True, margin=14)


def _datum(meta: dict) -> str:
    d = meta.get("projDate") or ""
    try:
        return date.fromisoformat(str(d)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return date.today().strftime("%d.%m.%Y")


def parameter_liste(inp: Inputs, R: dict, n_str: int) -> list[tuple[str, str]]:
    P, st = R["P"], R["st"]
    ww = (f"manuell: {RP.fmt(P['zapfLmin'], 1)} l/min @ {RP.fmt(P['zapfTemp'])} °C" if inp.wwmode == "man"
          else f"Stufe: {R['stage']['kw']} kW · {R['stage']['lmin']} l/min @ 45 °C")
    name = "Flow 7000 (F7002 HPS)" if P["zuheizerOn"] else st["name"]
    return [("Leitersystem", f"{P['system']}-Leiter"), ("Wärmequelle", WAERMEQUELLEN[inp.waermequelle]["name"]),
            ("Wohnungsstation", f"{name} · {st['mode']}"), ("Warmwasser", ww),
            ("Heizlast je Wohnung", f"{RP.fmt(P['qhk'], 1)} kW · ΔT {RP.fmt(P['dthk'])} K"),
            ("Vorlauf / Versorgung", f"{RP.fmt(P['tvl'])} °C / {RP.fmt(P['vlhk'])} °C"),
            ("Rohrmaterial", MATNAME[P["mat"]]), ("max. Geschwindigkeit", f"{RP.fmt(P['vmax'], 1)} m/s"),
            ("GLZ-Verfahren", "TU Dresden" if P["glz"] == "tud" else "DIN 4708"),
            ("Kesseltotzeit / Wiederaufheiz.", f"{RP.fmt(R['anlage']['tTot'])} min / {RP.fmt(R['anlage']['tWied'])} min"),
            ("Spitzenzeit", f"{RP.fmt(R['anlage']['tSpitz'])} min"),
            ("Anzahl Stränge", f"{n_str} · Zentrale {'gemeinsam' if inp.zentral == 'gemeinsam' else 'getrennt'}")]


def pdf_bericht(inp: Inputs, straenge: list, meta: dict, results: list, bestaetigt_am: str = "") -> bytes:
    """Kompletter Auslegungsbericht als PDF (Bytes)."""
    aktiv = min(meta.get("activeStrang", 0), len(results) - 1)
    R = results[aktiv]
    P, A = R["P"], R["anlage"]
    G = gesamt_anlage(inp, results)
    pdf = Bericht(meta.get("projName", ""))
    pdf.add_page()

    # ------------------------------------------------------------ Deckblatt
    pdf.set_font(pdf.schrift, "B", 18)
    pdf.cell(0, 10, pdf.t(meta.get("projName") or "Projekt ohne Namen"), new_x="LMARGIN", new_y="NEXT")
    pdf.absatz(f"Standort: {meta.get('projLoc') or '–'} · Planer / Bearbeiter: {meta.get('projPlanner') or '–'} · "
               f"Datum: {_datum(meta)}", 9.5)
    pdf.abschnitt("Eingabeparameter")
    pdf.parameter(parameter_liste(inp, R, len(results)))
    pdf.abschnitt("Gesamt-Kennzahlen der Anlage")
    gs = seg(G["we"], P)
    pp = puffer_produkt(G["pufferVol"])
    gz_ges = G["gz"] if G["gz"] is not None else gz(G["we"], P["glz"])   # getrennt: nur informativ (wie V54)
    pdf.kacheln([("Wohnungen gesamt", str(G["we"])), ("Gesamt-Volumenstrom", f"{RP.fmt(gs['Vtot'], 2)} m³/h"),
                 ("Kessel-/FW-Leistung" + (" (Σ getrennt)" if G["getrennt"] else ""), f"{RP.fmt(G['kesselQ'])} kW"),
                 ("Pufferspeicher" + (" (Σ getrennt)" if G["getrennt"] else " (Auswahl)"),
                  f"{RP.fmt(G['pufferVol'])} l" if G["getrennt"] else pp["text"]),
                 ("Gleichzeitigkeit (GZ)", RP.fmt(gz_ges, 1))])
    HL = project_headline(R, inp)
    pdf.absatz(f"Strangfuß {'gesamt' if HL['projektweit'] else 'unten'}: {HL['dim']} bei {RP.fmt(HL['Vtot'], 2)} m³/h, "
               f"v = {RP.fmt(HL['v'], 2)} m/s. {RP.anlage_note(A)}", 8.5, GRAU)

    # ------------------------------------------------------------ je Strang
    for i, r in enumerate(results):
        foot = r["vRows"][0]
        pdf.abschnitt(f"Strang {i + 1} · {r['totalWE']} Wohnungen · {r['floors']} Etagen · "
                      f"{'beidseitig' if r['split'] == 'both' else 'einseitig'} · Strangfuß {foot['dim']} · "
                      f"{RP.fmt(foot['Vtot'], 2)} m³/h", neue_seite=True)
        pdf.szene(SC.netzschema(r), hoehe_max=118)
        df = RP.strang_table(r, "V")
        pdf.tabelle(list(df.columns), [[_z(v, c) for c, v in zip(df.columns, row)] for row in df.itertuples(index=False)],
                    [60, 18, 14, 26, 24, 26, 20, 22, 30])

    # ------------------------------------------------------------ Gesamtübersicht
    if len(results) > 1:
        pos = meta.get("topoPos", 50)
        T = topologie(results, pos)
        pdf.abschnitt(f"Gesamtübersicht – alle {len(results)} Stränge", neue_seite=True)
        pdf.absatz("Netztopologie: Wärmezentrale (Keller) → Steigrohr → horizontaler Hauptstrang → vertikale Stränge "
                   f"mit Wohnungsstationen. Position der Wärmezentrale: {T['label']}.", 8.5, GRAU)
        if G["getrennt"]:
            pdf.absatz("Hinweis – getrennte Ausführung: Es gibt keinen gemeinsamen Hauptstrang. Jeder Strang hat eine "
                       "eigene Wärmezentrale. Die Topologie dient nur der Übersicht.", 8.5, (178, 106, 0))
        pdf.szene(SC.topologie_szene(results, pos), hoehe_max=72)
        zeilen = [[f"Strang {i + 1}", r["totalWE"], r["floors"], "beidseitig" if r["split"] == "both" else "einseitig",
                   r["vRows"][0]["dim"], f"{RP.fmt(r['vRows'][0]['Vtot'], 2)} m³/h", f"{RP.fmt(r['vRows'][0]['v'], 2)} m/s"]
                  for i, r in enumerate(results)]
        zeilen.append(["Summe", G["we"], "–", "getrennte Anlagen", "–", "–", "–"] if G["getrennt"] else
                      ["Summe", G["we"], "–", "alle Stränge", T["gesamt"]["dim"], f"{RP.fmt(T['gesamt']['Vtot'], 2)} m³/h",
                       f"{RP.fmt(T['gesamt']['v'], 2)} m/s"])
        pdf.tabelle(["Strang", "Wohnungen", "Etagen", "Aufteilung", "Strangfuß", "V̇ Strangfuß", "v"], zeilen,
                    fett_wenn=lambda z: z[0] == "Summe")
        pdf.abschnitt("Hauptstrang – Nennweite je Abschnitt (folgt der Position der Wärmezentrale)", platz=50)
        pdf.tabelle(["Abschnitt", "kum. WE", "Strang", "Leitung", "Nennweite", "V̇", "v"],
                    [[f"Abschnitt {a['strang']}", a["load"], f"Strang {a['strang']}", "Hauptstrang", a["dn"],
                      f"{RP.fmt(a['V'], 2)} m³/h", f"{RP.fmt(a['v'], 2)} m/s" + ("  ◆ maßgeblich" if a["kritisch"] else "")]
                     for a in T["abschnitte"]], fett_wenn=lambda z: "◆" in z[-1])
        pdf.absatz(RP.hauptstrang_erklaerung(results, T), 8, GRAU)
        pdf.kacheln([("Wohnungen gesamt", str(G["we"])),
                     (f"Kessel-/FW-Leistung {'(Σ getrennte Anlagen)' if G['getrennt'] else '(gesamt)'}",
                      f"{RP.fmt(G['kesselQ'])} kW"),
                     (f"Pufferspeicher {'(Σ getrennte Anlagen)' if G['getrennt'] else '(gesamt)'}",
                      f"{RP.fmt(G['pufferVol'])} l")])
        pdf.absatz(RP.gesamt_note(G, len(results)), 8, GRAU)

    # ------------------------------------------------------------ Diagramme
    pdf.abschnitt(f"Diagramme – Volumenstrom & Gleichzeitigkeit (Bezug {G['we']} Wohnungen)", neue_seite=True)
    y = pdf.get_y()
    bw = (pdf.w - 24 - 8) / 2
    h1 = in_pdf(pdf, SC.diagramm_volumenstrom(P, G["we"]), 12, y, bw)
    in_pdf(pdf, SC.diagramm_gleichzeitigkeit(G["we"]), 12 + bw + 8, y, bw)
    pdf.set_y(y + h1 + 2)
    pdf.absatz("Volumenstrom über kumulierte Wohnungszahl. WW-Anteil je Station auf 1,3 m³/h gedeckelt – dadurch "
               "realistische, nicht überzogene Dimensionen. TU Dresden (ROUND(WE^-0,57·WE)) liegt bei vielen Wohnungen "
               "unter DIN 4708.", 8, GRAU)

    # ------------------------------------------------------------ Anlagenschema + Tabellen (aktiver Strang)
    titel = f" – Strang {aktiv + 1}" if len(results) > 1 else ""
    pdf.abschnitt("Anlagenschema (Heizzentrale)" + titel, neue_seite=True)
    pdf.szene(SC.anlagenschema(R, HL), hoehe_max=105)
    pdf.abschnitt("Auslegungs-Tabelle – maßgeblicher Etagenstrang" + titel, platz=60)
    df = RP.strang_table(R, "H")
    pdf.tabelle(list(df.columns), [[_z(v, c) for c, v in zip(df.columns, row)] for row in df.itertuples(index=False)],
                [60, 18, 14, 26, 24, 26, 20, 22, 30])
    pdf.absatz(f"Maßgeblicher (längster) Etagenstrang: von der äußersten Station (1 WE, kleinste Dimension) bis zum "
               f"Steigstrang ({R['govN']} WE). WW-Volumenstrom je Station gedeckelt auf 1,3 m³/h.", 8, GRAU)
    pdf.abschnitt("Wärmezentrale – Kessel & Pufferspeicher" + titel, neue_seite=True)
    pdf.tabelle(["Größe", "Wert", "Einheit", "Herleitung"], [list(r) for r in RP.anlage_rows(A)], [62, 30, 16, 165],
                fett_wenn=lambda z: str(z[0]).startswith("→"))
    pdf.absatz(RP.anlage_note(A), 8, GRAU)

    # ------------------------------------------------------------ Wohnungsstation & Stückliste (Katalog)
    g = KA.geraet(inp, meta)
    pdf.abschnitt(f"Wohnungsstation & Stückliste – {KA.KATALOG}", neue_seite=True)
    y0 = pdf.get_y()
    pdf.image(str(g["bild"]), x=pdf.l_margin, y=y0, h=48, keep_aspect_ratio=True, w=40)
    pdf.set_left_margin(pdf.l_margin + 46)
    pdf.set_xy(pdf.l_margin, y0)
    pdf.set_font(pdf.schrift, "B", 13)
    pdf.set_text_color(*BOSCH_BLAU)
    pdf.cell(0, 7, pdf.t(f"{g['typ']}  ·  Bestell-Nr. {g['bestellnr']}  ·  UVP {RP.fmt(g['uvp'])} €"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.parameter([("Montage / Heizkreis", f"{KA.MONTAGE[g['montage']]} · {g['heizkreis']}"),
                   ("Abmessungen H × B × T", g["abmessungen"]),
                   ("Primär-VL laut Katalog", f"{g['vlMin']}–{g['vlMax']} °C"),
                   ("Primär-Volumenstrom", f"{RP.fmt(g['vPrim'])} l/h bei {g['vlPunkt']}"),
                   ("Primär-Druckverlust", f"{RP.fmt(g['dpPrim'])} mbar bei {g['vlPunkt']}"),
                   ("Zapfmenge max.", f"{g['zapf']} l/min")], spalten=3)
    hw = [t for _, t in g["hinweise"]]
    pdf.absatz("\n".join(f"- {t}" for t in hw), 7.5, GRAU)
    pdf.set_left_margin(12)
    pdf.set_y(max(pdf.get_y(), y0 + 50) + 2)
    zeilen = KA.projekt_stueckliste(inp, straenge, meta)

    def eur(v):
        return "auf Anfrage" if v is None else f"{RP.fmt(v, 2)} €"
    summe = sum(z["summe"] or 0 for z in zeilen)
    pdf.tabelle(["Position", "Bezeichnung", "Bestell-Nr.", "Menge", "UVP", "Summe"],
                [[z["pos"], z["text"], z["nr"], str(z["menge"]), eur(z["uvp"]), eur(z["summe"])] for z in zeilen]
                + [["Summe", "Katalogpositionen (UVP, ohne MwSt.)", "", "", "", eur(summe)]],
                [30, 130, 28, 16, 32, 37], fett_wenn=lambda z: z[0] == "Summe")
    pdf.absatz(KA.PREISHINWEIS + " Rohrleitungen, Erzeuger, Puffer und Montage nicht enthalten. Netzpumpenmodul nach "
               "Spitzen-Volumenstrom bei 0,8 bar Restförderhöhe; die Förderhöhe des Netzes ist gesondert zu prüfen.",
               7.5, GRAU)

    if A["zuheizerOn"]:
        pdf.abschnitt("DLE-Auslegungshilfe (Mischbooster, analog Bosch Tab. 7)", platz=70)
        pdf.tabelle(["Netztemp. an Station", "Stufe 48 °C", "Stufe 53 °C", "Stufe 60 °C"],
                    RP.dle_rows_text(dle_table(A)), fett_wenn=lambda z: "aktuell" in z[0])
        _, fazit = RP.dle_fazit(A)
        pdf.absatz(fazit, 8.5)
        pdf.absatz(RP.DLE_ELEKTRO, 8, (178, 106, 0))
        d = din18015(A["weForZentrale"])
        pdf.abschnitt("Stromseitige Gleichzeitigkeit · DIN 18015-1 (Anhang A)", platz=80)
        pdf.kacheln([(f"MIT elektr. WW (maßgeblich) · {d['nWE']} WE", f"≈ {RP.fmt(d['mit'])} kW"),
                     ("OHNE elektr. WW (Referenz)", f"≈ {RP.fmt(d['ohne'])} kW")])
        pdf.absatz(RP.PMAX_HINWEIS, 8, GRAU)

    # ------------------------------------------------------------ Variantenvergleich
    V = VA.vergleich(inp, straenge, float(meta.get("topoPos", 50)))
    pdf.abschnitt("Variantenvergleich – dieselbe Planung mit anderen Eingaben", neue_seite=True)
    best = V["empfehlung"]
    if best["variante"].gruppe == "Planung":
        pdf.absatz("Ergebnis: Die aktuelle Planung ist unter den geprüften Varianten die beste.", 9, BOSCH_BLAU)
    else:
        pdf.absatz(f"Empfehlung: {best['variante'].titel} ({best['variante'].gruppe}) – Bewertung "
                   f"{RP.fmt(best['wert'] * 100)} % der aktuellen Planung: "
                   + "; ".join(VA.begruendung(best, V["basis"])), 9, BOSCH_BLAU)
    basis = V["basis"]
    pdf.tabelle(["Variante", "Bereich", "Anschluss", "V̇ [m³/h]", "Δ Rohrnetz", "max. v/v_max", "> v_max",
                 "Erzeuger [kW]", "Puffer", "Bewertung"],
                [[z["variante"].titel + ("" if z["variante"].empfehlbar else " *"), z["variante"].gruppe,
                  z["k"]["anschluss"], RP.fmt(z["k"]["V"], 2),
                  f"{(z['k']['dnSumme'] / basis['dnSumme'] - 1) * 100:+.0f} %".replace("-", "−"),
                  f"{RP.fmt(z['k']['auslastung'] * 100)} %", str(z["k"]["ueber"]), RP.fmt(z["k"]["kessel"]),
                  z["k"]["pufferText"], f"{RP.fmt(z['wert'] * 100)} %"] for z in V["zeilen"]],
                [50, 24, 20, 20, 22, 24, 16, 24, 50, 22], fett_wenn=lambda z: z[0] == best["variante"].titel)
    pdf.absatz("Bewertung: 50 % Rohrnetz (Summe der Nennweiten aller Abschnitte), 25 % Erzeugerleistung, 25 % "
               "Puffervolumen; Abschnitte über v_max werden bestraft. Preise, Energieeffizienz und Montage fließen "
               "nicht ein. * = gezeigt, aber nicht automatisch empfohlen (Rechenverfahren, Leitersystem, höherer "
               "Vorlauf). 4-Leiter: das zusätzliche Heiznetz ist im Rohrvergleich nicht enthalten.", 8, GRAU)

    # ------------------------------------------------------------ Hinweise
    pdf.abschnitt("Hinweise", platz=50)
    pdf.absatz("\n".join(f"- {h}" for h in RP.HAFTUNGSHINWEISE)
               + (f"\nHinweise bestätigt am {bestaetigt_am}." if bestaetigt_am else ""), 8, GRAU)
    return bytes(pdf.output())


def _z(v, spalte: str) -> str:
    if isinstance(v, float):
        nk = 0 if "Δp" in spalte else 1 if spalte == "GZ" else 2
        return RP.fmt(v, nk)
    return str(v)
