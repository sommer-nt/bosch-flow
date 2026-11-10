"""Texte und Formatierung für App und PDF (wie die Anzeige in index.html)."""
from __future__ import annotations

from . import rechnen as R

BETRIEBSWEISE = {"monovalent": "monovalent", "monoenergetisch": "monoenergetisch", "hybrid": "GEG-Hybrid"}
KRITERIUM = {"monovalent": "QGES bei θe (monovalent)",
             "monoenergetisch": "0,7 · QGES bei A-7 (monoenergetisch, ca. 98 % Deckung)",
             "hybrid": "0,3 · QH bei A-7 (GEG § 71 Hybrid)"}


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


def meldungen(e: dict, r: dict, katalog: dict) -> list[str]:
    m = list(r["hinweise"])
    g = r.get("gewaehlt")
    if g and not g["moeglich"]:
        m.append(f"{g['geraet']}: {g['grund']}.")
    elif g and not g["ok"]:
        m.append(f"{g['geraet']}{' (' + str(g['n']) + '×)' if g['n'] > 1 else ''} erfüllt das Kriterium nicht: {g['grund']}.")
    if g and g.get("ueberdimensioniert"):
        m.append("Gewählte Wärmepumpe ist deutlich überdimensioniert (Abdeckung bei θe über 150 %) – Taktverhalten prüfen.")
    if g and g["moeglich"] and r["nat"] < g["t_daten_min"]:
        m.append(f"Leistungsdaten erst ab {ft(g['t_daten_min'])} °C – unterhalb wird der letzte Wert angesetzt.")
    ie = inneneinheit(e, r, katalog)
    if ie and ie.get("vl_max") and r["vl"] > ie["vl_max"]:
        m.append(f"{ie['typ']}: max. Vorlauftemperatur {ie['vl_max']} °C.")
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
        z.append(("Trinkwarmwasser Ew,g,in", tww_formel(e) if hl.get("ww_im_verbrauch") else "nicht im Verbrauch enthalten", f(h["ew_kwh"], 0) + " kWh/a"))
        z.append(("Heizung Ehg,in", "Eg,in − Ew,g,in", f(h["ehg_kwh"], 0) + " kWh/a"))
        z.append(("Leistung Wärmeerzeuger Øh,g = QH", f"Ehg,in · η / th = {f(h['ehg_kwh'], 0)} · {f(h['eta'], 2)} / {f(h['th'], 0)} h/a", f(r["qh"], 2) + " kW"))
        z.append(("Øh,in (Heizung + TWW, Excel-Blatt)", f"Øh,g + Ew,g,in / (td · 365), td = {f(t['td'], 0)} h/d", f(h["oh_in_kw"], 2) + " kW"))
    if t.get("aktiv") is False:
        z.append(("Warmwasserzuschlag QTW", "Warmwasser nicht über die WP", "0,00 kW"))
    elif t.get("methode") == "nachheizzeit":
        z.append(("Warmwasserzuschlag QTW", f"Ew,g,in / (td · 365) = {f(r['tww_kwh'], 0)} / ({f(t['td'], 0)} · 365)", f(r["qtw"], 2) + " kW"))
    else:
        z.append(("Warmwasserzuschlag QTW", f"np · Lastprofil = {f(t['personen'], 0)} P · {f(t['kw_person'], 2)} kW/P", f(r["qtw"], 2) + " kW"))
    sp = int(e.get("sperrzeit_h") or 0)
    z.append(("Sperrzeitzuschlag QSperr", f"(QH + QTW) · {({2: 5, 4: 10, 6: 15}).get(sp, 0)} % ({sp} h/d)" if sp else "keine Sperrzeit",
              f(r["qsperr"], 2) + " kW"))
    z.append(("Gesamtheizlast QGES", "QH + QTW + QSperr", f(r["qges"], 2) + " kW"))
    z.append(("Mindestleistung Wärmepumpe", KRITERIUM[r["kriterium"]], f(r["mindestleistung"], 2) + " kW"))
    return z


def tww_formel(e: dict) -> str:
    t = e["tww"]
    if t.get("bezug") == "flaeche":
        return f"Qw,b · ANGF · 1,1 · 365 = {f(t['qwb'], 4)} · {f(t['flaeche_m2'], 0)} · 1,1 · 365"
    return f"Qw,b · np · 365 = {f(t['qwb'], 2)} · {f(t['personen'], 0)} · 365"


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
