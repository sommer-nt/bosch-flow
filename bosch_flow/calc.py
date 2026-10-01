"""Rechenkern – 1:1 übertragen aus index.html (compute, seg, pufferProdukt …).

Die Feldnamen von ``Inputs`` entsprechen bewusst den Element-IDs der HTML-Version,
damit Projektdateien (JSON) zwischen beiden Versionen austauschbar bleiben.
Ergebnis-Dictionaries verwenden dieselben Schlüssel wie das JavaScript-Original.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from .data import DIN4708, DIN_MIT, DIN_OHNE, DN_SERIES, NU, PIPES, PUFFER_SIZES, RHO, STATIONS

KW_KALT = 10          # Kaltwassertemperatur [°C]
HEIZ_RESERVE = 3      # kW Reserve über Geräte-Heizleistung
NETZ_VERLUST = 0      # V53: kein pauschaler Netz-/Verteilverlust (Station = Keller-VL)
DLE_MAX_LMIN = 8      # über den DLE laufen immer die ersten 8 l/min
K_RED = 0.7           # Reduktionsfaktor Heizung (HIU)


def _or(x, default):
    """JavaScript-Semantik von ``+wert || default``: 0, None, NaN, '' -> default."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or v == 0:
        return default
    return v


def js_round(x: float) -> int:
    """Math.round aus JavaScript (halbe Werte immer aufrunden, kein Banker's Rounding)."""
    return math.floor(x + 0.5)


# ---------------------------------------------------------------- Eingaben
@dataclass
class Strang:
    """Ein Steigstrang: je Etage Wohnungen links (l) und rechts (r). Index 0 = EG."""
    floors: int = 4
    split: str = "both"            # 'both' = beidseitig, 'one' = einseitig
    cfg: list = field(default_factory=lambda: [{"l": 5, "r": 5} for _ in range(4)])

    @classmethod
    def new(cls, floors: int = 4, split: str = "both", seed: int = 5) -> "Strang":
        s = max(0, min(16, seed))
        return cls(floors, split, [{"l": s, "r": s if split == "both" else 0} for _ in range(floors)])

    def normalized(self) -> "Strang":
        split = self.split if self.split in ("both", "one", "left") else "both"
        cfg = [{"l": max(0, min(16, int(_or(c.get("l"), 0)))),
                "r": max(0, min(16, int(_or(c.get("r"), 0)))) if split == "both" else 0}
               for c in (self.cfg or [])]
        floors = max(1, min(20, int(_or(self.floors, len(cfg) or 1))))
        while len(cfg) < floors:
            cfg.append({"l": 5, "r": 5 if split == "both" else 0})
        return Strang(floors, split, cfg[:floors])

    @property
    def we(self) -> int:
        return sum(floor_total(c, self.split) for c in self.cfg)


@dataclass
class Inputs:
    """Projektweite Eingaben (Defaults = Ausgangswerte der HTML-Version)."""
    system: str = "2"              # '2' = 2-Leiter, '4' = 4-Leiter
    waermequelle: str = "kessel"
    station: str = "flow8000"
    wwstage: int = 0
    wwmode: str = "std"            # 'std' | 'man'
    zapfMenge: float = 10
    zapfTemp: float = 45
    zuheizer: str = "off"          # 'off' | 'on'
    zuheizerKW: float = 11
    dleStufe: float = 53
    qhk: float = 4.0
    dthk: float = 7
    tvl: float = 55
    vlhk: float = 35
    glz: str = "din"               # 'din' | 'tud'
    mat: str = "stahl"
    vmax: float = 1.0
    tsp: float = 8
    tTot: float = 5
    tWied: float = 30
    heizTueber: float = 10
    heizDt: float = 10
    zentral: str = "gemeinsam"     # 'gemeinsam' | 'getrennt'

    def as_fields(self) -> dict:
        return {k: str(v) for k, v in asdict(self).items()}


# ---------------------------------------------------------------- Grundfunktionen
def gz_din(we: float) -> float:
    if we <= 1:
        return 1
    if we in DIN4708:
        return DIN4708[we]
    mx = 18
    if we > mx:
        return DIN4708[mx] + (we - mx) * 0.1
    lo, hi = math.floor(we), math.ceil(we)
    return DIN4708[lo] + (we - lo) * (DIN4708.get(hi, DIN4708[mx]) - DIN4708[lo])


def gz_tud(we: float) -> float:
    if we <= 1:
        return 1
    return js_round(math.pow(we, -0.57) * we * 10) / 10


def gz(we: float, glz: str) -> float:
    return gz_tud(we) if glz == "tud" else gz_din(we)


def dn_label(di: float) -> str:
    """Nächstgelegene genormte DN-Stufe zum Innendurchmesser (für alle Materialien)."""
    best, best_d = DN_SERIES[0], abs(di - DN_SERIES[0][1])
    for s in DN_SERIES:
        d = abs(di - s[1])
        if d < best_d:
            best, best_d = s, d
    return best[0]


def floor_total(c: dict, split: str) -> int:
    return (c["l"] + c["r"]) if split == "both" else c["l"]


def etage_label(idx: int) -> str:
    """Etagen-Index 1 = EG, 2 = 1. OG …"""
    return "EG" if idx <= 1 else f"{idx - 1}. OG"


def puffer_produkt(vol_needed: float) -> dict:
    """Kombination lieferbarer Bosch-Puffer mit minimalem Gesamtvolumen ≥ Bedarf."""
    v = max(0, math.ceil(vol_needed))
    if v <= 0:
        return {"liter": 0, "text": "–", "anzahl": 0, "combo": []}
    sizes = sorted(PUFFER_SIZES)
    mx = sizes[-1]
    for s in sizes:
        if v <= s:
            return {"liter": s, "text": f"{s} l", "anzahl": 1, "combo": [s]}
    best = None
    for n_big in range(math.ceil(v / mx) + 2):
        rest = v - n_big * mx
        combo_rest = []
        if rest > 0:
            r = next((s for s in sizes if rest <= s), None)
            if r is None:
                continue
            combo_rest = [r]
        combo = [mx] * n_big + combo_rest
        total = sum(combo)
        if total >= v and (best is None or total < best["total"]
                           or (total == best["total"] and len(combo) < len(best["combo"]))):
            best = {"combo": combo, "total": total}
    if best is None:
        n = math.ceil(v / mx)
        best = {"combo": [mx] * n, "total": n * mx}
    grp: dict = {}
    for s in best["combo"]:
        grp[s] = grp.get(s, 0) + 1
    parts = [f"{grp[s]} × {s}" if grp[s] > 1 else str(s) for s in sorted(grp, reverse=True)]
    return {"liter": best["total"], "text": " + ".join(parts) + " l", "anzahl": len(best["combo"]),
            "combo": best["combo"]}


def din_interp(pts, n: float) -> float:
    n = max(1, n)
    if n <= pts[0][0]:
        return pts[0][1]
    for i in range(1, len(pts)):
        if n <= pts[i][0]:
            (x0, y0), (x1, y1) = pts[i - 1], pts[i]
            return y0 + (y1 - y0) * (n - x0) / (x1 - x0)
    return pts[-1][1]


def din18015(n_we: float) -> dict:
    """Stromseitige Gleichzeitigkeit (Richtwerte kW am Netzanschluss)."""
    n = max(1, js_round(n_we or 1))
    return {"nWE": n, "mit": din_interp(DIN_MIT, n), "ohne": din_interp(DIN_OHNE, n)}


def station(inp: Inputs) -> dict:
    return STATIONS.get(inp.station, STATIONS["flow8000"])


def stage(inp: Inputs) -> dict:
    st = station(inp)
    i = max(0, min(len(st["stages"]) - 1, int(_or(inp.wwstage, 0))))
    return st["stages"][i]


def dle_is_on(inp: Inputs) -> bool:
    return inp.zuheizer == "on" and inp.system == "2"


def tvl_bounds(inp: Inputs) -> tuple:
    """Erlaubter Bereich der Versorgungs-VL: manuell 40–70, Standard mit HPS 40–50, sonst 50–70 °C."""
    if inp.wwmode == "man":
        return (40, 70)
    return (40, 50) if dle_is_on(inp) else (50, 70)


def zapf_max_lmin(inp: Inputs) -> float:
    """Max. Zapfmenge der kW-Klasse (auf 0,1 l/min abgerundet) – Anschlag im manuellen Modus."""
    zt = min(60, max(45, _or(inp.zapfTemp, 45)))
    dT = max(1, zt - KW_KALT)
    return math.floor(stage(inp)["kw"] / (1.163 * dT) * 1000 / 60 * 10) / 10


# ---------------------------------------------------------------- Abschnitt
def seg(we_cum: float, P: dict) -> dict:
    """Ein Leitungsabschnitt, der ``we_cum`` Wohnungen versorgt."""
    g = gz(we_cum, P["glz"])
    vww_single = min(P["P_WW"] / (1.163 * (P["tvl"] - 25)), 1.3)   # gedeckelt auf 1,3 m³/h (HIU F)
    vww_tot = g * vww_single
    dt_netz = P["tvl"] - P["rlhk"]
    v_heat_wohnung = P["qhk"] / (1.163 * dt_netz)
    v_heat_raw = (max(we_cum - g, 0) if P["wwVorrang"] else we_cum) * v_heat_wohnung
    v_heat = 0 if P["system"] == "4" else v_heat_raw                # 4-Leiter: Strang trägt nur WW
    vtot = v_heat + vww_tot
    d_calc = math.sqrt(vtot * 4 / (P["vmax"] * math.pi * 3600) * 1e6)   # mm (HIU J)
    lst = PIPES[P["mat"]]
    sel = next((p for p in lst if p[2] >= vtot), lst[-1])
    di = sel[1]
    v = vtot / 3600 * 4 / (math.pi * (di / 1000) ** 2)                # reale Geschwindigkeit (HIU M)
    re = P["vmax"] * (d_calc / 1000) / (NU * 1e-6)                    # HIU N
    lam = 0 if re == 0 else 0.309 / math.log10(re / 7) ** 2           # turbulent (HIU P)
    dp = (lam * 1 / (d_calc / 1000) * RHO * P["vmax"] ** 2 / 2) if d_calc else float("nan")  # Pa/m (HIU Q)
    return {"weCum": we_cum, "gz": g, "vWWsingle": vww_single, "vWWtot": vww_tot, "vHeat": v_heat, "Vtot": vtot,
            "dim": dn_label(di), "raw": sel[0], "di": di, "dCalc": d_calc, "v": v, "Re": re, "lam": lam, "dp": dp}


# ---------------------------------------------------------------- Parameter
def build_params(inp: Inputs) -> dict:
    """Entspricht dem Objekt ``P`` in compute() der HTML-Version."""
    st, stg = station(inp), stage(inp)
    qhk_max = st["maxHeatKW"] + HEIZ_RESERVE
    qhk = min(max(0, _or(inp.qhk, 0)), qhk_max)
    P = {"qhk": qhk, "dthk": _or(inp.dthk, 7), "tvl": _or(inp.tvl, 45), "vlhk": _or(inp.vlhk, 35),
         "glz": inp.glz, "mat": inp.mat, "vmax": _or(inp.vmax, 1), "system": inp.system,
         "wwVorrang": st["wwVorrang"], "maxHeatKW": st["maxHeatKW"], "qhkMax": qhk_max}
    P["rlhk"] = P["vlhk"] - P["dthk"]
    ww_mode = inp.wwmode or "std"
    if ww_mode == "man":
        P["zapfTemp"] = min(60, max(45, _or(inp.zapfTemp, 45)))
        dT = max(1, P["zapfTemp"] - KW_KALT)
        max_lmin = stg["kw"] / (1.163 * dT) * 1000 / 60
        wanted = max(5, _or(inp.zapfMenge, 10))
        P["zapfLmin"] = min(wanted, max_lmin)
        P["zapfLminMax"] = max_lmin
        P["zapfGekappt"] = wanted > max_lmin + 0.05
    else:
        P["zapfLmin"] = stg["lmin"]
        P["zapfTemp"] = 45
        P["zapfLminMax"] = stg["lmin"]
        P["zapfGekappt"] = False
    P["stationKW"] = stg["kw"]

    zuheizer_allowed = st["zuheizerFaehig"] is True and P["system"] == "2"
    zuheizer_on = zuheizer_allowed and inp.zuheizer == "on"
    zuheizer_kw = max(0, _or(inp.zuheizerKW, 11))
    dle_stufe = max(35, _or(inp.dleStufe, 53))
    P.update(zuheizerOn=zuheizer_on, zuheizerMaxKW=zuheizer_kw, zuheizerAllowed=zuheizer_allowed,
             dleStufe=dle_stufe, netzVerlust=NETZ_VERLUST, dleStufeZuNiedrig=None)

    # Versorgungs-VL (Keller)
    if ww_mode == "man":
        v = _or(inp.tvl, 0) or (P["zapfTemp"] + NETZ_VERLUST)
        v = 40 if v < 40 else 70 if v > 70 else v
    else:
        lo, hi = (40, 50) if zuheizer_on else (50, 70)
        v = _or(inp.tvl, lo)
        v = lo if v < lo else hi if v > hi else v
    P["vlKeller"] = v
    P["netzTemp"] = max(KW_KALT, P["vlKeller"] - NETZ_VERLUST)
    P["vlhkZuHoch"] = P["vlhk"] > P["netzTemp"] + 0.1
    P["vlhkMax"] = js_round(P["netzTemp"])
    P["vlKellerWW"] = P["zapfTemp"] + NETZ_VERLUST
    P["vlHeizFuehrt"] = False
    P["tvl"] = P["vlKeller"]
    P["P_WW"] = P["zapfLmin"] * 60 / 1000 * 1.163 * (P["zapfTemp"] - KW_KALT)
    P["P_WW_full"] = P["P_WW"]

    # Elektrischer Zuheizer (DLE) als Booster in der Wohnung
    off = dict(zuheizerNeed=0, zuheizerRestNetz=0, zuheizerErschoepft=False, entlastungKW=0)
    if zuheizer_on:
        vges = P["zapfLmin"]
        if P["netzTemp"] >= P["zapfTemp"] - 0.1:
            P.update(off, dleAktiv=False, zuheizerKW=0, dleLmin=0, netzLmin=vges, mischTemp=P["zapfTemp"],
                     zielErreicht=True, zuheizerWirkungslos=True)
        elif dle_stufe <= P["zapfTemp"] + 0.1:
            P.update(off, dleAktiv=True, zuheizerKW=0, dleLmin=0, netzLmin=vges, mischTemp=P["netzTemp"],
                     zielErreicht=False, zuheizerWirkungslos=True, dleStufeZuNiedrig=True)
        else:
            dle_lmin = min(vges, DLE_MAX_LMIN)
            bypass = max(0, vges - DLE_MAX_LMIN)
            p_need = dle_lmin * 60 / 1000 * 1.163 * (dle_stufe - P["netzTemp"])
            p_real = min(zuheizer_kw, p_need)
            t_dle = P["netzTemp"] + p_real / (dle_lmin * 60 / 1000 * 1.163) if dle_lmin > 0 else P["netzTemp"]
            P["mischTemp"] = (dle_lmin * t_dle + bypass * P["netzTemp"]) / vges
            P.update(dleAktiv=True, zuheizerNeed=p_need, zuheizerKW=p_real,
                     zuheizerErschoepft=p_need > zuheizer_kw + 0.05, dleLmin=dle_lmin, netzLmin=bypass,
                     zielErreicht=P["mischTemp"] >= P["zapfTemp"] - 0.5, zuheizerRestNetz=0, entlastungKW=0,
                     zuheizerWirkungslos=False)
    else:
        P.update(off, dleAktiv=False, zuheizerKW=0, dleLmin=0, netzLmin=P["zapfLmin"],
                 zuheizerWirkungslos=False, mischTemp=P["zapfTemp"], zielErreicht=True)
    P["heatOver"] = P["qhk"] > st["maxHeatKW"]
    return P


def _zentrale(P: dict, inp: Inputs, we: float) -> dict:
    """Kessel & Puffer exakt HIU für ``we`` Wohnungen."""
    g = gz(we, P["glz"])
    t_tot = max(1, _or(inp.tTot, 5))
    t_wied = max(10, _or(inp.tWied, 30))
    t_spitz = _or(inp.tsp, 8)
    q_theor = P["P_WW"] * g + P["qhk"] * max(we - g, 0) * K_RED
    q_entn = q_theor * t_tot + (t_spitz - t_tot) * (20 * g - (1 - K_RED) * P["qhk"] * we)
    puffer = (((q_theor * t_tot) + (t_spitz - t_tot) * (P["P_WW"] * g - (1 - K_RED) * P["qhk"] * we))
              / (4.19 * 20 * 1000) * 60000) / 0.9
    qk_zus = max(q_entn / t_wied - (1 - K_RED) * P["qhk"] * we, 0)
    kessel = js_round(qk_zus + we * P["qhk"])
    return {"gz": g, "kRed": K_RED, "tTot": t_tot, "tWied": t_wied, "tSpitz": t_spitz, "Qtheor": q_theor,
            "Qentn": q_entn, "pufferVol": max(0, puffer), "QKzus": qk_zus, "kesselQ": kessel}


# ---------------------------------------------------------------- Strang rechnen
def compute(inp: Inputs, strang: Strang, straenge: list | None = None, active: int = 0) -> dict:
    """Rechnet einen Strang. ``straenge`` = alle Stränge des Projekts (für die gemeinsame Zentrale)."""
    straenge = straenge if straenge is not None else [strang]
    s = strang.normalized()
    floors, split, cfg = s.floors, s.split, s.cfg
    st, stg = station(inp), stage(inp)
    P = build_params(inp)
    sides = 2 if split == "both" else 1

    floor_we = [floor_total(c, split) for c in cfg]
    max_left = max([1] + [c["l"] for c in cfg])
    max_right = max([0] + [c["r"] for c in cfg]) if split == "both" else 0

    def build_side(n):
        return [seg(k, P) for k in range(1, n + 1)]

    per_floor_rows = [{"l": build_side(c["l"]), "r": build_side(c["r"]) if split == "both" else []} for c in cfg]
    gov_n = max(max_left, max_right)
    h_rows = build_side(max(1, gov_n))
    v_rows = []
    for f in range(1, floors + 1):
        we_cum = sum(floor_we[f - 1:])
        v_rows.append({"floor": f, "weFloor": floor_we[f - 1], **seg(we_cum, P)})
    total_we = sum(floor_we)
    single = seg(1, P)

    zentral_mode = inp.zentral or "gemeinsam"
    n_str = len(straenge)
    all_we = sum(x.normalized().we for x in straenge)
    we_z = all_we if (zentral_mode == "gemeinsam" and n_str > 1) else total_we
    z = _zentrale(P, inp, we_z)

    four = P["system"] == "4"
    heat_load = we_z * P["qhk"]
    heiz_tueber = max(5, _or(inp.heizTueber, 10))
    heiz_dt = max(3, _or(inp.heizDt, 10))
    heiz_puffer = js_round((heat_load * (heiz_tueber / 60)) / (1.163 * heiz_dt) * 1000) if four else 0
    heiz_pump = heat_load / (1.163 * max(5, P["dthk"])) if four else 0
    ww_pump = (P["P_WW"] * z["gz"]) / (1.163 * max(5, P["tvl"] - 25)) if four else 0

    keys = ("P_WW", "stationKW", "zapfLmin", "zuheizerOn", "zuheizerKW", "zuheizerMaxKW", "dleStufe", "netzTemp",
            "netzLmin", "dleLmin", "dleAktiv", "dleStufeZuNiedrig", "P_WW_full", "entlastungKW", "zapfTemp",
            "zuheizerNeed", "zuheizerRestNetz", "zuheizerErschoepft", "zuheizerWirkungslos", "mischTemp",
            "zielErreicht", "tvl", "vlKeller", "vlKellerWW", "vlHeizFuehrt", "vlhk", "netzVerlust")
    anlage = {**z, **{k: P[k] for k in keys}, "totalHeat": we_z * P["qhk"], "zuheizerLmin": P["zapfLmin"],
              "wwmode": inp.wwmode or "std", "zentralMode": zentral_mode, "nStraenge": n_str, "weForZentrale": we_z,
              "four": four, "wwPufferVol": z["pufferVol"], "heizPufferVol": heiz_puffer, "heizPumpV": heiz_pump,
              "wwPumpV": ww_pump, "heatLoad": heat_load, "heizTueber": heiz_tueber, "heizDt": heiz_dt}
    return {"P": P, "floors": floors, "split": split, "sides": sides, "cfg": cfg, "floorWE": floor_we,
            "maxLeft": max_left, "maxRight": max_right, "perFloorRows": per_floor_rows, "govN": gov_n,
            "hRows": h_rows, "vRows": v_rows, "totalWE": total_we, "anlage": anlage, "st": st, "stage": stg,
            "nStraenge": n_str, "activeStrang": active, "allWE": all_we, "singleStationV": single["Vtot"],
            "perStationDim": single["dim"]}


def compute_all(inp: Inputs, straenge: list) -> list:
    return [compute(inp, s, straenge, i) for i, s in enumerate(straenge)]


def project_headline(R: dict, inp: Inputs) -> dict:
    """KPI-Werte: bei gemeinsamer Zentrale mit mehreren Strängen projektweit, sonst aktiver Strang."""
    foot = R["vRows"][0]
    if R["anlage"]["zentralMode"] == "gemeinsam" and R["nStraenge"] > 1:
        gs = seg(R["allWE"], R["P"])
        return {"we": R["allWE"], "Vtot": gs["Vtot"], "dim": gs["dim"], "v": gs["v"], "projektweit": True}
    return {"we": R["totalWE"], "Vtot": foot["Vtot"], "dim": foot["dim"], "v": foot["v"], "projektweit": False}


def gesamt_anlage(inp: Inputs, results: list) -> dict:
    """Gesamtübersicht aller Stränge: getrennt = Summe der Einzelanlagen, gemeinsam = eine Zentrale."""
    gtot = sum(r["totalWE"] for r in results)
    first = results[0]
    if first["anlage"]["zentralMode"] == "getrennt":
        return {"we": gtot, "gz": None, "kesselQ": sum(r["anlage"]["kesselQ"] for r in results),
                "pufferVol": sum(r["anlage"]["pufferVol"] for r in results), "getrennt": True}
    z = _zentrale(first["P"], inp, gtot)
    return {"we": gtot, "gz": z["gz"], "kesselQ": z["kesselQ"], "pufferVol": z["pufferVol"], "getrennt": False}


def dle_cell(t_net: float, t_dle: float, vges: float, t_zapf: float, max_kw: float) -> dict:
    """Eine Zelle der DLE-Auslegungshilfe: nötige Leistung, um ``vges`` l/min auf Zapftemperatur zu mischen."""
    if t_net >= t_zapf - 0.1:
        return {"txt": "nicht nötig", "state": "none"}
    if t_dle <= t_net + 0.1:
        return {"txt": "—", "state": "none"}
    dle_lmin = min(vges, DLE_MAX_LMIN)
    bypass = max(0, vges - DLE_MAX_LMIN)
    misch_max = (dle_lmin * t_dle + bypass * t_net) / vges
    if misch_max < t_zapf - 0.05:
        return {"txt": "Stufe zu niedrig", "state": "over", "warn": True,
                "kw": dle_lmin * 60 / 1000 * 1.163 * (t_dle - t_net)}
    need = vges * 60 / 1000 * 1.163 * (t_zapf - t_net)
    return {"txt": None, "state": "ok" if need <= max_kw + 0.05 else "over", "kw": need}


def dle_table(A: dict) -> list:
    """Zeilen der DLE-Auslegungshilfe (analog Bosch Tab. 7)."""
    tn_real = js_round(A["netzTemp"])
    temps = sorted({t for t in (35, 40, 45, 50) if abs(t - tn_real) >= 2} | {tn_real})
    return [{"netzTemp": t, "aktuell": t == tn_real,
             "cells": {stufe: dle_cell(t, stufe, A["zapfLmin"], A["zapfTemp"], A["zuheizerMaxKW"])
                       for stufe in (48, 53, 60)}} for t in temps]
