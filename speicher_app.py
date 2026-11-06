"""Speicherauswahl Wärmepumpe – eigenständige Streamlit-App (parallel zum Netzrechner).

Start lokal:   streamlit run speicher_app.py
Server:        deploy/docker-compose.yml, Dienst „speicher“ (siehe deploy/ANLEITUNG.md)

Inhalt und Logik wie in der Netzrechner-App unter ?tool=speicher (bosch_flow/speicher_seite.py).
Optional mit Passwort: Umgebungsvariable SPEICHER_PASSWORT (sonst APP_PASSWORT).
"""
from __future__ import annotations

import hmac
import os

import streamlit as st

st.set_page_config(page_title="Bosch Speicherauswahl", page_icon="💧", layout="wide")

from bosch_flow.speicher_seite import seite  # noqa: E402

try:
    DUNKEL = st.context.theme.type == "dark"
except Exception:  # noqa: BLE001
    DUNKEL = False
try:
    _ua = st.context.headers.get("User-Agent", "") or ""
except Exception:  # noqa: BLE001
    _ua = ""
MOBIL = any(t in _ua for t in ("iPhone", "iPod", "Android", "Mobile"))

F = dict(seite="#0b1016", kachel="#131b24", linie="rgba(255,255,255,.07)", text="#e8eef4", leise="#8fa1b3",
         akzent="#4fa3e0", akzent_bg="rgba(79,163,224,.12)", gruen="#3ecf6e", gelb="#f2c14e", rot="#ff5a6a") if DUNKEL else \
    dict(seite="#f3f5f8", kachel="#ffffff", linie="rgba(16,24,40,.07)", text="#101828", leise="#667085",
         akzent="#005691", akzent_bg="rgba(0,86,145,.08)", gruen="#12b76a", gelb="#f79009", rot="#e5484d")

st.markdown(f"""<style>
.stApp {{background:{F['seite']}}}
header[data-testid="stHeader"] {{background:transparent}}
.block-container {{padding-top:2.4rem; max-width:min(1600px, 98vw)}}
.superband {{position:fixed; top:0; left:0; right:0; height:4px; z-index:999990;
            background:linear-gradient(90deg,#e20015 0%,#b90276 22%,#50237f 44%,#005691 70%,#008ecf 100%)}}
.marke {{font-weight:800; font-size:22px; letter-spacing:.2px; color:#e20015; line-height:1.1}}
.marke span {{color:{F['text']}}}
.marke small {{display:block; font-size:12px; font-weight:500; color:{F['leise']}; letter-spacing:0; margin-top:2px}}
.g-zeile {{display:flex; justify-content:space-between; font-size:13px; padding:4px 0;
          border-bottom:1px solid {F['linie']}; color:{F['text']}}}
.g-zeile span {{color:{F['leise']}}}
</style><div class="superband"></div>""", unsafe_allow_html=True)


def _passwort() -> str | None:
    for name in ("SPEICHER_PASSWORT", "APP_PASSWORT"):
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
        try:
            wert = str(st.secrets[name]).strip()
            if wert:
                return wert
        except Exception:  # noqa: BLE001 – keine Secrets hinterlegt
            pass
    return None


PASSWORT = _passwort()
if PASSWORT and not st.session_state.get("sp_angemeldet"):
    st.markdown('<div class="marke">BOSCH <span>Speicherauswahl</span><small>Wärmepumpe → Speicher → E-Heizer</small></div>',
                unsafe_allow_html=True)
    with st.form("anmelden", border=False):
        eingabe = st.text_input("Passwort", type="password")
        if st.form_submit_button("Anmelden", type="primary", icon=":material/login:"):
            if eingabe and hmac.compare_digest(eingabe, PASSWORT):
                st.session_state.sp_angemeldet = True
                st.rerun()
            st.error("Passwort falsch.")
    st.stop()

seite(F, DUNKEL, MOBIL, eigenstaendig=True)
