"""Browser-Anbindung: Auto-Sicherung im localStorage und Hell/Dunkel-Schalter (wie in der HTML-Version).

Eine kleine Streamlit-Komponente (components v2), die im Browser des Nutzers läuft:
- liest beim Öffnen die letzte Sicherung und gibt sie an Python (``gespeichert``),
- schreibt bei jeder Änderung den aktuellen Projektstand in den localStorage,
- schaltet das Farbschema um (Streamlit-Theme) und lädt die Seite neu – die Sicherung stellt das Projekt
  danach sofort wieder her.
Die Daten bleiben im Browser des Nutzers und gehen nicht an den Server.
"""
from __future__ import annotations

import streamlit as st

SPEICHER_KEY = "bosch_flow_streamlit_v54"

HTML = '<button class="theme" type="button" title="Hell / Dunkel umschalten" aria-label="Farbschema umschalten">☾</button>'
CSS = """
.theme {width:38px; height:32px; border:1px solid rgba(128,128,128,.35); background:transparent; border-radius:20px;
        cursor:pointer; font-size:15px; line-height:1; color:inherit; display:inline-flex; align-items:center;
        justify-content:center; padding:0; transition:.18s}
.theme:hover {border-color:#005691; color:#005691; box-shadow:0 0 0 3px rgba(0,86,145,.12)}
"""
JS = """
export default function (component) {
  const { data, setStateValue, parentElement } = component;
  const KEY = "%KEY%";
  const THEME = `stActiveTheme-${window.location.pathname}-v2`;
  const btn = parentElement.querySelector(".theme");
  if (!parentElement.__init) {
    parentElement.__init = true;
    let v = "";
    try { v = window.localStorage.getItem(KEY) || ""; } catch (e) {}
    setStateValue("gespeichert", v);
    btn.addEventListener("click", () => {
      const dunkel = btn.dataset.dunkel === "1";
      try { window.localStorage.setItem(THEME, JSON.stringify(dunkel ? "Light" : "Dark")); } catch (e) {}
      window.location.reload();
    });
  }
  if (data) {
    btn.dataset.dunkel = data.dunkel ? "1" : "0";
    btn.textContent = data.dunkel ? "☀" : "☾";
    btn.title = data.dunkel ? "Hell darstellen" : "Dunkel darstellen";
    if (data.speichern) { try { window.localStorage.setItem(KEY, data.speichern); } catch (e) {} }
  }
}
""".replace("%KEY%", SPEICHER_KEY)

_REG: dict = {}


def _komponente():
    from streamlit.components.v2 import get_bidi_component_manager
    manager = get_bidi_component_manager()
    if _REG.get("manager") is not manager:          # einmal je Streamlit-Laufzeit registrieren
        _REG["manager"] = manager
        _REG["render"] = st.components.v2.component("bosch_flow_browser", html=HTML, css=CSS, js=JS)
    return _REG["render"]


def browser(speichern: str | None, dunkel: bool) -> str | None:
    """Komponente einbinden. ``speichern``: Projektstand für die Auto-Sicherung (None = noch nicht sichern).
    Gibt beim ersten Lauf die gespeicherte Sicherung zurück ("" = keine), danach dauerhaft denselben Wert."""
    try:
        erg = _komponente()(key="bf_browser", data={"speichern": speichern, "dunkel": dunkel},
                            on_gespeichert_change=lambda: None)
    except Exception:  # noqa: BLE001 – ohne Komponenten-API läuft die App ohne Auto-Sicherung weiter
        return None
    return erg.get("gespeichert") if hasattr(erg, "get") else getattr(erg, "gespeichert", None)
