"""Bosch Flow – Netz- & Anlagenrechner (Streamlit-Version).

Start:  streamlit run app.py
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import date

import pandas as pd
import streamlit as st

from bosch_flow import plots
from bosch_flow.calc import (Inputs, Strang, compute, compute_all, din18015, dle_table, etage_label,
                             gesamt_anlage, project_headline, puffer_produkt, tvl_bounds, zapf_max_lmin)
from bosch_flow.data import MATNAME, STATIONS, WAERMEQUELLEN
from bosch_flow.project import META_KEYS, dumps, from_html_state
from bosch_flow.report import (anlage_note, anlage_rows, dle_cell_text, dle_fazit, excel_bytes, fmt,
                               strang_table)

st.set_page_config(page_title="Bosch Flow", page_icon="🔥", layout="wide")
ss = st.session_state
DEFAULTS = Inputs()
FLOAT_FIELDS = [f.name for f in fields(Inputs) if isinstance(getattr(DEFAULTS, f.name), (int, float))
                and f.name != "wwstage"]


# ------------------------------------------------------------------ Zustand
def init_state(force: bool = False):
    if force or "straenge" not in ss:
        for k in list(ss.keys()):
            del ss[k]
        ss.straenge = [Strang.new()]
        ss.active = 0
        ss.edver = 0
        for f in fields(Inputs):
            v = getattr(DEFAULTS, f.name)
            ss[f"i_{f.name}"] = float(v) if f.name in FLOAT_FIELDS else v
        for k in META_KEYS:
            ss[f"m_{k}"] = ""
        ss.m_projDate = date.today()


def current_inputs() -> Inputs:
    return Inputs(**{f.name: ss[f"i_{f.name}"] for f in fields(Inputs)})


def current_meta() -> dict:
    m = {k: ss[f"m_{k}"] for k in META_KEYS}
    m["projDate"] = m["projDate"].isoformat() if isinstance(m["projDate"], date) else (m["projDate"] or "")
    m["activeStrang"] = ss.active
    return m


def load_project():
    up = ss.get("upload")
    if up is None:
        return
    try:
        inp, straenge, meta = from_html_state(json.loads(up.getvalue().decode("utf-8")))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
        ss.load_msg = ("error", f"Projekt konnte nicht geladen werden: {e}")
        return
    for f in fields(Inputs):
        v = getattr(inp, f.name)
        ss[f"i_{f.name}"] = float(v) if f.name in FLOAT_FIELDS else v
    for k in META_KEYS:
        ss[f"m_{k}"] = meta.get(k, "")
    try:
        ss.m_projDate = date.fromisoformat(meta.get("projDate") or "")
    except ValueError:
        ss.m_projDate = date.today()
    ss.straenge, ss.active = straenge, meta["activeStrang"]
    ss.edver += 1
    ss.load_msg = ("success", f"Projekt „{up.name}“ geladen.")


def apply_waermequelle():
    q = WAERMEQUELLEN[ss.i_waermequelle]
    ss.i_tTot, ss.i_tWied = float(q["tot"]), float(q["wied"])


def add_strang():
    ss.straenge.append(Strang.new(4, "both", int(ss.get("quickval", 5))))
    ss.active = len(ss.straenge) - 1
    ss.edver += 1


def del_strang():
    if len(ss.straenge) > 1:
        ss.straenge.pop(ss.active)
        ss.active = min(ss.active, len(ss.straenge) - 1)
        ss.edver += 1


def quick_set():
    s = ss.straenge[ss.active]
    v = int(ss.quickval)
    s.cfg = [{"l": v, "r": v if s.split == "both" else 0} for _ in range(s.floors)]
    ss.edver += 1


def set_active():
    ss.active = int(ss.strang_pick.split()[-1]) - 1
    ss.edver += 1


init_state()

# ------------------------------------------------------------------ Seitenleiste: Eingaben
sb = st.sidebar
with sb:
    st.markdown("### Projekt")
    st.text_input("Projektname", key="m_projName", placeholder="z. B. Wohnanlage Musterstraße")
    st.text_input("Standort", key="m_projLoc", placeholder="z. B. Stuttgart")
    c1, c2 = st.columns(2)
    c1.text_input("Planer / Bearbeiter", key="m_projPlanner", placeholder="Name")
    c2.date_input("Datum", key="m_projDate", format="DD.MM.YYYY")
    st.file_uploader("Projekt laden (.json)", type=["json"], key="upload", on_change=load_project,
                     help="Auch Projektdateien aus der HTML-Version können geladen werden.")
    if "load_msg" in ss:
        kind, msg = ss.pop("load_msg")
        getattr(st, kind)(msg)

    # ① Gebäude
    st.markdown("### ① Gebäude")
    st.selectbox("Wärmezentrale", ["gemeinsam", "getrennt"], key="i_zentral",
                 format_func=lambda v: "gemeinsam (eine Zentrale)" if v == "gemeinsam" else "getrennt (je Strang)",
                 help="Gemeinsam = eine Zentrale für alle Stränge (Summe der Wohnungen). "
                      "Getrennt = jeder Strang eigener Kessel/Puffer.")
    n_str = len(ss.straenge)
    labels = [f"Strang {i + 1}" for i in range(n_str)]
    ss.strang_pick = labels[ss.active]
    st.radio("Steigstrang", labels, key="strang_pick", horizontal=True, on_change=set_active)
    b1, b2 = st.columns(2)
    b1.button("+ Strang", on_click=add_strang, width="stretch")
    b2.button("− Strang", on_click=del_strang, disabled=n_str <= 1, width="stretch")

    strang = ss.straenge[ss.active]
    kv = f"{ss.active}_{ss.edver}"
    c1, c2 = st.columns(2)
    floors = int(c1.number_input("Etagen", 1, 20, int(strang.floors), 1, key=f"floors_{kv}",
                                 help="Geschosse, die DIESER Steigstrang versorgt."))
    split = c2.selectbox("Aufteilung", ["both", "one"], index=0 if strang.split == "both" else 1, key=f"split_{kv}",
                         format_func=lambda v: "beidseitig (L + R)" if v == "both" else "einseitig")
    if floors != strang.floors or split != strang.split:
        cfg = [dict(c) for c in strang.cfg[:floors]]
        while len(cfg) < floors:
            cfg.append({"l": 5, "r": 5})
        for c in cfg:
            if split != "both":
                c["r"] = 0
            elif strang.split != "both":
                c["r"] = c["l"]
        strang.floors, strang.split, strang.cfg = floors, split, cfg

    c1, c2 = st.columns([1, 1.4])
    c1.number_input("Schnell setzen", 0, 16, 5, 1, key="quickval", label_visibility="collapsed")
    c2.button("auf alle Etagen", on_click=quick_set, width="stretch")
    df = pd.DataFrame([{"Etage": etage_label(f + 1), "links": c["l"], "rechts": c["r"]}
                       for f, c in enumerate(strang.cfg)][::-1])
    if split != "both":
        df = df.drop(columns="rechts")
    edited = st.data_editor(
        df, key=f"cfg_{kv}_{floors}_{split}", hide_index=True, width="stretch", disabled=["Etage"],
        column_config={c: st.column_config.NumberColumn(c, min_value=0, max_value=16, step=1, required=True)
                       for c in ("links", "rechts")})
    for i, row in enumerate(edited.iloc[::-1].itertuples(index=False)):
        strang.cfg[i] = {"l": int(row.links or 0), "r": int(getattr(row, "rechts", 0) or 0) if split == "both" else 0}

    # ② System & Gerät
    st.markdown("### ② System & Gerät")
    st.selectbox("Leitersystem (projektweit)", ["2", "4"], key="i_system",
                 format_func=lambda v: "2-Leiter (Heizung + Trinkwasser über Station)" if v == "2"
                 else "4-Leiter (Heizung + Trinkwasser getrennt)")
    st.caption("Ein gemeinsames Leitungspaar für Heizung + Trinkwasser. Passt zu Erzeugern mit hoher Vorlauftemperatur "
               "(Kessel, Fernwärme)." if ss.i_system == "2" else
               "Getrennte Leitungspaare für Heizung und Trinkwasser (vier Rohre). Typisch bei Wärmepumpen / Niedertemperatur.")
    st.selectbox("Wärmequelle", list(WAERMEQUELLEN), key="i_waermequelle", on_change=apply_waermequelle,
                 format_func=lambda v: WAERMEQUELLEN[v]["name"])
    q = WAERMEQUELLEN[ss.i_waermequelle]
    st.caption(f"{q['txt']}  \n**Automatisch gesetzt:** Kesseltotzeit **{q['tot']} min** · "
               f"Wiederaufheizzeit **{q['wied']} min** (unten anpassbar).")
    st.selectbox("Wohnungsstation", list(STATIONS), key="i_station", format_func=lambda v: STATIONS[v]["name"],
                 help="Flow 8000: WW-Vorrang (Heizung pausiert beim Zapfen). Flow 7000: WW-Parallelbetrieb.")
    stn = STATIONS[ss.i_station]
    st.selectbox("Warmwasser-Leistungsstufe", [0, 1], key="i_wwstage",
                 format_func=lambda i: "{kw} kW · bis {lmin} l/min".format(**stn["stages"][i]))
    st.selectbox("Warmwasser-Parameter", ["std", "man"], key="i_wwmode",
                 format_func=lambda v: "Standard (aus Leistungsstufe)" if v == "std" else "Manuelle Eingabe")
    if ss.i_wwmode == "man":
        c1, c2 = st.columns(2)
        c1.number_input("Zapfmenge [l/min]", min_value=5.0, step=0.5, format="%.1f", key="i_zapfMenge")
        c2.number_input("Zapftemperatur [°C]", min_value=45.0, max_value=60.0, step=1.0, format="%.0f", key="i_zapfTemp")
        st.caption(f"max. {fmt(zapf_max_lmin(current_inputs()), 1)} l/min bei dieser Leistungsstufe und Zapftemperatur")
    if stn["zuheizerFaehig"] and ss.i_system == "2":
        st.selectbox("Elektrischer Zuheizer (DLE)", ["off", "on"], key="i_zuheizer",
                     format_func=lambda v: "mit elektrischem Zuheizer" if v == "on" else "ohne Zuheizer")
        if ss.i_zuheizer == "on":
            c1, c2 = st.columns(2)
            c1.selectbox("Zuheizer-Leistung", [11.0, 13.0], key="i_zuheizerKW", format_func=lambda v: f"{v:.0f} kW")
            c2.selectbox("DLE-Stufe", [48.0, 53.0, 60.0], key="i_dleStufe", format_func=lambda v: f"{v:.0f} °C")

    # ③ Auslegung
    st.markdown("### ③ Auslegung")
    inp0 = current_inputs()
    lo, hi = tvl_bounds(inp0)
    c1, c2 = st.columns(2)
    c1.number_input("Heizlast je Wohnung [kW]", min_value=0.0, step=0.1, format="%.1f", key="i_qhk",
                    help=f"Hart begrenzt auf Geräte-Heizleistung + 3 kW (max. {stn['maxHeatKW'] + 3} kW).")
    c2.number_input("Spreizung ΔT [K]", min_value=1.0, step=1.0, format="%.0f", key="i_dthk")
    c1.number_input("Versorgungs-VL [°C]", step=1.0, format="%.0f", key="i_tvl", help=f"Frei einstellbar {lo}–{hi} °C.")
    c2.number_input("VL Heizkreis [°C]", min_value=30.0, max_value=70.0, step=1.0, format="%.0f", key="i_vlhk")
    c1.selectbox("Gleichzeitigkeit", ["din", "tud"], key="i_glz",
                 format_func=lambda v: "DIN 4708" if v == "din" else "TU Dresden")
    c2.selectbox("Rohrmaterial", list(MATNAME), key="i_mat", format_func=lambda v: MATNAME[v])
    c1.number_input("max. Geschwindigkeit [m/s]", min_value=0.5, step=0.1, format="%.1f", key="i_vmax")
    c2.number_input("Spitzenzeit [min]", min_value=5.0, step=1.0, format="%.0f", key="i_tsp")
    c1.number_input("Kesseltotzeit [min]", min_value=1.0, max_value=10.0, step=1.0, format="%.0f", key="i_tTot")
    c2.number_input("Wiederaufheizzeit [min]", min_value=10.0, max_value=60.0, step=1.0, format="%.0f", key="i_tWied")
    if ss.i_system == "4":
        c1.number_input("Puffer-Mindestlaufzeit [min]", min_value=5.0, max_value=30.0, step=1.0, format="%.0f",
                        key="i_heizTueber")
        c2.number_input("Puffer-Spreizung ΔT [K]", min_value=3.0, max_value=20.0, step=1.0, format="%.0f",
                        key="i_heizDt")

# ------------------------------------------------------------------ Rechnung
inp, meta, straenge = current_inputs(), current_meta(), ss.straenge
results = compute_all(inp, straenge)
R = results[ss.active]
P, A = R["P"], R["anlage"]
HL = project_headline(R, inp)
foot = R["vRows"][0]

with sb:
    if P["vlKeller"] != inp.tvl:
        st.warning(f"Versorgungs-VL außerhalb {lo}–{hi} °C – gerechnet wird mit {fmt(P['vlKeller'])} °C.")
    if P["qhk"] < inp.qhk:
        st.warning(f"Heizlast auf {fmt(P['qhkMax'], 1)} kW begrenzt (Stationsleistung + 3 kW Reserve).")
    if P["zapfGekappt"]:
        st.warning(f"Zapfmenge auf {fmt(P['zapfLmin'], 1)} l/min gedeckelt (Leistungsanschlag der kW-Klasse).")
    if P["vlhkZuHoch"]:
        st.error(f"Der Heizkreis-Vorlauf ({fmt(P['vlhk'])} °C) liegt über der Netztemperatur an der Station "
                 f"({fmt(P['netzTemp'])} °C) – ohne eigenen Booster nicht möglich, max. {P['vlhkMax']} °C.")
    st.divider()
    stem = (meta["projName"] or "bosch-flow-projekt").strip().replace(" ", "_")
    st.download_button("💾 Projekt speichern (.json)", dumps(inp, straenge, meta), file_name=f"{stem}.json",
                       mime="application/json", width="stretch")
    st.download_button("📊 Auslegung als Excel", excel_bytes(inp, meta, results, straenge), file_name=f"{stem}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")
    st.button("↺ Alles zurücksetzen", on_click=init_state, kwargs={"force": True}, width="stretch")

# ------------------------------------------------------------------ Hauptbereich
st.markdown(
    "<div style='display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;border-bottom:3px solid;"
    "border-image:linear-gradient(90deg,#e20015,#b90276 22%,#50237f 44%,#005691 70%,#008ecf) 1;padding-bottom:8px;"
    "margin-bottom:12px'><span style='font-weight:800;font-size:24px;color:#e20015'>BOSCH "
    "<span style='color:var(--text-color, #141e29)'>Flow</span></span>"
    "<span style='color:#78889a'>Netz- & Anlagenrechner für Wohnungsstationen</span></div>",
    unsafe_allow_html=True)

scope = " (Projekt)" if HL["projektweit"] else ""
pp = puffer_produkt(A["pufferVol"])
k1, k2, k3, k4 = st.columns(4)
k1.metric("Spitzen-Volumenstrom" + scope, f"{fmt(HL['Vtot'], 2)} m³/h")
k2.metric("Strangfuß" + (" gesamt" if HL["projektweit"] else " unten"), HL["dim"])
k3.metric("Kessel-/FW-Leistung", f"{fmt(A['kesselQ'])} kW")
k4.metric("Pufferspeicher", pp["text"])
if pp["liter"]:
    k4.caption(f"berechnet {fmt(A['pufferVol'])} l → Auswahl")

if P["heatOver"]:
    st.warning(f"⚠ Heizlast {fmt(P['qhk'], 1)} kW liegt über der Nenn-Heizleistung der {R['st']['name']} "
               f"({R['st']['maxHeatKW']} kW) – im Reservebereich (bis max. {R['st']['maxHeatKW'] + 3} kW). "
               "Für mehr Heizlast ein größeres Gerät wählen.")

tab_names = ["Netzschema", "Anlagenschema", "Auslegungs-Tabelle", "Diagramm", "Wärmezentrale"]
if A["zuheizerOn"]:
    tab_names.append("DLE-Auslegungshilfe")
if len(straenge) > 1:
    tab_names.append("Alle Stränge")
tabs = dict(zip(tab_names, st.tabs(tab_names)))
strang_hint = f"Strang {ss.active + 1} von {len(straenge)} · " if len(straenge) > 1 else ""
station_name = "Flow 7000 (F7002 HPS)" if P["zuheizerOn"] else R["st"]["name"]

with tabs["Netzschema"]:
    st.plotly_chart(plots.netzschema(R), width="stretch", config={"displayModeBar": False})
    st.info(f"{strang_hint}**{R['floors']}** Etagen · **{R['totalWE']}** Wohnungen "
            f"{'in diesem Strang' if len(straenge) > 1 else 'gesamt'} · {P['system']}-Leiter · {station_name} · "
            f"GLZ nach **{'TU Dresden' if P['glz'] == 'tud' else 'DIN 4708'}**. Maßgeblicher Etagenstrang außen "
            f"**{R['hRows'][0]['dim']}**, Strangfuß **{foot['dim']}** bei **{fmt(foot['Vtot'], 2)} m³/h**, "
            f"v = {fmt(foot['v'], 2)} m/s.")

with tabs["Anlagenschema"]:
    st.plotly_chart(plots.anlagenschema(R, HL), width="stretch", config={"displayModeBar": False})

NUMFMT = {"GZ": st.column_config.NumberColumn(format="%.1f"),
          "V̇ ges. [m³/h]": st.column_config.NumberColumn(format="%.2f"),
          "v [m/s]": st.column_config.NumberColumn(format="%.2f"),
          "Δp [Pa/m]": st.column_config.NumberColumn(format="%.0f")}


def styled(df: pd.DataFrame):
    colors = {"OK": "color:#2e7d32;font-weight:700", "grenzwertig": "color:#b26a00;font-weight:700",
              "zu schnell": "color:#c0161d;font-weight:700"}
    return df.style.map(lambda v: colors.get(v, ""), subset=["Status"])


with tabs["Auslegungs-Tabelle"]:
    mode = st.segmented_control("Ansicht", ["Etagenstrang", "Steigstrang"], default="Etagenstrang",
                                label_visibility="collapsed") or "Etagenstrang"
    m = "H" if mode == "Etagenstrang" else "V"
    st.dataframe(styled(strang_table(R, m)), hide_index=True, width="stretch", column_config=NUMFMT)
    st.caption(f"Maßgeblicher (längster) Etagenstrang: von der äußersten Station (1 WE, kleinste Dimension) bis zum "
               f"Steigstrang ({R['govN']} WE). WW-Volumenstrom je Station gedeckelt auf 1,3 m³/h." if m == "H" else
               f"Steigstrang kumuliert alle Etagen. Ganz unten trägt er alle {R['totalWE']} Wohnungen – maßgeblich "
               "für die zentrale Pumpe.")

with tabs["Diagramm"]:
    mode = st.segmented_control("Diagramm", ["Volumenstrom", "Gleichzeitigkeit"], default="Volumenstrom",
                                label_visibility="collapsed") or "Volumenstrom"
    if mode == "Volumenstrom":
        st.plotly_chart(plots.chart_volumenstrom(R), width="stretch")
        st.caption("Volumenstrom über kumulierte Wohnungszahl. WW-Anteil je Station auf 1,3 m³/h gedeckelt – "
                   "dadurch realistische, nicht überzogene Dimensionen.")
    else:
        st.plotly_chart(plots.chart_gleichzeitigkeit(R), width="stretch")
        st.caption("TU Dresden (ROUND(WE^-0,57·WE)) liegt bei vielen Wohnungen unter DIN 4708.")

with tabs["Wärmezentrale"]:
    rows = anlage_rows(A)
    st.dataframe(pd.DataFrame(rows, columns=["Größe", "Wert", "Einheit", "Herleitung"]).style.apply(
        lambda r: ["font-weight:700;color:#005691" if r["Größe"].startswith("→") else ""] * len(r), axis=1),
        hide_index=True, width="stretch", column_config={"Größe": st.column_config.TextColumn(width="medium"),
                       "Wert": st.column_config.TextColumn(width="small"),
                       "Einheit": st.column_config.TextColumn(width="small"),
                       "Herleitung": st.column_config.TextColumn(width="large")})
    st.caption(anlage_note(A))

if "DLE-Auslegungshilfe" in tabs:
    with tabs["DLE-Auslegungshilfe"]:
        tbl = dle_table(A)
        bg = {"none": "background:#f4f6f8;color:#8a94a0", "ok": "background:#e7f4e8;color:#1f7d24;font-weight:700",
              "over": "background:#fbe7e7;color:#c0161d;font-weight:700"}
        df = pd.DataFrame([{"Netztemp. an Station": f"{r['netzTemp']} °C" + (" ◄ aktuell" if r["aktuell"] else ""),
                            **{f"Stufe {s} °C": dle_cell_text(r["cells"][s]) for s in (48, 53, 60)}} for r in tbl])
        states = [[bg[r["cells"][s]["state"]] for s in (48, 53, 60)] for r in tbl]
        st.dataframe(df.style.apply(lambda col: [""] * len(col) if col.name == "Netztemp. an Station" else
                                    [states[i][list(df.columns).index(col.name) - 1] for i in range(len(col))]),
                     hide_index=True, width="stretch")
        state, text = dle_fazit(A)
        {"none": st.info, "ok": st.success, "over": st.error}[state](text)
        st.caption(f"Die Tabelle zeigt die nötige DLE-Leistung, um {fmt(A['zapfLmin'])} l/min von der jeweiligen "
                   f"Netztemperatur auf {fmt(A['zapfTemp'])} °C zu mischen.")
        st.warning("**⚡ Elektrische Anmeldung & Leitungsbemessung (DLE 11 kW / 13 kW):** Die dezentralen "
                   "Durchlauferhitzer sind elektrische Großgeräte. Die Dimensionierung des Hausanschlusses und der "
                   "Hauptleitungen darf **nicht** durch einfache Addition der Einzelleistungen erfolgen, sondern muss "
                   "durch eine **ELT-Fachkraft** mit dem degressiven Gleichzeitigkeitsfaktor nach **DIN 18015-1 "
                   "(Anhang A)** bemessen werden. Anmeldung bzw. Genehmigung beim örtlichen **Netzbetreiber** gemäß "
                   "regionaler **TAB** bauseits.")
        d = din18015(A["weForZentrale"])
        st.markdown("##### Stromseitige Gleichzeitigkeit · DIN 18015-1 (Anhang A)")
        st.plotly_chart(plots.chart_din18015(d["nWE"]), width="stretch")
        c1, c2 = st.columns(2)
        c1.metric(f"MIT elektr. WW (maßgeblich) · {d['nWE']} WE", f"≈ {fmt(d['mit'])} kW")
        c2.metric("OHNE elektr. WW (Referenz)", f"≈ {fmt(d['ohne'])} kW")
        st.caption("**Hinweis Pmax:** Die maximale Anschlussleistung Pmax ergibt sich aus dem Wohnbedarf nach DIN "
                   "zuzüglich bewerteter Sonderlasten (z. B. Ladeinfrastruktur), abzüglich möglicher Effekte durch "
                   "Lastmanagement, Speicher und Gleichzeitigkeitsfaktoren, und muss bauseits ermittelt werden.")

if "Alle Stränge" in tabs:
    with tabs["Alle Stränge"]:
        G = gesamt_anlage(inp, results)
        st.markdown(f"#### Gesamtübersicht – alle {len(results)} Stränge")
        if G["getrennt"]:
            st.warning("**Getrennte Ausführung:** Jeder Strang hat eine eigene Wärmezentrale. Die Gesamtwerte sind die "
                       "Summe der Einzelanlagen.")
        c = st.columns(4)
        c[0].metric("Wohnungen gesamt", G["we"])
        c[1].metric("Gleichzeitigkeit gesamt", "–" if G["gz"] is None else fmt(G["gz"], 1))
        c[2].metric("Kessel-/FW-Leistung", f"{fmt(G['kesselQ'])} kW")
        c[3].metric("Pufferspeicher", puffer_produkt(G["pufferVol"])["text"])
        c[3].caption(f"berechnet {fmt(G['pufferVol'])} l")
        st.dataframe(pd.DataFrame([{
            "Strang": f"Strang {i + 1}", "Etagen": r["floors"], "Aufteilung": "beidseitig" if r["split"] == "both"
            else "einseitig", "Wohnungen": r["totalWE"], "Strangfuß": r["vRows"][0]["dim"],
            "V̇ Strangfuß [m³/h]": r["vRows"][0]["Vtot"], "v [m/s]": r["vRows"][0]["v"],
            **({"Kessel [kW]": r["anlage"]["kesselQ"], "Puffer [l]": round(r["anlage"]["pufferVol"])}
               if G["getrennt"] else {})} for i, r in enumerate(results)]),
            hide_index=True, width="stretch",
            column_config={"V̇ Strangfuß [m³/h]": st.column_config.NumberColumn(format="%.2f"),
                           "v [m/s]": st.column_config.NumberColumn(format="%.2f")})
        for i, r in enumerate(results):
            with st.expander(f"Strang {i + 1} · {r['totalWE']} Wohnungen · Strangfuß {r['vRows'][0]['dim']}"):
                st.plotly_chart(plots.netzschema(r), width="stretch", config={"displayModeBar": False},
                                key=f"schema_all_{i}")
                st.dataframe(styled(strang_table(r, "V")), hide_index=True, width="stretch",
                             column_config=NUMFMT)

st.caption("Rechenkern nach Bosch-HIU-Methodik (Gleichzeitigkeit DIN 4708 / TU Dresden, Knotenpunkt-Formel, "
           "Darcy-Weisbach, turbulent). Werkzeug zur Vorplanung – ersetzt keine verbindliche Rohrnetzberechnung. "
           "Prüfung obliegt Planer, Installateur oder Bauherr. Entwickelt von Daniel Sommer · HC/SDE3-PSD")
