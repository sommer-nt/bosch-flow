"""Bosch WP-Schnellauslegung (Streamlit) – gleicher Rechenweg wie index.html.

Start:  streamlit run wp_auslegung/app.py
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
st.set_page_config(page_title="Bosch WP-Schnellauslegung", page_icon="♨️", layout="wide")

from wp import bericht as B  # noqa: E402
from wp import daten as D  # noqa: E402
from wp import projekt as P  # noqa: E402
from wp import rechnen as R  # noqa: E402
from wp import texte as T  # noqa: E402

BLAU, ROT = "#005691", "#e20015"
ss = st.session_state

# ------------------------------------------------------------------ Zugang (optional, wie Bosch Flow)
_pw = os.environ.get("APP_PASSWORT", "").strip()
if _pw and not ss.get("angemeldet"):
    st.title("Bosch WP-Schnellauslegung")
    if st.text_input("Passwort", type="password") == _pw:
        ss.angemeldet = True
        st.rerun()
    st.stop()

if "e" not in ss:
    ss.e = P.neu()
E = ss.e
DATEN, KAT = D.geraete(), D.katalog()

st.markdown("""<style>
.block-container{padding-top:3rem}
.kpi{border:1px solid #d3dce5;border-radius:9px;padding:8px 12px;background:#f4f7fa;margin-bottom:8px}
.kpi .t{font-size:11px;color:#4a5866;text-transform:uppercase}.kpi .v{font-size:21px;font-weight:700;color:#005691}
.kpi .s{font-size:11px;color:#78889a}.kpi.ok{border-left:4px solid #2e7d32}.kpi.warn{border-left:4px solid #b26a00}.kpi.bad{border-left:4px solid #c0161d}
</style>""", unsafe_allow_html=True)
st.markdown(f"<span style='color:{ROT};font-weight:800;font-size:22px'>BOSCH</span> "
            "<span style='font-size:20px;font-weight:600'>WP-Schnellauslegung</span> "
            "<span style='color:#4a5866'>· Luft/Wasser-Wärmepumpen · Heizlast, Bivalenzpunkt, Geräteauswahl</span>",
            unsafe_allow_html=True)


def zahl(label, pfad, **kw):
    teile = pfad.split(".")
    ziel = E
    for t in teile[:-1]:
        ziel = ziel[t]
    ziel[teile[-1]] = st.number_input(label, value=float(ziel[teile[-1]]), key="n_" + pfad, **kw)


links, rechts = st.columns([1, 2.2], gap="large")

# ================================================================== Eingaben
with links:
    with st.expander("① Projekt & Standort", expanded=True):
        E["projekt"]["name"] = st.text_input("Projekt / Bauvorhaben", E["projekt"]["name"])
        E["projekt"]["kunde"] = st.text_input("Kunde / Interessent", E["projekt"]["kunde"])
        E["projekt"]["bearbeiter"] = st.text_input("Bearbeiter", E["projekt"]["bearbeiter"])
        plz = st.text_input("PLZ", E["projekt"]["plz"], max_chars=5)
        if plz != E["projekt"]["plz"]:
            E["projekt"]["plz"] = plz
            treffer = D.plz_suche(plz) if len(plz) >= 4 else None
            if treffer:
                E["projekt"]["ort"], E["klima"]["nat"] = treffer
                ss.pop("n_klima.nat", None)
        E["projekt"]["ort"] = st.text_input("Ort", E["projekt"]["ort"])
        c1, c2, c3 = st.columns(3)
        with c1:
            zahl("θe [°C]", "klima.nat", step=0.5, help="Norm-Außentemperatur (über PLZ vorbelegt)")
        with c2:
            zahl("Heizgrenze [°C]", "klima.heizgrenze", step=1.0)
        with c3:
            zahl("Innen [°C]", "klima.innen", step=1.0)

    with st.expander("② Heizlast QH", expanded=True):
        h = E["heizlast"]
        methoden = {"vorgabe": "Vorgabe", "verbrauch": "Jahresverbrauch", "flaeche": "Wohnfläche", "huelle": "Gebäudehülle"}
        h["methode"] = st.radio("Methode", list(methoden), format_func=methoden.get, horizontal=True,
                                index=list(methoden).index(h["methode"]))
        if h["methode"] == "vorgabe":
            zahl("Heizlast (z. B. DIN EN 12831) [kW]", "heizlast.vorgabe_kw", min_value=0.0, step=0.1)
        elif h["methode"] == "flaeche":
            zahl("Beheizte Wohnfläche [m²]", "heizlast.flaeche_m2", min_value=0.0, step=1.0)
            zahl("Spezifischer Wärmebedarf [W/m²]", "heizlast.spez_w_m2", min_value=0.0, step=1.0,
                 help="Bestand WSchVO 1982: 80–120 · WSchVO 1995: 60–80 · EnEV 2002: 40–60 · EnEV 2009: 35–40 · "
                      "KfW 55: 30 · KfW 40+: 20–25 · Passivhaus: 15")
        elif h["methode"] == "huelle":
            zahl("Gebäudehüllfläche A [m²]", "heizlast.huell_a_m2", min_value=0.0)
            zahl("H'T [W/m²K]", "heizlast.ht", min_value=0.0, step=0.01)
            zahl("Luftvolumen V (Ve · 0,76) [m³]", "heizlast.volumen_m3", min_value=0.0)
            zahl("Luftwechsel n [1/h]", "heizlast.luftwechsel", min_value=0.0, step=0.1)
        else:
            arten = list(R.VOLLBENUTZUNGSSTUNDEN)
            art = st.selectbox("Gebäudeart", arten, index=arten.index(h["gebaeudeart"]),
                               format_func=lambda a: f"{a} ({R.VOLLBENUTZUNGSSTUNDEN[a]} h/a)")
            if art != h["gebaeudeart"]:
                h["gebaeudeart"], h["vbh"] = art, R.VOLLBENUTZUNGSSTUNDEN[art]
                ss.pop("n_heizlast.vbh", None)
            zahl("Vollbenutzungsstunden th [h/a]", "heizlast.vbh", min_value=1.0, step=50.0)
            traeger = {"gas": "Erdgas", "oel": "Heizöl", "pellet": "Pellets", "kwh": "kWh (Fernwärme, Strom …)"}
            tr = st.selectbox("Energieträger", list(traeger), format_func=traeger.get, index=list(traeger).index(h["energietraeger"]))
            if tr != h["energietraeger"]:
                h["energietraeger"], h["heizwert"] = tr, R.HEIZWERT[tr][0]
                ss.pop("n_heizlast.heizwert", None)
            einheit = R.HEIZWERT[tr][1]
            zahl(f"Jahres-Gesamtverbrauch [{einheit}]", "heizlast.menge", min_value=0.0, step=10.0)
            zahl(f"Heizwert Hu [kWh/{einheit}]", "heizlast.heizwert", min_value=0.0, step=0.01)
            zahl("Jahresnutzungsgrad Altanlage η", "heizlast.nutzungsgrad", min_value=0.5, max_value=1.1, step=0.01,
                 help="1,0 = Rechenweg Excel (ohne Umrechnungsfaktoren und Gradtage)")
            h["ww_im_verbrauch"] = st.checkbox("Warmwasser im Verbrauch enthalten", h["ww_im_verbrauch"])

    with st.expander("③ Warmwasser & Sperrzeit", expanded=False):
        t = E["tww"]
        t["aktiv"] = st.checkbox("Warmwasser über die Wärmepumpe", t["aktiv"])
        zahl("Personen / Nutzer np", "tww.personen", min_value=0.0, step=1.0)
        t["methode"] = st.radio("Zuschlag nach", ["personen", "nachheizzeit"], horizontal=True,
                                index=["personen", "nachheizzeit"].index(t["methode"]),
                                format_func={"personen": "Personen × kW/P", "nachheizzeit": "Jahresbedarf / Nachheizzeit"}.get)
        if t["methode"] == "personen":
            lp = {0.1: "Standard 0,10 kW/P", 0.2: "Standard Plus 0,20 kW/P", 0.25: "Regendusche 0,25 kW/P"}
            t["kw_person"] = st.selectbox("Lastprofil", list(lp), format_func=lp.get,
                                          index=list(lp).index(t["kw_person"]) if t["kw_person"] in lp else 0)
        else:
            td = {4: "Standard · 4 h/d", 3: "Gehobener Standard · 3 h/d", 2: "Luxus · 2 h/d"}
            t["td"] = st.selectbox("Komfortanspruch (Nachheizzeit td)", list(td), format_func=td.get,
                                   index=list(td).index(int(t["td"])) if int(t["td"]) in td else 0)
        nutz = list(R.TWW_BEDARF)
        nu = st.selectbox("Nutzung (DIN V 18599-10)", nutz, index=nutz.index(t["nutzung"]))
        bz = st.radio("Bezug", ["personen", "flaeche"], horizontal=True, index=["personen", "flaeche"].index(t["bezug"]),
                      format_func={"personen": "je Person", "flaeche": "flächenbezogen"}.get)
        if nu != t["nutzung"] or bz != t["bezug"]:
            t["nutzung"], t["bezug"] = nu, bz
            t["qwb"] = R.TWW_BEDARF[nu][1 if bz == "flaeche" else 0]
            ss.pop("n_tww.qwb", None)
        zahl("Qw,b [kWh/(m²·d)]" if bz == "flaeche" else "Qw,b [kWh/(P·d)]", "tww.qwb", min_value=0.0, step=0.0001, format="%.4f")
        if bz == "flaeche":
            zahl("Nutzfläche ANGF [m²]", "tww.flaeche_m2", min_value=0.0)
        sp = {0: "keine", 2: "2 h → +5 %", 4: "4 h → +10 %", 6: "6 h → +15 %"}
        E["sperrzeit_h"] = st.selectbox("Sperrzeit Energieversorger", list(sp), format_func=sp.get, index=list(sp).index(int(E["sperrzeit_h"])))

    with st.expander("④ Auslegung & Gerät", expanded=True):
        zahl("Max. erforderliche Vorlauftemperatur [°C]", "vl", min_value=30.0, max_value=70.0, step=1.0)
        bw = {"monoenergetisch": "monoenergetisch (0,7 · QGES bei A-7)", "monovalent": "monovalent (QGES bei θe)",
              "hybrid": "GEG-Hybrid (0,3 · QH bei A-7)"}
        E["auslegung"] = st.selectbox("Betriebsweise", list(bw), format_func=bw.get, index=list(bw).index(E["auslegung"]))
        alle = [s["id"] for s in DATEN["serien"]]
        gew = st.multiselect("Baureihen", alle, default=E["serien"] or alle,
                             format_func=lambda s: D.serie(s)["name"].replace("Compress ", ""))
        E["serien"] = [] if set(gew) == set(alle) else gew
        R_ = R.rechne(E, DATEN, KAT)
        optionen = [""] + [g["id"] for g in DATEN["geraete"]]
        ok = {c["geraet"]: c for c in R_["kandidaten"]}
        wahl = st.selectbox("Wärmepumpe", optionen, index=optionen.index(E["auswahl"]["geraet"]) if E["auswahl"]["geraet"] in optionen else 0,
                            format_func=lambda g: "automatisch (Empfehlung)" if not g else g + (" ✓" if ok.get(g, {}).get("ok") else ""))
        if wahl != E["auswahl"]["geraet"]:
            E["auswahl"]["geraet"] = wahl
            E["auswahl"]["anzahl"] = ok[wahl]["n"] if wahl in ok else 1
            E["auswahl"]["inneneinheit"] = ""
            st.rerun()
        if wahl:
            smax = D.serie(D.geraet(wahl)["serie"])["kaskade_max"]
            n = st.number_input("Anzahl (Kaskade)", 1, smax, int(E["auswahl"]["anzahl"]))
            if n != E["auswahl"]["anzahl"]:
                E["auswahl"]["anzahl"] = n
                st.rerun()
        R_ = R.rechne(E, DATEN, KAT)
        ies = T.inneneinheiten(R_, KAT)
        if ies:
            typen = [i["typ"] for i in ies]
            akt = E["auswahl"]["inneneinheit"] if E["auswahl"]["inneneinheit"] in typen else typen[0]
            E["auswahl"]["inneneinheit"] = st.selectbox("Inneneinheit / Regelung", typen, index=typen.index(akt),
                                                        format_func=lambda x: x + " – " + next(i["art"] for i in ies if i["typ"] == x))
        E["preise_drucken"] = st.checkbox("Preise (UVP) im PDF – intern", E["preise_drucken"])
        E["projekt"]["notiz"] = st.text_area("Notiz", E["projekt"]["notiz"], height=70)
        R_ = R.rechne(E, DATEN, KAT)

    st.divider()
    if not E["projekt"]["datum"]:
        E["projekt"]["datum"] = date.today().isoformat()
    name = (E["projekt"]["name"] or "Projekt").replace(" ", "_")
    st.download_button("💾 Projekt speichern (.json)", P.dumps(E), f"WP-Auslegung_{name}.json", "application/json",
                       width="stretch")
    datei = st.file_uploader("Projekt öffnen (.json, auch aus der HTML-Version)", type="json")
    if datei is not None and ss.get("geladen") != datei.file_id:
        try:
            ss.e = P.loads(datei.getvalue().decode("utf-8"))
            ss.geladen = datei.file_id
            for k in [k for k in ss if str(k).startswith("n_")]:
                del ss[k]
            st.rerun()
        except ValueError as fehler:
            st.error(str(fehler))

# ================================================================== Ergebnisse
r, g = R_, R_["gewaehlt"]
ie = T.inneneinheit(E, r, KAT)
with rechts:
    for m in T.meldungen(E, r, KAT):
        st.warning(m)
    ks = [("Gesamtheizlast QGES", f"{T.f(r['qges'], 2)} kW", f"QH {T.f(r['qh'], 2)} + QTW {T.f(r['qtw'], 2)} + QSperr {T.f(r['qsperr'], 2)}", ""),
          ("Mindestleistung WP", f"{T.f(r['mindestleistung'], 2)} kW", T.KRITERIUM[r["kriterium"]], "")]
    if g and g["moeglich"]:
        ks += [("Bivalenzpunkt", T.biv_text(g), "Schnitt mit Gebäudekennlinie", "ok" if g["ok"] else "bad"),
               ("Leistung bei θe", f"{T.f(g['q_nat'], 2)} kW", f"Abdeckung {T.f(g['abdeckung'] * 100, 0)} %", "ok" if g["abdeckung"] >= 1 else "warn"),
               ("Heizstab bei θe", f"{T.f(g['heizstab_kw'], 2)} kW",
                f"verfügbar {T.f(g['heizstab_max_kw'], 0)} kW" if g["heizstab_max_kw"] is not None else "bauseits",
                "ok" if g["heizstab_kw"] <= 0 else "warn"),
               ("WP-Deckungsanteil", f"{T.f(g['deckung'] * 100, 1)} %", "VDI 4650 (Luft/Wasser, parallel)", "ok" if g["deckung"] >= 0.98 else "warn")]
    spalten = st.columns(3)
    for i, (a, b, c, klasse) in enumerate(ks):
        spalten[i % 3].markdown(f"<div class='kpi {klasse}'><div class='t'>{a}</div><div class='v'>{b}</div><div class='s'>{c}</div></div>",
                                unsafe_allow_html=True)

    if g:
        k = KAT["geraete"].get(g["geraet"], {})
        s = D.serie(g["serie"])
        st.subheader(("{} × ".format(g["n"]) if g["n"] > 1 else "") + g["geraet"])
        st.caption(f"{s['name']} · {s['bauart']} · {'Empfehlung' if not E['auswahl']['geraet'] else 'manuell gewählt'}"
                   + (f" · mit {ie['typ']} ({ie['art']})" if ie else ""))
        d = st.columns(4)
        d[0].metric("Bestell-Nr. Außeneinheit", k.get("artnr") or "–")
        d[1].metric("Bestell-Nr. Inneneinheit", (ie or {}).get("artnr") or "–")
        d[2].metric(f"Max. Leistung A-7/W{T.f(r['vl'], 0)}", f"{T.f(g.get('q_a7'), 2)} kW")
        d[3].metric("Taktgrenze", f"≈ {T.ft(g['taktgrenze'])} °C" if g.get("taktgrenze") is not None else "–")
        st.caption(f"SCOP 35/55 °C: {T.f(k.get('scop35'), 2)} / {T.f(k.get('scop55'), 2)} · Schallleistung ErP: "
                   f"{k.get('lw_db', '–')} dB(A) · {k.get('masse', '')} · UVP (intern): {T.euro(k['uvp'] * g['n']) if k.get('uvp') else '–'}"
                   + (f" + {T.euro(ie['uvp'])}" if ie and ie.get("uvp") else ""))

    if r.get("kennlinien"):
        kl = r["kennlinien"]
        fig = go.Figure()
        for d_ in DATEN["geraete"]:
            if d_["serie"] == g["serie"] and d_["id"] != g["geraet"]:
                kk = R.kurve_bei_vl(d_["max"], r["vl"])
                if kk:
                    fig.add_scatter(x=kl["t"], y=[g["n"] * kk[0](t) for t in kl["t"]], name=d_["kurz"], mode="lines",
                                    line=dict(color="#a0aab5", width=1, dash="dot"))
        if kl["min"]:
            fig.add_scatter(x=kl["t"], y=kl["min"], name="Mindestleistung (1 Gerät)", mode="lines", line=dict(color=BLAU, dash="dash"))
        fig.add_scatter(x=kl["t"], y=kl["last"], name="Gebäudekennlinie", mode="lines", line=dict(color="#141e29", width=2.5))
        fig.add_scatter(x=kl["t"], y=kl["max"], name=g["geraet"] + " (max.)", mode="lines", line=dict(color=BLAU, width=3.5))
        if g["bivalenz_art"] == "punkt":
            qb = R.last(g["bivalenz"], r["qh"] + r["qsperr"], r["qtw"], r["nat"], r["heizgrenze"])
            fig.add_scatter(x=[g["bivalenz"]], y=[qb], mode="markers+text", text=[f"Bivalenzpunkt {T.ft(g['bivalenz'])} °C"],
                            textposition="bottom left", marker=dict(size=11, color=BLAU), showlegend=False)
        fig.add_vline(x=r["nat"], line_dash="dot", line_color="#78889a", annotation_text=f"θe {T.ft(r['nat'])} °C")
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), xaxis_title="Außentemperatur in °C",
                          yaxis_title="Heizleistung in kW", legend=dict(orientation="h", y=1.12), template="plotly_white")
        st.plotly_chart(fig, width="stretch")

    st.markdown("**Mögliche Wärmepumpen** – kleinste passende Größe je Gerät (★ kleinste der Baureihe)")
    emp = set(r["empfehlung_je_serie"])
    zeilen = []
    for c in r["kandidaten"]:
        zeilen.append({"": "🟢" if c["ok"] else ("⚪" if not c["moeglich"] else "🔴"),
                       "Wärmepumpe": c["geraet"] + (" ★" if f"{c['geraet']}|{c['n']}" in emp else ""), "Anz.": c["n"],
                       f"A-7/W{T.f(r['vl'], 0)} [kW]": round(c["q_a7"], 2) if c["moeglich"] else None,
                       "bei θe [kW]": round(c["q_nat"], 2) if c["moeglich"] else None,
                       "Abdeckung [%]": round(c["abdeckung"] * 100) if c["moeglich"] else None,
                       "Bivalenzpunkt": T.biv_text(c), "Heizstab [kW]": round(c["heizstab_kw"], 1) if c["moeglich"] else None,
                       "Deckung [%]": round(c["deckung"] * 100, 1) if c["moeglich"] else None,
                       "UVP [€]": KAT["geraete"].get(c["geraet"], {}).get("uvp", 0) * c["n"] or None,
                       "Hinweis": c["grund"] or ("überdimensioniert" if c.get("ueberdimensioniert") else "")})
    st.dataframe(zeilen, hide_index=True, width="stretch")

    with st.expander("Herleitung Heizlast", expanded=False):
        st.table([{"Größe": a, "Formel": b, "Wert": c} for a, b, c in T.herleitung(E, r)])
    en = r.get("energie")
    if en:
        with st.expander("Jahresbilanz (Schätzung)", expanded=False):
            c = st.columns(4)
            c[0].metric("Jahreswärme Heizung + WW", f"{T.f(en['waerme_kwh'], 0)} kWh/a")
            if en.get("scop"):
                c[1].metric("Strom Wärmepumpe", f"{T.f(en['strom_wp_kwh'], 0)} kWh/a", help=f"SCOP ≈ {T.f(en['scop'], 2)}")
                c[2].metric("Strom Heizstab", f"{T.f(en['strom_heizstab_kwh'], 0)} kWh/a")
                c[3].metric("Umweltwärme", f"{T.f(en['umwelt_kwh'], 0)} kWh/a")

    st.download_button("📄 Auslegung als PDF", B.pdf_bytes(E, r, DATEN, KAT),
                       f"WP-Auslegung_{name}{'_intern' if E['preise_drucken'] else ''}.pdf", "application/pdf", type="primary")
    st.caption(f"Leistungsdaten: {DATEN['quelle']} · Katalog: Gesamtkatalog März 2026 · Ergebnis ersetzt keine Fachplanung.")
