"""Druckverlust, Förderhöhe der Netzpumpe und Rohrmengen – Erweiterung über den Rechenkern V54 hinaus.

Grundlage sind die Abschnitte des Rechenkerns (Volumenstrom, gewähltes Rohr mit Innendurchmesser, reale
Geschwindigkeit). Ergänzt werden Leitungslängen aus einer vereinfachten Gebäudegeometrie:

- Steigstrang: je Geschoss eine Geschosshöhe (der unterste Abschnitt vom Keller bis zum EG ebenfalls),
- Etagenleitung: Anschluss Steigstrang → erste Station, danach je Station der Stationsabstand,
- Hauptstrang (mehrere Stränge, gemeinsame Zentrale): zwischen zwei Abzweigen der Strangabstand, der Abschnitt an
  der Zentrale die Länge Zentrale → erster Abzweig; bei einem Strang oder getrennten Zentralen nur diese Zuleitung.

Druckverlust je Abschnitt nach Darcy-Weisbach mit dem realen Rohr: R = λ/dᵢ · ρ·v²/2, λ wie im Kern
(turbulent 0,309/log10(Re/7)², laminar 64/Re). Der ungünstigste Fließweg (Vor- und Rücklauf) führt von der Zentrale zur
entferntesten Station; dazu kommen ein Zuschlag für Einzelwiderstände (Formstücke, Armaturen), der Primär-Druckverlust
der Station laut Katalog und ein Ansatz für die Wärmezentrale. Ergebnis: erforderliche Förderhöhe, Prüfung gegen die
Netzpumpenmodule NM 3/6/10 (Restförderhöhe 0,8 bar) und Rohrmengen je Nennweite. Vereinfachtes Vorplanungsmodell –
ersetzt keine Rohrnetzberechnung.
"""
from __future__ import annotations

import math

from .calc import Inputs, compute_all, gesamt_anlage, seg, topologie
from .data import NU, RHO

G_ERDE = 9.81

# Geometrie-Vorgaben (in den Projekt-Metadaten gespeichert, Schlüssel wie hier)
GEOMETRIE = {
    "hG": (3.0, "Geschosshöhe", "m", 2.4, 5.0, 0.1),
    "aAn": (3.0, "Steigstrang → erste Station", "m", 0.5, 30.0, 0.5),
    "aSt": (5.0, "Abstand zwischen Stationen", "m", 0.5, 30.0, 0.5),
    "aStr": (15.0, "Abstand zwischen Strängen (Keller)", "m", 1.0, 100.0, 1.0),
    "aZen": (8.0, "Zentrale → erster Abzweig", "m", 0.5, 100.0, 0.5),
    "zuschlag": (30.0, "Zuschlag Einzelwiderstände", "%", 0.0, 100.0, 5.0),
    "dpZen": (100.0, "Druckverlust Wärmezentrale", "mbar", 0.0, 1000.0, 10.0),
}


def geometrie(meta: dict) -> dict:
    out = {}
    for key, (vorgabe, _t, _e, lo, hi, _s) in GEOMETRIE.items():
        try:
            v = float(meta.get(key, vorgabe))
        except (TypeError, ValueError):
            v = vorgabe
        out[key] = min(hi, max(lo, v)) if math.isfinite(v) else vorgabe
    return out


def r_pa_m(row: dict) -> float:
    """Druckgefälle R [Pa/m] im gewählten Rohr bei realer Geschwindigkeit."""
    v, di = row["v"], row["di"] / 1000
    if v <= 0 or di <= 0:
        return 0.0
    re = v * di / (NU * 1e-6)
    lam = 64 / re if re < 2320 else 0.309 / math.log10(re / 7) ** 2
    return lam / di * RHO * v ** 2 / 2


def _stueck(name: str, row: dict, laenge: float, art: str) -> dict:
    r = r_pa_m(row)
    return {"name": name, "art": art, "we": row["weCum"], "dim": row["dim"], "rohr": row["raw"], "di": row["di"],
            "V": row["Vtot"], "v": row["v"], "L": laenge, "R": r, "dp": r * laenge}


def _strangweg(R: dict, geo: dict, i: int) -> list[dict]:
    """Ungünstigster Weg innerhalb eines Strangs: Steigstrang bis Etage f + längste Seite der Etage f."""
    bester, best_dp = [], -1.0
    for f in range(1, R["floors"] + 1):
        steig = [_stueck(f"S{i + 1} Steigstrang {'Keller → EG' if k == 0 else f'Etage {k} → {k + 1}'}",
                         R["vRows"][k], geo["hG"], "Steigstrang") for k in range(f)]
        for seite in ("l", "r"):
            rows = R["perFloorRows"][f - 1][seite]
            nst = len(rows)
            if not nst:
                continue
            etage = [_stueck(f"S{i + 1} Etage {f} {'links' if seite == 'l' else 'rechts'} → St. {k + 1}",
                             rows[nst - 1 - k], geo["aAn"] if k == 0 else geo["aSt"], "Etagenleitung")
                     for k in range(nst)]
            weg = steig + etage
            dp = sum(s["dp"] for s in weg)
            if dp > best_dp:
                bester, best_dp = weg, dp
    return bester


def berechne(inp: Inputs, straenge: list, meta: dict) -> dict:
    """Druckverlust des ungünstigsten Fließwegs, Förderhöhe, Pumpenprüfung und Rohrmengen."""
    from .katalog import geraet, netzpumpe

    geo = geometrie(meta)
    res = compute_all(inp, straenge)
    P = res[0]["P"]
    G = gesamt_anlage(inp, res)
    gemeinsam = not G["getrennt"] and len(res) > 1
    pos = float(meta.get("topoPos", 50))

    # Zuleitungen je Strang (Keller): gemeinsamer Hauptstrang oder eigene Zuleitung
    zuleitung: dict[int, list[dict]] = {}
    hauptstrang: list[dict] = []
    if gemeinsam:
        T = topologie(res, pos)
        links = T["links"]
        ab = {a["strang"] - 1: a for a in T["abschnitte"]}
        for a in T["abschnitte"]:
            i = a["strang"] - 1
            an_zentrale = (i == links - 1) if i < links else (i == links)
            L = geo["aZen"] if an_zentrale else geo["aStr"]
            hauptstrang.append(_stueck(f"Hauptstrang Abschnitt {i + 1}", seg(a["load"], P), L, "Hauptstrang"))
        for i in range(len(res)):
            kette = range(i, links) if i < links else range(i, links - 1, -1)
            zuleitung[i] = [next(h for h in hauptstrang if h["name"] == f"Hauptstrang Abschnitt {k + 1}") for k in kette
                            if k in ab]
    else:
        for i, R in enumerate(res):
            zuleitung[i] = [_stueck(f"S{i + 1} Zuleitung Zentrale → Strangfuß", seg(R["totalWE"], P), geo["aZen"],
                                    "Zuleitung")]

    # ungünstigster Weg über alle Stränge
    wege = []
    for i, R in enumerate(res):
        weg = zuleitung[i] + _strangweg(R, geo, i)
        wege.append((sum(s["dp"] for s in weg), i, weg))
    dp_rohr_einfach, kritisch, pfad = max(wege, key=lambda w: w[0])
    dp_rohr = 2 * dp_rohr_einfach                                   # Vor- und Rücklauf
    dp_einzel = dp_rohr * geo["zuschlag"] / 100
    g = geraet(inp, meta)
    dp_station = g["dpPrim"] * 100                                  # mbar → Pa
    dp_zentrale = geo["dpZen"] * 100
    dp_ges = dp_rohr + dp_einzel + dp_station + dp_zentrale

    # Volumenstrom je Netzpumpe
    if G["getrennt"]:
        v_pumpe, pumpen = res[kritisch]["vRows"][0]["Vtot"], len(res)
    elif gemeinsam:
        v_pumpe, pumpen = seg(G["we"], P)["Vtot"], 1
    else:
        v_pumpe, pumpen = res[0]["vRows"][0]["Vtot"], 1
    nm = netzpumpe(v_pumpe, dp_ges / 1e5)

    # Rohrmengen (Vorlauf + Rücklauf) je Nennweite
    teile = list(hauptstrang)
    if not gemeinsam:
        teile += [s for i in range(len(res)) for s in zuleitung[i]]
    for i, R in enumerate(res):
        teile += [_stueck("", R["vRows"][k], geo["hG"], "Steigstrang") for k in range(R["floors"])]
        for f in range(R["floors"]):
            for seite in ("l", "r"):
                rows = R["perFloorRows"][f][seite]
                teile += [_stueck("", rows[len(rows) - 1 - k], geo["aAn"] if k == 0 else geo["aSt"], "Etagenleitung")
                          for k in range(len(rows))]
    mengen: dict[str, dict] = {}
    for s in teile:
        m = mengen.setdefault(s["dim"], {"dim": s["dim"], "rohr": s["rohr"], "di": s["di"], "L": 0.0, "inhalt": 0.0,
                                         "arten": set()})
        m["L"] += 2 * s["L"]
        m["inhalt"] += 2 * s["L"] * math.pi / 4 * (s["di"] / 1000) ** 2 * 1000      # Liter
        m["arten"].add(s["art"])
    from .data import DN_SERIES
    ordnung = [d[0] for d in DN_SERIES]
    rohrmengen = sorted(mengen.values(), key=lambda m: ordnung.index(m["dim"]) if m["dim"] in ordnung else 99)
    for m in rohrmengen:
        m["arten"] = ", ".join(sorted(m["arten"]))

    return {"geo": geo, "pfad": pfad, "kritisch": kritisch, "dpRohr": dp_rohr, "dpEinzel": dp_einzel,
            "dpStation": dp_station, "dpZentrale": dp_zentrale, "dpGes": dp_ges, "bar": dp_ges / 1e5,
            "H": dp_ges / (RHO * G_ERDE), "V": v_pumpe, "pumpen": pumpen, "nm": nm, "station": g["typ"],
            "stationVL": g["vlPunkt"], "rohrmengen": rohrmengen, "laenge": sum(m["L"] for m in rohrmengen),
            "inhalt": sum(m["inhalt"] for m in rohrmengen), "vierLeiter": inp.system == "4",
            "wegLaenge": 2 * sum(s["L"] for s in pfad)}
