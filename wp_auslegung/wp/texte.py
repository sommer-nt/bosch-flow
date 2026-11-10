"""Texte und Formatierung für App und PDF (wie die Anzeige in index.html)."""
from __future__ import annotations

from . import rechnen as R

BETRIEBSWEISE = {"monovalent": "monovalent", "monoenergetisch": "monoenergetisch", "hybrid": "GEG-Hybrid"}
VERTEILUNG_VL = {"fbh": 35, "hk": 55, "beides": 55, "konvektor": 45}
VERTEILUNG_TEXT = {"fbh": "Fußbodenheizung", "hk": "Heizkörper", "beides": "Fußbodenheizung + Heizkörper",
                   "konvektor": "Konvektoren"}
SPEZ = {"neubau": [(22, "KfW-Effizienzhaus 40+ (20–25 W/m²)"), (30, "KfW-Effizienzhaus 55 (30 W/m²)"),
                   (35, "KfW-Effizienzhaus 85 (35 W/m²)"), (38, "EnEV 2009 / GEG (35–40 W/m²)"), (15, "Passivhaus (15 W/m²)")],
        "sanierung": [(100, "Bestand WSchVO 1982 (80–120 W/m²)"), (70, "Bestand WSchVO 1995 (60–80 W/m²)"),
                      (50, "EnEV 2002 (40–60 W/m²)"), (40, "KfW-Effizienzhaus 100 (40 W/m²)"), (38, "EnEV 2009 (35–40 W/m²)")]}
HK_TYP = {"hk": "Heizkörper", "fbh": "Fußbodenheizung", "konvektor": "Konvektoren"}
HK_MAX = 4


def heizkreis_liste(e: dict) -> list[dict]:
    """Heizkreise wie index.html: der Kreis mit dem höchsten Vorlauf ungemischt, die anderen gemischt."""
    hk = e.get("heizkreise") or [{"typ": e.get("verteilung") if e.get("verteilung") in ("fbh", "konvektor") else "hk"}]
    vmax = max(VERTEILUNG_VL.get(h["typ"], 55) for h in hk)
    return [{"nr": i + 1, "typ": h["typ"], "vl": VERTEILUNG_VL.get(h["typ"], 55),
             "gemischt": VERTEILUNG_VL.get(h["typ"], 55) < vmax} for i, h in enumerate(hk)]


def heizkreis_text(e: dict) -> str:
    return " + ".join(HK_TYP[h["typ"]] + (" (gem.)" if h["gemischt"] else "") for h in heizkreis_liste(e))


KRITERIUM = {"monovalent": "QGES bei θe (monovalent)",
             "monoenergetisch": "0,7 · QGES bei A-7 (Außenluft −7 °C; monoenergetisch, ca. 98 % Deckung)",
             "hybrid": "0,3 · QH bei A-7 (Außenluft −7 °C; GEG § 71 Hybrid)"}


def f(x, d: int = 1) -> str:
    if x is None:
        return "–"
    s = f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def ft(x) -> str:
    return "–" if x is None else f(x, 1).replace("-", "−")


def euro(x) -> str:
    return "–" if x is None else f(x, 0) + " €"


def biv_text(g: dict | None) -> str:
    if not g or not g.get("moeglich"):
        return "–"
    if g["bivalenz_art"] == "nicht":
        return "nicht erreicht"
    if g["bivalenz_art"] == "unter":
        return "≤ " + ft(g["bivalenz"]) + " °C"
    return ft(g["bivalenz"]) + " °C"


def inneneinheit(e: dict, r: dict, katalog: dict) -> dict | None:
    g = r.get("gewaehlt")
    if not g:
        return None
    liste = [i for i in katalog["inneneinheiten"].get(g["serie"], []) if not i.get("ab_anzahl") or g["n"] >= i["ab_anzahl"]]
    return next((i for i in liste if i["typ"] == e["auswahl"].get("inneneinheit")), liste[0] if liste else None)


def inneneinheiten(r: dict, katalog: dict) -> list[dict]:
    g = r.get("gewaehlt")
    if not g:
        return []
    return [i for i in katalog["inneneinheiten"].get(g["serie"], []) if not i.get("ab_anzahl") or g["n"] >= i["ab_anzahl"]]


def experten_abweichungen(e: dict) -> list[str]:
    """Experteneinstellungen abweichend vom Standard (wirken auch bei ausgeblendetem Expertenmodus)."""
    a, t = [], e["tww"]
    if e.get("serien"):
        a.append("Baureihen-Filter")
    if t.get("bezug", "liter") != "liter":
        a.append("Warmwasser nach DIN V 18599" + (" (je m²)" if t.get("bezug") == "flaeche" else ""))
    if t.get("methode", "auto") != "auto":
        a.append("Warmwasser-Zuschlag fest")
    if int(e.get("sperrzeit_h") or 0):
        a.append(f"Sperrzeit {int(e['sperrzeit_h'])} h")
    if e.get("auslegung") != ("monovalent" if e.get("waermequelle") == "sole" else "monoenergetisch"):
        a.append(f"Betriebsweise {e.get('auslegung')}")
    if e["heizlast"]["methode"] == "huelle":
        a.append("Heizlast über Gebäudehülle")
    return a


def experten_zuruecksetzen(e: dict) -> None:
    e["serien"] = []
    e["tww"]["bezug"], e["tww"]["methode"], e["sperrzeit_h"] = "liter", "auto", 0
    e["auslegung"] = "monovalent" if e.get("waermequelle") == "sole" else "monoenergetisch"
    if e["heizlast"]["methode"] == "huelle":
        e["heizlast"]["methode"] = "vorgabe"


def meldungen(e: dict, r: dict, katalog: dict) -> list[str]:
    m = list(r["hinweise"])
    if r["tww"]["aktiv"] and e["tww"].get("bezug") == "flaeche" and not float(e["tww"].get("flaeche_m2") or 0) > 0:
        m.append("Warmwasser flächenbezogen, aber keine Nutzfläche ANGF eingegeben – Warmwasserbedarf ist 0 (Expertenmodus).")
    g = r.get("gewaehlt")
    if g and not g["moeglich"]:
        m.append(f"{g['geraet']}: {g['grund']}.")
    elif g and not g["ok"]:
        m.append(f"{g['geraet']}{' (' + str(g['n']) + '×)' if g['n'] > 1 else ''} erfüllt das Kriterium nicht: {g['grund']}.")
    if g and g.get("ueberdimensioniert"):
        m.append("Gewählte Wärmepumpe ist deutlich überdimensioniert (Abdeckung bei θe über 150 %) – Taktverhalten prüfen.")
    tw = r["tww"]
    if g and g["moeglich"] and r["nat"] < g["t_daten_min"]:
        m.append(f"Leistungsdaten erst ab {ft(g['t_daten_min'])} °C – darunter wird der letzte Wert angesetzt "
                 "(Kurve im Diagramm nicht verlängert).")
    if g and g["moeglich"] and tw["aktiv"] and not g["vl_tww_ok"]:
        m.append(f"Warmwasser: {'Puffer' if tw['system'] == 'friwa' else 'Speicher'} {f(tw['t_speicher'], 0)} °C braucht ca. "
                 f"{f(tw['vl_tww'], 0)} °C Vorlauf – über {f(g['vl_max_geraet'], 0)} °C des Geräts, Nacherwärmung (E-Heizer) einplanen.")
    if tw["aktiv"] and tw["grossanlage"]:
        m.append(f"Warmwasser-Tagesbedarf ca. {f(tw['volumen_tag_l'], 0)} l: voraussichtlich Großanlage nach DVGW W 551 – "
                 "Speicheraustritt ≥ 60 °C (Nacherwärmung) oder Frischwasserstation einplanen.")
    ie = inneneinheit(e, r, katalog)
    if ie and ie.get("vl_max") and r["vl"] > ie["vl_max"]:
        m.append(f"{ie['typ']}: max. Vorlauftemperatur {ie['vl_max']} °C.")
    if r["waermequelle"] == "sole" and r["kriterium"] != "monovalent":
        m.append("Sole/Wasser-Wärmepumpen werden üblicherweise monovalent ausgelegt (Betriebsweise im Expertenmodus).")
    if not r["empfehlung"] and r["qges"] > 0:
        m.append("Keine passende Wärmepumpe in den gewählten Baureihen – Kaskade, Vorlauf oder Betriebsweise prüfen.")
    if r["heizlast"]["methode"] != "vorgabe":
        m.append("Überschlägige Heizlast – vor Ausführung ist eine Heizlastberechnung nach DIN EN 12831 erforderlich.")
    return m


def herleitung(e: dict, r: dict) -> list[tuple[str, str, str]]:
    """Zeilen (Größe, Formel, Wert) wie „Herleitung Heizlast“ in index.html."""
    h, hl, t = r["heizlast"], e["heizlast"], e["tww"]
    z: list[tuple[str, str, str]] = []
    if h["methode"] == "vorgabe":
        z.append(("Heizlast QH (Vorgabe)", "z. B. aus Heizlastberechnung DIN EN 12831", f(r["qh"], 2) + " kW"))
    elif h["methode"] == "flaeche":
        z.append(("Überschlägige Heizlast QH", f"A · q = {f(hl['flaeche_m2'], 0)} m² · {f(hl['spez_w_m2'], 0)} W/m²", f(r["qh"], 2) + " kW"))
    elif h["methode"] == "huelle":
        z.append(("Transmission QT", f"(θi − θe) · A · H'T = ({f(r['innen'], 0)} − {ft(r['nat'])}) · {f(hl['huell_a_m2'], 0)} · {f(hl['ht'], 2)}",
                  f(h["transmission_kw"], 2) + " kW"))
        z.append(("Lüftung QL", f"0,5 · n · V · 0,36 · (θi − θe) = 0,5 · {f(hl['luftwechsel'], 1)} · {f(hl['volumen_m3'], 0)} · 0,36 · {f(r['innen'] - r['nat'], 1)}",
                  f(h["lueftung_kw"], 2) + " kW"))
        z.append(("Heizlast QH", "QT + QL", f(r["qh"], 2) + " kW"))
    else:
        einheit = R.HEIZWERT.get(hl.get("energietraeger"), R.HEIZWERT["gas"])[1]
        z.append(("Jahres-Endenergie Eg,in", f"Verbrauch · Hu = {f(hl['menge'], 0)} {einheit} · {f(hl['heizwert'], 2)} kWh/{einheit}", f(h["eg_kwh"], 0) + " kWh/a"))
        z.append(("Trinkwarmwasser Ew,g,in", tww_formel(e, r) if hl.get("ww_im_verbrauch") else "nicht im Verbrauch enthalten", f(h["ew_kwh"], 0) + " kWh/a"))
        z.append(("Heizung Ehg,in", "Eg,in − Ew,g,in", f(h["ehg_kwh"], 0) + " kWh/a"))
        z.append(("Leistung Wärmeerzeuger Øh,g = QH", f"Ehg,in · η / th = {f(h['ehg_kwh'], 0)} · {f(h['eta'], 2)} / {f(h['th'], 0)} h/a", f(r["qh"], 2) + " kW"))
        z.append(("Øh,in (Heizung + TWW, Excel-Blatt)", f"Øh,g + Ew,g,in / (td · 365), td = {f(t['td'], 0)} h/d", f(h["oh_in_kw"], 2) + " kW"))
    tw = r["tww"]
    if not tw["aktiv"]:
        z.append(("Warmwasserzuschlag QTW", "Warmwasser nicht über die WP", "0,00 kW"))
    else:
        liter = t.get("bezug", "liter") == "liter"
        if h["methode"] != "verbrauch":
            if liter:
                z.append(("Warmwasser je Person Qw,b", f"V · c · (45 °C − ϑKW) = {f(t['liter_p'], 0)} l · 1,163 Wh/(l·K) · "
                          f"{f(45 - (t.get('t_kw') or 10), 0)} K", f(tw["qwb_person"], 2) + " kWh/(P·d)"))
            z.append(("Trinkwarmwasser Ew,g,in", tww_formel(e, r), f(r["tww_kwh"], 0) + " kWh/a"))
        if tw["methode"] == "nachheizzeit":
            z.append(("Warmwasserzuschlag QTW", f"Ew,g,in / (td · 365) = {f(r['tww_kwh'], 0)} / ({f(t['td'], 0)} · 365)", f(r["qtw"], 2) + " kW"))
        else:
            zus = f" (aus {f(t['liter_p'], 0)} l/(P·d))" if t.get("methode", "auto") == "auto" and liter else ""
            z.append(("Warmwasserzuschlag QTW", f"np · Lastprofil = {f(t['personen'], 0)} P · {f(tw['kw_person'], 2)} kW/P{zus}",
                      f(r["qtw"], 2) + " kW"))
    sp = int(e.get("sperrzeit_h") or 0)
    z.append(("Sperrzeitzuschlag QSperr", f"(QH + QTW) · {({2: 5, 4: 10, 6: 15}).get(sp, 0)} % ({sp} h/d)" if sp else "keine Sperrzeit",
              f(r["qsperr"], 2) + " kW"))
    z.append(("Gesamtheizlast QGES", "QH + QTW + QSperr", f(r["qges"], 2) + " kW"))
    z.append(("Mindestleistung Wärmepumpe", KRITERIUM[r["kriterium"]], f(r["mindestleistung"], 2) + " kW"))
    return z


def tww_formel(e: dict, r: dict) -> str:
    t = e["tww"]
    if t.get("bezug") == "flaeche":
        return f"Qw,b · ANGF · 1,1 · 365 = {f(t['qwb'], 4)} · {f(t['flaeche_m2'], 0)} · 1,1 · 365"
    return f"Qw,b · np · 365 = {f(r['tww']['qwb_person'], 2)} · {f(t['personen'], 0)} · 365"


def eheizer_zeilen(r: dict) -> list[dict]:
    """E-Heizer je Baugröße wie index.html (Text für Tabelle)."""
    out = []
    for x in r.get("eheizer") or []:
        if x["status"] == "E-Heizer":
            bew = "E-Heizer unterstützt" + (f" (max. {f(x['eheizer_max_kw'], 0)} kW)" if x.get("eheizer_max_kw") is not None else " (bauseits)")
        else:
            bew = x["status"]
        out.append({**x, "text_q": "–" if x["q_nat"] is None else f(x["q_nat"], 2) + " kW",
                    "text_eh": "–" if x["eheizer_kw"] is None else f(x["eheizer_kw"], 1) + " kW",
                    "text_w": "–" if x["eheizer_kw"] is None else f(round(x["eheizer_kw"] * 10) * 100, 0) + " W",
                    "bewertung": bew})
    return out


def min_hinweis(r: dict) -> str:
    """Erläuterung der Mindestleistung (Modulationsgrenze) wie minHinweis() in index.html."""
    k, g = r.get("kennlinien"), r.get("gewaehlt")
    if not k or not g:
        return ""
    if not k["min"]:
        return "Für diese Baureihe liegen keine Mindestleistungen vor – keine Taktgrenze."
    v = [x for x in k["min"] if x is not None]
    sprung = max((abs(b - a) for a, b in zip(v, v[1:])), default=0.0)
    if r["waermequelle"] == "sole":
        quelle = "Mindestleistung laut Katalog (Modulationsbereich" + (", bei Supraeco T 1. Verdichter" if g["serie"] == "SupraecoT" else "") + ")"
    else:
        quelle = "Mindestleistung je Gerät laut Excel-Werkzeug" + (" (gilt für ein Gerät der Kaskade)" if g["n"] > 1 else "")
    if sprung > 0.5:
        quelle += f" · Stufen bis {f(sprung, 1)} kW stammen aus den Herstellerdaten (Temperaturbänder), sie werden nicht geglättet."
    return quelle


def anbindung(e: dict, r: dict) -> list[tuple[str, str, str]]:
    """Kacheln (Titel, Wert, Zusatz) „Warmwasser & Anbindung“ wie index.html."""
    tw, ltg, er, k = r["tww"], r.get("leitung"), r.get("erdreich"), []
    if tw["aktiv"]:
        k.append(("Warmwasser je Tag", f(tw["q_tag_kwh"], 1) + " kWh/d",
                  f"{f(tw['volumen_tag_l'], 0)} l bei {f(tw['t_speicher'], 0)} °C · " +
                  (f(tw["qwb_person"], 2) + " kWh/(P·d)" if tw["qwb_person"] is not None else "flächenbezogen")))
        k.append(("Frischwasserstation" if tw["system"] == "friwa" else "Speichersystem", f(tw["t_speicher"], 0) + " °C",
                  f"{'Puffer' if tw['system'] == 'friwa' else 'Speicher'} für {f(tw['t_zapf'], 0)} °C Zapftemperatur · "
                  f"Ladevorlauf ≈ {f(tw['vl_tww'], 0)} °C"))
        k.append(("Zuschlag Warmwasser QTW", f(r["qtw"], 2) + " kW",
                  f"Ew,g,in / (td · 365), td = {f(e['tww']['td'], 0)} h" if tw["methode"] == "nachheizzeit"
                  else f"{f(e['tww']['personen'], 0)} P · {f(tw['kw_person'], 2)} kW/P"))
    if ltg:
        k.append(("Verbindungsleitung", ltg["rohr"],
                  f"{f(ltg['volumenstrom_m3h'], 2)} m³/h (Δϑ {f(ltg['spreizung'], 0)} K) · v {f(ltg['v_ms'], 2)} m/s · "
                  f"R {f(ltg['r_pa_m'], 0)} Pa/m · Δp ≈ {f(ltg['dp_kpa'], 1)} kPa für 2 × {f(ltg['laenge_m'], 0)} m"))
    if er:
        k.append(("Erdwärmesonde (Richtwert)", f(er["sondenlaenge_m"], 0) + " m",
                  f"Entzug {f(er['q_entzug_kw'], 2)} kW (COP B0/W35 {f(er['cop'], 2)}) bei {f(er['entzug_w_m'], 0)} W/m – "
                  "Bemessung nach VDI 4640 / Geologie"))
    return k


HAFTUNG = ("Die Schnellauslegung dient der Produktvor- und Systemauswahl und ersetzt nicht die fachtechnische Planung. Sie "
           "berücksichtigt nicht die individuellen Eigenschaften eines Bauvorhabens. Leistungsdaten nach Herstellerangaben "
           "(Excel-Werkzeug „WP-Auslegung_S“, Gesamtkatalog März 2026); Zwischenwerte linear interpoliert. Die Heizlast ist "
           "nach der im Land gültigen Norm (DIN EN 12831) zu berechnen; eine Auslegung über Vorjahresverbräuche oder "
           "Flächenkennwerte ist nur überschlägig und kann zu Unter- oder Überdimensionierung führen. Der Deckungsanteil "
           "nach VDI 4650 gilt für parallelen Betrieb. Energiewerte sind Näherungen ohne Gewähr; Schallimmissionen sind "
           "gesondert nachzuweisen (TA Lärm). Vor Ausführung sind Planung und Angaben durch den ausführenden Fachbetrieb "
           "oder ein Planungsbüro auf Plausibilität, Aktualität, Richtigkeit und Vollständigkeit zu prüfen. "
           "Aufstellbedingungen, Einsatzgrenzen, R290-Sicherheitsbereiche und die elektrischen Anschlussbedingungen des "
           "Netzbetreibers sind zu beachten.")
