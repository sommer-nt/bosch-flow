"""BOSCH Flow – Netz- & Anlagenrechner für Wohnungsstationen (Streamlit).

Start:  streamlit run app.py
Aufbau und Rechenkern wie die HTML-Version V54 (index.html): links die Eingabekarten ①②③, rechts Kennzahlen,
Netzschema (Aktueller Strang / Alle Stränge mit Netztopologie), Anlagenschema, Auslegungs-Tabelle, Diagramm,
Wärmezentrale und DLE-Auslegungshilfe. Auto-Sicherung im Browser, Hell/Dunkel, PDF-Export.
"""
from __future__ import annotations

import hmac
import json
import os
from dataclasses import replace
from datetime import date, datetime

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Bosch Flow – Netz- & Anlagenrechner", page_icon="🔥", layout="wide")

from bosch_flow import plots, schemata  # noqa: E402
from bosch_flow import report as RP  # noqa: E402
from bosch_flow.bericht import pdf_bericht  # noqa: E402
from bosch_flow.modell3d import modell  # noqa: E402
from bosch_flow import varianten as VA  # noqa: E402
from bosch_flow.calc import (Inputs, Strang, build_params, compute_all, din18015, dle_table, etage_label,  # noqa: E402
                             gesamt_anlage, project_headline, puffer_produkt, topo_label, topologie, tvl_bounds,
                             zapf_max_lmin)
from bosch_flow.data import MATNAME, STATIONS, WAERMEQUELLEN  # noqa: E402
from bosch_flow.project import dumps, from_html_state, stand  # noqa: E402
from bosch_flow.report import fmt  # noqa: E402
from bosch_flow.zeichnung import als_plotly  # noqa: E402
from browser import browser  # noqa: E402

ss = st.session_state
BLAU = "#005691"


# ====================================================================== Zugang (optional)
def _secret(name: str) -> str | None:
    """Umgebungsvariable oder Streamlit-Secret (Streamlit Cloud: Settings → Secrets)."""
    if os.environ.get(name, "").strip():
        return os.environ[name].strip()
    try:
        return str(st.secrets[name]).strip() or None
    except Exception:  # noqa: BLE001 – keine Secrets hinterlegt
        return None


_passwort = _secret("APP_PASSWORT")
if _passwort and not ss.get("angemeldet"):
    st.markdown("### 🔒 BOSCH Flow · Netz- & Anlagenrechner")
    eingabe = st.text_input("Passwort", type="password")
    if eingabe:
        if hmac.compare_digest(eingabe, _passwort):
            ss.angemeldet = True
            st.rerun()
        st.error("Passwort falsch.")
    st.stop()

try:
    DUNKEL = st.context.theme.type == "dark"
except Exception:  # noqa: BLE001
    DUNKEL = False
AKZENT = "#4fa3e0" if DUNKEL else BLAU

# ====================================================================== Stil
st.markdown(f"""
<style>
.block-container {{padding-top: 2.6rem; max-width: min(1720px, 98vw)}}
.kopf {{display:flex; align-items:baseline; gap:16px; flex-wrap:wrap; padding-bottom:10px; border-bottom:3px solid;
       border-image:linear-gradient(90deg,#e20015 0%,#b90276 22%,#50237f 44%,#005691 70%,#008ecf 100%) 1}}
.logo {{font-weight:800; letter-spacing:.3px; font-size:22px; color:#e20015}}
.logo span {{color:{'#e6edf3' if DUNKEL else '#141e29'}}}
.unter {{color:#78889a; font-size:13px}}
.devbadge {{font-size:12px; color:#78889a; border:1px solid rgba(128,128,128,.3); padding:5px 13px;
           border-radius:20px; font-weight:500; white-space:nowrap; text-align:center}}
.devbadge b {{color:{'#4fa3e0' if DUNKEL else BLAU}}}
.karte-titel {{font-size:12px; font-weight:800; letter-spacing:.6px; text-transform:uppercase;
              color:{'#4fa3e0' if DUNKEL else BLAU}; margin:-4px 0 6px}}
.karte-titel small {{text-transform:none; letter-spacing:0; font-weight:500; color:#78889a; margin-left:8px}}
.empf {{border:1px solid rgba(43,147,72,.45); background:rgba(43,147,72,.08); border-radius:12px; padding:10px 14px;
        margin-bottom:.6rem; font-size:14px; line-height:1.5}}
.empf ul {{margin:.3rem 0 .2rem 1.1rem; padding:0}} .empf small {{color:#78889a}}
.empf-tag {{background:#2b9348; color:#fff; border-radius:20px; padding:1px 9px; font-size:11px; font-weight:700;
            margin-right:8px; letter-spacing:.03em; text-transform:uppercase}}
.hinweis {{font-size:12px; line-height:1.45; color:#78889a; border-left:3px solid {BLAU}; padding:6px 10px;
          background:rgba(0,86,145,.07); border-radius:0 6px 6px 0; margin:2px 0 8px}}
.autosave {{font-size:11.5px; color:#2e7d32; text-align:center; margin:2px 0 6px}}
.info-zeile {{display:flex; justify-content:space-between; gap:.6rem; font-size:12.5px; padding:.18rem 0;
             border-bottom:1px dashed rgba(128,128,128,.25)}}
.info-zeile span:first-child {{color:#78889a}}
.etage {{font-size:13px; font-weight:700; text-align:right}}
.lr {{font-size:11px; color:#78889a}}
.abschnitt {{flex:1 1 160px; min-width:150px; border:1px solid rgba(128,128,128,.25); border-left:4px solid {BLAU};
            border-radius:8px; padding:8px 10px}}
.abschnitt.krit {{border-color:#b26a00; border-left-color:#b26a00; background:rgba(178,106,0,.08)}}
.abschnitt .num {{display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px;
                 border-radius:50%; background:{BLAU}; color:#fff; font-size:11px; font-weight:700; margin-right:6px}}
.abschnitt.krit .num {{background:#b26a00}}
.strangkopf {{font-weight:700; font-size:14px; margin:4px 0}}
.badge2 {{display:inline-block; font-size:11.5px; font-weight:600; padding:2px 9px; border-radius:12px;
         border:1px solid rgba(128,128,128,.3); margin:0 4px 4px 0}}
[data-testid="stMetric"] {{border:1px solid rgba(128,128,128,.25); border-top:3px solid {BLAU}; border-radius:12px;
                          padding:10px 14px}}
[data-testid="stMetricValue"] {{font-size:clamp(1.3rem, 2vw, 1.9rem) !important; font-weight:700;
                               color:{'#4fa3e0' if DUNKEL else BLAU}}}
[data-testid="stMetricValue"] > div {{overflow:visible !important; text-overflow:clip !important}}
.st-key-kopfschalter {{display:flex; justify-content:flex-end}}
/* „Anheften“: Netzschema bleibt beim Scrollen oben stehen */
.st-key-schemakarte-an {{position:sticky; top:3.4rem; z-index:20; max-height:62vh; overflow:auto;
                        background:{'#0e1117' if DUNKEL else '#ffffff'}}}
.fuss {{text-align:center; color:#8a949e; font-size:12px; line-height:1.6; padding:1.4rem 0 .4rem;
        border-top:1px solid rgba(128,128,128,.2); margin-top:1rem}}
</style>""", unsafe_allow_html=True)


# ====================================================================== Projektzustand
def neues_projekt(inp: Inputs | None = None, straenge: list | None = None, meta: dict | None = None) -> None:
    ss.inp = inp or Inputs()
    ss.straenge = straenge or [Strang.new()]
    m = {"projName": "", "projLoc": "", "projPlanner": "", "projDate": date.today().isoformat(),
         "activeStrang": 0, "topoPos": 50.0}
    m.update(meta or {})
    m["activeStrang"] = max(0, min(len(ss.straenge) - 1, int(m.get("activeStrang") or 0)))
    ss.meta = m
    ss.rev = ss.get("rev", 0) + 1
    ss.pop("va_vorher", None)
    ss.pdf_cache = {}


def laden(text: str | bytes, quelle: str) -> bool:
    try:
        inp, straenge, meta = from_html_state(json.loads(text))
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as e:
        ss.meldung = ("error", f"Projekt konnte nicht geladen werden: {e}")
        return False
    neues_projekt(inp, straenge, meta)
    ss.meldung = ("success", quelle)
    return True


def k(name: str) -> str:
    """Widget-Schlüssel; neu, sobald das Projekt von außen ersetzt wird (Laden, Wiederherstellen, Zurücksetzen)."""
    return f"{name}_{ss.rev}"


def setze(**felder) -> None:
    neu = replace(ss.inp, **felder)
    if neu != ss.inp:
        ss.inp = neu


if "inp" not in ss:
    neues_projekt()
if msg := ss.pop("meldung", None):
    st.toast(msg[1], icon="✅" if msg[0] == "success" else "⚠️")


# ====================================================================== Kopfzeile
c1, c2, c3 = st.columns([6, 2.2, 0.5], vertical_alignment="center")
c1.markdown('<div class="kopf"><span class="logo">BOSCH <span>Flow</span></span>'
            '<span class="unter">Netz- &amp; Anlagenrechner für Wohnungsstationen</span></div>', unsafe_allow_html=True)
c2.markdown('<div class="devbadge">Entwickelt von <b>Daniel Sommer</b> · HC/SDE3-PSD</div>', unsafe_allow_html=True)
kopfschalter = c3.container(key="kopfschalter")   # Hell/Dunkel-Schalter (wird am Ende des Laufs eingesetzt)

links, rechts = st.columns([1.12, 3], gap="medium")


def karte(titel: str, zusatz: str = "", key: str | None = None):
    c = st.container(border=True, key=key)
    c.markdown(f'<div class="karte-titel">{titel}{f"<small>{zusatz}</small>" if zusatz else ""}</div>',
               unsafe_allow_html=True)
    return c


# ====================================================================== Eingaben (links)
with links:
    meta = ss.meta
    # ---------------------------------------------------------------- Projekt
    with karte("Projekt"):
        meta["projName"] = st.text_input("Projektname", meta["projName"], key=k("projName"),
                                         placeholder="z. B. Wohnanlage Musterstraße")
        meta["projLoc"] = st.text_input("Standort", meta["projLoc"], key=k("projLoc"), placeholder="z. B. Stuttgart")
        a, b = st.columns(2)
        meta["projPlanner"] = a.text_input("Planer / Bearbeiter", meta["projPlanner"], key=k("projPlanner"),
                                           placeholder="Name")
        try:
            d0 = date.fromisoformat(str(meta.get("projDate") or "")[:10])
        except ValueError:
            d0 = date.today()
        meta["projDate"] = b.date_input("Datum", d0, key=k("projDate"), format="DD.MM.YYYY").isoformat()
        projekt_knoepfe = st.container()          # Knöpfe brauchen den Stand nach allen Eingaben – unten befüllt

    # ---------------------------------------------------------------- ① Gebäude
    with karte("① Gebäude"):
        straenge = ss.straenge
        n = len(straenge)
        aktiv = meta["activeStrang"]
        if n > 1:                                  # eigene Zeile, damit auch viele Stränge sichtbar bleiben
            namen = [f"Strang {i + 1}" if n <= 3 else f"S{i + 1}" for i in range(n)]
            w = st.segmented_control("Strang", namen, default=namen[aktiv], key=f"strang_geb_{ss.rev}_{aktiv}_{n}",
                                     label_visibility="collapsed", width="stretch")
            if w and namen.index(w) != aktiv:
                meta["activeStrang"] = namen.index(w)
                st.rerun()
        b, c = st.columns(2, vertical_alignment="center")
        if b.button("＋ Strang", help="Neuer Strang als Kopie des aktuellen", width="stretch"):
            cur = straenge[aktiv]
            straenge.append(Strang(cur.floors, cur.split, [dict(x) for x in cur.cfg]))
            meta["activeStrang"] = len(straenge) - 1
            st.rerun()
        if c.button("－ Strang", help="Aktuellen Strang löschen", disabled=n <= 1, width="stretch"):
            straenge.pop(aktiv)
            meta["activeStrang"] = min(aktiv, len(straenge) - 1)
            ss.rev += 1
            st.rerun()
        z = st.selectbox("Wärmezentrale", ["gemeinsam", "getrennt"], ["gemeinsam", "getrennt"].index(ss.inp.zentral),
                         key=k("zentral"),
                         format_func=lambda v: "gemeinsam (eine Zentrale)" if v == "gemeinsam" else "getrennt (je Strang)",
                         help="Gemeinsam = eine Zentrale für alle Stränge (Summe der Wohnungen). Getrennt = jeder Strang "
                              "eigener Kessel/Puffer.")
        setze(zentral=z)
        si = meta["activeStrang"]
        s = straenge[si]
        a, b = st.columns(2)
        fl = int(a.number_input("Etagen", 1, 20, int(s.floors), 1, key=k(f"floors{si}"),
                                help="Geschosse, die DIESER Steigstrang versorgt. Für jede Etage kann die Stationszahl "
                                     "einzeln gesetzt werden."))
        sp = b.selectbox("Aufteilung", ["both", "one"], 0 if s.split == "both" else 1, key=k(f"split{si}"),
                         format_func=lambda v: "beidseitig (L + R)" if v == "both" else "einseitig",
                         help="Beidseitig = Stationen links und rechts vom Steigstrang. Einseitig = ein Strang je Etage.")
        if fl != s.floors or sp != s.split:
            cfg = [dict(x) for x in s.cfg[:fl]]
            while len(cfg) < fl:
                cfg.append({"l": 5, "r": 5})
            for x in cfg:
                x["r"] = (x["r"] if s.split == "both" else x["l"]) if sp == "both" else 0
            s.floors, s.split, s.cfg = fl, sp, cfg
            ss.rev += 1
            st.rerun()
        a, b, _ = st.columns([0.9, 0.5, 1.5], vertical_alignment="center")
        a.markdown('<div class="lr" style="text-align:right">Schnell setzen:</div>', unsafe_allow_html=True)
        q = b.number_input("Schnell setzen", 0, 16, 5, 1, key=k("quick"), label_visibility="collapsed")
        if _.button("auf alle Etagen", width="stretch"):
            s.cfg = [{"l": int(q), "r": int(q) if s.split == "both" else 0} for _x in range(s.floors)]
            ss.rev += 1
            st.rerun()
        # Etagenliste wie in der HTML: oberste Etage zuerst, je Etage links / rechts
        for f in range(s.floors, 0, -1):
            cf = s.cfg[f - 1]
            if s.split == "both":
                e, l, ll, r, rr = st.columns([0.9, 1.3, 0.3, 1.3, 0.3], vertical_alignment="center")
            else:
                e, l, ll = st.columns([0.9, 2.6, 0.6], vertical_alignment="center")
            e.markdown(f'<div class="etage">{etage_label(f)}</div>', unsafe_allow_html=True)
            cf["l"] = int(l.number_input(f"{etage_label(f)} links", 0, 16, int(cf["l"]), 1,
                                         key=k(f"l{si}_{f}"), label_visibility="collapsed"))
            ll.markdown('<div class="lr">L</div>' if s.split == "both" else '<div class="lr">Stationen</div>',
                        unsafe_allow_html=True)
            if s.split == "both":
                cf["r"] = int(r.number_input(f"{etage_label(f)} rechts", 0, 16, int(cf["r"]), 1,
                                             key=k(f"r{si}_{f}"), label_visibility="collapsed"))
                rr.markdown('<div class="lr">R</div>', unsafe_allow_html=True)

    # ---------------------------------------------------------------- ② System & Gerät
    with karte("② System & Gerät"):
        v = st.selectbox("Leitersystem (projektweit)", ["2", "4"], ["2", "4"].index(ss.inp.system), key=k("system"),
                         format_func=lambda x: "2-Leiter (Heizung + Trinkwasser über Station)" if x == "2"
                         else "4-Leiter (Heizung + Trinkwasser getrennt)",
                         help="Grundsatzentscheidung für die GESAMTE Anlage – gilt für alle Stränge. 2-Leiter für "
                              "Erzeuger mit hoher Vorlauftemperatur (>55 °C, z. B. Kessel/Fernwärme), 4-Leiter für "
                              "Wärmepumpen/Niedertemperatur.")
        setze(system=v)
        st.markdown('<div class="hinweis">' + (
            "Ein gemeinsames Leitungspaar für Heizung + Trinkwasser. Passt zu Erzeugern mit hoher Vorlauftemperatur "
            "(Kessel, Fernwärme)." if v == "2" else
            "Getrennte Leitungspaare für Heizung und Trinkwasser (vier Rohre). Typisch bei Wärmepumpen / "
            "Niedertemperatur.") + "</div>", unsafe_allow_html=True)
        qv = st.selectbox("Wärmequelle", list(WAERMEQUELLEN), list(WAERMEQUELLEN).index(ss.inp.waermequelle),
                          key=k("waermequelle"), format_func=lambda x: WAERMEQUELLEN[x]["name"],
                          help="Setzt Kesseltotzeit / Wiederaufheizzeit automatisch (unten anpassbar).")
        if qv != ss.inp.waermequelle:
            wq = WAERMEQUELLEN[qv]
            setze(waermequelle=qv, tTot=float(wq["tot"]), tWied=float(wq["wied"]))
            ss.rev += 1
            st.rerun()
        wq = WAERMEQUELLEN[qv]
        st.markdown(f'<div class="hinweis">{wq["txt"]}<br><b>Automatisch gesetzt:</b> Kesseltotzeit '
                    f'<b>{wq["tot"]} min</b> · Wiederaufheizzeit <b>{wq["wied"]} min</b> (unten anpassbar).</div>',
                    unsafe_allow_html=True)
        stv = st.selectbox("Wohnungsstation", list(STATIONS), list(STATIONS).index(ss.inp.station), key=k("station"),
                           format_func=lambda x: STATIONS[x]["name"],
                           help="Flow 8000: WW-Vorrang (Heizung pausiert beim Zapfen). Flow 7000: WW-Parallelbetrieb "
                                "(Heizung läuft weiter).")
        stn = STATIONS[stv]
        setze(station=stv, wwstage=min(ss.inp.wwstage, len(stn["stages"]) - 1))
        ws = st.selectbox("Warmwasser-Leistungsstufe", list(range(len(stn["stages"]))), ss.inp.wwstage,
                          key=k(f"wwstage_{stv}"),
                          format_func=lambda i: "{kw} kW · bis {lmin} l/min".format(**stn["stages"][i]),
                          help="Bestimmt die Zapfmenge je Station laut Gerätedatenblatt (Standard-Modus).")
        wm = st.selectbox("Warmwasser-Parameter", ["std", "man"], ["std", "man"].index(ss.inp.wwmode), key=k("wwmode"),
                          format_func=lambda x: "Standard (aus Leistungsstufe)" if x == "std" else "Manuelle Eingabe",
                          help="Standard: Zapfmenge aus der Leistungsstufe, 45 °C. Manuell: bedarfsgerechte Zapfmenge "
                               "und Zapftemperatur – optimiert Speicher- und Erzeugergröße.")
        setze(wwstage=ws, wwmode=wm)
        if wm == "man":
            a, b = st.columns(2)
            zt = b.number_input("Zapftemperatur °C", 45.0, 60.0, min(max(float(ss.inp.zapfTemp), 45.0), 60.0), 1.0,
                                format="%.0f", key=k("zapfTemp"), help="45 °C (Muss-Minimum) bis 60 °C.")
            mx = max(5.0, zapf_max_lmin(replace(ss.inp, zapfTemp=zt)))
            zm = a.number_input("Zapfmenge l/min", 5.0, mx, min(max(5.0, float(ss.inp.zapfMenge)), mx), 0.5,
                                format="%.1f", key=k(f"zapfMenge_{mx}"),
                                help="Ab 5 l/min. Der Maximalwert ergibt sich aus der kW-Klasse der Station und der "
                                     "Zapftemperatur – mehr kann die Station nicht liefern.")
            setze(zapfTemp=zt, zapfMenge=zm)
            st.caption(f"max. {fmt(mx, 1)} l/min bei {stn['stages'][ws]['kw']} kW und {fmt(zt)} °C")
        if stn["zuheizerFaehig"] and ss.inp.system == "2":
            zh = st.selectbox("Elektrischer Zuheizer (DLE)", ["off", "on"], ["off", "on"].index(ss.inp.zuheizer),
                              key=k("zuheizer"),
                              format_func=lambda x: "mit elektrischem Zuheizer" if x == "on" else "ohne Zuheizer",
                              help="Nachgeschalteter Durchlauferhitzer (Flow 7000 HPS). Mischt einen elektrisch erhitzten "
                                   "Teilstrom bei, wenn die Netztemperatur nicht reicht. Feste Stufen 48/53/60 °C.")
            setze(zuheizer=zh)
            if zh == "on":
                a, b = st.columns(2)
                kw = a.selectbox("Zuheizer-Leistung", [11.0, 13.0], [11.0, 13.0].index(float(ss.inp.zuheizerKW))
                                 if float(ss.inp.zuheizerKW) in (11.0, 13.0) else 0, key=k("zuheizerKW"),
                                 format_func=lambda x: f"{x:.0f} kW", help="Verfügbar: 11 kW und 13 kW.")
                ds = b.selectbox("DLE-Stufe", [48.0, 53.0, 60.0], [48.0, 53.0, 60.0].index(float(ss.inp.dleStufe))
                                 if float(ss.inp.dleStufe) in (48.0, 53.0, 60.0) else 1, key=k("dleStufe"),
                                 format_func=lambda x: f"{x:.0f} °C",
                                 help="Mechanischer Wählschalter – nur drei feste Stufen, nicht gradweise regelbar.")
                setze(zuheizerKW=kw, dleStufe=ds)
                st.markdown('<div class="hinweis">↑ Der DLE ist ein Booster in der Wohnung: Reicht die Netztemperatur '
                            '(aus dem zentralen Erzeuger) nicht, mischt der DLE einen auf die gewählte Stufe erhitzten '
                            'Teilstrom bei. Er entlastet die zentrale Auslegung nicht.</div>', unsafe_allow_html=True)
        P0 = build_params(ss.inp)
        zeilen = [("Betriebsart", stn["mode"]),
                  ("WW-Leistung (manuell)", f"{fmt(P0['P_WW_full'], 1)} kW · {fmt(P0['zapfLmin'], 1)} l/min @ "
                   f"{fmt(P0['zapfTemp'])} °C") if wm == "man" else
                  ("WW-Leistung / Zapfmenge", "{kw} kW · {lmin} l/min".format(**stn["stages"][ws]))]
        if P0["zuheizerOn"]:
            zeilen.append(("Elektr. Zuheizer", f"{fmt(P0['zuheizerMaxKW'])} kW-Klasse · Stufe {fmt(P0['dleStufe'])} °C"))
        zeilen += [("Heizleistung max.", f"{stn['maxHeatKW']} kW"), ("System", f"{ss.inp.system}-Leiter")]
        st.markdown("".join(f'<div class="info-zeile"><span>{x}</span><b>{y}</b></div>' for x, y in zeilen),
                    unsafe_allow_html=True)

    # ---------------------------------------------------------------- ③ Auslegung
    with karte("③ Auslegung"):
        lo, hi = tvl_bounds(ss.inp)
        mxq = float(stn["maxHeatKW"] + 3)
        a, b = st.columns(2)
        qhk = a.number_input("Heizlast je Wohnung kW", 0.0, mxq, min(float(ss.inp.qhk), mxq), 0.1, format="%.1f",
                             key=k(f"qhk_{mxq}"), help=f"Wärmebedarf einer Wohnung. Hart begrenzt auf die Geräte-"
                                                      f"Heizleistung + 3 kW Reserve (max. {mxq:g} kW).")
        dthk = b.number_input("Spreizung ΔT K", 1.0, 40.0, float(ss.inp.dthk), 1.0, format="%.0f", key=k("dthk"),
                              help="Vorlauf minus Rücklauf im Heizkreis.")
        tvl = a.number_input("Versorgungs-VL °C", float(lo), float(hi), float(min(max(float(ss.inp.tvl), lo), hi)), 1.0,
                             format="%.0f", key=k(f"tvl_{lo}_{hi}"),
                             help=f"Frei einstellbar {lo}–{hi} °C (ohne HPS 50–70, mit HPS 40–50, manuell 40–70). "
                                  "Kommt 1:1 an der Wohnungsstation an. Unabhängig vom VL Heizkreis.")
        vlhk = b.number_input("VL Heizkreis °C", 30.0, 70.0, float(ss.inp.vlhk), 1.0, format="%.0f", key=k("vlhk"),
                              help="Vorlauf im Wohnungs-Heizkreis (nach Mischer). Kann nicht höher sein als die "
                                   "Netztemperatur an der Station.")
        glz = a.selectbox("Gleichzeitigkeit", ["din", "tud"], ["din", "tud"].index(ss.inp.glz), key=k("glz"),
                          format_func=lambda x: "DIN 4708" if x == "din" else "TU Dresden",
                          help="DIN 4708 (konservativ) oder TU Dresden (aus Messungen, kleinere Rohre).")
        mat = b.selectbox("Rohrmaterial", list(MATNAME), list(MATNAME).index(ss.inp.mat), key=k("mat"),
                          format_func=lambda x: MATNAME[x], help="Dimensionsreihen nach HIU-Datenbasis.")
        vmax = a.number_input("max. Geschwindigkeit m/s", 0.5, 3.0, float(ss.inp.vmax), 0.1, format="%.1f",
                              key=k("vmax"), help="Auslegungsgrenze. Bosch-Standard: 1,0 m/s.")
        tsp = b.number_input("Spitzenzeit min", 5.0, 60.0, max(5.0, float(ss.inp.tsp)), 1.0, format="%.0f", key=k("tsp"),
                             help="Dauer der Spitzenzapfung für die Pufferauslegung. Nicht unter 5 min.")
        tTot = a.number_input("Kesseltotzeit min", 1.0, 10.0, float(ss.inp.tTot), 1.0, format="%.0f", key=k("tTot"),
                              help="Wandgeräte 2–3 min, bodenstehende Kessel 5–7 min. Längere Totzeit wird durch "
                                   "größeres Puffervolumen kompensiert.")
        tWied = b.number_input("Wiederaufheizzeit min", 10.0, 60.0, float(ss.inp.tWied), 1.0, format="%.0f",
                               key=k("tWied"), help="Empfehlung (Bosch): 20–30 min, Wärmepumpen ca. 45 min.")
        setze(qhk=qhk, dthk=dthk, tvl=tvl, vlhk=vlhk, glz=glz, mat=mat, vmax=vmax, tsp=tsp, tTot=tTot, tWied=tWied)
        if ss.inp.system == "4":
            hT = a.number_input("Puffer-Mindestlaufzeit min", 5.0, 30.0, float(ss.inp.heizTueber), 1.0, format="%.0f",
                                key=k("heizTueber"), help="Nur 4-Leiter: Taktschutz nach VDI 4645 (10–20 min).")
            hD = b.number_input("Puffer-Spreizung ΔT K", 3.0, 20.0, float(ss.inp.heizDt), 1.0, format="%.0f",
                                key=k("heizDt"), help="Nur 4-Leiter: Herstellerpraxis (VDI 4645) 10 K.")
            setze(heizTueber=hT, heizDt=hD)

# ====================================================================== Rechnung
inp, straenge, meta = ss.inp, ss.straenge, ss.meta
results = compute_all(inp, straenge)
R = results[meta["activeStrang"]]
P, A = R["P"], R["anlage"]
HL = project_headline(R, inp)
n = len(results)
name = (meta["projName"] or "bosch-flow-projekt").strip().replace(" ", "_")

# ---------------------------------------------------------------------- Projekt-Knöpfe (Stand nach allen Eingaben)
with projekt_knoepfe:
    _inp, _str, _meta = inp, [Strang(s.floors, s.split, [dict(c) for c in s.cfg]) for s in straenge], dict(meta)

    def _pdf() -> bytes:
        schluessel = stand(_inp, _str, _meta)
        cache = ss.setdefault("pdf_cache", {})
        if schluessel not in cache:
            cache.clear()
            cache[schluessel] = pdf_bericht(_inp, _str, _meta, compute_all(_inp, _str))
        return cache[schluessel]

    st.download_button("Planung als PDF exportieren", _pdf, file_name=f"Bosch_Flow_{name}.pdf", mime="application/pdf",
                       type="primary", width="stretch", icon=":material/picture_as_pdf:")
    a, b = st.columns(2)
    a.download_button("Speichern", dumps(inp, straenge, meta), file_name=f"{name}.json",
                      mime="application/json", width="stretch", icon=":material/save:",
                      help="Projektdatei (.json) auf den Rechner – gleiches Format wie die HTML-Version.")
    with b.popover("Laden", icon=":material/folder_open:", width="stretch"):
        datei = st.file_uploader("Projektdatei (.json)", type=["json"], key="upload")
        st.caption("Dateien dieser App und der HTML-Version (V52–V54). Das aktuelle Projekt wird ersetzt.")
        if datei is not None and ss.get("geladen_id") != datei.file_id:
            ss.geladen_id = datei.file_id
            if laden(datei.getvalue(), f"Projekt „{datei.name}“ geladen."):
                st.rerun()
    if st.button("Zwischenspeichern", icon=":material/backup:", width="stretch",
                help="Sichert den aktuellen Stand sofort im Browser. Gesichert wird außerdem automatisch bei jeder "
                     "Eingabe. Für eine Datei auf dem Rechner „Projekt speichern“ nutzen."):
        ss.zwischen = datetime.now().strftime("%H:%M:%S")
        st.toast(f"Zwischenstand im Browser gesichert ({ss.zwischen}).", icon="💾")
    st.markdown(f'<div class="autosave" title="Eingaben werden automatisch im Browser gesichert und beim erneuten '
                f'Öffnen wiederhergestellt.">↻ Automatisch im Browser gesichert · '
                f'{ss.get("zwischen") or datetime.now().strftime("%H:%M")}</div>', unsafe_allow_html=True)
    a, b = st.columns(2)
    a.download_button("Excel", RP.excel_bytes(inp, meta, results, straenge), file_name=f"Bosch_Flow_{name}.xlsx",
                      width="stretch", icon=":material/table_view:",
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with b.popover("Zurücksetzen", icon=":material/restart_alt:", width="stretch"):
        st.markdown("**Alle Eingaben zurücksetzen?**")
        st.caption("Projektangaben, Gebäude und alle Stränge werden auf die Ausgangswerte gestellt. Vorher ggf. "
                   "„Projekt speichern“.")
        if st.button("Ja, zurücksetzen", type="primary", width="stretch"):
            neues_projekt()
            ss.meldung = ("success", "Alle Eingaben zurückgesetzt.")
            st.rerun()


# ====================================================================== Bausteine Ergebnisse
def schema(szene, key: str, max_hoehe: int | None = None, breite_px: int = 1000, leiste: bool = False) -> None:
    cfg = {"responsive": True, "displaylogo": False, "displayModeBar": "hover" if leiste else False,
           "modeBarButtonsToRemove": ["zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d",
                                      "autoScale2d", "resetScale2d"],
           "toImageButtonOptions": {"format": "png", "scale": 2, "filename": key}}
    st.plotly_chart(als_plotly(szene, max_hoehe=max_hoehe, breite_px=breite_px), width="stretch", config=cfg,
                    key=key, theme=None)


def status_style(df: pd.DataFrame):
    farben = {"OK": "color:#2e7d32;font-weight:700", "grenzwertig": "color:#b26a00;font-weight:700",
              "zu schnell": "color:#c0161d;font-weight:700"}
    return df.style.map(lambda v: farben.get(v, ""), subset=["Status"])


NUMFMT = {"GZ": st.column_config.NumberColumn(format="%.1f"),
          "V̇ ges. [m³/h]": st.column_config.NumberColumn(format="%.2f"),
          "v [m/s]": st.column_config.NumberColumn(format="%.2f"),
          "Δp [Pa/m]": st.column_config.NumberColumn(format="%.0f")}


def abschnitt_karten(T: dict) -> None:
    html = "".join(
        f'<div class="abschnitt{" krit" if a["kritisch"] else ""}"><div><span class="num">{a["strang"]}</span>'
        f'<b>Abschnitt {a["strang"]}</b></div><div style="font-size:13px"><b>{a["load"]} WE</b> · {fmt(a["V"], 2)} m³/h'
        f'</div><div style="font-size:13px;color:{AKZENT};font-weight:700">{a["dn"]} · {fmt(a["v"], 2)} m/s</div>'
        + ('<div style="margin-top:4px;font-size:10.5px;font-weight:700;color:#b26a00">◆ maßgeblich (höchste '
           'Geschwindigkeit)</div>' if a["kritisch"] else "") + "</div>" for a in T["abschnitte"])
    st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 12px">{html}</div>',
                unsafe_allow_html=True)


def hauptstrang_tabelle(T: dict) -> None:
    hs = pd.DataFrame([{"Abschnitt": f"Abschnitt {a['strang']}", "kum. WE": a["load"], "Strang": f"Strang {a['strang']}",
                        "Leitung": "Hauptstrang", "Nennweite": a["dn"], "V̇": f"{fmt(a['V'], 2)} m³/h",
                        "v": f"{fmt(a['v'], 2)} m/s" + ("  ◆ maßgeblich" if a["kritisch"] else "")}
                       for a in T["abschnitte"]])
    st.dataframe(hs.style.apply(lambda r: ["color:#b26a00;font-weight:700" if "◆" in r["v"] else ""] * len(r), axis=1),
                 hide_index=True, width="stretch")


@st.dialog("Netztopologie – Vollbild", width="large")
def topologie_vollbild() -> None:
    pos = st.slider("Position Wärmezentrale", 0, 100, int(ss.meta["topoPos"]), 1, key=f"topo_fs_{ss.rev}",
                    help="0 = links, 50 = mittig, 100 = rechts")
    ss.meta["topoPos"] = float(pos)
    st.markdown(f"**{topo_label(pos)}**")
    res = compute_all(ss.inp, ss.straenge)
    schema(schemata.topologie_szene(res, pos, True, DUNKEL), "topo_voll", breite_px=1150, leiste=True)
    T = topologie(res, pos)
    abschnitt_karten(T)
    hauptstrang_tabelle(T)
    if st.button("Schließen", type="primary", icon=":material/close_fullscreen:"):
        st.rerun()


def modell_3d(res: list, key: str, hoehe: int) -> None:
    farbe = "dn" if ss.get("m3d_farbe") == "Nennweite" else "v"
    nur = ss.meta["activeStrang"] if ss.get("m3d_umfang") == "Aktueller Strang" and len(res) > 1 else None
    fig = modell(res, ss.meta["topoPos"], farbe, DUNKEL, nur, hoehe)
    st.plotly_chart(fig, width="stretch", key=key, theme=None,
                    config={"displaylogo": False, "responsive": True,
                            "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "Bosch_Flow_3D"}})


@st.dialog("3D-Gebäudemodell – Vollbild", width="large")
def modell_vollbild() -> None:
    modell_3d(compute_all(ss.inp, ss.straenge), "m3d_voll", 760)
    if st.button("Schließen", type="primary", icon=":material/close_fullscreen:"):
        st.rerun()


def variante_uebernehmen(aenderung: dict, titel: str) -> None:
    ss.va_vorher = (ss.inp, titel)
    ss.inp = VA.anwenden(ss.inp, aenderung)
    ss.rev += 1
    ss.meldung = ("success", f"Variante übernommen: {titel}")


def varianten_karte() -> None:
    V = VA.vergleich(ss.inp, ss.straenge, ss.meta["topoPos"])
    basis, zeilen, best = V["basis"], V["zeilen"], V["empfehlung"]
    bv = best["variante"]
    if bv.gruppe == "Planung" and basis["ueber"]:
        st.warning(f"{basis['ueber']} Abschnitt(e) über v_max – keine der geprüften Auslegungsvarianten behebt das. "
                   "Rohrmaterial, Strangaufteilung oder v_max prüfen.", icon=":material/warning:")
    elif bv.gruppe == "Planung":
        st.markdown('<div class="empf ok"><b>✓ Die aktuelle Planung ist unter den geprüften Varianten die beste.</b>'
                    '<br>Keine Auslegungsvariante ist ohne Geschwindigkeits-Überschreitung günstiger.</div>',
                    unsafe_allow_html=True)
    else:
        punkte = "".join(f"<li>{x}</li>" for x in VA.begruendung(best, basis))
        st.markdown(f'<div class="empf"><span class="empf-tag">Empfehlung</span><b>{bv.titel}</b> '
                    f'<small>({bv.gruppe})</small> · Bewertung {fmt(best["wert"] * 100)} % der aktuellen Planung'
                    f'<ul>{punkte}</ul>{f"<small>{bv.hinweis}</small>" if bv.hinweis else ""}</div>',
                    unsafe_allow_html=True)
        st.button(f"Empfehlung übernehmen: {bv.titel}", type="primary", icon=":material/check:", key="va_best",
                  on_click=variante_uebernehmen, args=(bv.aenderung, bv.titel))

    # Balken: Bewertung je Variante (100 % = aktuelle Planung)
    import plotly.graph_objects as go
    farbe = []
    for z in zeilen:
        v = z["variante"]
        farbe.append("#e63946" if z["k"]["zuSchnell"] else "#f4a261" if z["k"]["ueber"] else
                     ("#4fa3e0" if DUNKEL else "#005691") if v.gruppe == "Planung" else
                     "#2b9348" if z is best else "#80b918" if v.empfehlbar and z["wert"] < 1 else
                     "#9aa5b1" if not v.empfehlbar else "#c4ccd4")
    namen = [f"{z['variante'].titel}{'' if z['variante'].empfehlbar else ' ⓘ'}" for z in zeilen]
    werte = [z["wert"] * 100 for z in zeilen]
    fig = go.Figure(go.Bar(x=werte, y=namen, orientation="h", marker=dict(color=farbe),
                           text=[f"{fmt(w)} %" for w in werte], textposition="outside", cliponaxis=False,
                           hovertext=[f"<b>{z['variante'].titel}</b> · {z['variante'].gruppe}<br>"
                                      + ("<br>".join(VA.begruendung(z, basis)) or "keine Änderung")
                                      + (f"<br><i>{z['variante'].hinweis}</i>" if z["variante"].hinweis else "")
                                      for z in zeilen], hoverinfo="text"))
    fig.add_vline(x=100, line=dict(color="#8a949e", dash="dot", width=1))
    ink = "#e6edf3" if DUNKEL else "#12181f"
    fig.update_layout(height=60 + 30 * len(zeilen), margin=dict(l=10, r=40, t=10, b=30), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color=ink, size=12), showlegend=False, separators=",.",
                      bargap=0.35)
    fig.update_xaxes(title="Bewertung in % der aktuellen Planung (kleiner = besser)", gridcolor="rgba(128,128,128,.2)",
                     range=[0, max(werte) * 1.15])
    fig.update_yaxes(autorange="reversed", automargin=True)
    st.plotly_chart(fig, width="stretch", key="va_chart", theme=None, config={"displayModeBar": False})

    df = pd.DataFrame([{
        "Variante": z["variante"].titel + ("" if z["variante"].empfehlbar else " ⓘ"),
        "Anschluss": z["k"]["anschluss"], "V̇ [m³/h]": z["k"]["V"],
        "Δ Rohrnetz": (z["k"]["dnSumme"] / basis["dnSumme"] - 1) * 100,
        "max. v/v_max": z["k"]["auslastung"] * 100, "> v_max": z["k"]["ueber"],
        "Erzeuger [kW]": z["k"]["kessel"], "Puffer": z["k"]["pufferText"],
        "Bewertung [%]": z["wert"] * 100} for z in zeilen])
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "V̇ [m³/h]": st.column_config.NumberColumn(format="%.2f"),
        "Δ Rohrnetz": st.column_config.NumberColumn(format="%+.0f %%", help="Summe der Nennweiten aller Abschnitte "
                                                    "gegenüber der aktuellen Planung"),
        "max. v/v_max": st.column_config.ProgressColumn(format="%.0f %%", min_value=0, max_value=120),
        "Erzeuger [kW]": st.column_config.NumberColumn(format="%.0f"),
        "Puffer": st.column_config.TextColumn(width="medium"),
        "Bewertung [%]": st.column_config.NumberColumn(format="%.0f %%")})
    a, b = st.columns([3, 1.3], vertical_alignment="bottom")
    andere = [z["variante"] for z in zeilen if z["variante"].gruppe != "Planung"]
    wahl = a.selectbox("Variante übernehmen", range(len(andere)), format_func=lambda i: andere[i].titel,
                       key=f"va_wahl_{ss.rev}")
    b.button("Übernehmen", key="va_ueb", width="stretch", icon=":material/swap_horiz:",
             on_click=variante_uebernehmen, args=(andere[wahl].aenderung, andere[wahl].titel))
    if vorher := ss.get("va_vorher"):
        if st.button(f"Rückgängig: {vorher[1]}", key="va_undo", icon=":material/undo:"):
            ss.inp = vorher[0]
            ss.rev += 1
            del ss.va_vorher
            st.rerun()
    st.caption("Bewertung: 50 % Rohrnetz (Summe der Nennweiten aller Abschnitte), 25 % Erzeugerleistung, 25 % "
               "Puffervolumen; Abschnitte über v_max werden bestraft. Preise, Energieeffizienz und Montage fließen "
               "nicht ein. ⓘ = wird gezeigt, aber nicht automatisch empfohlen (Rechenverfahren, Leitersystem, höherer "
               "Vorlauf). „Übernehmen“ ändert die Eingaben links und lässt sich rückgängig machen.")


# ====================================================================== Ergebnisse (rechts)
with rechts:
    k1, k2, k3, k4 = st.columns(4)
    scope = " (Projekt)" if HL["projektweit"] else ""
    pp = puffer_produkt(A["pufferVol"])
    k1.metric("Spitzen-Volumenstrom" + scope, f"{fmt(HL['Vtot'], 2)} m³/h")
    k2.metric("Strangfuß" + (" gesamt" if HL["projektweit"] else " unten"), HL["dim"])
    k3.metric("Kessel-/FW-Leistung", f"{fmt(A['kesselQ'])} kW")
    k4.metric("Pufferspeicher", pp["text"], help=f"berechnet {fmt(A['pufferVol'])} l → Auswahl" if pp["liter"] else None)

    if P["heatOver"]:
        st.warning(f"⚠ Heizlast {fmt(P['qhk'], 1)} kW liegt über der Nenn-Heizleistung der {R['st']['name']} "
                   f"({R['st']['maxHeatKW']} kW) – im Reservebereich (bis max. {R['st']['maxHeatKW'] + 3} kW). Höher ist "
                   "nicht möglich; für mehr Heizlast ein größeres Gerät wählen.")
    if P["vlhkZuHoch"]:
        st.error(f"⚠ Der Heizkreis-Vorlauf ({fmt(P['vlhk'])} °C) liegt über der Netztemperatur an der Station "
                 f"({fmt(P['netzTemp'])} °C). Das ist ohne eigenen Booster für die Heizung technisch nicht möglich – "
                 f"max. {P['vlhkMax']} °C.")
    if P["zapfGekappt"]:
        st.warning(f"Zapfmenge auf {fmt(P['zapfLmin'], 1)} l/min gedeckelt (Leistungsanschlag der kW-Klasse).")

    # ---------------------------------------------------------------- Netzschema
    angeheftet = ss.get("angeheftet", False)
    with st.container(border=True, key="schemakarte-an" if angeheftet else "schemakarte"):
        a, b, c, d = st.columns([1.5, 2.5, 1.3, 2.3], vertical_alignment="center")
        a.markdown('<div class="karte-titel" style="margin:0">Netzschema</div>', unsafe_allow_html=True)
        if n > 1:
            w = b.segmented_control("Strang (Schema)", [f"S{i + 1}" for i in range(n)],
                                    default=f"S{meta['activeStrang'] + 1}", label_visibility="collapsed",
                                    key=f"strang_schema_{ss.rev}_{meta['activeStrang']}_{n}")
            if w and int(w[1:]) - 1 != meta["activeStrang"]:
                meta["activeStrang"] = int(w[1:]) - 1
                st.rerun()
        an = c.toggle("📌 Anheften", angeheftet, key="anheften", help="Vorschau beim Scrollen anheften")
        if an != angeheftet:
            ss.angeheftet = an
            st.rerun()
        ansicht = "Aktueller Strang"
        if n > 1:
            ansicht = d.segmented_control("Ansicht", ["Aktueller Strang", "Alle Stränge"], default="Aktueller Strang",
                                          key="ansicht", label_visibility="collapsed") or "Aktueller Strang"
        if ansicht == "Aktueller Strang":
            schema(schemata.netzschema(R, DUNKEL), "schema", max_hoehe=1200)
            st.info(RP.schema_note(R, n), icon=":material/info:")
            st.caption("Tipp: Mit der Maus über Stationen und Nennweiten-Marken fahren – zeigt WE, Gleichzeitigkeit, "
                       "Volumenstrom, Rohr, Geschwindigkeit und Druckverlust. Farbe der Nennweite: grün = OK, "
                       "orange = grenzwertig, rot = zu schnell.")
        else:
            G = gesamt_anlage(inp, results)
            for i, r in enumerate(results):
                with st.container(border=True):
                    st.markdown(
                        f'<div class="strangkopf">Strang {i + 1} <span class="badge2">{r["totalWE"]} Wohnungen</span>'
                        f'<span class="badge2">{r["floors"]} Etagen</span><span class="badge2">'
                        f'{"beidseitig" if r["split"] == "both" else "einseitig"}</span><span class="badge2">Strangfuß '
                        f'{r["vRows"][0]["dim"]} · {fmt(r["vRows"][0]["Vtot"], 2)} m³/h</span></div>',
                        unsafe_allow_html=True)
                    schema(schemata.netzschema(r, DUNKEL), f"schema_all_{i}", max_hoehe=900)
                    st.markdown(f"**Auslegung Steigstrang – Strang {i + 1}**")
                    st.dataframe(status_style(RP.strang_table(r, "V")), hide_index=True, width="stretch",
                                 column_config=NUMFMT)
            # Gesamtübersicht mit Netztopologie
            with st.container(border=True):
                st.markdown(f"#### Gesamtübersicht – alle {n} Stränge")
                st.caption("Netztopologie: Wärmezentrale (Keller) → Steigrohr → horizontaler Hauptstrang → vertikale "
                           "Stränge mit Wohnungsstationen")
                if G["getrennt"]:
                    st.warning("**Hinweis – getrennte Ausführung:** Es gibt **keinen gemeinsamen Hauptstrang**. Jeder "
                               "Strang hat eine **eigene Wärmezentrale** (siehe Einzelschemata oben). Die folgende "
                               "Topologie mit gemeinsamer Leitung dient nur der Übersicht – für die getrennte Ausführung "
                               "gelten die Einzelwerte je Strang.")
                a, b, c = st.columns([3, 1.2, 1], vertical_alignment="bottom")
                pos = a.slider("Position Wärmezentrale", 0, 100, int(meta["topoPos"]), 1, key=f"topo_{ss.rev}",
                               help="0 = links, 50 = mittig, 100 = rechts. Wird mit dem Projekt gespeichert.")
                meta["topoPos"] = float(pos)
                b.markdown(f"**{topo_label(pos)}**")
                if c.button("⤢ Vollbild", width="stretch"):
                    topologie_vollbild()
                T = topologie(results, pos)
                schema(schemata.topologie_szene(results, pos, False, DUNKEL), "topo", leiste=True)
                abschnitt_karten(T)
                zeilen = [{"Strang": f"Strang {i + 1}", "Wohnungen": r["totalWE"], "Etagen": str(r["floors"]),
                           "Aufteilung": "beidseitig" if r["split"] == "both" else "einseitig",
                           "Strangfuß": r["vRows"][0]["dim"], "V̇ Strangfuß": f"{fmt(r['vRows'][0]['Vtot'], 2)} m³/h",
                           "v": f"{fmt(r['vRows'][0]['v'], 2)} m/s"} for i, r in enumerate(results)]
                zeilen.append({"Strang": "Summe", "Wohnungen": G["we"], "Etagen": "–",
                               "Aufteilung": "getrennte Anlagen" if G["getrennt"] else "alle Stränge",
                               "Strangfuß": "–" if G["getrennt"] else T["gesamt"]["dim"],
                               "V̇ Strangfuß": "–" if G["getrennt"] else f"{fmt(T['gesamt']['Vtot'], 2)} m³/h",
                               "v": "–" if G["getrennt"] else f"{fmt(T['gesamt']['v'], 2)} m/s"})
                st.dataframe(pd.DataFrame(zeilen).style.apply(
                    lambda r: ["font-weight:700" if r["Strang"] == "Summe" else ""] * len(r), axis=1),
                    hide_index=True, width="stretch")
                st.markdown('<div class="karte-titel">Hauptstrang – Nennweite je Abschnitt <small>folgt der Position '
                            'der Wärmezentrale</small></div>', unsafe_allow_html=True)
                hauptstrang_tabelle(T)
                st.info(RP.hauptstrang_erklaerung(results, T), icon=":material/school:")
                c = st.columns(3)
                c[0].metric("Wohnungen gesamt", G["we"])
                c[1].metric(f"Kessel-/FW-Leistung {'(Σ getrennte Anlagen)' if G['getrennt'] else '(gesamt)'}",
                            f"{fmt(G['kesselQ'])} kW")
                c[2].metric(f"Pufferspeicher {'(Σ getrennte Anlagen)' if G['getrennt'] else '(gesamt)'}",
                            f"{fmt(G['pufferVol'])} l")
                st.caption(RP.gesamt_note(G, n))
            with st.container(border=True):
                st.markdown("#### Diagramme – Volumenstrom & Gleichzeitigkeit")
                st.caption(f"Referenz-Verlauf über alle {G['we']} Wohnungen (bei gemeinsamer Zentrale). In getrennter "
                           "Ausführung gilt je Strang der eigene Verlauf." if G["getrennt"] else
                           f"Bezogen auf die Gesamtanlage ({G['we']} Wohnungen) – kumuliert über alle Stränge")
                ctx = {"P": results[0]["P"], "totalWE": G["we"]}
                a, b = st.columns(2)
                a.plotly_chart(plots.chart_volumenstrom(ctx), width="stretch", key="chart_all_v")
                b.plotly_chart(plots.chart_gleichzeitigkeit(ctx), width="stretch", key="chart_all_g")

    # ---------------------------------------------------------------- 3D-Gebäudemodell
    with karte("3D-Gebäudemodell", "Drehen: ziehen · Zoom: Mausrad · Werte: Maus über ein Rohr"):
        a, b, c = st.columns([2, 2, 1], vertical_alignment="center")
        a.segmented_control("Färbung", ["Geschwindigkeit", "Nennweite"], default="Geschwindigkeit", key="m3d_farbe",
                            label_visibility="collapsed")
        if n > 1:
            b.segmented_control("Umfang", ["Ganzes Projekt", "Aktueller Strang"], default="Ganzes Projekt",
                                key="m3d_umfang", label_visibility="collapsed")
        if c.button("⤢ Vollbild", key="m3d_vb", width="stretch"):
            modell_vollbild()
        modell_3d(results, "m3d", 560)
        st.caption("Schematisches Raummodell: Keller mit Hauptstrang und Wärmezentrale (Position wie in der "
                   "Netztopologie), je Strang das Steigrohr und je Etage die Leitungen zu den Stationen. Rohrdicke = "
                   "Nennweite, Farbe = Ausnutzung der zulässigen Geschwindigkeit bzw. Nennweite. Legende anklicken "
                   "blendet einzelne Stufen ein/aus.")

    # ---------------------------------------------------------------- Variantenvergleich
    with karte("Variantenvergleich", "dieselbe Planung mit anderen Eingaben – automatisch bewertet"):
        varianten_karte()

    # ---------------------------------------------------------------- Anlagenschema
    with karte("Anlagenschema (Heizzentrale)", "Erzeuger · Puffer · Netzpumpe · Station"):
        schema(schemata.anlagenschema(R, HL, DUNKEL), "anlage")

    # ---------------------------------------------------------------- Auslegungs-Tabelle
    with karte("Auslegungs-Tabelle", f"Strang {meta['activeStrang'] + 1} von {n}" if n > 1 else ""):
        mo = st.segmented_control("Tabelle", ["Etagenstrang", "Steigstrang"], default="Etagenstrang", key="tab",
                                  label_visibility="collapsed") or "Etagenstrang"
        m = "H" if mo == "Etagenstrang" else "V"
        st.dataframe(status_style(RP.strang_table(R, m)), hide_index=True, width="stretch", column_config=NUMFMT)
        st.caption(f"Maßgeblicher (längster) Etagenstrang: von der äußersten Station (1 WE, kleinste Dimension) bis zum "
                   f"Steigstrang ({R['govN']} WE). WW-Volumenstrom je Station gedeckelt auf 1,3 m³/h." if m == "H" else
                   f"Steigstrang kumuliert alle Etagen. Ganz unten trägt er alle {R['totalWE']} Wohnungen – maßgeblich "
                   "für die zentrale Pumpe.")

    # ---------------------------------------------------------------- Diagramm
    with karte("Diagramm"):
        mo = st.segmented_control("Diagramm", ["Volumenstrom", "Gleichzeitigkeit"], default="Volumenstrom",
                                  key="chart", label_visibility="collapsed") or "Volumenstrom"
        if mo == "Volumenstrom":
            st.plotly_chart(plots.chart_volumenstrom(R), width="stretch", key="chart_v")
            st.caption("Volumenstrom über kumulierte Wohnungszahl. WW-Anteil je Station auf 1,3 m³/h gedeckelt – "
                       "dadurch realistische, nicht überzogene Dimensionen.")
        else:
            st.plotly_chart(plots.chart_gleichzeitigkeit(R), width="stretch", key="chart_g")
            st.caption("TU Dresden (ROUND(WE^-0,57·WE)) liegt bei vielen Wohnungen unter DIN 4708.")

    # ---------------------------------------------------------------- Wärmezentrale
    with karte("Wärmezentrale – Kessel & Pufferspeicher", "HIU-Rechenlogik"):
        st.dataframe(pd.DataFrame(RP.anlage_rows(A), columns=["Größe", "Wert", "Einheit", "Herleitung"]).style.apply(
            lambda r: [f"font-weight:700;color:{BLAU}" if r["Größe"].startswith("→") else ""] * len(r), axis=1),
            hide_index=True, width="stretch",
            column_config={"Größe": st.column_config.TextColumn(width="medium"),
                           "Wert": st.column_config.TextColumn(width="small"),
                           "Einheit": st.column_config.TextColumn(width="small"),
                           "Herleitung": st.column_config.TextColumn(width="large")})
        st.caption(RP.anlage_note(A))

    # ---------------------------------------------------------------- DLE-Auslegungshilfe
    if A["zuheizerOn"]:
        with karte("DLE-Auslegungshilfe"):
            tbl = dle_table(A)
            bg = {"none": "background:rgba(128,128,128,.08);color:#8a94a0",
                  "ok": "background:rgba(46,125,50,.14);color:#1f7d24;font-weight:700",
                  "over": "background:rgba(192,22,29,.12);color:#c0161d;font-weight:700"}
            df = pd.DataFrame([{"Netztemp. an Station": f"{r['netzTemp']} °C" + (" ◄ aktuell" if r["aktuell"] else ""),
                                **{f"Stufe {x} °C": RP.dle_cell_text(r["cells"][x]) for x in (48, 53, 60)}} for r in tbl])
            zust = [[r["cells"][x]["state"] for x in (48, 53, 60)] for r in tbl]
            akt = [r["aktuell"] for r in tbl]
            stufe = int(A["dleStufe"])

            def faerben(col):
                if col.name == "Netztemp. an Station":
                    return ["font-weight:700" if akt[i] else "" for i in range(len(col))]
                j = list(df.columns).index(col.name) - 1
                return [bg[zust[i][j]] + (";outline:2px solid #007BC0" if akt[i] and (48, 53, 60)[j] == stufe else "")
                        for i in range(len(col))]
            st.dataframe(df.style.apply(faerben), hide_index=True, width="stretch")
            state, text = RP.dle_fazit(A)
            {"none": st.info, "ok": st.success, "over": st.error}[state](text)
            st.caption(f"Die Tabelle zeigt die nötige DLE-Leistung, um {fmt(A['zapfLmin'])} l/min von der jeweiligen "
                       f"Netztemperatur auf {fmt(A['zapfTemp'])} °C zu mischen. Grün = passt in die "
                       f"{fmt(A['zuheizerMaxKW'])}-kW-Klasse, rot = über der Klasse, grau = DLE nicht nötig. Der Rahmen "
                       "markiert die aktuelle Kombination. Referenz für energieeffiziente Betriebsweisen mit abgesenkter "
                       "Netztemperatur.")
            st.warning(RP.DLE_ELEKTRO)
            d = din18015(A["weForZentrale"])
            st.markdown("##### Stromseitige Gleichzeitigkeit · DIN 18015-1 (Anhang A)")
            st.caption(RP.DIN18015_TEXT)
            st.plotly_chart(plots.chart_din18015(d["nWE"]), width="stretch", key="chart_din")
            bezug = ("Wohneinheiten dieses Strangs (getrennte Zentrale)" if A["zentralMode"] == "getrennt" else
                     "Wohneinheiten aller Stränge (gemeinsame Zentrale)" if A["nStraenge"] > 1 else
                     "Wohneinheiten am Netzanschluss")
            a, b = st.columns(2)
            a.metric(f"MIT elektr. WW (maßgeblich) · {d['nWE']} {bezug}", f"≈ {fmt(d['mit'])} kW",
                     help="Richtwert Leistung am Netzanschluss" + (" – Kurve ab 30 WE im Plateau" if d["nWE"] >= 30 else ""))
            b.metric("OHNE elektr. WW (Referenz)", f"≈ {fmt(d['ohne'])} kW")
            st.caption(RP.PMAX_HINWEIS)

st.markdown('<div class="fuss">Rechenkern nach Bosch-HIU-Methodik (Gleichzeitigkeit DIN 4708 / TU Dresden, '
            'Knotenpunkt-Formel, Darcy-Weisbach, turbulent).<br>Werkzeug zur Vorplanung – ersetzt keine verbindliche '
            'Rohrnetzberechnung. Prüfung obliegt Planer, Installateur oder Bauherr.<br>Entwickelt von Daniel Sommer · '
            'HC/SDE3-PSD</div>', unsafe_allow_html=True)

# ====================================================================== Auto-Sicherung + Hell/Dunkel (Browser)
jetzt = stand(ss.inp, ss.straenge, ss.meta)
with kopfschalter:
    gespeichert = browser(dumps(ss.inp, ss.straenge, ss.meta) if ss.get("sicherung_gelesen") else None, DUNKEL)
if gespeichert is not None and not ss.get("sicherung_gelesen"):
    ss.sicherung_gelesen = True
    if gespeichert and not ss.get("veraendert"):
        try:
            if stand(*from_html_state(json.loads(gespeichert))) != jetzt:
                laden(gespeichert, "Letzte Sitzung wiederhergestellt (automatische Sicherung im Browser).")
        except (ValueError, KeyError, TypeError):
            pass
    st.rerun()
if ss.get("letzter_stand") not in (None, jetzt):
    ss.veraendert = True          # ab der ersten Änderung nicht mehr aus der Sicherung überschreiben
ss.letzter_stand = jetzt
