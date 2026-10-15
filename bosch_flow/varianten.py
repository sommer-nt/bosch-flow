"""Variantenvergleich: dieselbe Planung mit geänderten Eingaben durchrechnen und bewerten.

Jede Variante ist die aktuelle Planung mit wenigen geänderten Feldern (``aenderung``). Für jede Variante
rechnet der unveränderte Rechenkern alle Stränge; daraus entstehen vergleichbare Kennzahlen
(Anschluss, Rohrnetz, Erzeuger, Puffer, Geschwindigkeit). Die Empfehlung wählt unter den Auslegungsvarianten
(Rohrmaterial, niedrigerer Vorlauf, Station, Zentrale) die mit dem kleinsten Bewertungswert; ein höherer Vorlauf,
ein anderes Rechenverfahren (Gleichzeitigkeit) oder ein anderes Leitersystem werden gezeigt, aber nicht automatisch
empfohlen. Preise, Energieeffizienz und Montageaufwand fließen nicht in die Bewertung ein.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .calc import (Inputs, compute_all, gesamt_anlage, puffer_produkt, seg, topologie, tvl_bounds)
from .data import MATNAME, STATIONS

# Gewichte der Bewertung (kleiner = besser, aktuelle Planung = 1,0)
GEWICHT = {"rohr": 0.5, "kessel": 0.25, "puffer": 0.25}
STRAFE_UEBER = 0.15        # je Abschnitt über v_max
STRAFE_ZU_SCHNELL = 0.6    # je Abschnitt über 120 % v_max


@dataclass
class Variante:
    titel: str
    gruppe: str                      # Planung | Rohrmaterial | Vorlauf | Station | Zentrale | Verfahren | System
    aenderung: dict = field(default_factory=dict)
    empfehlbar: bool = True
    hinweis: str = ""


def _dn(dim: str) -> int:
    return int(dim.split()[-1])


def kennzahlen(inp: Inputs, straenge: list, pos: float = 50) -> dict:
    """Vergleichbare Kennzahlen einer Planung (alle Stränge)."""
    res = compute_all(inp, straenge)
    P = res[0]["P"]
    vmax = P["vmax"]
    gemeinsam = res[0]["anlage"]["zentralMode"] == "gemeinsam" and len(res) > 1
    abschnitte = []
    for r in res:
        abschnitte += r["vRows"]
        for fr in r["perFloorRows"]:
            abschnitte += fr["l"] + fr["r"]
    if gemeinsam:
        abschnitte += [seg(a["load"], P) for a in topologie(res, pos)["abschnitte"]]
        anschluss = seg(sum(r["totalWE"] for r in res), P)
    else:
        anschluss = max((r["vRows"][0] for r in res), key=lambda s: s["Vtot"])
    G = gesamt_anlage(inp, res)
    heiz_puffer = (sum(r["anlage"]["heizPufferVol"] for r in res) if G["getrennt"]
                   else res[0]["anlage"]["heizPufferVol"])
    ueber = sum(1 for s in abschnitte if s["v"] > vmax)
    zu_schnell = sum(1 for s in abschnitte if s["v"] > vmax * 1.2)
    return {
        "we": G["we"], "V": anschluss["Vtot"], "anschluss": anschluss["dim"], "vAnschluss": anschluss["v"],
        "steig": max((r["vRows"][0] for r in res), key=lambda s: s["di"])["dim"],
        "dnSumme": sum(_dn(s["dim"]) for s in abschnitte), "abschnitte": len(abschnitte),
        "vMax": max(s["v"] for s in abschnitte), "auslastung": max(s["v"] for s in abschnitte) / vmax,
        "dpMax": max(s["dp"] for s in abschnitte), "ueber": ueber, "zuSchnell": zu_schnell,
        "kessel": G["kesselQ"], "puffer": G["pufferVol"], "pufferText": puffer_produkt(G["pufferVol"])["text"],
        "heizPuffer": heiz_puffer, "tvl": P["tvl"], "vmax": vmax, "getrennt": G["getrennt"],
    }


def bewertung(k: dict, basis: dict) -> float:
    """Bewertungswert relativ zur aktuellen Planung (1,0 = gleich gut, kleiner = besser)."""
    def rel(a, b):
        return a / b if b else (1.0 if not a else 2.0)
    wert = (GEWICHT["rohr"] * rel(k["dnSumme"], basis["dnSumme"]) + GEWICHT["kessel"] * rel(k["kessel"], basis["kessel"])
            + GEWICHT["puffer"] * rel(k["puffer"] + k["heizPuffer"], basis["puffer"] + basis["heizPuffer"]))
    # Geschwindigkeits-Überschreitungen gegenüber der aktuellen Planung: mehr = Strafe, weniger = Bonus
    return (wert + STRAFE_UEBER * (k["ueber"] - basis["ueber"])
            + STRAFE_ZU_SCHNELL * (k["zuSchnell"] - basis["zuSchnell"]))


def standard_varianten(inp: Inputs, n_straenge: int) -> list[Variante]:
    """Sinnvolle Alternativen zur aktuellen Planung."""
    out = [Variante("Aktuelle Planung", "Planung")]
    for m in MATNAME:
        if m != inp.mat:
            out.append(Variante(MATNAME[m], "Rohrmaterial", {"mat": m}))
    lo, hi = tvl_bounds(inp)
    for d in (-5, 5):
        t = min(hi, max(lo, float(inp.tvl) + d))
        if t != float(inp.tvl):
            out.append(Variante(f"Vorlauf {t:.0f} °C", "Vorlauf", {"tvl": t}, empfehlbar=d < 0,
                                hinweis="höherer VL: kleinere Rohre, aber mehr Wärmeverluste und schlechtere "
                                        "Effizienz von Brennwert/Wärmepumpe – Betriebsentscheidung" if d > 0 else
                                "niedrigerer VL: effizienter (Wärmepumpe, Fernwärme), aber größere Rohre"))
    for s, d in STATIONS.items():
        if s != inp.station:
            out.append(Variante(d["name"], "Station",
                                {"station": s, "wwstage": min(int(inp.wwstage), len(d["stages"]) - 1)}, hinweis=d["mode"]))
    if n_straenge > 1:
        z = "getrennt" if inp.zentral == "gemeinsam" else "gemeinsam"
        out.append(Variante(f"Zentrale {z}", "Zentrale", {"zentral": z}))
    g = "tud" if inp.glz == "din" else "din"
    out.append(Variante("TU Dresden" if g == "tud" else "DIN 4708", "Verfahren", {"glz": g}, empfehlbar=False,
                        hinweis="Rechenverfahren der Gleichzeitigkeit – mit dem Planer/Normvorgabe abstimmen"))
    sy = "4" if inp.system == "2" else "2"
    out.append(Variante(f"{sy}-Leiter-System", "System", {"system": sy}, empfehlbar=False,
                        hinweis="4-Leiter: zusätzliches Heiznetz, im Rohrvergleich nicht enthalten" if sy == "4"
                        else "2-Leiter: ein Netz für Heizung und Warmwasser"))
    return out


def anwenden(inp: Inputs, aenderung: dict) -> Inputs:
    neu = replace(inp, **aenderung)
    if neu.system == "4":
        neu = replace(neu, zuheizer="off")
    lo, hi = tvl_bounds(neu)
    return replace(neu, tvl=min(hi, max(lo, float(neu.tvl))))


def vergleich(inp: Inputs, straenge: list, pos: float = 50, varianten: list[Variante] | None = None) -> dict:
    """Alle Varianten rechnen, bewerten und eine Empfehlung bestimmen."""
    varianten = varianten or standard_varianten(inp, len(straenge))
    basis = kennzahlen(inp, straenge, pos)
    zeilen = []
    for v in varianten:
        k = basis if v.gruppe == "Planung" else kennzahlen(anwenden(inp, v.aenderung), straenge, pos)
        zeilen.append({"variante": v, "k": k, "wert": bewertung(k, basis)})
    kandidaten = [z for z in zeilen if z["variante"].empfehlbar
                  and z["k"]["zuSchnell"] <= min(basis["zuSchnell"], 0 if z["variante"].gruppe != "Planung" else 99)]
    best = min(kandidaten, key=lambda z: z["wert"]) if kandidaten else zeilen[0]
    if best["variante"].gruppe != "Planung" and best["wert"] > zeilen[0]["wert"] - 0.01:
        best = zeilen[0]
    return {"basis": basis, "zeilen": zeilen, "empfehlung": best}


def begruendung(z: dict, basis: dict) -> list[str]:
    """Stichpunkte, was eine Variante gegenüber der aktuellen Planung ändert."""
    k = z["k"]
    out = []
    if k["anschluss"] != basis["anschluss"]:
        out.append(f"Anschluss {basis['anschluss']} → {k['anschluss']}")
    d = k["dnSumme"] - basis["dnSumme"]
    if d:
        out.append(f"Nennweiten-Summe {'−' if d < 0 else '+'}{abs(d)} ({abs(d) / basis['dnSumme'] * 100:.0f} %)")
    d = k["kessel"] - basis["kessel"]
    if d:
        out.append(f"Erzeuger {'−' if d < 0 else '+'}{abs(d):.0f} kW")
    d = (k["puffer"] + k["heizPuffer"]) - (basis["puffer"] + basis["heizPuffer"])
    if abs(d) >= 1:
        out.append(f"Puffer {'−' if d < 0 else '+'}{abs(d):.0f} l")
    if k["ueber"] != basis["ueber"]:
        out.append(f"Abschnitte über v_max: {basis['ueber']} → {k['ueber']}")
    return out
