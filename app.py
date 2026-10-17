"""BOSCH Flow – Netz- & Anlagenrechner für Wohnungsstationen (Streamlit).

Start:  streamlit run app.py
Kachel-Dashboard: oben die vier Kennzahlen, darunter 3D-Gebäude, Prüfungen, Variantenempfehlung, Rohrnetz, Gerät
und Stückliste. Jede Kachel öffnet per Klick ihre Details (Schemata, Tabellen, Herleitungen). Die Eingaben stehen im
Panel links (ein-/ausblendbar). Rechenkern wie die HTML-Version V54 (index.html). Auto-Sicherung im Browser, Hell/Dunkel,
PDF- und Excel-Export.
"""
from __future__ import annotations

import base64
import hmac
import json
import os
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Bosch Flow – Netz- & Anlagenrechner", page_icon="🔥", layout="wide")

from bosch_flow import hydraulik as HY  # noqa: E402
from bosch_flow import katalog as KA  # noqa: E402
from bosch_flow import plots, schemata  # noqa: E402
from bosch_flow import report as RP  # noqa: E402
from bosch_flow import varianten as VA  # noqa: E402
from bosch_flow.bericht import pdf_bericht  # noqa: E402
from bosch_flow.calc import (Inputs, Strang, compute_all, din18015, dle_table, etage_label,  # noqa: E402
                             gesamt_anlage, project_headline, puffer_produkt, topo_label, topologie, tvl_bounds,
                             zapf_max_lmin)
from bosch_flow.data import MATNAME, STATIONS, WAERMEQUELLEN  # noqa: E402
from bosch_flow.modell3d import STUFEN, modell  # noqa: E402
from bosch_flow.project import dumps, from_html_state, stand  # noqa: E402
from bosch_flow.report import fmt  # noqa: E402
from bosch_flow.zeichnung import als_plotly  # noqa: E402
from browser import browser  # noqa: E402

ss = st.session_state
BLAU = "#005691"
ICONS = Path(__file__).parent / "bosch_flow" / "daten" / "icons"


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

# Farb-Token (hell / dunkel)
F = dict(seite="#0b1016", kachel="#131b24", linie="rgba(255,255,255,.07)", text="#e8eef4", leise="#8fa1b3",
         akzent="#4fa3e0", akzent_bg="rgba(79,163,224,.12)", schatten="0 1px 2px rgba(0,0,0,.4)",
         schatten2="0 10px 30px rgba(0,0,0,.45)", gruen="#3ecf6e", gelb="#f2c14e", rot="#ff5a6a",
         feld="#0d131a", feldrand="rgba(255,255,255,.30)", fokus="rgba(79,163,224,.35)") if DUNKEL else \
    dict(seite="#f3f5f8", kachel="#ffffff", linie="rgba(16,24,40,.07)", text="#101828", leise="#667085",
         akzent=BLAU, akzent_bg="rgba(0,86,145,.08)", schatten="0 1px 2px rgba(16,24,40,.05)",
         schatten2="0 12px 32px rgba(16,24,40,.10)", gruen="#12b76a", gelb="#f79009", rot="#e5484d",
         feld="#ffffff", feldrand="#9aa6b2", fokus="rgba(0,86,145,.22)")


def _svg(name: str) -> str:
    raw = (ICONS / f"{name}.svg").read_text(encoding="utf-8")
    if DUNKEL:
        raw = raw.replace("#1D1D1B", "#e8eef4")
    return "data:image/svg+xml;base64," + base64.b64encode(raw.encode()).decode()


# ====================================================================== Stil
st.markdown(f"""
<style>
.stApp {{background:{F['seite']}}}
header[data-testid="stHeader"] {{background:transparent}}
.block-container {{padding-top:2.4rem; padding-bottom:1.5rem; max-width:min(1760px, 98vw)}}
.superband {{position:fixed; top:0; left:0; right:0; height:4px; z-index:999990;
            background:linear-gradient(90deg,#e20015 0%,#b90276 22%,#50237f 44%,#005691 70%,#008ecf 100%)}}
/* Kopfleiste */
.marke {{font-weight:800; font-size:22px; letter-spacing:.2px; color:#e20015; line-height:1.1}}
.marke span {{color:{F['text']}}}
.marke small {{display:block; font-size:12px; font-weight:500; color:{F['leise']}; letter-spacing:0; margin-top:2px}}
.pille {{display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:600; color:{F['leise']};
        background:{F['kachel']}; border:1px solid {F['linie']}; border-radius:999px; padding:5px 12px;
        white-space:nowrap}}
.kopf-info {{font-size:12.5px; color:{F['leise']}; text-align:right; line-height:1.45}}
.kopf-info b {{color:{F['text']}; font-size:13.5px}}
.pille i {{width:8px; height:8px; border-radius:50%; background:{F['gruen']}; display:inline-block}}
/* Kacheln */
[class*="st-key-kachel"] {{background:{F['kachel']}; border:1px solid {F['linie']}; border-radius:20px;
        padding:18px 20px 16px; box-shadow:{F['schatten']}; transition:box-shadow .18s, transform .18s;
        position:relative; gap:.35rem}}
[class*="st-key-kachelklick"]:hover {{box-shadow:{F['schatten2']}}}
[class*="st-key-kachelklick"]:hover {{transform:translateY(-2px); cursor:pointer}}
[class*="st-key-kachelklick"] [class*="st-key-klick_"] {{position:absolute; inset:0; z-index:4; margin:0}}
[class*="st-key-kachelklick"] [class*="st-key-klick_"] button {{width:100%; height:100%; opacity:0; cursor:pointer}}
.k-kopf {{display:flex; align-items:center; justify-content:space-between; gap:8px}}
.k-titel {{font-size:12.5px; font-weight:700; color:{F['leise']}; letter-spacing:.2px}}
.k-kopf {{position:relative}}
.k-mehr {{position:absolute; right:44px; top:50%; transform:translateY(-50%); font-size:11.5px; font-weight:600;
          color:{F['akzent']}; background:{F['kachel']}; padding-left:8px; opacity:0; white-space:nowrap;
          transition:opacity .18s}}
.st-key-kachel_3d [data-testid="stHorizontalBlock"]:first-of-type {{margin-top:8px}}
[class*="st-key-kachel"]:hover .k-mehr {{opacity:1}}
.k-wert {{font-size:clamp(28px, 2.6vw, 40px); font-weight:800; color:{F['text']}; letter-spacing:-.5px;
         line-height:1.05; margin-top:6px}}
.k-wert span {{font-size:.45em; font-weight:600; color:{F['leise']}; margin-left:5px; letter-spacing:0}}
.k-unter {{font-size:12.5px; color:{F['leise']}; margin-top:6px}}
.k-icon {{width:30px; height:30px; display:flex; align-items:center; justify-content:center; opacity:.75}}
.k-icon img {{width:22px; height:22px}}
.delta {{display:inline-block; font-size:11.5px; font-weight:700; border-radius:999px; padding:1px 8px; margin-left:6px}}
.delta.up {{background:rgba(229,72,77,.12); color:{F['rot']}}}
.delta.down {{background:rgba(18,183,106,.12); color:{F['gruen']}}}
/* Prüfungen */
.pruef {{display:flex; align-items:flex-start; gap:10px; padding:7px 0; border-bottom:1px solid {F['linie']};
        font-size:13.5px; color:{F['text']}}}
.pruef:last-child {{border-bottom:0}}
.pruef b {{font-weight:650}}
.pruef small {{display:block; color:{F['leise']}; font-size:12px; margin-top:1px}}
.dot {{flex:0 0 10px; height:10px; border-radius:50%; margin-top:5px}}
.dot.ok {{background:{F['gruen']}; box-shadow:0 0 0 4px rgba(18,183,106,.15)}}
.dot.warn {{background:{F['gelb']}; box-shadow:0 0 0 4px rgba(247,144,9,.15)}}
.dot.err {{background:{F['rot']}; box-shadow:0 0 0 4px rgba(229,72,77,.15)}}
.dot.info {{background:{F['akzent']}; box-shadow:0 0 0 4px {F['akzent_bg']}}}
.gesamt {{font-size:20px; font-weight:800; color:{F['text']}; margin:4px 0 2px}}
/* Empfehlung */
.empf-tag {{display:inline-block; font-size:11px; font-weight:800; letter-spacing:.4px; text-transform:uppercase;
           color:{F['gruen']}; background:rgba(18,183,106,.12); border-radius:999px; padding:2px 10px}}
.empf-titel {{font-size:22px; font-weight:800; color:{F['text']}; margin:8px 0 2px; line-height:1.15}}
.empf-pkt {{font-size:13px; color:{F['leise']}; margin:2px 0}}
/* Rohrnetz-Balken */
.rn {{display:grid; grid-template-columns:42px 1fr 64px 70px; align-items:center; gap:10px; font-size:13px;
     color:{F['text']}; padding:5px 0}}
.rn .s {{font-weight:800; color:{F['akzent']}}}
.rn .bar {{height:8px; border-radius:99px; background:{F['linie']}; overflow:hidden}}
.rn .bar i {{display:block; height:100%; border-radius:99px}}
.rn .dn {{font-weight:700; text-align:right}}
.rn .v {{color:{F['leise']}; text-align:right; font-size:12px}}
.rn-kopf {{font-size:12px; color:{F['leise']}; margin:2px 0 6px}}
/* Gerät */
.g-typ {{font-size:20px; font-weight:800; color:{F['text']}; line-height:1.15}}
.g-sub {{font-size:12.5px; color:{F['leise']}; margin:3px 0 8px}}
.g-zeile {{display:flex; justify-content:space-between; font-size:13px; padding:4px 0; border-bottom:1px solid {F['linie']};
          color:{F['text']}}}
.g-zeile span {{color:{F['leise']}}}
/* Eingabefelder: klare Rahmen, aktives Feld mit Fokus-Ring */
[data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"], [data-testid="stDateInputField"],
.react-aria-ComboBox > div[role="group"], [data-testid="stTextArea"] textarea {{
        background:{F['feld']} !important; border:1.5px solid {F['feldrand']} !important; border-radius:10px !important;
        transition:border-color .12s, box-shadow .12s}}
[data-testid="stNumberInputContainer"] input, [data-testid="stTextInputRootElement"] input,
.react-aria-ComboBox input {{color:{F['text']} !important; font-weight:600}}
[data-testid="stNumberInputContainer"] button {{background:transparent !important; color:{F['text']} !important;
        border-left:1px solid {F['linie']} !important; border-radius:0 !important}}
[data-testid="stNumberInputContainer"] button:hover {{background:{F['akzent_bg']} !important; color:{F['akzent']} !important}}
[data-testid="stNumberInputContainer"]:hover, [data-testid="stTextInputRootElement"]:hover,
[data-testid="stDateInputField"]:hover, .react-aria-ComboBox > div[role="group"]:hover {{border-color:{F['leise']} !important}}
[data-testid="stNumberInputContainer"]:focus-within, [data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stDateInputField"]:focus-within, .react-aria-ComboBox > div[role="group"]:focus-within {{
        border-color:{F['akzent']} !important; box-shadow:0 0 0 3px {F['fokus']} !important}}
[data-testid="stWidgetLabel"] p {{font-weight:650 !important; color:{F['text']} !important; font-size:13px !important}}
/* Reiter im Panel: aktiver Reiter deutlich */
.st-key-panel [role="tablist"] {{border-bottom:2px solid {F['feldrand']}}}
.st-key-panel [role="tab"] p {{font-weight:600; font-size:14px}}
.st-key-panel [role="tab"][aria-selected="true"] p {{color:{F['akzent']}; font-weight:800}}
/* Etagenliste: Zeilen als Bänder */
.etage {{font-size:13.5px !important; font-weight:800 !important}}
/* Eingabe-Panel */
.st-key-panel {{background:{F['kachel']}; border:1px solid {F['linie']}; border-radius:20px; padding:16px 16px 10px;
               box-shadow:{F['schatten2']}; position:sticky; top:3.2rem; max-height:calc(100vh - 4rem);
               overflow-y:auto; animation:reinfahren .28s ease-out}}
@keyframes reinfahren {{from {{opacity:0; transform:translateX(-28px)}} to {{opacity:1; transform:none}}}}
.p-titel {{font-size:16px; font-weight:800; color:{F['text']}}}
.hinweis {{font-size:12px; line-height:1.45; color:{F['leise']}; border-left:3px solid {F['akzent']}; padding:6px 10px;
          background:{F['akzent_bg']}; border-radius:0 8px 8px 0; margin:2px 0 8px}}
.info-zeile {{display:flex; justify-content:space-between; gap:.6rem; font-size:12.5px; padding:.2rem 0;
             border-bottom:1px solid {F['linie']}; color:{F['text']}}}
.info-zeile span:first-child {{color:{F['leise']}}}
.etage {{font-size:13px; font-weight:700; text-align:right; color:{F['text']}}}
.lr {{font-size:11px; color:{F['leise']}}}
/* Details (Dialoge) */
.abschnitt {{flex:1 1 160px; min-width:150px; border:1px solid {F['linie']}; border-left:4px solid {F['akzent']};
            border-radius:10px; padding:8px 10px; color:{F['text']}}}
.abschnitt.krit {{border-left-color:#b26a00; background:rgba(178,106,0,.08)}}
.abschnitt .num {{display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px;
                 border-radius:50%; background:{F['akzent']}; color:#fff; font-size:11px; font-weight:700; margin-right:6px}}
.abschnitt.krit .num {{background:#b26a00}}
.strangkopf {{font-weight:700; font-size:14px; margin:4px 0; color:{F['text']}}}
.badge2 {{display:inline-block; font-size:11.5px; font-weight:600; padding:2px 9px; border-radius:12px;
         border:1px solid {F['linie']}; margin:0 4px 4px 0; color:{F['leise']}}}
[data-testid="stCaptionContainer"] {{color:{F['leise']} !important}}
[data-testid="stMetric"] {{background:{F['akzent_bg']}; border-radius:14px; padding:10px 14px}}
.fuss {{text-align:center; color:{F['leise']}; font-size:11.5px; padding:1.2rem 0 .2rem}}
div[data-testid="stDialog"] div[role="dialog"] {{border-radius:20px}}
/* gleiche Höhen je Reihe */
.st-key-kachelklick_v, .st-key-kachelklick_dn, .st-key-kachelklick_kessel, .st-key-kachelklick_puffer {{min-height:150px}}
.st-key-kachelklick_rohrnetz, .st-key-kachelklick_geraet, .st-key-kachelklick_stueck,
.st-key-kachelklick_pumpe, .st-key-kachelklick_strom, .st-key-kachelklick_rohr {{min-height:190px}}
.st-key-kachelklick_geraet [data-testid="stImage"] img {{max-height:130px; object-fit:contain}}
.st-key-panel_zu button {{border:0; background:transparent; min-height:32px; padding:4px 8px}}
.st-key-panel [data-baseweb="tab-list"] {{gap:6px}}
</style>
<div class="superband"></div>""", unsafe_allow_html=True)


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
if "panel" not in ss:
    ss.panel = True
if msg := ss.pop("meldung", None):
    st.toast(msg[1], icon="✅" if msg[0] == "success" else "⚠️")


# ====================================================================== Kopfleiste
kopf = st.columns([3.2, 3.4, 1.15, 1.25, 0.62, 0.5], vertical_alignment="center")
kopf[0].markdown('<div class="marke">BOSCH <span>Flow</span><small>Netz- &amp; Anlagenrechner für '
                 'Wohnungsstationen</small></div>', unsafe_allow_html=True)
kopf_status = kopf[1].container()
if kopf[2].button("Eingaben", icon=":material/tune:", width="stretch",
                  type="secondary" if ss.panel else "primary", help="Eingabe-Panel ein-/ausblenden"):
    ss.panel = not ss.panel
    st.rerun()
kopf_pdf = kopf[3].empty()
kopf_menue = kopf[4].empty()
kopf_thema = kopf[5].container()
st.write("")

if ss.panel:
    panel_spalte, haupt = st.columns([1.05, 2.75], gap="large")
else:
    haupt, panel_spalte = st.container(), None


def zentrale_regler(schluessel: str) -> None:
    """Position der Wärmezentrale (0 = links … 100 = rechts); mehrere Regler teilen sich denselben Wert."""
    m = ss.meta
    pos = st.slider("Position Wärmezentrale", 0, 100, int(m["topoPos"]), 5,
                    key=f"{schluessel}_{ss.rev}_{int(m['topoPos'])}", format="%d %%",
                    help="0 % = links am ersten Strang, 50 % = mittig, 100 % = rechts. Der Hauptstrang wird je "
                         "Abschnitt neu dimensioniert und mit dem Projekt gespeichert.")
    if pos != int(m["topoPos"]):
        m["topoPos"] = float(pos)
        st.rerun()


# ====================================================================== Eingabe-Panel (links)
def eingaben() -> None:
    meta = ss.meta
    t_geb, t_sys, t_ausl, t_proj = st.tabs(["Gebäude", "System", "Auslegung", "Projekt"])

    # ---------------------------------------------------------------- Gebäude
    with t_geb:
        straenge = ss.straenge
        n = len(straenge)
        aktiv = meta["activeStrang"]
        if n > 1:
            namen = [f"Strang {i + 1}" if n <= 3 else f"S{i + 1}" for i in range(n)]
            w = st.segmented_control("Strang", namen, default=namen[aktiv], key=f"strang_geb_{ss.rev}_{aktiv}_{n}",
                                     label_visibility="collapsed", width="stretch")
            if w and namen.index(w) != aktiv:
                meta["activeStrang"] = namen.index(w)
                st.rerun()
        b, c = st.columns(2, vertical_alignment="center")
        if b.button("Strang", icon=":material/add:", help="Neuer Strang als Kopie des aktuellen", width="stretch"):
            cur = straenge[aktiv]
            straenge.append(Strang(cur.floors, cur.split, [dict(x) for x in cur.cfg]))
            meta["activeStrang"] = len(straenge) - 1
            st.rerun()
        if c.button("Strang", icon=":material/remove:", help="Aktuellen Strang löschen", disabled=n <= 1,
                    width="stretch", key="strang_weg"):
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
        if n > 1 and z == "gemeinsam":
            zentrale_regler("topo_geb")
            st.caption(f"Wärmezentrale: **{topo_label(meta['topoPos'])}**")
        si = meta["activeStrang"]
        s = straenge[si]
        a, b = st.columns(2)
        fl = int(a.number_input("Etagen", 1, 20, int(s.floors), 1, key=k(f"floors{si}"),
                                help="Geschosse, die DIESER Steigstrang versorgt."))
        sp = b.selectbox("Aufteilung", ["both", "one"], 0 if s.split == "both" else 1, key=k(f"split{si}"),
                         format_func=lambda v: "beidseitig" if v == "both" else "einseitig",
                         help="Beidseitig = Stationen links und rechts vom Steigstrang. Einseitig = ein Strang je Etage.")
        if fl != s.floors or sp != s.split:
            cfg = [dict(x) for x in s.cfg[:fl]]
            oben = dict(cfg[-1]) if cfg else {"l": 5, "r": 5}
            while len(cfg) < fl:                     # neue Etagen übernehmen die Belegung der obersten Etage
                cfg.append(dict(oben))
            for x in cfg:
                x["r"] = (x["r"] if s.split == "both" else x["l"]) if sp == "both" else 0
            s.floors, s.split, s.cfg = fl, sp, cfg
            ss.rev += 1
            st.rerun()
        a, b = st.columns([1, 1.4], vertical_alignment="bottom")
        q = a.number_input("Stationen je Seite", 0, 16, int(ss.get("schnell", 5)), 1, key=k("quick"))
        ss.schnell = int(q)
        if b.button("auf alle Etagen", width="stretch", icon=":material/done_all:"):
            s.cfg = [{"l": int(q), "r": int(q) if s.split == "both" else 0} for _x in range(s.floors)]
            ss.rev += 1
            st.rerun()
        for f in range(s.floors, 0, -1):
            cf = s.cfg[f - 1]
            if s.split == "both":
                e, l, ll, r, rr = st.columns([0.9, 1.3, 0.3, 1.3, 0.3], vertical_alignment="center")
            else:
                e, l, ll = st.columns([0.9, 2.6, 0.6], vertical_alignment="center")
            e.markdown(f'<div class="etage">{etage_label(f)}</div>', unsafe_allow_html=True)
            cf["l"] = int(l.number_input(f"{etage_label(f)} links", 0, 16, int(cf["l"]), 1,
                                         key=k(f"l{si}_{f}"), label_visibility="collapsed"))
            ll.markdown('<div class="lr">L</div>' if s.split == "both" else '<div class="lr">Stat.</div>',
                        unsafe_allow_html=True)
            if s.split == "both":
                cf["r"] = int(r.number_input(f"{etage_label(f)} rechts", 0, 16, int(cf["r"]), 1,
                                             key=k(f"r{si}_{f}"), label_visibility="collapsed"))
                rr.markdown('<div class="lr">R</div>', unsafe_allow_html=True)

    # ---------------------------------------------------------------- System & Gerät
    with t_sys:
        v = st.selectbox("Leitersystem", ["2", "4"], ["2", "4"].index(ss.inp.system), key=k("system"),
                         format_func=lambda x: "2-Leiter (Heizung + Trinkwasser über Station)" if x == "2"
                         else "4-Leiter (Heizung + Trinkwasser getrennt)",
                         help="Gilt für die gesamte Anlage. 2-Leiter für hohe Vorlauftemperaturen (Kessel/Fernwärme), "
                              "4-Leiter für Wärmepumpen/Niedertemperatur.")
        setze(system=v)
        qv = st.selectbox("Wärmequelle", list(WAERMEQUELLEN), list(WAERMEQUELLEN).index(ss.inp.waermequelle),
                          key=k("waermequelle"), format_func=lambda x: WAERMEQUELLEN[x]["name"],
                          help="Setzt Kesseltotzeit / Wiederaufheizzeit automatisch (unter Auslegung anpassbar).")
        if qv != ss.inp.waermequelle:
            wq = WAERMEQUELLEN[qv]
            setze(waermequelle=qv, tTot=float(wq["tot"]), tWied=float(wq["wied"]))
            ss.rev += 1
            st.rerun()
        stv = st.selectbox("Wohnungsstation", list(STATIONS), list(STATIONS).index(ss.inp.station), key=k("station"),
                           format_func=lambda x: STATIONS[x]["name"],
                           help="Flow 8000: WW-Vorrang (Heizung pausiert beim Zapfen). Flow 7000: WW-Parallelbetrieb.")
        stn = STATIONS[stv]
        setze(station=stv, wwstage=min(ss.inp.wwstage, len(stn["stages"]) - 1))
        a, b = st.columns(2)
        ws = a.selectbox("WW-Leistung", list(range(len(stn["stages"]))), ss.inp.wwstage, key=k(f"wwstage_{stv}"),
                         format_func=lambda i: "{kw} kW · {lmin} l/min".format(**stn["stages"][i]),
                         help="Zapfmenge je Station laut Gerätedatenblatt (Standard-Modus).")
        wm = b.selectbox("WW-Parameter", ["std", "man"], ["std", "man"].index(ss.inp.wwmode), key=k("wwmode"),
                         format_func=lambda x: "Standard" if x == "std" else "Manuell",
                         help="Standard: Zapfmenge aus der Leistungsstufe, 45 °C. Manuell: bedarfsgerechte Zapfmenge und "
                              "Zapftemperatur – optimiert Speicher- und Erzeugergröße.")
        setze(wwstage=ws, wwmode=wm)
        if wm == "man":
            a, b = st.columns(2)
            zt = b.number_input("Zapftemperatur °C", 45.0, 60.0, min(max(float(ss.inp.zapfTemp), 45.0), 60.0), 1.0,
                                format="%.0f", key=k("zapfTemp"), help="45 °C (Muss-Minimum) bis 60 °C.")
            mx = max(5.0, zapf_max_lmin(replace(ss.inp, zapfTemp=zt)))
            zm = a.number_input("Zapfmenge l/min", 5.0, mx, min(max(5.0, float(ss.inp.zapfMenge)), mx), 0.5,
                                format="%.1f", key=k(f"zapfMenge_{mx}"),
                                help="Ab 5 l/min; Maximum aus kW-Klasse und Zapftemperatur.")
            setze(zapfTemp=zt, zapfMenge=zm)
            st.caption(f"max. {fmt(mx, 1)} l/min bei {stn['stages'][ws]['kw']} kW und {fmt(zt)} °C")
        if stn["zuheizerFaehig"] and ss.inp.system == "2":
            zh = st.selectbox("Elektrischer Zuheizer (DLE)", ["off", "on"], ["off", "on"].index(ss.inp.zuheizer),
                              key=k("zuheizer"),
                              format_func=lambda x: "mit elektrischem Zuheizer (HPS)" if x == "on" else "ohne Zuheizer",
                              help="Nachgeschalteter Durchlauferhitzer (Flow 7000 HPS) als Booster in der Wohnung.")
            setze(zuheizer=zh)
            if zh == "on":
                a, b = st.columns(2)
                kw = a.selectbox("Zuheizer-Leistung", [11.0, 13.0], [11.0, 13.0].index(float(ss.inp.zuheizerKW))
                                 if float(ss.inp.zuheizerKW) in (11.0, 13.0) else 0, key=k("zuheizerKW"),
                                 format_func=lambda x: f"{x:.0f} kW")
                ds = b.selectbox("DLE-Stufe", [48.0, 53.0, 60.0], [48.0, 53.0, 60.0].index(float(ss.inp.dleStufe))
                                 if float(ss.inp.dleStufe) in (48.0, 53.0, 60.0) else 1, key=k("dleStufe"),
                                 format_func=lambda x: f"{x:.0f} °C", help="Drei feste Stufen (Wählschalter).")
                setze(zuheizerKW=kw, dleStufe=ds)
        a, b = st.columns(2)
        mo0, hk0 = KA.ausfuehrung(meta)
        mo = a.selectbox("Montage", list(KA.MONTAGE), list(KA.MONTAGE).index(mo0), key=k("montage"),
                         format_func=lambda x: {"ap": "Aufputz", "up": "Unterputz", "rs": "Thermentausch RS"}[x],
                         help="Ausführung laut Katalog – bestimmt Gerätetyp, Bestell-Nr. und Montagezubehör.")
        hk = b.selectbox("Heizkreis", list(KA.HEIZKREIS), list(KA.HEIZKREIS).index(hk0), key=k("heizkreis"),
                         help="Ungemischt: Heizkörper. Gemischt: Station mit Pumpe und Mischer (Fußbodenheizung).")
        meta["montage"], meta["heizkreis"] = mo, hk

    # ---------------------------------------------------------------- Auslegung
    with t_ausl:
        stn = STATIONS[ss.inp.station]
        lo, hi = tvl_bounds(ss.inp)
        mxq = float(stn["maxHeatKW"] + 3)
        a, b = st.columns(2)
        tvl = a.number_input("Versorgungs-VL °C", float(lo), float(hi), float(min(max(float(ss.inp.tvl), lo), hi)), 1.0,
                             format="%.0f", key=k(f"tvl_{lo}_{hi}"),
                             help=f"Frei einstellbar {lo}–{hi} °C. Kommt 1:1 an der Wohnungsstation an.")
        qhk = b.number_input("Heizlast je WE kW", 0.0, mxq, min(float(ss.inp.qhk), mxq), 0.1, format="%.1f",
                             key=k(f"qhk_{mxq}"), help=f"Begrenzt auf Geräte-Heizleistung + 3 kW (max. {mxq:g} kW).")
        vlhk = a.number_input("VL Heizkreis °C", 30.0, 70.0, float(ss.inp.vlhk), 1.0, format="%.0f", key=k("vlhk"),
                              help="Vorlauf im Wohnungs-Heizkreis; nicht höher als die Netztemperatur.")
        dthk = b.number_input("Spreizung ΔT K", 1.0, 40.0, float(ss.inp.dthk), 1.0, format="%.0f", key=k("dthk"))
        glz = a.selectbox("Gleichzeitigkeit", ["din", "tud"], ["din", "tud"].index(ss.inp.glz), key=k("glz"),
                          format_func=lambda x: "DIN 4708" if x == "din" else "TU Dresden",
                          help="DIN 4708 (konservativ) oder TU Dresden (aus Messungen, kleinere Rohre).")
        mat = b.selectbox("Rohrmaterial", list(MATNAME), list(MATNAME).index(ss.inp.mat), key=k("mat"),
                          format_func=lambda x: MATNAME[x])
        vmax = a.number_input("v max m/s", 0.5, 3.0, float(ss.inp.vmax), 0.1, format="%.1f", key=k("vmax"),
                              help="Auslegungsgrenze. Bosch-Standard: 1,0 m/s.")
        tsp = b.number_input("Spitzenzeit min", 5.0, 60.0, max(5.0, float(ss.inp.tsp)), 1.0, format="%.0f", key=k("tsp"),
                             help="Dauer der Spitzenzapfung für die Pufferauslegung.")
        tTot = a.number_input("Kesseltotzeit min", 1.0, 10.0, float(ss.inp.tTot), 1.0, format="%.0f", key=k("tTot"),
                              help="Wandgeräte 2–3 min, bodenstehende Kessel 5–7 min.")
        tWied = b.number_input("Wiederaufheizzeit min", 10.0, 60.0, float(ss.inp.tWied), 1.0, format="%.0f",
                               key=k("tWied"), help="Empfehlung: 20–30 min, Wärmepumpen ca. 45 min.")
        setze(qhk=qhk, dthk=dthk, tvl=tvl, vlhk=vlhk, glz=glz, mat=mat, vmax=vmax, tsp=tsp, tTot=tTot, tWied=tWied)
        if ss.inp.system == "4":
            hT = a.number_input("Puffer-Mindestlaufzeit min", 5.0, 30.0, float(ss.inp.heizTueber), 1.0, format="%.0f",
                                key=k("heizTueber"), help="Nur 4-Leiter: Taktschutz nach VDI 4645 (10–20 min).")
            hD = b.number_input("Puffer-Spreizung ΔT K", 3.0, 20.0, float(ss.inp.heizDt), 1.0, format="%.0f",
                                key=k("heizDt"), help="Nur 4-Leiter: Herstellerpraxis (VDI 4645) 10 K.")
            setze(heizTueber=hT, heizDt=hD)

        # ------------------------------------------------------------ Experteneinstellungen (Hydraulik)
        geaendert = any(k_ in meta for k_ in HY.GEOMETRIE)
        with st.expander("Experteneinstellungen" + (" · angepasst" if geaendert else ""), icon=":material/tune:"):
            st.caption("Leitungslängen und Zuschläge für Druckverlust, Förderhöhe der Netzpumpe und Rohrmengen. "
                       "Standardwerte passen für übliche Wohngebäude.")
            geo = HY.geometrie(meta)
            spalten = st.columns(2)
            for i, (key, (vorgabe, titel, einheit, lo, hi, schritt)) in enumerate(HY.GEOMETRIE.items()):
                wert = float(spalten[i % 2].number_input(f"{titel} [{einheit}]", float(lo), float(hi), float(geo[key]),
                                                         float(schritt), format="%.1f" if schritt < 1 else "%.0f",
                                                         key=k(f"geo_{key}")))
                if wert != vorgabe:
                    meta[key] = wert
                else:
                    meta.pop(key, None)
            if geaendert and st.button("Standardwerte", icon=":material/restart_alt:", key="geo_standard"):
                for key in HY.GEOMETRIE:
                    meta.pop(key, None)
                ss.rev += 1
                st.rerun()

    # ---------------------------------------------------------------- Projekt
    with t_proj:
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


if panel_spalte is not None:
    with panel_spalte:
        with st.container(key="panel"):
            a, b = st.columns([4, 1], vertical_alignment="center")
            a.markdown('<div class="p-titel">Eingaben</div>', unsafe_allow_html=True)
            if b.button("", icon=":material/close:", key="panel_zu", help="Panel schließen"):
                ss.panel = False
                st.rerun()
            eingaben()

# ====================================================================== Rechnung
inp, straenge, meta = ss.inp, ss.straenge, ss.meta
results = compute_all(inp, straenge)
R = results[meta["activeStrang"]]
P, A = R["P"], R["anlage"]
HL = project_headline(R, inp)
G = gesamt_anlage(inp, results)
n = len(results)
name = (meta["projName"] or "bosch-flow-projekt").strip().replace(" ", "_")
KZ = VA.kennzahlen(inp, straenge, meta["topoPos"])
GERAET = KA.geraet(inp, meta)
STUECK = KA.projekt_stueckliste(inp, straenge, meta)
HYD = HY.berechne(inp, straenge, meta)
jetzt = stand(inp, straenge, meta)


# ====================================================================== Prüfungen
def pruefungen() -> list[tuple[str, str, str]]:
    """(Stufe ok/warn/err/info, Titel, Text)."""
    out = []
    if KZ["zuSchnell"]:
        out.append(("err", f"{KZ['zuSchnell']} Abschnitt(e) zu schnell", f"über 120 % von v_max = {fmt(P['vmax'], 1)} m/s"))
    elif KZ["ueber"]:
        out.append(("warn", f"{KZ['ueber']} Abschnitt(e) grenzwertig", "zwischen 100 und 120 % von v_max"))
    else:
        out.append(("ok", "Geschwindigkeiten im Rahmen", f"alle {KZ['abschnitte']} Abschnitte ≤ {fmt(P['vmax'], 1)} m/s · "
                    f"max. {fmt(KZ['auslastung'] * 100)} %"))
    out.append(("info", "Betriebspunkt Netzpumpe", f"V̇ {fmt(HYD['V'], 2)} m³/h · Förderhöhe {fmt(HYD['bar'], 2)} bar "
                f"(≈ {fmt(HYD['H'], 1)} m) – bauseits zu erbringen"))
    if P["vlhkZuHoch"]:
        out.append(("err", "Heizkreis-VL zu hoch", f"{fmt(P['vlhk'])} °C über Netztemperatur {fmt(P['netzTemp'])} °C – "
                    f"max. {P['vlhkMax']} °C"))
    if P["heatOver"]:
        out.append(("warn", "Heizlast im Reservebereich", f"{fmt(P['qhk'], 1)} kW > {R['st']['maxHeatKW']} kW Nennleistung"))
    if P["zapfGekappt"]:
        out.append(("warn", "Zapfmenge gedeckelt", f"auf {fmt(P['zapfLmin'], 1)} l/min (kW-Klasse)"))
    for stufe, text in GERAET["hinweise"]:
        if stufe == "warn":
            out.append(("warn", "Katalog-Hinweis", text))
    if A["zuheizerOn"]:
        zst, ztext = RP.dle_fazit(A)
        out.append(({"none": "info", "ok": "ok", "over": "err"}[zst],
                    {"none": "DLE wird nicht gebraucht", "ok": "DLE-Leistung passt", "over": "DLE reicht nicht"}[zst],
                    ztext.replace("**", "")[:140] + ("…" if len(ztext) > 140 else "")))
    if not any(s in ("warn", "err") for s, _, _ in out):
        out.append(("ok", f"{GERAET['typ']} im Katalogbereich", f"Primär-VL {GERAET['vlMin']}–{GERAET['vlMax']} °C"))
    return out


PRUEF = pruefungen()
n_err = sum(1 for s, _, _ in PRUEF if s == "err")
n_warn = sum(1 for s, _, _ in PRUEF if s == "warn")


# ====================================================================== Kopfleiste befüllen
farbe_status = F["rot"] if n_err else F["gelb"] if n_warn else F["gruen"]
text_status = (f"{n_err} Fehler" if n_err else f"{n_warn} Hinweis{'e' if n_warn > 1 else ''}" if n_warn
               else "Auslegung OK")
with kopf_status:
    a, b = st.columns([1.5, 1], vertical_alignment="center")
    a.markdown(f'<div class="kopf-info"><b>{meta["projName"] or "Neues Projekt"}</b><br>'
               f'<span title="Jede Eingabe wird automatisch im Browser gesichert.">↻ automatisch gesichert '
               f'{ss.get("zwischen") or datetime.now().strftime("%H:%M")}</span></div>', unsafe_allow_html=True)
    b.markdown(f'<style>.st-key-status_knopf button {{border-radius:999px; font-weight:700; color:{farbe_status}; '
               f'border-color:{farbe_status}}}</style>', unsafe_allow_html=True)
    if b.button(text_status, key="status_knopf", width="stretch",
                icon=":material/check_circle:" if not (n_err or n_warn) else ":material/error:",
                help="Alle Prüfungen anzeigen"):
        ss.oeffne = "pruef"

_inp, _str, _meta = inp, [Strang(s.floors, s.split, [dict(c) for c in s.cfg]) for s in straenge], dict(meta)


def _pdf() -> bytes:
    cache = ss.setdefault("pdf_cache", {})
    if jetzt not in cache:
        cache.clear()
        cache[jetzt] = pdf_bericht(_inp, _str, _meta, compute_all(_inp, _str))
    return cache[jetzt]


kopf_pdf.download_button("PDF", _pdf, file_name=f"Bosch_Flow_{name}.pdf", mime="application/pdf", type="primary",
                         width="stretch", icon=":material/picture_as_pdf:", help="Planung als PDF-Bericht exportieren")
with kopf_menue.popover("", icon=":material/more_horiz:", width="stretch", help="Speichern, Laden, Excel, Zurücksetzen"):
    st.download_button("Projekt speichern (.json)", dumps(inp, straenge, meta), file_name=f"{name}.json",
                       mime="application/json", width="stretch", icon=":material/save:")
    datei = st.file_uploader("Projekt laden (.json)", type=["json"], key="upload")
    if datei is not None and ss.get("geladen_id") != datei.file_id:
        ss.geladen_id = datei.file_id
        if laden(datei.getvalue(), f"Projekt „{datei.name}“ geladen."):
            st.rerun()
    if st.button("Zwischenspeichern", icon=":material/backup:", width="stretch",
                 help="Sichert sofort im Browser (automatisch passiert das bei jeder Eingabe)."):
        ss.zwischen = datetime.now().strftime("%H:%M:%S")
        st.toast(f"Zwischenstand im Browser gesichert ({ss.zwischen}).", icon="💾")
    st.download_button("Excel-Export", RP.excel_bytes(inp, meta, results, straenge), file_name=f"Bosch_Flow_{name}.xlsx",
                       width="stretch", icon=":material/table_view:",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.divider()
    if st.button("Alles zurücksetzen", icon=":material/restart_alt:", width="stretch"):
        neues_projekt()
        ss.meldung = ("success", "Alle Eingaben zurückgesetzt.")
        st.rerun()


# ====================================================================== Bausteine
def schema(szene, key: str, max_hoehe: int | None = None, breite_px: int = 1000, leiste: bool = False) -> None:
    cfg = {"responsive": True, "displaylogo": False, "displayModeBar": "hover" if leiste else False,
           "modeBarButtonsToRemove": ["zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d",
                                      "autoScale2d", "resetScale2d"],
           "toImageButtonOptions": {"format": "png", "scale": 2, "filename": key}}
    fig = als_plotly(szene, max_hoehe=max_hoehe, breite_px=breite_px)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch", config=cfg, key=key, theme=None)


def status_style(df: pd.DataFrame):
    farben = {"OK": f"color:{F['gruen']};font-weight:700", "grenzwertig": "color:#b26a00;font-weight:700",
              "zu schnell": f"color:{F['rot']};font-weight:700"}
    return df.style.map(lambda v: farben.get(v, ""), subset=["Status"])


NUMFMT = {"GZ": st.column_config.NumberColumn(format="%.1f"),
          "V̇ ges. [m³/h]": st.column_config.NumberColumn(format="%.2f"),
          "v [m/s]": st.column_config.NumberColumn(format="%.2f"),
          "Δp [Pa/m]": st.column_config.NumberColumn(format="%.0f")}


def kachel(key: str, titel: str, icon: str | None = None, klick=None, mehr: str = "Details"):
    """Kachel-Container; mit ``klick`` ist die ganze Kachel ein Knopf, der den Detail-Dialog öffnet."""
    c = st.container(key=("kachelklick_" if klick else "kachel_") + key)
    ic = f'<div class="k-icon"><img src="{_svg(icon)}"></div>' if icon else ""
    c.markdown(f'<div class="k-kopf"><span class="k-titel">{titel}</span>'
               + (f'<span class="k-mehr">{mehr} →</span>' if klick else "") + f'{ic}</div>', unsafe_allow_html=True)
    if klick:
        if c.button(titel, key=f"klick_{key}", help=f"{titel}: {mehr}"):
            klick()
    return c


def ausl_farbe(q: float) -> str:
    return next((f for g, f, _ in STUFEN if q <= g), STUFEN[-1][1])


# ====================================================================== Detail-Dialoge
def abschnitt_karten(T: dict) -> None:
    html = "".join(
        f'<div class="abschnitt{" krit" if a["kritisch"] else ""}"><div><span class="num">{a["strang"]}</span>'
        f'<b>Abschnitt {a["strang"]}</b></div><div style="font-size:13px"><b>{a["load"]} WE</b> · {fmt(a["V"], 2)} m³/h'
        f'</div><div style="font-size:13px;color:{F["akzent"]};font-weight:700">{a["dn"]} · {fmt(a["v"], 2)} m/s</div>'
        + ('<div style="margin-top:4px;font-size:10.5px;font-weight:700;color:#b26a00">◆ maßgeblich</div>'
           if a["kritisch"] else "") + "</div>" for a in T["abschnitte"])
    st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 12px">{html}</div>',
                unsafe_allow_html=True)


def schliessen() -> None:
    if st.button("Fertig", type="primary", icon=":material/check:"):
        st.rerun()


@st.dialog("Rohrnetz", width="large")
def dialog_rohrnetz() -> None:
    res = compute_all(ss.inp, ss.straenge)
    m = ss.meta
    nn = len(res)
    optionen = ["Strang", "Alle Stränge", "Hauptstrang"] if nn > 1 else ["Strang"]
    a, b = st.columns([2, 2], vertical_alignment="center")
    ansicht = a.segmented_control("Ansicht", optionen, default="Strang", key="rn_ansicht",
                                  label_visibility="collapsed") or "Strang"
    if ansicht == "Strang":
        if nn > 1:
            w = b.segmented_control("Strang", [f"S{i + 1}" for i in range(nn)], default=f"S{m['activeStrang'] + 1}",
                                    key=f"rn_strang_{m['activeStrang']}", label_visibility="collapsed")
            if w and int(w[1:]) - 1 != m["activeStrang"]:
                m["activeStrang"] = int(w[1:]) - 1
                st.rerun(scope="fragment")
        r = res[m["activeStrang"]]
        schema(schemata.netzschema(r, DUNKEL), "d_schema", max_hoehe=1100, breite_px=1150)
        st.caption(RP.schema_note(r, nn).replace("**", ""))
        mo = st.segmented_control("Tabelle", ["Etagenstrang", "Steigstrang"], default="Etagenstrang", key="d_tab",
                                  label_visibility="collapsed") or "Etagenstrang"
        st.dataframe(status_style(RP.strang_table(r, "H" if mo == "Etagenstrang" else "V")), hide_index=True,
                     width="stretch", column_config=NUMFMT)
    elif ansicht == "Alle Stränge":
        for i in range(0, nn, 2):
            spalten = st.columns(2)
            for j, r in enumerate(res[i:i + 2]):
                with spalten[j]:
                    st.markdown(f'<div class="strangkopf">Strang {i + j + 1} <span class="badge2">{r["totalWE"]} WE'
                                f'</span><span class="badge2">{r["floors"]} Etagen</span><span class="badge2">Strangfuß '
                                f'{r["vRows"][0]["dim"]}</span></div>', unsafe_allow_html=True)
                    schema(schemata.netzschema(r, DUNKEL), f"d_all_{i + j}", max_hoehe=700, breite_px=560)
    else:
        G_ = gesamt_anlage(ss.inp, res)
        if G_["getrennt"]:
            st.warning("Getrennte Ausführung: kein gemeinsamer Hauptstrang – die Topologie dient nur der Übersicht.")
        a, b = st.columns([3, 1], vertical_alignment="bottom")
        pos = a.slider("Position Wärmezentrale", 0, 100, int(m["topoPos"]), 5, key=f"topo_d_{ss.rev}", format="%d %%",
                       help="0 % = links, 50 % = mittig, 100 % = rechts. Wird mit dem Projekt gespeichert.")
        m["topoPos"] = float(pos)
        b.markdown(f"**{topo_label(pos)}**")
        schema(schemata.topologie_szene(res, pos, True, DUNKEL), "d_topo", breite_px=1150, leiste=True)
        T = topologie(res, pos)
        abschnitt_karten(T)
        st.info(RP.hauptstrang_erklaerung(res, T), icon=":material/school:")
    schliessen()


@st.dialog("Volumenstrom & Gleichzeitigkeit", width="large")
def dialog_volumenstrom() -> None:
    res = compute_all(ss.inp, ss.straenge)
    G_ = gesamt_anlage(ss.inp, res)
    ctx = {"P": res[0]["P"], "totalWE": G_["we"]}
    st.caption(f"Bezogen auf {G_['we']} Wohnungen" + (" (Summe getrennter Anlagen; je Strang gilt der eigene Verlauf)"
                                                       if G_["getrennt"] else " – kumuliert über alle Stränge"))
    a, b = st.columns(2)
    a.plotly_chart(plots.chart_volumenstrom(ctx, DUNKEL), width="stretch", key="d_v", theme=None)
    b.plotly_chart(plots.chart_gleichzeitigkeit(ctx, DUNKEL), width="stretch", key="d_g", theme=None)
    st.caption("WW-Anteil je Station auf 1,3 m³/h gedeckelt – realistische, nicht überzogene Dimensionen. TU Dresden "
               "liegt bei vielen Wohnungen unter DIN 4708.")
    schliessen()


@st.dialog("Wärmezentrale", width="large")
def dialog_zentrale() -> None:
    res = compute_all(ss.inp, ss.straenge)
    r = res[ss.meta["activeStrang"]]
    a_ = r["anlage"]
    schema(schemata.anlagenschema(r, project_headline(r, ss.inp), DUNKEL), "d_anlage", breite_px=1150)
    st.dataframe(pd.DataFrame(RP.anlage_rows(a_), columns=["Größe", "Wert", "Einheit", "Herleitung"]).style.apply(
        lambda z: [f"font-weight:700;color:{F['akzent']}" if z["Größe"].startswith("→") else ""] * len(z), axis=1),
        hide_index=True, width="stretch",
        column_config={"Herleitung": st.column_config.TextColumn(width="large")})
    st.caption(RP.anlage_note(a_).replace("**", ""))
    if a_["zuheizerOn"]:
        st.markdown("##### DLE-Auslegungshilfe")
        tbl = dle_table(a_)
        st.dataframe(pd.DataFrame(RP.dle_rows_text(tbl), columns=["Netztemp. an Station", "Stufe 48 °C",
                                                                  "Stufe 53 °C", "Stufe 60 °C"]),
                     hide_index=True, width="stretch")
        zst, ztext = RP.dle_fazit(a_)
        {"none": st.info, "ok": st.success, "over": st.error}[zst](ztext)
        st.caption("Stromseitige Gleichzeitigkeit (DIN 18015-1): eigene Kachel „Strom“ auf dem Dashboard.")
    with st.expander("Systemprinzip aus dem Katalog", icon=":material/image:"):
        st.image(str(KA.BILDER / "systemprinzip.jpg"), width="stretch")
    schliessen()


@st.dialog("3D-Gebäudemodell", width="large")
def dialog_3d() -> None:
    a, b = st.columns(2)
    farbe = a.segmented_control("Färbung", ["Geschwindigkeit", "Nennweite"], default="Geschwindigkeit",
                                key="m3d_farbe", label_visibility="collapsed") or "Geschwindigkeit"
    res = compute_all(ss.inp, ss.straenge)
    nur = None
    if len(res) > 1:
        umfang = b.segmented_control("Umfang", ["Ganzes Projekt", "Aktueller Strang"], default="Ganzes Projekt",
                                     key="m3d_umfang", label_visibility="collapsed") or "Ganzes Projekt"
        nur = ss.meta["activeStrang"] if umfang == "Aktueller Strang" else None
    h = HY.berechne(ss.inp, ss.straenge, ss.meta)
    fig = modell(res, ss.meta["topoPos"], "dn" if farbe == "Nennweite" else "v", DUNKEL, nur, 720,
                 ss.inp.waermequelle, f"Betriebspunkt V̇ {fmt(h['V'], 2)} m³/h · {fmt(h['bar'], 2)} bar (≈ {fmt(h['H'], 1)} m)")
    st.plotly_chart(fig, width="stretch", key="m3d_voll", theme=None,
                    config={"displaylogo": False, "toImageButtonOptions": {"format": "png", "scale": 2}})
    st.caption("Ziehen = drehen · Mausrad = zoomen · Maus über ein Rohr = Werte · Legende anklicken = Stufe ein/aus")
    schliessen()


@st.dialog("Stromseitige Gleichzeitigkeit · DIN 18015-1", width="large")
def dialog_strom() -> None:
    res = compute_all(ss.inp, ss.straenge)
    a_ = res[ss.meta["activeStrang"]]["anlage"]
    d = din18015(a_["weForZentrale"])
    bezug = ("Wohneinheiten dieses Strangs (getrennte Zentrale)" if a_["zentralMode"] == "getrennt" else
             "Wohneinheiten aller Stränge (gemeinsame Zentrale)" if a_["nStraenge"] > 1 else
             "Wohneinheiten am Netzanschluss")
    if a_["zuheizerOn"]:
        st.caption(RP.DIN18015_TEXT)
    else:
        st.caption("Ohne elektrischen Zuheizer (DLE) gilt die rote Kurve (OHNE elektr. WW-Bereitung). Mit Flow 7000 HPS "
                   "und DLE wird die blaue Kurve (MIT) maßgeblich.")
    st.plotly_chart(plots.chart_din18015(d["nWE"], DUNKEL), width="stretch", key="d_strom", theme=None)
    a, b = st.columns(2)
    a.metric(f"MIT elektr. WW{' (maßgeblich)' if a_['zuheizerOn'] else ''} · {d['nWE']} {bezug}", f"≈ {fmt(d['mit'])} kW",
             help="Richtwert Leistung am Netzanschluss" + (" – Kurve ab 30 WE im Plateau" if d["nWE"] >= 30 else ""))
    b.metric(f"OHNE elektr. WW{' (maßgeblich)' if not a_['zuheizerOn'] else ' (Referenz)'}", f"≈ {fmt(d['ohne'])} kW")
    st.caption(RP.PMAX_HINWEIS)
    if a_["zuheizerOn"]:
        st.warning(RP.DLE_ELEKTRO)
    schliessen()


@st.dialog("Druckverlust, Pumpe & Rohrmengen", width="large")
def dialog_hydraulik() -> None:
    h = HY.berechne(ss.inp, ss.straenge, ss.meta)
    st.caption("Erweiterung über den Rechenkern V54 hinaus: vereinfachtes Vorplanungsmodell mit "
               "Standardlängen (anpassbar unter Auslegung → Experteneinstellungen). Ersetzt keine Rohrnetzberechnung.")
    a, b, c, d = st.columns(4)
    a.metric("Förderhöhe Netzpumpe", f"{fmt(h['bar'], 2)} bar", help="Erforderlich am ungünstigsten Fließweg")
    b.metric("Förderhöhe", f"{fmt(h['H'], 1)} m", help="Wassersäule")
    c.metric("Volumenstrom" + (f" je Anlage ({h['pumpen']}×)" if h["pumpen"] > 1 else ""), f"{fmt(h['V'], 2)} m³/h")
    d.metric("Rohrleitung VL + RL", f"{fmt(h['laenge'])} m", help=f"Wasserinhalt ≈ {fmt(h['inhalt'])} l")
    teile = [("Rohrnetz VL + RL", h["dpRohr"], F["akzent"]), ("Einzelwiderstände", h["dpEinzel"], "#80b918"),
             (f"Station {h['station']}", h["dpStation"], F["gelb"]), ("Wärmezentrale", h["dpZentrale"], "#9aa5b1")]
    fig = go.Figure([go.Bar(y=["Förderhöhe"], x=[w / 1e5], name=t, orientation="h", marker=dict(color=f),
                            text=f"{t}<br>{fmt(w / 1e5, 2)} bar" if w / h["dpGes"] > 0.12 else "",
                            textposition="inside", insidetextanchor="middle",
                            hovertemplate=f"{t}: {fmt(w / 1e5, 3)} bar<extra></extra>") for t, w, f in teile])
    fig.update_layout(barmode="stack", height=170, margin=dict(l=10, r=20, t=40, b=30), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", separators=",.",
                      font=dict(color=F["text"], size=12))
    fig.update_xaxes(title="bar", gridcolor=F["linie"], range=[0, h["bar"] * 1.04])
    fig.update_yaxes(visible=False)
    st.plotly_chart(fig, width="stretch", key="hy_bar", theme=None, config={"displayModeBar": False})
    st.info(f"**Betriebspunkt der Netzpumpe (bauseits):** V̇ = {fmt(h['V'], 2)} m³/h bei {fmt(h['bar'], 2)} bar "
            f"(≈ {fmt(h['H'], 1)} m). Davon Station {h['station']} {fmt(h['dpStation'] / 1e5, 2)} bar bei "
            f"{h['stationVL']} laut Katalog.", icon=":material/water_pump:")
    if h["vierLeiter"]:
        st.info("4-Leiter: gerechnet ist das Trinkwasser-Netz. Das Heiznetz ist eine eigene Pumpengruppe und hier nicht "
                "enthalten.", icon=":material/info:")
    reiter = st.tabs(["Ungünstigster Fließweg", "Rohrmengen"])
    with reiter[0]:
        st.caption(f"Strang {h['kritisch'] + 1} · Weg Zentrale → letzte Station {fmt(h['wegLaenge'] / 2)} m (einfach). "
                   "Druckverlust je Abschnitt im gewählten Rohr bei realer Geschwindigkeit.")
        st.dataframe(pd.DataFrame([{"Abschnitt": z["name"], "WE": z["we"], "Rohr": z["rohr"], "Dimension": z["dim"],
                                    "V̇ [m³/h]": z["V"], "v [m/s]": z["v"], "L [m]": z["L"], "R [Pa/m]": z["R"],
                                    "Δp [mbar]": z["dp"] / 100} for z in h["pfad"]]), hide_index=True,
                     width="stretch", column_config={
                         "V̇ [m³/h]": st.column_config.NumberColumn(format="%.2f"),
                         "v [m/s]": st.column_config.NumberColumn(format="%.2f"),
                         "L [m]": st.column_config.NumberColumn(format="%.1f"),
                         "R [Pa/m]": st.column_config.NumberColumn(format="%.0f"),
                         "Δp [mbar]": st.column_config.NumberColumn(format="%.1f")})
        st.caption(f"Summe Rohrnetz einfach {fmt(h['dpRohr'] / 200, 1)} mbar · VL + RL {fmt(h['dpRohr'] / 100, 1)} mbar · "
                   f"+ {fmt(h['geo']['zuschlag'])} % Einzelwiderstände · + Station {fmt(h['dpStation'] / 100)} mbar "
                   f"({h['stationVL']}) · + Zentrale {fmt(h['dpZentrale'] / 100)} mbar = {fmt(h['dpGes'] / 100)} mbar.")
    with reiter[1]:
        rm = h["rohrmengen"]
        fig2 = go.Figure(go.Bar(x=[m["dim"] for m in rm], y=[m["L"] for m in rm], marker=dict(color=F["akzent"],
                                cornerradius=6), text=[f"{fmt(m['L'])} m" for m in rm], textposition="outside",
                                cliponaxis=False))
        fig2.update_layout(height=280, margin=dict(l=64, r=10, t=24, b=30), paper_bgcolor="rgba(0,0,0,0)",
                           plot_bgcolor="rgba(0,0,0,0)", font=dict(color=F["text"]), separators=",.")
        fig2.update_yaxes(title="Länge VL + RL [m]", gridcolor=F["linie"], automargin=False)
        st.plotly_chart(fig2, width="stretch", key="hy_mengen", theme=None, config={"displayModeBar": False})
        st.dataframe(pd.DataFrame([{"Dimension": m["dim"], "Rohr": m["rohr"], "dᵢ [mm]": m["di"], "Länge VL + RL [m]":
                                    m["L"], "Wasserinhalt [l]": m["inhalt"], "Einsatz": m["arten"]} for m in rm]),
                     hide_index=True, width="stretch", column_config={
                         "dᵢ [mm]": st.column_config.NumberColumn(format="%.1f"),
                         "Länge VL + RL [m]": st.column_config.NumberColumn(format="%.0f"),
                         "Wasserinhalt [l]": st.column_config.NumberColumn(format="%.0f")})
        st.caption(f"Gesamt {fmt(h['laenge'])} m Rohr (Vor- und Rücklauf), Wasserinhalt ≈ {fmt(h['inhalt'])} l "
                   f"({MATNAME[ss.inp.mat]}). Ohne Dämmung, Formstücke und Verschnitt.")
    schliessen()


@st.dialog("Prüfungen", width="medium")
def dialog_pruefungen() -> None:
    for stufe, titel, text in PRUEF:
        st.markdown(f'<div class="pruef"><span class="dot {stufe}"></span><div><b>{titel}</b><small>{text}</small>'
                    f'</div></div>', unsafe_allow_html=True)
    infos = [t for s_, t in GERAET["hinweise"] if s_ == "info"]
    if infos:
        st.markdown("##### Katalog-Hinweise")
        st.markdown("\n".join(f"- {t}" for t in infos))
    schliessen()


def variante_uebernehmen(aenderung: dict, titel: str) -> None:
    ss.va_vorher = (ss.inp, titel)
    ss.inp = VA.anwenden(ss.inp, aenderung)
    ss.rev += 1
    ss.meldung = ("success", f"Variante übernommen: {titel}")


@st.dialog("Variantenvergleich", width="large")
def dialog_varianten() -> None:
    V = VA.vergleich(ss.inp, ss.straenge, ss.meta["topoPos"])
    basis, zeilen, best = V["basis"], V["zeilen"], V["empfehlung"]
    farbe = []
    for z in zeilen:
        v = z["variante"]
        farbe.append(F["rot"] if z["k"]["zuSchnell"] else F["gelb"] if z["k"]["ueber"] else
                     F["akzent"] if v.gruppe == "Planung" else F["gruen"] if z is best else
                     "#80b918" if v.empfehlbar and z["wert"] < 1 else "#9aa5b1")
    werte = [z["wert"] * 100 for z in zeilen]
    fig = go.Figure(go.Bar(x=werte, y=[z["variante"].titel + ("" if z["variante"].empfehlbar else " ⓘ") for z in zeilen],
                           orientation="h", marker=dict(color=farbe, cornerradius=6),
                           text=[f"{fmt(w)} %" for w in werte], textposition="outside", cliponaxis=False,
                           hovertext=[("<br>".join(VA.begruendung(z, basis)) or "keine Änderung")
                                      + (f"<br><i>{z['variante'].hinweis}</i>" if z["variante"].hinweis else "")
                                      for z in zeilen], hoverinfo="text"))
    fig.add_vline(x=100, line=dict(color=F["leise"], dash="dot", width=1))
    fig.update_layout(height=60 + 32 * len(zeilen), margin=dict(l=10, r=40, t=10, b=30), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color=F["text"], size=12), showlegend=False,
                      separators=",.", bargap=0.35)
    fig.update_xaxes(title="Bewertung in % der aktuellen Planung (kleiner = besser)", gridcolor=F["linie"],
                     range=[0, max(werte) * 1.15])
    fig.update_yaxes(autorange="reversed", automargin=True)
    st.plotly_chart(fig, width="stretch", key="va_chart", theme=None, config={"displayModeBar": False})
    andere = [z for z in zeilen if z["variante"].gruppe != "Planung"]
    a, b = st.columns([3, 1.3], vertical_alignment="bottom")
    vorgabe = next((i for i, z in enumerate(andere) if z is best), 0)
    wahl = a.selectbox("Variante", range(len(andere)), vorgabe, key=f"va_wahl_{ss.rev}",
                       format_func=lambda i: f"{andere[i]['variante'].titel} · {fmt(andere[i]['wert'] * 100)} %")
    if b.button("Übernehmen", type="primary", width="stretch", icon=":material/swap_horiz:"):
        z = andere[wahl]["variante"]
        variante_uebernehmen(z.aenderung, z.titel)
        st.rerun()
    st.caption("Bewertung: 50 % Rohrnetz (Summe der Nennweiten), 25 % Erzeugerleistung, 25 % Puffervolumen; Abschnitte "
               "über v_max werden bestraft. Preise, Energieeffizienz und Montage fließen nicht ein. ⓘ = nur gezeigt, nicht "
               "automatisch empfohlen (Rechenverfahren, Leitersystem, höherer Vorlauf).")


@st.dialog("Wohnungsstation", width="large")
def dialog_geraet() -> None:
    g = KA.geraet(ss.inp, ss.meta)
    a, b = st.columns([1, 1.6], vertical_alignment="center")
    a.image(str(g["bild"]), width="stretch")
    with b:
        st.markdown(f'<div class="g-typ">{g["typ"]}</div><div class="g-sub">Bestell-Nr. {g["bestellnr"]} · UVP '
                    f'{fmt(g["uvp"])} € · {KA.MONTAGE[g["montage"]]}</div>', unsafe_allow_html=True)
        zeilen = [("Primär-Volumenstrom", f"{fmt(g['vPrim'])} l/h"), ("Primär-Druckverlust", f"{fmt(g['dpPrim'])} mbar"),
                  ("bei Vorlauf", g["vlPunkt"]), ("Zapfmenge max.", f"{g['zapf']} l/min"),
                  ("Primär-VL laut Katalog", f"{g['vlMin']}–{g['vlMax']} °C"), ("H × B × T", g["abmessungen"]),
                  ("Heizleistung max.", f"{g['heizKW']} kW")]
        st.markdown("".join(f'<div class="g-zeile"><span>{x}</span><b>{y}</b></div>' for x, y in zeilen),
                    unsafe_allow_html=True)
    for stufe, text in g["hinweise"]:
        (st.warning if stufe == "warn" else st.caption)(text)
    st.caption(KA.KATALOG)
    schliessen()


@st.dialog("Stückliste", width="large")
def dialog_stueckliste() -> None:
    zeilen = KA.projekt_stueckliste(ss.inp, ss.straenge, ss.meta)

    def eur(v):
        return "auf Anfrage" if v is None else f"{fmt(v, 2)} €"
    df = pd.DataFrame([{"Position": z["pos"], "Bezeichnung": z["text"], "Bestell-Nr.": z["nr"], "Menge": str(z["menge"]),
                        "UVP": "–" if z["nr"] == "bauseits" else eur(z["uvp"]),
                        "Summe": "bauseits" if z["nr"] == "bauseits" else eur(z["summe"])} for z in zeilen])
    df.loc[len(df)] = ["Summe", "Katalogpositionen (UVP, ohne MwSt.)", "", "", "",
                       eur(sum(z["summe"] or 0 for z in zeilen))]
    st.dataframe(df.style.apply(lambda r: ["font-weight:700" if r["Position"] == "Summe" else ""] * len(r), axis=1),
                 hide_index=True, width="stretch", column_config={"Bezeichnung": st.column_config.TextColumn(width="large")})
    st.caption(KA.PREISHINWEIS + " Rohrleitungen, Erzeuger, Puffer, Netzpumpe und Montage nicht enthalten.")
    schliessen()


if ss.pop("oeffne", None) == "pruef":
    dialog_pruefungen()


# ====================================================================== Dashboard
def kpi_werte() -> dict:
    return {"V": HL["Vtot"], "kessel": float(G["kesselQ"] if n > 1 else A["kesselQ"]),
            "puffer": float(G["pufferVol"] if n > 1 else A["pufferVol"])}


kpi = kpi_werte()
if ss.get("kpi_stand") != jetzt:
    ss.kpi_alt, ss.kpi_neu, ss.kpi_stand = ss.get("kpi_neu"), kpi, jetzt
alt = ss.get("kpi_alt") or {}


def delta(key: str, d: int = 0) -> str:
    if key not in alt or abs(kpi[key] - alt[key]) < 10 ** -max(d, 0) / 2:
        return ""
    x = kpi[key] - alt[key]
    return f'<span class="delta {"up" if x > 0 else "down"}">{"▲" if x > 0 else "▼"} {fmt(abs(x), d)}</span>'


with haupt:
    # ---------------------------------------------------------------- Reihe 1: Kennzahlen
    pp = puffer_produkt(kpi["puffer"])
    kach = st.columns(4, gap="medium")
    with kach[0]:
        with kachel("v", "Volumenstrom", "pumpe", dialog_volumenstrom, "Diagramme"):
            st.markdown(f'<div class="k-wert">{fmt(HL["Vtot"], 2)}<span>m³/h</span></div><div class="k-unter">'
                        f'{"Projekt" if HL["projektweit"] else "Strangfuß"} · {HL["we"]} WE {delta("V", 2)}</div>',
                        unsafe_allow_html=True)
    with kach[1]:
        with kachel("dn", "Anschluss", "station", dialog_rohrnetz, "Rohrnetz"):
            st.markdown(f'<div class="k-wert">{HL["dim"]}</div><div class="k-unter">v = {fmt(HL["v"], 2)} m/s · '
                        f'{MATNAME[inp.mat].split(" ")[0]}</div>', unsafe_allow_html=True)
    with kach[2]:
        with kachel("kessel", "Erzeuger", "erzeuger", dialog_zentrale, "Wärmezentrale"):
            st.markdown(f'<div class="k-wert">{fmt(kpi["kessel"])}<span>kW</span></div><div class="k-unter">'
                        f'{WAERMEQUELLEN[inp.waermequelle]["name"].split(" (")[0]} {delta("kessel")}</div>',
                        unsafe_allow_html=True)
    with kach[3]:
        with kachel("puffer", "Pufferspeicher", "puffer", dialog_zentrale, "Wärmezentrale"):
            st.markdown(f'<div class="k-wert">{fmt(kpi["puffer"])}<span>l</span></div><div class="k-unter">'
                        f'Auswahl {pp["text"]} {delta("puffer")}</div>', unsafe_allow_html=True)

    # ---------------------------------------------------------------- Reihe 2: 3D | Prüfungen + Empfehlung
    links, rechts = st.columns([1.85, 1], gap="medium")
    with links:
        with kachel("3d", "Gebäude · Rohrnetz live"):
            optionen = ["3D", "2D Strang"] + (["2D Hauptstrang"] if n > 1 else [])
            if ss.get("bildansicht") not in optionen:
                ss.bildansicht = "3D"
            a, b = st.columns([2.2, 1.6], vertical_alignment="center")
            ansicht = a.segmented_control("Ansicht", optionen, key="bildansicht", label_visibility="collapsed") or "3D"
            if ansicht == "2D Strang" and n > 1:
                w = b.segmented_control("Strang", [f"S{i + 1}" for i in range(n)], default=f"S{meta['activeStrang'] + 1}",
                                        key=f"bild_strang_{meta['activeStrang']}_{n}", label_visibility="collapsed")
                if w and int(w[1:]) - 1 != meta["activeStrang"]:
                    meta["activeStrang"] = int(w[1:]) - 1
                    st.rerun()
            if ansicht == "3D":
                fig3d = modell(results, meta["topoPos"], "v", DUNKEL, None, 470, inp.waermequelle,
                               f"Betriebspunkt V̇ {fmt(HYD['V'], 2)} m³/h · {fmt(HYD['bar'], 2)} bar (≈ {fmt(HYD['H'], 1)} m)")
                fig3d.update_layout(legend=dict(title=None, font=dict(size=10)))
                st.plotly_chart(fig3d, width="stretch", key="m3d", theme=None,
                                config={"displayModeBar": False, "displaylogo": False})
                hilfe = "Ziehen = drehen · Mausrad = zoomen · Maus über ein Rohr = Werte"
            elif ansicht == "2D Strang":
                schema(schemata.netzschema(R, DUNKEL), "schema2d", max_hoehe=600, breite_px=640 if ss.panel else 900)
                hilfe = (f"Strang {meta['activeStrang'] + 1}: Maus über Stationen und DN-Marken = Werte · "
                         "grün = OK, orange = grenzwertig, rot = zu schnell")
            else:
                schema(schemata.topologie_szene(results, meta["topoPos"], True, DUNKEL), "topo2d",
                       breite_px=640 if ss.panel else 900)
                hilfe = f"Hauptstrang im Keller · Wärmezentrale {topo_label(meta['topoPos'])}"
            if n > 1 and not G["getrennt"] and ansicht != "2D Strang":
                zentrale_regler("topo_3d")
            a, b = st.columns([3, 1], vertical_alignment="center")
            a.caption(hilfe)
            if b.button("Vollbild", icon=":material/open_in_full:", key="m3d_vb", width="stretch"):
                dialog_3d() if ansicht == "3D" else dialog_rohrnetz()
    with rechts:
        with kachel("pruef", "Prüfungen", None, dialog_pruefungen, "Alle"):
            gesamt = ("Alles im grünen Bereich" if not (n_err or n_warn) else
                      f"{n_err} Fehler · {n_warn} Hinweise" if n_err else f"{n_warn} Hinweis{'e' if n_warn > 1 else ''}")
            st.markdown(f'<div class="gesamt" style="color:{farbe_status}">{gesamt}</div>' + "".join(
                f'<div class="pruef"><span class="dot {s_}"></span><div><b>{t}</b><small>{x}</small></div></div>'
                for s_, t, x in PRUEF[:4]), unsafe_allow_html=True)
        V = VA.vergleich(inp, straenge, meta["topoPos"])
        best = V["empfehlung"]
        with kachel("varianten", "Empfehlung", None, dialog_varianten, "Vergleich"):
            if best["variante"].gruppe == "Planung":
                st.markdown(f'<span class="empf-tag">Optimal</span><div class="empf-titel">Aktuelle Planung</div>'
                            f'<div class="empf-pkt">Keine der {len(V["zeilen"]) - 1} geprüften Varianten ist besser.</div>',
                            unsafe_allow_html=True)
            else:
                pkt = "".join(f'<div class="empf-pkt">• {x}</div>' for x in VA.begruendung(best, V["basis"])[:3])
                st.markdown(f'<span class="empf-tag">Besser · {fmt(best["wert"] * 100)} %</span><div class="empf-titel">'
                            f'{best["variante"].titel}</div>{pkt}', unsafe_allow_html=True)

    # ---------------------------------------------------------------- Reihe 3: Rohrnetz | Pumpe | Strom
    c1, c4, c5 = st.columns([1.3, 1, 1], gap="medium")
    with c1:
        with kachel("rohrnetz", "Rohrnetz", "station", dialog_rohrnetz, "Schemata & Tabellen"):
            vmax = P["vmax"]
            kopfzeile = (f"Hauptstrang zur Zentrale ({topo_label(meta['topoPos'])}): <b>{topologie(results, meta['topoPos'])['gesamt']['dim']}</b>"
                         if n > 1 and not G["getrennt"] else
                         f"{n} getrennte Anlagen" if G["getrennt"] else f"{R['floors']} Etagen · {R['totalWE']} Wohnungen")
            zeilen = []
            for i, r in enumerate(results[:6]):
                fuss = r["vRows"][0]
                q = fuss["v"] / vmax
                zeilen.append(f'<div class="rn"><span class="s">S{i + 1}</span><span class="bar"><i style="width:'
                              f'{min(100, q * 100 / 1.2):.0f}%;background:{ausl_farbe(q)}"></i></span><span class="dn">'
                              f'{fuss["dim"]}</span><span class="v">{r["totalWE"]} WE · {fmt(fuss["v"], 2)}</span></div>')
            mehr = f'<div class="rn-kopf">+ {n - 6} weitere Stränge</div>' if n > 6 else ""
            st.markdown(f'<div class="rn-kopf">{kopfzeile}</div>{"".join(zeilen)}{mehr}'
                        f'<div class="rn-kopf" style="margin-top:8px">Balken = Strangfuß v / v_max</div>',
                        unsafe_allow_html=True)
    with c4:
        with kachel("pumpe", "Netzpumpe · Betriebspunkt", "pumpe", dialog_hydraulik, "Druckverlust"):
            st.markdown(f'<div class="k-wert">{fmt(HYD["bar"], 2)}<span>bar</span></div><div class="k-unter">'
                        f'Förderhöhe ≈ {fmt(HYD["H"], 1)} m<br>bei {fmt(HYD["V"], 2)} m³/h · bauseits</div>',
                        unsafe_allow_html=True)
    with c5:
        dstrom = din18015(A["weForZentrale"])
        mit_dle = A["zuheizerOn"]
        with kachel("strom", "Strom · Gleichzeitigkeit DIN 18015", None, dialog_strom, "Kurve"):
            st.markdown(f'<div class="k-wert">≈ {fmt(dstrom["mit"] if mit_dle else dstrom["ohne"])}<span>kW</span></div>'
                        f'<div class="k-unter">am Netzanschluss · {dstrom["nWE"]} WE · '
                        f'{"MIT elektr. WW (DLE)" if mit_dle else "ohne elektr. WW"}<br>'
                        f'{"ohne DLE wären es" if mit_dle else "mit DLE wären es"} ≈ '
                        f'{fmt(dstrom["ohne"] if mit_dle else dstrom["mit"])} kW</div>', unsafe_allow_html=True)

    # ---------------------------------------------------------------- Reihe 4: Gerät | Stückliste | Rohrmengen
    c2, c3, c6 = st.columns([1.3, 1, 1], gap="medium")
    with c6:
        with kachel("rohr", "Rohrmengen", None, dialog_hydraulik, "je Nennweite"):
            dn_max = max(HYD["rohrmengen"], key=lambda m: m["L"])
            st.markdown(f'<div class="k-wert">{fmt(HYD["laenge"])}<span>m</span></div><div class="k-unter">'
                        f'Vor- und Rücklauf · {len(HYD["rohrmengen"])} Nennweiten<br>meist {dn_max["dim"]} '
                        f'({fmt(dn_max["L"])} m) · Inhalt ≈ {fmt(HYD["inhalt"])} l</div>', unsafe_allow_html=True)
    with c2:
        with kachel("geraet", "Wohnungsstation", None, dialog_geraet, "Gerätedaten"):
            stg = STATIONS[inp.station]["stages"][min(int(inp.wwstage), len(STATIONS[inp.station]["stages"]) - 1)]
            bild = base64.b64encode(GERAET["bild"].read_bytes()).decode()
            st.markdown(f'<div style="display:flex;gap:16px;align-items:center;margin-top:14px">'
                        f'<img src="data:image/png;base64,{bild}" style="height:104px;width:auto;object-fit:contain">'
                        f'<div><div class="g-typ">{GERAET["typ"]}</div><div class="g-sub">{G["we"]} Stationen · '
                        f'{stg["kw"]} kW · {stg["lmin"]} l/min<br>{KA.MONTAGE[GERAET["montage"]].split(" (")[0]} · '
                        f'{GERAET["heizkreis"]}</div></div></div>', unsafe_allow_html=True)
    with c3:
        summe = sum(z["summe"] or 0 for z in STUECK)
        pumpe = next((z for z in STUECK if z["pos"] == "Netzpumpe"), None)
        with kachel("stueck", "Stückliste (UVP)", None, dialog_stueckliste, "Positionen"):
            st.markdown(f'<div class="k-wert">{fmt(summe / 1000, 1)}<span>T€</span></div><div class="k-unter">'
                        f'{len(STUECK)} Positionen · {STUECK[0]["menge"]} Stationen<br>'
                        f'ohne Rohrleitung und Netzpumpe (bauseits)</div>', unsafe_allow_html=True)

    st.markdown('<div class="fuss">Werkzeug zur Vorplanung nach Bosch-HIU-Methodik – ersetzt keine verbindliche '
                'Rohrnetzberechnung · Entwickelt von Daniel Sommer · HC/SDE3-PSD</div>', unsafe_allow_html=True)

# ====================================================================== Auto-Sicherung + Hell/Dunkel (Browser)
with kopf_thema:
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
