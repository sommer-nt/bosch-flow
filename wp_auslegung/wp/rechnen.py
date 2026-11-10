"""Rechenkern der Wärmepumpen-Schnellauslegung.

Gleicher Rechenweg wie der Block <script id="rechenkern"> in wp_auslegung/index.html – Änderungen in beiden
nachziehen (tests/test_rechnen.py vergleicht beide Versionen über node).

Ablauf
1. Heizlast QH – Vorgabe (z. B. aus DIN EN 12831), überschlägig über Wohnfläche × W/m², über die Gebäudehülle
   (Transmission + Lüftung wie Excel „WP-Auslegung_S“) oder über den Jahresverbrauch
   (Eg,in = Verbrauch · Hu;  Ehg,in = Eg,in − Ew,g,in;  Øh,g = Ehg,in · η / th).
2. Warmwasserzuschlag QTW – Personen × kW/Person (Excel) oder Ew,g,in / (td · 365) (Nachheizzeit).
3. Sperrzeitzuschlag QSperr – 2/4/6 h → 5/10/15 % von QH + QTW.
4. QGES = QH + QTW + QSperr.  Mindestleistung der WP bei A-7: monovalent 1,0 · QGES, monoenergetisch 0,7 · QGES,
   GEG-Hybrid 0,3 · QH (Excel „WP-Auslegung_S“, Erfüllungsoptionen GEG § 71 ff.).
5. Je Gerät (auch als Kaskade) die maximale Heizleistung über der Außentemperatur beim Auslegungsvorlauf:
   Bivalenzpunkt (Schnitt mit der Gebäudekennlinie), Leistung und Abdeckung bei Norm-Außentemperatur,
   Heizstab-Bedarf, Deckungsanteil nach VDI 4650 (Luft/Wasser, parallel) und Taktgrenze (Mindestleistung).
"""
from __future__ import annotations

import math

T_SUCHE_MIN = -25.0          # tiefste Außentemperatur für die Bivalenzpunktsuche
SPERRZUSCHLAG = {0: 0.0, 2: 0.05, 4: 0.10, 6: 0.15}
FAKTOR = {"monovalent": 1.0, "monoenergetisch": 0.7, "hybrid": 0.3}

# Excel „DIN EN 12831 Heizlast nach Verbrauch“
VOLLBENUTZUNGSSTUNDEN = {"EFH": 2100, "MFH": 2000, "Bürogebäude": 1700, "Krankenhaus": 2400,
                         "Schule einschichtig": 1100, "Schule mehrschichtig": 1300}
HEIZWERT = {"gas": (10.42, "m³"), "oel": (10.08, "l"), "pellet": (5.20, "kg"), "kwh": (1.0, "kWh")}
TWW_BEDARF = {  # Nutzenergiebedarf Trinkwarmwasser Qw,b nach DIN V 18599-10 (Auszug)
    "Wohngebäude": (1.1, 0.0343), "Bürogebäude": (0.4, 0.0300), "Krankenhaus": (6.0, 0.4000),
    "Schule ohne Duschen": (0.4, 0.1300), "Schule mit Duschen": (1.5, 0.5000)}
NACHHEIZZEIT = {"Standard": 4, "Gehobener Standard": 3, "Luxus": 2}


def runden_ab(x: float) -> int:
    """Kaufmännisch runden (wie Excel RUNDEN bei positiven Zahlen, identisch in JS)."""
    return math.floor(x + 0.5)


def aufrunden1(x: float) -> float:
    """Excel AUFRUNDEN(x; 1) für x ≥ 0."""
    return math.ceil(x * 10 - 1e-9) / 10


def interp(punkte: list, t: float) -> float:
    """Stückweise linear, außerhalb des Datenbereichs konstant."""
    if t <= punkte[0][0]:
        return punkte[0][1]
    if t >= punkte[-1][0]:
        return punkte[-1][1]
    for (t0, q0), (t1, q1) in zip(punkte, punkte[1:]):
        if t0 <= t <= t1:
            return q0 + (q1 - q0) * (t - t0) / (t1 - t0)
    return punkte[-1][1]


def kurve_bei_vl(kurven: dict | None, vl: float):
    """Liefert (Funktion T -> Q, tiefste erfasste Außentemperatur) beim Vorlauf vl oder None.

    Zwischen den erfassten Vorlauftemperaturen wird linear interpoliert; unterhalb der kleinsten gilt deren Kurve
    (tieferer Vorlauf liefert eher mehr Leistung), oberhalb der größten ist das Gerät nicht auslegbar.
    """
    if not kurven:
        return None
    vls = sorted(float(k) for k in kurven)
    if vl > vls[-1] + 1e-9:
        return None
    if vl <= vls[0]:
        k = kurven[_schluessel(vls[0])]
        return (lambda t: interp(k, t)), k[0][0]
    for v0, v1 in zip(vls, vls[1:]):
        if v0 <= vl <= v1:
            k0, k1 = kurven[_schluessel(v0)], kurven[_schluessel(v1)]
            w = (vl - v0) / (v1 - v0)
            return (lambda t: interp(k0, t) * (1 - w) + interp(k1, t) * w), max(k0[0][0], k1[0][0])
    return None


def _schluessel(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def vdi4650(tabelle: list, anteil_prozent: float) -> float:
    """Deckungsanteil α (Luft/Wasser, parallel) zum Leistungsanteil in % (Tabelle aus dem Excel-Werkzeug)."""
    p = min(100, max(tabelle[0][0], runden_ab(anteil_prozent)))
    for a, alpha in tabelle:
        if a == p:
            return alpha
    return tabelle[0][1]


# ------------------------------------------------------------------------------------------------ Heizlast
def heizlast(e: dict, nat: float) -> dict:
    h = e["heizlast"]
    m = h["methode"]
    ti = e["klima"]["innen"]
    d: dict = {"methode": m}
    hinweise: list[str] = []
    if m == "vorgabe":
        qh = float(h.get("vorgabe_kw") or 0)
    elif m == "flaeche":
        qh = float(h.get("flaeche_m2") or 0) * float(h.get("spez_w_m2") or 0) / 1000
    elif m == "huelle":
        qt = (ti - nat) * float(h.get("huell_a_m2") or 0) * float(h.get("ht") or 0) / 1000
        ql = aufrunden1(0.5 * float(h.get("luftwechsel") or 0) * float(h.get("volumen_m3") or 0) * 0.36 * (ti - nat) / 1000)
        d.update(transmission_kw=qt, lueftung_kw=ql)
        qh = qt + ql
    elif m == "verbrauch":
        hu = float(h.get("heizwert") or 0)
        eg = float(h.get("menge") or 0) * hu
        ew = tww_jahresenergie(e) if h.get("ww_im_verbrauch") else 0.0
        ehg = eg - ew
        th = float(h.get("vbh") or 0)
        eta = float(h.get("nutzungsgrad") or 1)
        qh = ehg * eta / th if th > 0 and ehg > 0 else 0.0
        td = float(e["tww"].get("td") or 4)
        d.update(eg_kwh=eg, ew_kwh=ew, ehg_kwh=ehg, th=th, eta=eta,
                 oh_in_kw=qh + (ew / (td * 365) if td > 0 else 0))
        if ew > eg:
            hinweise.append("Daten prüfen: Warmwasserbedarf größer als der Jahresverbrauch.")
    else:
        raise ValueError(f"Unbekannte Heizlastmethode: {m}")
    d["qh_kw"] = qh
    return {"d": d, "hinweise": hinweise}


def tww_jahresenergie(e: dict) -> float:
    """Ew,g,in nach Excel-Blatt: personenbezogen Qw,b · np · 365, flächenbezogen Qw,b · ANGF · 1,1 · 365."""
    t = e["tww"]
    if t.get("bezug") == "flaeche":
        return float(t.get("qwb") or 0) * float(t.get("flaeche_m2") or 0) * 1.1 * 365
    return float(t.get("qwb") or 0) * float(t.get("personen") or 0) * 365


def tww_zuschlag(e: dict) -> float:
    t = e["tww"]
    if not t.get("aktiv", True):
        return 0.0
    if t.get("methode") == "nachheizzeit":
        td = float(t.get("td") or 0)
        return tww_jahresenergie(e) / (td * 365) if td > 0 else 0.0
    return float(t.get("personen") or 0) * float(t.get("kw_person") or 0)


# ------------------------------------------------------------------------------------------------ Auslegung
def last(t: float, qh_sperr: float, qtw: float, nat: float, thg: float) -> float:
    """Gebäudekennlinie: Heizung linear von QH (bei NAT) auf 0 (bei Heizgrenze), Warmwasser konstant."""
    if thg <= nat:
        return qh_sperr + qtw
    return qh_sperr * max(0.0, (thg - t) / (thg - nat)) + qtw


def bewerte(geraet: dict, n: int, vl: float, r: dict, daten: dict, katalog: dict | None = None) -> dict:
    """Bewertet ein Gerät (n Stück in Kaskade) für die Anlage r (Ergebnis aus rechne ohne Geräteteil)."""
    nat, thg, qges = r["nat"], r["heizgrenze"], r["qges"]
    qhs, qtw = r["qh"] + r["qsperr"], r["qtw"]
    serie = next(s for s in daten["serien"] if s["id"] == geraet["serie"])
    kat = (katalog or {}).get("geraete", {}).get(geraet["id"], {})
    out = {"geraet": geraet["id"], "serie": serie["id"], "serienname": serie["name"], "kurz": geraet["kurz"],
           "n": n, "vl": vl, "moeglich": False, "grund": "", "ok": False}
    vl_max = kat.get("vl_max")
    km = kurve_bei_vl(geraet["max"], vl)
    if km is None:
        out["grund"] = f"Keine Leistungsdaten für {_zahl(vl)} °C Vorlauf"
        return out
    if vl_max is not None and vl > vl_max:
        out["grund"] = f"Vorlauf über {_zahl(vl_max)} °C"
        return out
    fmax, t_daten = km
    kmin = kurve_bei_vl(geraet.get("min"), vl)
    q = lambda t: n * fmax(t)  # noqa: E731
    lt = lambda t: last(t, qhs, qtw, nat, thg)  # noqa: E731
    out["moeglich"] = True

    q_nat, q_a7 = q(nat), q(-7.0)
    out.update(q_nat=q_nat, q_a7=q_a7, abdeckung=q_nat / qges if qges > 0 else 0.0,
               heizstab_kw=max(0.0, qges - q_nat), t_daten_min=t_daten)
    anteil = 100.0 * q_nat / qges if qges > 0 else 100.0
    out["leistungsanteil"] = min(100, runden_ab(anteil))
    out["deckung"] = vdi4650(daten["vdi4650_luft_parallel"], anteil)

    # Bivalenzpunkt: höchste Außentemperatur, ab der die WP die Last allein deckt
    t0 = max(T_SUCHE_MIN, math.ceil(t_daten))
    ts = [float(t) for t in range(int(t0), int(math.floor(thg)) + 1)]
    biv, art = None, "unter"
    if ts:
        f = [q(t) - lt(t) for t in ts]
        if f[-1] < 0:
            art = "nicht"           # reicht selbst an der Heizgrenze nicht
        elif f[0] >= 0:
            biv, art = ts[0], "unter"   # deckt die Last im ganzen Datenbereich
        else:
            for i in range(len(ts) - 1, 0, -1):
                if f[i - 1] < 0 <= f[i]:
                    biv = ts[i - 1] + (ts[i] - ts[i - 1]) * (-f[i - 1]) / (f[i] - f[i - 1])
                    art = "punkt"
                    break
    out["bivalenz"], out["bivalenz_art"] = biv, art

    # Taktgrenze: ab dieser Außentemperatur liegt die Gebäudelast unter der Mindestleistung eines Geräts
    takt = None
    if kmin is not None:
        fmin = kmin[0]
        tt = [nat + i * 0.5 for i in range(int((thg + 10 - nat) * 2) + 1)]
        g = [fmin(t) - lt(t) for t in tt]
        for i in range(1, len(tt)):
            if g[i - 1] < 0 <= g[i]:
                takt = tt[i - 1] + (tt[i] - tt[i - 1]) * (-g[i - 1]) / (g[i] - g[i - 1])
                break
        if takt is None and g and g[0] >= 0:
            takt = nat
        out["q_min_nat"] = fmin(nat)
    out["taktgrenze"] = takt

    # Prüfung
    krit = r["kriterium"]
    mind_ok = q_a7 >= r["mindestleistung"] - 1e-9
    if krit == "monovalent":
        ok = q_nat >= qges - 1e-9
        grund = "" if ok else "Leistung bei Norm-Außentemperatur zu klein"
    else:
        ok = mind_ok
        grund = "" if ok else "Mindestleistung bei A-7 nicht erreicht"
    eh = serie.get("eheizer_kw")
    if eh is not None and krit == "monoenergetisch" and out["heizstab_kw"] > n * eh + 1e-9:
        ok, grund = False, f"Heizstab-Bedarf über {_zahl(n * eh)} kW"
    out.update(ok=ok, grund=grund, mindest_ok=mind_ok, heizstab_max_kw=(n * eh if eh is not None else None))
    out["ueberdimensioniert"] = bool(ok and out["abdeckung"] > 1.5)
    return out


def _zahl(x: float) -> str:
    return (f"{x:.1f}".rstrip("0").rstrip(".")).replace(".", ",")


def kennlinien(geraet: dict, n: int, vl: float, r: dict) -> dict:
    """Wertetabellen für Diagramme (1-K-Raster von NAT−3 bis Heizgrenze+3)."""
    km = kurve_bei_vl(geraet["max"], vl)
    kmin = kurve_bei_vl(geraet.get("min"), vl)
    t0, t1 = math.floor(min(r["nat"], -7.0)) - 3, math.ceil(r["heizgrenze"]) + 3
    ts = [float(t) for t in range(int(t0), int(t1) + 1)]
    qhs = r["qh"] + r["qsperr"]
    return {"t": ts,
            "last": [last(t, qhs, r["qtw"], r["nat"], r["heizgrenze"]) for t in ts],
            "max": [n * km[0](t) for t in ts] if km else None,
            "min": [kmin[0](t) for t in ts] if kmin else None}


def rechne(e: dict, daten: dict, katalog: dict | None = None) -> dict:
    """Komplette Auslegung zu den Eingaben e (Format siehe STANDARD in wp/projekt.py)."""
    k = e["klima"]
    nat, thg = float(k["nat"]), float(k["heizgrenze"])
    vl = float(e["vl"])
    hl = heizlast(e, nat)
    qh = hl["d"]["qh_kw"]
    qtw = tww_zuschlag(e)
    sperr = int(e.get("sperrzeit_h") or 0)
    qsperr = (qh + qtw) * SPERRZUSCHLAG.get(sperr, 0.0)
    qges = qh + qtw + qsperr
    krit = e.get("auslegung", "monoenergetisch")
    mindest = FAKTOR[krit] * (qh if krit == "hybrid" else qges)
    r = {"nat": nat, "heizgrenze": thg, "innen": float(k["innen"]), "vl": vl, "heizlast": hl["d"], "qh": qh,
         "qtw": qtw, "tww_kwh": tww_jahresenergie(e), "qsperr": qsperr, "qges": qges, "kriterium": krit,
         "faktor": FAKTOR[krit], "mindestleistung": mindest, "hinweise": list(hl["hinweise"])}
    if qges <= 0:
        r["hinweise"].append("Heizlast eingeben.")

    serien = e.get("serien") or [s["id"] for s in daten["serien"]]
    # je Gerät die kleinste passende Anzahl (Kaskade bis kaskade_max)
    kandidaten = []
    for g in daten["geraete"]:
        if g["serie"] not in serien:
            continue
        smax = next(s for s in daten["serien"] if s["id"] == g["serie"])["kaskade_max"]
        best = None
        for n in range(1, smax + 1):
            b = bewerte(g, n, vl, r, daten, katalog)
            if best is None:
                best = b
            if not b["moeglich"]:
                break
            if b["ok"]:
                best = b
                break
        kandidaten.append(best)
    r["kandidaten"] = kandidaten

    # Empfehlung je Serie (kleinste passende Leistung bei A-7) und gesamt: Einzelgerät vor Kaskade,
    # dann Reihenfolge der Serien in geraete.json (aktuelle R290-Geräte zuerst)
    passend = [c for c in kandidaten if c["ok"] and qges > 0]
    je_serie = {}
    for c in passend:
        s = c["serie"]
        if s not in je_serie or (c["n"], c["q_a7"]) < (je_serie[s]["n"], je_serie[s]["q_a7"]):
            je_serie[s] = c
    r["empfehlung_je_serie"] = [je_serie[s["id"]]["geraet"] + "|" + str(je_serie[s["id"]]["n"])
                                for s in daten["serien"] if s["id"] in je_serie]
    rang = {s["id"]: i for i, s in enumerate(daten["serien"])}
    gesamt = sorted(je_serie.values(), key=lambda c: (c["n"] > 1, rang[c["serie"]], c["q_a7"]))
    r["empfehlung"] = (gesamt[0]["geraet"] + "|" + str(gesamt[0]["n"])) if gesamt else None

    # gewähltes Gerät (Vorgabe des Nutzers, sonst Empfehlung)
    wahl = e.get("auswahl") or {}
    gid, n = wahl.get("geraet"), int(wahl.get("anzahl") or 1)
    if not gid and r["empfehlung"]:
        gid, n = r["empfehlung"].split("|")[0], int(r["empfehlung"].split("|")[1])
    geraet = next((g for g in daten["geraete"] if g["id"] == gid), None)
    if geraet is not None and qges > 0:
        r["gewaehlt"] = bewerte(geraet, n, vl, r, daten, katalog)
        r["kennlinien"] = kennlinien(geraet, n, vl, r) if r["gewaehlt"]["moeglich"] else None
        r["energie"] = energie(e, r, katalog)
    else:
        r["gewaehlt"], r["kennlinien"], r["energie"] = None, None, None
    return r


def energie(e: dict, r: dict, katalog: dict | None) -> dict | None:
    """Grobe Jahresbilanz: Wärme = QH · Vollbenutzungsstunden + Warmwasser; Strom über SCOP (EN 14825)."""
    g = r["gewaehlt"]
    if not g or not g["moeglich"]:
        return None
    h = e["heizlast"]
    if h["methode"] == "verbrauch" and r["heizlast"]["ehg_kwh"] > 0:
        q_heiz = r["heizlast"]["ehg_kwh"] * r["heizlast"]["eta"]
    else:
        q_heiz = r["qh"] * float(h.get("vbh") or 2100)
    q_ww = r["tww_kwh"] if e["tww"].get("aktiv", True) else 0.0
    q = q_heiz + q_ww
    kat = (katalog or {}).get("geraete", {}).get(g["geraet"], {})
    s35, s55 = kat.get("scop35"), kat.get("scop55")
    if s35 is None or s55 is None:
        return {"waerme_kwh": q, "heiz_kwh": q_heiz, "ww_kwh": q_ww, "scop": None}
    w = min(1.0, max(0.0, (r["vl"] - 35) / 20))
    scop = s35 + (s55 - s35) * w
    q_wp = q * g["deckung"]
    strom_wp = q_wp / scop
    strom_hs = q - q_wp
    return {"waerme_kwh": q, "heiz_kwh": q_heiz, "ww_kwh": q_ww, "scop": scop, "strom_wp_kwh": strom_wp,
            "strom_heizstab_kwh": strom_hs, "umwelt_kwh": q_wp - strom_wp}

