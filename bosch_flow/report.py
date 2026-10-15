"""Texte, Tabellen und Excel-Export – Inhalte wie in der HTML-Version."""
from __future__ import annotations

import io
import math

import pandas as pd

from .calc import Inputs, dle_cell, etage_label, puffer_produkt
from .data import MATNAME, STATIONS, WAERMEQUELLEN


def fmt(x, d: int = 0) -> str:
    """Zahl im deutschen Format (wie toLocaleString('de-DE'))."""
    if x is None or x == "" or (isinstance(x, float) and math.isnan(x)):
        return "–"
    s = f"{float(x):,.{d}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def status(v: float, vmax: float) -> str:
    if v <= vmax:
        return "OK"
    return "grenzwertig" if v <= vmax * 1.2 else "zu schnell"


def strang_table(R: dict, mode: str = "H") -> pd.DataFrame:
    """Auslegungstabelle: 'H' = maßgeblicher Etagenstrang, 'V' = Steigstrang."""
    rows = list(reversed(R["hRows"] if mode == "H" else R["vRows"]))
    n = len(R["hRows"])
    out = []
    for i, r in enumerate(rows):
        if mode == "H":
            pos = n - i
            name = "am Steigstrang" if pos == n else ("äußerste Station" if pos == 1 else f"{pos}. von außen")
        else:
            name = f"unter {etage_label(r['floor'])}" + (" · Strangfuß" if r["floor"] == R["floors"] else "")
        out.append({"Abschnitt": name, "WE" + (" kum." if mode == "V" else ""): r["weCum"], "GZ": r["gz"],
                    "V̇ ges. [m³/h]": r["Vtot"], "Dimension": r["dim"], "Rohr": r["raw"], "v [m/s]": r["v"],
                    "Δp [Pa/m]": r["dp"], "Status": status(r["v"], R["P"]["vmax"])})
    return pd.DataFrame(out)


def anlage_rows(A: dict) -> list[tuple]:
    """Wärmezentrale – Kessel & Pufferspeicher: (Größe, Wert, Einheit, Herleitung)."""
    if A["wwmode"] == "man":
        vl_her = f"Manuelle Eingabe: Versorgungs-VL {fmt(A['vlKeller'])} °C – kommt 1:1 an der Station an"
    elif A["zuheizerOn"]:
        vl_her = f"Standard mit HPS: frei eingestellt {fmt(A['vlKeller'])} °C (Bereich 40–50 °C)"
    else:
        vl_her = f"Standard: frei eingestellt {fmt(A['vlKeller'])} °C (Bereich 50–70 °C, unabhängig vom Heizkreis)"
    netz_her = f"was der Puffer liefert, kommt 1:1 an der Station an: {fmt(A['netzTemp'])} °C"
    if A["zuheizerOn"] and A["dleAktiv"]:
        netz_her += f" · der DLE hebt von hier auf {fmt(A['zapfTemp'])} °C"
    if A["zentralMode"] == "gemeinsam" and A["nStraenge"] > 1:
        gz_row = ("Gleichzeitigkeit (Gesamtanlage)", fmt(A["gz"], 1), "–",
                  f"über alle {A['weForZentrale']} Wohnungen der gemeinsamen Zentrale")
    else:
        gz_row = ("Gleichzeitigkeit (je Zentrale)", fmt(A["gz"], 1), "–",
                  f"bei {A['weForZentrale']} Wohnungen" + (" je Strang (getrennte Zentralen)" if A["nStraenge"] > 1 else ""))
    zapf = fmt(A["zapfLmin"], 1).removesuffix(",0")
    rows = [
        ("WW-Leistung je Station", fmt(A["P_WW"], 1), "kW",
         f"aus Zapfmenge {zapf} l/min: Zapfmenge × 60/1000 × 1,163 × ({fmt(A['zapfTemp'])}−10)"),
        ("Versorgungs-VL (Keller)", fmt(A["vlKeller"]), "°C", vl_her),
        ("= Netztemperatur an Station", fmt(A["netzTemp"]), "°C", netz_her),
        gz_row,
        ("Q theoretisch", fmt(A["Qtheor"], 1), "kW", "WW-Leistung × GZ + reduzierter Heizanteil"),
        ("entnommene Wärmemenge", fmt(A["Qentn"]), "kWh", f"Energie aus dem Puffer während der {fmt(A['tSpitz'])}-min-Spitze"),
        ("→ Kessel-/FW-Leistung", fmt(A["kesselQ"]), "kW", "Zusatzleistung für Puffernachladung + Grund-Heizleistung"),
    ]
    if A["zuheizerOn"]:
        if A["zuheizerWirkungslos"] and not A["dleStufeZuNiedrig"]:
            ins = [("DLE nicht erforderlich", "—", "",
                    f"Die Netztemperatur ({fmt(A['netzTemp'])} °C) erreicht bereits die Zapftemperatur "
                    f"({fmt(A['zapfTemp'])} °C). Der Booster wird erst bei niedrigerer Netztemperatur aktiv.")]
        elif A["dleStufeZuNiedrig"]:
            ins = [("⚠ DLE-Stufe zu niedrig", "—", "",
                    f"Die gewählte DLE-Stufe ({fmt(A['dleStufe'])} °C) liegt nicht über der Zapftemperatur "
                    f"({fmt(A['zapfTemp'])} °C) – es lässt sich nichts hochmischen. Höhere Stufe (53/60 °C) wählen.")]
        else:
            leistung = (f"⚠ {fmt(A['zuheizerMaxKW'])}-kW-Klasse ausgeschöpft – Mischtemperatur wird nicht ganz erreicht. "
                        "Größere Klasse (13 kW) oder kleinere Stufe prüfen." if A["zuheizerErschoepft"] else
                        f"hebt den DLE-Teilstrom auf Stufe {fmt(A['dleStufe'])} °C · Reserve "
                        f"{fmt(A['zuheizerMaxKW'] - A['zuheizerKW'], 1)} kW")
            ziel = (f"✓ Zieltemperatur {fmt(A['zapfTemp'])} °C wird durch Beimischung erreicht" if A["zielErreicht"] else
                    f"⚠ nur {fmt(A['mischTemp'])} °C statt {fmt(A['zapfTemp'])} °C – DLE-Leistung reicht für diesen Teilstrom nicht")
            ins = [
                ("Netztemperatur an Station", fmt(A["netzTemp"]), "°C",
                 f"eingestellte Versorgungstemperatur · VL am Erzeuger im Keller = {fmt(A['vlKeller'])} °C (kommt 1:1 an der Station an)"),
                ("Mischung DLE / Bypass", f"{fmt(A['dleLmin'], 1)} / {fmt(A['netzLmin'], 1)}", "l/min",
                 f"erste {fmt(A['dleLmin'], 1)} l/min über DLE auf {fmt(A['dleStufe'])} °C, {fmt(A['netzLmin'], 1)} l/min über "
                 f"Bypass mit {fmt(A['netzTemp'])} °C → Mischung {fmt(A['mischTemp'])} °C"),
                ("DLE-Leistung (Boost)", f"{fmt(A['zuheizerKW'], 1)} / {fmt(A['zuheizerMaxKW'])}", "kW", leistung),
                ("Mischtemperatur (Zapf)", fmt(A["mischTemp"]), "°C", ziel),
            ]
        rows[1:1] = ins
    if A["four"]:
        ww, hz = puffer_produkt(A["wwPufferVol"]), puffer_produkt(A["heizPufferVol"])
        rows += [
            ("→ Puffer Trinkwasser", fmt(A["wwPufferVol"]), "l", f"deckt die Warmwasser-Zapfspitzen (GLZ, Totzeit {fmt(A['tTot'])} min)"),
            ("→ Auswahl Puffer Trinkwasser (Bosch)", ww["text"], "",
             (f"Kombination {ww['liter']} l · " if ww["anzahl"] > 1 else "nächste lieferbare Baugröße · ")
             + f"aufgerundet aus {fmt(A['wwPufferVol'])} l"),
            ("→ Puffer Heizung", fmt(A["heizPufferVol"]), "l",
             f"Taktschutz (VDI 4645): Heizleistung × {fmt(A['heizTueber'])} min Mindestlaufzeit / (1,163 × {fmt(A['heizDt'])} K)"),
            ("→ Auswahl Puffer Heizung (Bosch)", hz["text"], "",
             (f"Kombination {hz['liter']} l · " if hz["anzahl"] > 1 else "nächste lieferbare Baugröße · ")
             + f"aufgerundet aus {fmt(A['heizPufferVol'])} l"),
            ("Netzpumpe Trinkwasser", fmt(A["wwPumpV"], 1), "m³/h", "Volumenstrom TWW-Kreis bei Spitzenlast"),
            ("Netzpumpe Heizung", fmt(A["heizPumpV"], 1), "m³/h", "Volumenstrom Heizkreis bei Auslegungslast"),
        ]
    else:
        pp = puffer_produkt(A["pufferVol"])
        rows += [
            ("→ Pufferspeicher-Volumen", fmt(A["pufferVol"]), "l", f"Bereitschaftsvolumen inkl. Totzeit {fmt(A['tTot'])} min"),
            ("→ Auswahl Pufferspeicher (Bosch)", pp["text"], "",
             (f"Kombination {pp['liter']} l (min. Überschuss) · " if pp["anzahl"] > 1 else "nächste lieferbare Baugröße · ")
             + f"aufgerundet aus {fmt(A['pufferVol'])} l (Reihe 500/750/1000/1500)"),
        ]
    return rows


def anlage_note(A: dict) -> str:
    if A["four"]:
        return ("4-Leiter: Heizung und Trinkwasser hydraulisch getrennt – je eigener Puffer und eigene Netzpumpe. "
                "Der Trinkwasser-Puffer deckt die Zapfspitzen, der Heizungs-Puffer dient als Bereitschaftsvolumen. "
                f"Kennwerte: Reduktionsfaktor {A['kRed']}, Totzeit {fmt(A['tTot'])} min, Wiederaufheizzeit {fmt(A['tWied'])} min.")
    return ("Kessel richtet sich nach der HEIZUNG; Warmwasserspitzen deckt der Puffer. "
            f"Kennwerte: Reduktionsfaktor {A['kRed']}, Totzeit {fmt(A['tTot'])} min, Wiederaufheizzeit {fmt(A['tWied'])} min. "
            "„entnommene Wärmemenge“ in **kWh**. Rechenweg 1:1 aus dem Bosch-HIU-Tool.")


def dle_cell_text(c: dict) -> str:
    return c["txt"] if c["txt"] is not None else f"{fmt(c['kw'], 1)} kW"


def dle_rows_text(rows: list) -> list:
    return [[f"{r['netzTemp']} °C" + (" ◄ aktuell" if r["aktuell"] else "")]
            + [dle_cell_text(r["cells"][s]) for s in (48, 53, 60)] for r in rows]


def dle_fazit(A: dict) -> tuple[str, str]:
    """(Zustand, Text) für die aktuelle DLE-Kombination."""
    c = dle_cell(A["netzTemp"], A["dleStufe"], A["zapfLmin"], A["zapfTemp"], A["zuheizerMaxKW"])
    v, tn, tz, kl = fmt(A["zapfLmin"]), fmt(A["netzTemp"]), fmt(A["zapfTemp"]), fmt(A["zuheizerMaxKW"])
    if c["state"] == "none":
        return "none", (f"**In dieser Konfiguration wird der DLE nicht gebraucht:** Die Netztemperatur an der Station ({tn} °C "
                        f"= Versorgungs-VL, kommt 1:1 an der Station an) erreicht bereits die Zapftemperatur {tz} °C – es muss "
                        "nichts beigemischt werden. Der DLE arbeitet erst, wenn die Netztemperatur **unter** der Zapftemperatur "
                        "liegt – dann eine niedrigere Versorgungs-VL wählen (mit HPS 40–50 °C).")
    if c["state"] == "ok":
        return "ok", (f"**Passt:** Für {v} l/min von {tn} °C auf {tz} °C braucht der DLE {dle_cell_text(c)} – das liegt "
                      f"innerhalb deiner {kl}-kW-Klasse.")
    if c.get("warn"):
        return "over", (f"**Achtung:** Mit Stufe {fmt(A['dleStufe'])} °C erreicht der DLE bei {v} l/min die Zapftemperatur "
                        f"{tz} °C nicht – der 8-l/min-Teilstrom ist zu klein. Höhere DLE-Stufe wählen oder Netztemperatur anheben.")
    return "over", (f"**Achtung:** Für {v} l/min von {tn} °C auf {tz} °C bräuchte der DLE {dle_cell_text(c)} – das übersteigt "
                    f"deine {kl}-kW-Klasse. Größere Klasse (13 kW) wählen oder Netztemperatur anheben.")


def inputs_table(inp: Inputs, meta: dict) -> pd.DataFrame:
    st = STATIONS.get(inp.station, STATIONS["flow8000"])
    rows = [
        ("Projektname", meta.get("projName", "")), ("Standort", meta.get("projLoc", "")),
        ("Planer / Bearbeiter", meta.get("projPlanner", "")), ("Datum", meta.get("projDate", "")),
        ("Leitersystem", f"{inp.system}-Leiter"), ("Wärmequelle", WAERMEQUELLEN[inp.waermequelle]["name"]),
        ("Wohnungsstation", st["name"]), ("WW-Leistungsstufe", "{kw} kW · bis {lmin} l/min".format(**st["stages"][int(inp.wwstage)])),
        ("Warmwasser-Parameter", "Manuell" if inp.wwmode == "man" else "Standard"),
        ("Heizlast je Wohnung [kW]", inp.qhk), ("Spreizung ΔT [K]", inp.dthk), ("Versorgungs-VL [°C]", inp.tvl),
        ("VL Heizkreis [°C]", inp.vlhk), ("Gleichzeitigkeit", "TU Dresden" if inp.glz == "tud" else "DIN 4708"),
        ("Rohrmaterial", MATNAME[inp.mat]), ("max. Geschwindigkeit [m/s]", inp.vmax), ("Spitzenzeit [min]", inp.tsp),
        ("Kesseltotzeit [min]", inp.tTot), ("Wiederaufheizzeit [min]", inp.tWied),
        ("Wärmezentrale", "gemeinsam" if inp.zentral == "gemeinsam" else "getrennt je Strang"),
    ]
    if inp.wwmode == "man":
        rows += [("Zapfmenge [l/min]", inp.zapfMenge), ("Zapftemperatur [°C]", inp.zapfTemp)]
    if inp.zuheizer == "on" and st["zuheizerFaehig"] and inp.system == "2":
        rows += [("Elektr. Zuheizer", f"{fmt(inp.zuheizerKW)} kW · Stufe {fmt(inp.dleStufe)} °C")]
    if inp.system == "4":
        rows += [("Puffer-Mindestlaufzeit [min]", inp.heizTueber), ("Puffer-Spreizung ΔT [K]", inp.heizDt)]
    return pd.DataFrame(rows, columns=["Eingabe", "Wert"])


def excel_bytes(inp: Inputs, meta: dict, results: list, straenge: list) -> bytes:
    """Excel-Mappe: Eingaben, Wärmezentrale, je Strang Etagen- & Steigstrang, Etagenbelegung."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        inputs_table(inp, meta).to_excel(xw, sheet_name="Eingaben", index=False)
        for i, R in enumerate(results):
            A = R["anlage"]
            pd.DataFrame(anlage_rows(A), columns=["Größe", "Wert", "Einheit", "Herleitung"]).to_excel(
                xw, sheet_name=f"Zentrale S{i + 1}" if A["zentralMode"] == "getrennt" else "Wärmezentrale", index=False)
            if A["zentralMode"] != "getrennt":
                break
        for i, R in enumerate(results):
            sh = f"Strang {i + 1}"
            belegung = pd.DataFrame([{"Etage": etage_label(f + 1), "links": c["l"], "rechts": c["r"], "WE": R["floorWE"][f]}
                                     for f, c in enumerate(R["cfg"])][::-1])
            belegung.to_excel(xw, sheet_name=sh, index=False, startrow=1)
            col = len(belegung.columns) + 1
            pd.DataFrame([["Etagenstrang (maßgeblich)"]]).to_excel(xw, sheet_name=sh, index=False, header=False, startcol=col)
            strang_table(R, "H").to_excel(xw, sheet_name=sh, index=False, startrow=1, startcol=col)
            start = len(R["hRows"]) + 4
            pd.DataFrame([["Steigstrang"]]).to_excel(xw, sheet_name=sh, index=False, header=False, startrow=start, startcol=col)
            strang_table(R, "V").to_excel(xw, sheet_name=sh, index=False, startrow=start + 1, startcol=col)
        from .katalog import KATALOG, PREISHINWEIS, projekt_stueckliste
        zeilen = projekt_stueckliste(inp, straenge, meta)
        sl = pd.DataFrame([{"Position": z["pos"], "Bezeichnung": z["text"], "Bestell-Nr.": z["nr"], "Menge": z["menge"],
                            "UVP €": z["uvp"], "Summe €": z["summe"]} for z in zeilen])
        sl.loc[len(sl)] = ["Summe", "Katalogpositionen (UVP, ohne MwSt.)", "", None, None,
                           float(sum(z["summe"] or 0 for z in zeilen))]
        sl.to_excel(xw, sheet_name="Stückliste", index=False, startrow=1)
        pd.DataFrame([[f"{KATALOG} – {PREISHINWEIS}"]]).to_excel(xw, sheet_name="Stückliste", index=False, header=False)
        for ws in xw.book.worksheets:
            for column in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in column)
                ws.column_dimensions[column[0].column_letter].width = min(60, max(8, width + 2))
                for c in column:
                    if isinstance(c.value, float):
                        c.number_format = "0.00"
    return buf.getvalue()


# ---------------------------------------------------------------- Texte (wie HTML V54)
DLE_ELEKTRO = ("⚡ Elektrische Anmeldung & Leitungsbemessung (DLE 11 kW / 13 kW): Die dezentralen Durchlauferhitzer "
               "(11 kW / 13 kW) sind elektrische Großgeräte. Die Dimensionierung des Hausanschlusses und der "
               "Hauptleitungen darf nicht durch einfache Addition der Einzelleistungen erfolgen. Sie muss zwingend "
               "durch eine ELT-Fachkraft unter Anwendung des degressiven Gleichzeitigkeitsfaktors nach DIN 18015-1 "
               "(Anhang A) bemessen werden. Die Anmeldung bzw. Genehmigung sind beim örtlichen Netzbetreiber gemäß den "
               "regionalen TAB bauseits vorzunehmen.")
PMAX_HINWEIS = ("Hinweis Pmax: Die maximale Anschlussleistung Pmax ergibt sich aus dem Wohnbedarf nach DIN zuzüglich "
                "bewerteter Sonderlasten (z. B. Ladeinfrastruktur), abzüglich möglicher Effekte durch Lastmanagement, "
                "Speicher und Gleichzeitigkeitsfaktoren, und muss bauseits ermittelt werden.")
DIN18015_TEXT = ("Die HPS-Variante hat je Wohnung einen elektrischen Durchlauferhitzer (11 / 13 kW). Für den "
                 "elektrischen Netzanschluss dürfen die Einzelleistungen nicht addiert werden – es gilt der degressive "
                 "Gleichzeitigkeitsfaktor. Da HPS immer elektrische WW-Bereitung nutzt, ist die blaue Kurve (MIT) "
                 "maßgeblich.")
HAFTUNGSHINWEISE = [
    "Rechenkern nach Bosch-HIU-Methodik (Gleichzeitigkeit DIN 4708 / TU Dresden, Knotenpunkt-Formel, "
    "Darcy-Weisbach, turbulent).",
    "Werkzeug zur Vorplanung – ersetzt keine verbindliche Rohrnetzberechnung. Prüfung obliegt Planer, Installateur "
    "oder Bauherr.",
    "Kesselleistung und Pufferspeicher sind überschlägige Auslegungswerte (Rechenweg 1:1 aus dem Bosch-HIU-Tool).",
    "Elektrische Durchlauferhitzer (DLE) sind von einer ELT-Fachkraft nach DIN 18015-1 zu bemessen und beim "
    "Netzbetreiber anzumelden.",
]


def hauptstrang_erklaerung(results: list, T: dict) -> str:
    from .calc import seg
    P = results[0]["P"]
    w_outer = results[0]["totalWE"]
    dn_outer = seg(w_outer, P)["dim"]
    g = T["gesamt"]["dim"]
    return (f"So liest sich die Hauptstrang-Auslegung: Der senkrechte Strang (Steigleitung) und der waagerechte "
            f"Hauptstrang sind zwei verschiedene Leitungen. Ein einzelner Strang führt am Strangfuß {dn_outer} "
            f"({w_outer} WE). Der Hauptstrang sammelt die Stränge von außen zur Zentrale hin auf und wird deshalb "
            f"abschnittsweise dicker: am äußeren Abschnitt {dn_outer} (nur {w_outer} WE), und mit jedem weiteren Strang "
            f"eine Stufe größer – bis zur Gesamtlast an der Zentrale ({g}, {T['gesamtWE']} WE). Die scheinbare "
            f"Reduzierung „{g} → {dn_outer}“ ist also kein Sprung, sondern die zwei Enden derselben Treppe: viel Last "
            f"nahe der Zentrale, wenig Last ganz außen. Dimensioniert wird je Abschnitt nach der Strömungsgeschwindigkeit "
            f"(v ≤ {fmt(P['vmax'], 2)} m/s). Der als ◆ maßgeblich markierte Abschnitt hat die höchste Geschwindigkeit.")


def gesamt_note(G: dict, n: int) -> str:
    if G["getrennt"]:
        return (f"Getrennte Ausführung: Jeder Strang ist eine eigene Anlage mit eigenem Kessel und Puffer. Die "
                f"Gesamtwerte sind die Summe der {n} Einzelanlagen – NICHT eine gemeinsame Zentrale über {G['we']} "
                "Wohnungen. Deshalb liegt die Summe höher als bei gemeinsamer Ausführung (ungünstigere "
                "Gleichzeitigkeit kleiner Einzelanlagen).")
    return (f"Gemeinsame Wärmezentrale über alle Stränge ({G['we']} Wohnungen). Bei getrennter Ausführung siehe die "
            "Einzelwerte je Strang.")


def schema_note(R: dict, n_str: int) -> str:
    P, foot = R["P"], R["vRows"][0]
    name = "Flow 7000 (F7002 HPS)" if P["zuheizerOn"] else R["st"]["name"]
    vor = (f"Strang {R['activeStrang'] + 1} von {n_str} · alle Stränge zusammen {R['allWE']} Wohnungen · "
           f"Wärmezentrale {'gemeinsam' if R['anlage']['zentralMode'] == 'gemeinsam' else 'getrennt je Strang'}. "
           if n_str > 1 else "")
    return (f"{vor}**{R['floors']}** Etagen · **{R['totalWE']}** Wohnungen "
            f"{'in diesem Strang' if n_str > 1 else 'gesamt'}"
            + (" (links/rechts je Etage einstellbar)" if R["sides"] == 2 else " (einseitig)")
            + f" · {P['system']}-Leiter · {name} · GLZ nach **{'TU Dresden' if P['glz'] == 'tud' else 'DIN 4708'}**. "
            f"Maßgeblicher Etagenstrang außen **{R['hRows'][0]['dim']}**, Strangfuß **{foot['dim']}** bei "
            f"**{fmt(foot['Vtot'], 2)} m³/h**, v = {fmt(foot['v'], 2)} m/s.")
