"""Streamlit-Seite „Speicherauswahl Wärmepumpe“ (Gegenstück zu speicher.html).

Aufruf in app.py über ?tool=speicher. Logik in bosch_flow/speicher.py.
"""
from __future__ import annotations

import html

import streamlit as st

from bosch_flow import speicher as SP

KAT_FARBE = {"puffer": ("#92d050", "#5f8f2c"), "ww": ("#ffc000", "#a77d00"), "biv": ("#bdd7ee", "#3d6285"),
             "kombi": ("#cc99ff", "#7a4fae")}
E = html.escape


def _ttnr_text(s: dict) -> str:
    return " / ".join(s["ttnr"]) if s["ttnr"] else (s.get("ttnr_hinweis") or "TTNr fehlt")


def _tags(s: dict, e: dict | None, F: dict) -> str:
    t = []
    if s.get("info"):
        t.append(s["info"])
    if s.get("alt"):
        t.append(f'<b style="color:{F["rot"]}">Alt</b>')
    if e and e["status"] == "bedingt":
        t.append(f'<b style="color:{F["gelb"]}">{E(e["code"])} eingeschränkt</b>')
    elif e and e["zusatz"]:
        t.append(f'<b style="color:{F["akzent"]}">{E(e["zusatz"])}</b>')
    if e and e["notiz"]:
        t.append(f'<span style="color:{F["gelb"]}">ⓘ {E(e["notiz"])}</span>')
    return " · ".join([E(_ttnr_text(s))] + [x if x.startswith("<") else E(x) for x in t])


def _spalten(gruppen: dict, d: dict, F: dict, dunkel: bool, mobil: bool) -> None:
    kats = list(d["kategorien"].items())
    reihen = [kats] if not mobil else [[k] for k in kats]
    for reihe in reihen:
        for (k, titel), col in zip(reihe, st.columns(len(reihe))):
            eintraege = gruppen[k]
            farbe = KAT_FARBE[k][1 if dunkel else 0]
            col.markdown(f'<div style="background:{farbe};color:{"#fff" if dunkel else "#141e29"};font-weight:700;'
                         f'border-radius:10px 10px 0 0;padding:7px 12px;display:flex;justify-content:space-between">'
                         f'{E(titel)}<span style="opacity:.75">{len(eintraege)}</span></div>', unsafe_allow_html=True)
            with col.container(border=True):
                if not eintraege:
                    st.caption("kein Speicher")
                for s, e in eintraege:
                    an = st.session_state.get("sp_wahl") == s["id"]
                    if st.button(s["name"], key=f"sp_{k}_{s['id']}", width="stretch",
                                 type="primary" if an else "secondary"):
                        st.session_state.sp_wahl = None if an else s["id"]
                        st.rerun()
                    st.markdown(f'<div style="font-size:11.5px;color:{F["leise"]};margin:-10px 0 6px 4px">'
                                f'{_tags(s, e, F)}</div>', unsafe_allow_html=True)


def _detail(s: dict, d: dict, F: dict, wp_id: str | None, mobil: bool) -> None:
    eh = s.get("eheizer") or {}
    with st.container(border=True):
        k1, k2 = st.columns([3, 2] if not mobil else [1, 1])
        meta = [d["kategorien"][s["kategorie"]]] + ([s["info"]] if s.get("info") else []) + \
               (["Alt – auslaufend"] if s.get("alt") else [])
        k1.markdown(f'<div style="font-size:24px;font-weight:800;color:{F["text"]}">{E(s["name"])}</div>'
                    f'<div style="color:{F["leise"]};font-size:13px">{E(_ttnr_text(s))} · {E(" · ".join(meta))}'
                    + (f' · in der E-Heizer-Liste: {E(eh["name_heizerliste"])}' if eh.get("name_heizerliste") else "")
                    + '</div>', unsafe_allow_html=True)
        with k2:
            b1, b2 = st.columns(2)
            if s.get("im"):
                b1.link_button("Installationsanleitung", s["im"], icon=":material/description:", type="primary",
                               width="stretch")
            b2.link_button("Alle Dokumente", SP.doku_link(s), icon=":material/search:", width="stretch",
                           help="Bosch Dokumentensuche zur TTNr")

        if wp_id and s.get("matrix"):
            status, zusatz = SP.bewertung(s["kombi"].get(wp_id, ""))
            wp = SP.wp_nach_id(wp_id, d)
            if status == "bedingt":
                st.warning(f"Mit {wp['name']}: {zusatz} (Matrix: „{s['kombi'].get(wp_id)}“)")
            elif zusatz:
                st.info(f"Mit {wp['name']}: {zusatz}")
            if s["notiz"].get(wp_id):
                st.warning(f"ⓘ {s['notiz'][wp_id]}")

        links, rechts = st.columns([1, 2] if not mobil else [1, 1])
        with links:
            bild = SP.bild(s)
            if bild:
                st.image(str(bild), width="stretch")
            else:
                st.markdown(f'<div style="border:1px dashed {F["linie"]};border-radius:10px;min-height:200px;display:flex;'
                            f'align-items:center;justify-content:center;text-align:center;color:{F["leise"]};font-size:12.5px;'
                            f'padding:14px">Maßbild noch nicht hinterlegt.'
                            + ("<br>Maße und Anschlüsse siehe Installationsanleitung." if s.get("im") else "")
                            + '</div>', unsafe_allow_html=True)
        with rechts:
            zeilen = [("TTNr", _ttnr_text(s)), ("Kategorie", " · ".join(meta[:2]))]
            if eh.get("tiefe_muffe_mm"):
                zeilen.append(("max. Eintauchtiefe E-Muffe", f'{eh["tiefe_muffe_mm"]} mm'))
            if eh.get("tiefe_handloch_mm"):
                zeilen.append(("max. Eintauchtiefe Handloch", f'{eh["tiefe_handloch_mm"]} mm'))
            if eh.get("handlochdeckel_ttnr"):
                zeilen.append(("Handlochdeckel", eh["handlochdeckel_ttnr"]))
            for k, t in SP.STAMMDATEN_TITEL.items():
                if (s.get("daten") or {}).get(k):
                    zeilen.append((t, s["daten"][k]))
            st.markdown("".join(f'<div class="g-zeile"><span>{E(a)}</span><b>{E(str(b))}</b></div>' for a, b in zeilen),
                        unsafe_allow_html=True)
            if not s.get("daten"):
                st.caption("Volumen, Maße und Anschlüsse folgen mit den SAP-Stammdaten.")
            st.markdown("**Freigegeben für Wärmepumpen**")
            if not s.get("matrix"):
                st.caption("Nicht in der WP-Kombinationsmatrix (z. B. Speicher für Gas-/Ölgeräte) – nur E-Heizer-Daten.")
            else:
                fam: dict[str, list] = {}
                for e in SP.wps_fuer_speicher(s["id"], d):
                    w = SP.wp_nach_id(e["id"], d)
                    fam.setdefault(w["familie"], []).append(w["groesse"] + (" (eingeschränkt)" if e["status"] == "bedingt" else ""))
                if not fam:
                    st.caption("Mit keiner Wärmepumpe der Matrix freigegeben.")
                st.markdown("\n".join(f"- **{E(f)}:** {E(' · '.join(g))}" for f, g in fam.items()))

        st.markdown("**Passende E-Heizer**")
        if eh.get("hinweis"):
            st.warning(eh["hinweis"])
        if not eh:
            st.caption("Für diesen Speicher sind keine E-Heizer hinterlegt.")
            return
        hz = SP.heizer_fuer_speicher(s["id"], d)
        typen = list(d["heizertypen"].items())
        for reihe in ([typen] if not mobil else [typen[:2], typen[2:]]):
            for (typ, titel), col in zip(reihe, st.columns(len(reihe))):
                with col.container(border=True):
                    st.image(str(SP.ORDNER / "speicher" / SP.HEIZER_BILDER[typ]), width=140 if typ != "flh" else 50)
                    st.markdown(f"**{titel}**")
                    if typ == "led_hd" and eh.get("handlochdeckel_ttnr"):
                        st.caption(f"Handlochdeckel {eh['handlochdeckel_ttnr']}")
                    elif typ == "led" and eh.get("tiefe_muffe_mm"):
                        st.caption(f"max. Eintauchtiefe {eh['tiefe_muffe_mm']} mm")
                    if not hz[typ]:
                        st.caption("nicht freigegeben")
                    for e in hz[typ]:
                        h = d["heizer"][e["id"]]
                        name = ("" if h["modell"] == "E-Heater" else h["modell"] + " · ") + \
                            f'{str(h["leistung_kw"]).replace(".0", "").replace(".", ",")} kW / {h["spannung"]}'
                        st.markdown(f'{E(name)}' + (f' <b style="color:{F["gelb"]}">nur HZG</b>' if e["status"] == "hzg" else "")
                                    + f'<br><span style="font-size:12px;color:{F["leise"]}">TTNr {h["ttnr"]} · '
                                      f'≥ {h["einbautiefe_mm"]} mm</span>', unsafe_allow_html=True)
        if any(hz.values()):
            st.caption(" ".join(d["hinweise_heizer"]))


def seite(F: dict, dunkel: bool = False, mobil: bool = False) -> None:
    d = SP.laden()
    ss = st.session_state
    st.markdown('<style>[class*="st-key-sp_"] button {justify-content:flex-start; min-height:34px; padding:4px 10px}'
                '[class*="st-key-sp_"] button p {font-weight:650}</style>', unsafe_allow_html=True)
    k1, k2 = st.columns([4, 1])
    k1.markdown(f'<div class="marke">BOSCH <span>Speicherauswahl</span>'
                f'<small>Wärmepumpe → Speicher → E-Heizer · Matrix-Stand {E(d["stand"])}</small></div>',
                unsafe_allow_html=True)
    if k2.button("Netzrechner", icon=":material/arrow_back:", width="stretch"):
        st.query_params.clear()
        st.rerun()

    modus = st.segmented_control("Suche", ["Über Wärmepumpe", "Über Speicher / TTNr"], default="Über Wärmepumpe",
                                 key="sp_modus", label_visibility="collapsed") or "Über Wärmepumpe"
    wp_id = None
    if modus == "Über Wärmepumpe":
        familien = list(dict.fromkeys(w["familie"] for w in d["wp"]))
        c = st.columns([2, 2, 3] if not mobil else [1])
        fam = c[0].selectbox("Baureihe", familien, key="sp_familie")
        wps = [w for w in d["wp"] if w["familie"] == fam]
        wp_id = c[1 % len(c)].selectbox("Wärmepumpe", [w["id"] for w in wps], key=f"sp_wp_{fam}",
                                        format_func=lambda i: SP.wp_nach_id(i, d)["name"])
        with c[2 % len(c)]:
            st.write("")
            t1, t2 = st.columns(2)
            alte = t1.toggle("auslaufende („Alt“)", value=True, key="sp_alte")
            bedingte = t2.toggle("eingeschränkte", value=True, key="sp_bed",
                                 help="z. B. (-)* – abweichend bei Wasser-Wasser-Betrieb")
        roh = SP.speicher_fuer_wp(wp_id, alte, bedingte, d)
        gruppen = {k: [(SP.speicher_nach_id(e["id"], d), e) for e in v] for k, v in roh.items()}
        n = sum(len(v) for v in gruppen.values())
        st.markdown(f"#### Zugelassene Speicher für {SP.wp_nach_id(wp_id, d)['name']} "
                    f"<span style='font-size:13px;color:{F['leise']}'>{n} Speicher · Klick zeigt Details</span>",
                    unsafe_allow_html=True)
    else:
        q = st.text_input("Speichername oder TTNr", key="sp_suche", placeholder="z. B. WPS 390, BH 200 oder 8732921683")
        ids = SP.suche(q, d) if q.strip() else [s["id"] for s in d["speicher"]]
        if len(ids) == 1:
            ss.sp_wahl = ids[0]
        gruppen = {k: [] for k in d["kategorien"]}
        for i in ids:
            s = SP.speicher_nach_id(i, d)
            gruppen[s["kategorie"]].append((s, None))
        st.caption(f"{len(ids)} Treffer" if q.strip() else
                   f"{len(ids)} Speicher – inkl. Speicher für Gas-/Ölgeräte (nur E-Heizer-Daten)")
    _spalten(gruppen, d, F, dunkel, mobil)

    s = SP.speicher_nach_id(ss.get("sp_wahl") or "", d)
    if s:
        _detail(s, d, F, wp_id, mobil)
    st.caption("Legende Matrix: + freigegeben · ++ zwei Speichereinheiten · (-)* abweichend bei Wasser-Wasser-Betrieb  \n"
               + "  \n".join(d["hinweise_matrix"]) + f"  \nQuelle: {d['quelle']}")
