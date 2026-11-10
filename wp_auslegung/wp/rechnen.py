"""Rechenkern der Wärmepumpen-Schnellauslegung.

Gleicher Rechenweg wie der Block <script id="rechenkern"> in wp_auslegung/index.html – Änderungen in beiden
nachziehen (tests/test_rechnen.py vergleicht beide Versionen über node).

Ablauf
1. Heizlast QH – Vorgabe (z. B. aus DIN EN 12831), überschlägig über Wohnfläche × W/m², über die Gebäudehülle
   (Transmission + Lüftung wie Excel „WP-Auslegung_S“) oder über den Jahresverbrauch
   (Eg,in = Verbrauch · Hu;  Ehg,in = Eg,in − Ew,g,in;  Øh,g = Ehg,in · η / th).
2. Warmwasser – Tagesbedarf aus Liter je Person bei 45 °C (oder DIN V 18599-10), Ew,g,in = Qw,b · np · 365.
   Zuschlag QTW automatisch: beim Jahresverbrauch wie Excel-Blatt Ew,g,in / (td · 365) (Øh,in), sonst
   Personen × Lastprofil (≤ 30 l → 0,10 · ≤ 50 l → 0,20 · darüber 0,25 kW/P). Speicher- bzw. Pufferstemperatur aus
   Zapftemperatur (+5 K Speicher, +10 K Frischwasserstation), Ladevorlauf +5 K.
3. Sperrzeitzuschlag QSperr – 2/4/6 h → 5/10/15 % von QH + QTW.
4. QGES = QH + QTW + QSperr.  Mindestleistung der WP bei A-7: monovalent 1,0 · QGES, monoenergetisch 0,7 · QGES,
   GEG-Hybrid 0,3 · QH (Excel „WP-Auslegung_S“, Erfüllungsoptionen GEG § 71 ff.).
5. Je Gerät (auch als Kaskade) die maximale Heizleistung über der Außentemperatur beim Auslegungsvorlauf:
   Bivalenzpunkt (Schnitt mit der Gebäudekennlinie), Leistung und Abdeckung bei Norm-Außentemperatur,
   Heizstab-Bedarf, Deckungsanteil nach VDI 4650 (Luft- bzw. Sole/Wasser, parallel) und Taktgrenze (Mindestleistung).
   Sole/Wasser: Leistung konstant (Sole ≈ 0 °C), Entzugsleistung und Sondenlänge als Richtwert (VDI 4640).
6. Luft/Wasser-Außeneinheit: Volumenstrom und Rohrdimension der Verbindungsleitung (v ≤ 1 m/s, Darcy-Weisbach).
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
T_WW_BEZUG = 45.0            # Bezugstemperatur der Warmwassermenge (l/(P·d) bei 45 °C)
C_WASSER = 1.163             # Wh/(l·K)
# Verbindungsleitung Außeneinheit (Innendurchmesser mm, Rauigkeit mm)
ROHRE = [("Cu 22 × 1", 20.0, 0.0015), ("Cu 28 × 1,5", 25.0, 0.0015), ("Cu 35 × 1,5", 32.0, 0.0015),
         ("Cu 42 × 1,5", 39.0, 0.0015), ("Cu 54 × 2", 50.0, 0.0015), ("St 60,3 × 2,9 (DN 50)", 54.5, 0.045),
         ("St 76,1 × 2,9 (DN 65)", 70.3, 0.045), ("St 88,9 × 3,2 (DN 80)", 82.5, 0.045),
         ("St 114,3 × 3,6 (DN 100)", 107.1, 0.045), ("St 139,7 × 4 (DN 125)", 131.7, 0.045)]
V_MAX_ROHR = 1.0             # m/s
R_MAX_ROHR = 200.0           # Pa/m
ZUSCHLAG_EINZEL = 1.3        # Einzelwiderstände pauschal +30 %


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
    """Liefert (Funktion T -> Q, tiefste, höchste erfasste Außentemperatur) beim Vorlauf vl oder None.

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
        return (lambda t: interp(k, t)), k[0][0], k[-1][0]
    for v0, v1 in zip(vls, vls[1:]):
        if v0 <= vl <= v1:
            k0, k1 = kurven[_schluessel(v0)], kurven[_schluessel(v1)]
            w = (vl - v0) / (v1 - v0)
            return ((lambda t: interp(k0, t) * (1 - w) + interp(k1, t) * w), max(k0[0][0], k1[0][0]),
                    min(k0[-1][0], k1[-1][0]))
    return None


def _schluessel(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def vdi4650(tabelle: list, anteil_prozent: float) -> float:
    """Deckungsanteil α (parallel) zum Leistungsanteil in % (Tabelle VDI 4650 aus dem Excel-Werkzeug)."""
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


def tww_qwb_person(e: dict) -> float:
    """Nutzenergie Warmwasser je Person und Tag [kWh/(P·d)]: aus Litern bei 45 °C oder DIN V 18599-10."""
    t = e["tww"]
    if t.get("bezug", "liter") == "liter":
        return float(t.get("liter_p") or 0) * C_WASSER * (T_WW_BEZUG - float(t.get("t_kw") or 10)) / 1000
    return float(t.get("qwb") or 0)


def tww_jahresenergie(e: dict) -> float:
    """Ew,g,in nach Excel-Blatt: personenbezogen Qw,b · np · 365, flächenbezogen Qw,b · ANGF · 1,1 · 365."""
    t = e["tww"]
    if t.get("bezug") == "flaeche":
        return float(t.get("qwb") or 0) * float(t.get("flaeche_m2") or 0) * 1.1 * 365
    return tww_qwb_person(e) * float(t.get("personen") or 0) * 365


def lastprofil_aus_liter(liter: float) -> float:
    """Lastprofil des Excel-Werkzeugs aus der Warmwassermenge je Person (45 °C)."""
    if liter <= 30:
        return 0.10
    if liter <= 50:
        return 0.20
    return 0.25


def tww_zuschlag(e: dict) -> tuple[float, str, float | None]:
    """(QTW in kW, wirksame Methode, kW je Person oder None)."""
    t = e["tww"]
    if not t.get("aktiv", True):
        return 0.0, "aus", None
    m = t.get("methode", "auto")
    if m == "auto":
        if e["heizlast"]["methode"] == "verbrauch":
            m = "nachheizzeit"
        elif t.get("bezug", "liter") == "liter":
            kwp = lastprofil_aus_liter(float(t.get("liter_p") or 0))
            return float(t.get("personen") or 0) * kwp, "personen", kwp
        else:
            m = "personen"
    if m == "nachheizzeit":
        td = float(t.get("td") or 0)
        return (tww_jahresenergie(e) / (td * 365) if td > 0 else 0.0), "nachheizzeit", None
    kwp = float(t.get("kw_person") or 0)
    return float(t.get("personen") or 0) * kwp, "personen", kwp


def tww_temperaturen(e: dict) -> dict:
    """Speicher-/Puffertemperatur, Ladevorlauf und Tagesvolumen bei Speichertemperatur."""
    t = e["tww"]
    friwa = t.get("system") == "friwa"
    t_zapf = float(t.get("zapftemp") or 45)
    t_sp = t_zapf + (10.0 if friwa else 5.0)
    t_kw = float(t.get("t_kw") or 10)
    q_tag = tww_jahresenergie(e) / 365
    vol = q_tag * 1000 / (C_WASSER * (t_sp - t_kw)) if t_sp > t_kw else 0.0
    return {"system": "friwa" if friwa else "speicher", "t_zapf": t_zapf, "t_speicher": t_sp, "vl_tww": t_sp + 5.0,
            "q_tag_kwh": q_tag, "volumen_tag_l": vol, "grossanlage": bool(not friwa and vol > 400)}


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
    fmax, t_daten, t_daten_max = km
    kmin = kurve_bei_vl(geraet.get("min"), vl)
    q = lambda t: n * fmax(t)  # noqa: E731
    lt = lambda t: last(t, qhs, qtw, nat, thg)  # noqa: E731
    out["moeglich"] = True

    q_nat, q_a7 = q(nat), q(-7.0)
    out.update(q_nat=q_nat, q_a7=q_a7, abdeckung=q_nat / qges if qges > 0 else 0.0,
               heizstab_kw=max(0.0, qges - q_nat), t_daten_min=t_daten, t_daten_max=t_daten_max)
    anteil = 100.0 * q_nat / qges if qges > 0 else 100.0
    out["leistungsanteil"] = min(100, runden_ab(anteil))
    tab = daten["vdi4650_sole_parallel"] if serie.get("quelle") == "sole" else daten["vdi4650_luft_parallel"]
    out["deckung"] = vdi4650(tab, anteil)
    vl_dev = vl_max if vl_max is not None else max(float(v) for v in geraet["max"])
    out["vl_max_geraet"] = vl_dev
    out["vl_tww_ok"] = r["tww"]["vl_tww"] <= vl_dev + 1e-9 if r["tww"]["aktiv"] else True

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
    """Wertetabellen für Diagramme (1-K-Raster von NAT−3 bis Heizgrenze+3).

    Gerätekurven nur im erfassten Datenbereich (außerhalb None) – es wird nichts extrapoliert dargestellt.
    """
    km = kurve_bei_vl(geraet["max"], vl)
    kmin = kurve_bei_vl(geraet.get("min"), vl)
    t0, t1 = math.floor(min(r["nat"], -7.0)) - 3, math.ceil(r["heizgrenze"]) + 3
    ts = [float(t) for t in range(int(t0), int(t1) + 1)]
    qhs = r["qh"] + r["qsperr"]
    return {"t": ts,
            "last": [last(t, qhs, r["qtw"], r["nat"], r["heizgrenze"]) for t in ts],
            "max": werte_im_bereich(km, ts, n) if km else None,
            "min": werte_im_bereich(kmin, ts, 1) if kmin else None}


def werte_im_bereich(k, ts: list, n: int) -> list:
    return [n * k[0](t) if k[1] - 1e-9 <= t <= k[2] + 1e-9 else None for t in ts]


def rechne(e: dict, daten: dict, katalog: dict | None = None) -> dict:
    """Komplette Auslegung zu den Eingaben e (Format siehe STANDARD in wp/projekt.py)."""
    k = e["klima"]
    nat, thg = float(k["nat"]), float(k["heizgrenze"])
    vl = float(e["vl"])
    hl = heizlast(e, nat)
    qh = hl["d"]["qh_kw"]
    qtw, tww_methode, tww_kwp = tww_zuschlag(e)
    quelle = e.get("waermequelle", "luft")
    sperr = int(e.get("sperrzeit_h") or 0)
    qsperr = (qh + qtw) * SPERRZUSCHLAG.get(sperr, 0.0)
    qges = qh + qtw + qsperr
    krit = e.get("auslegung", "monoenergetisch")
    mindest = FAKTOR[krit] * (qh if krit == "hybrid" else qges)
    r = {"nat": nat, "heizgrenze": thg, "innen": float(k["innen"]), "vl": vl, "heizlast": hl["d"], "qh": qh,
         "qtw": qtw, "tww_kwh": tww_jahresenergie(e), "qsperr": qsperr, "waermequelle": quelle, "qges": qges, "kriterium": krit,
         "faktor": FAKTOR[krit], "mindestleistung": mindest, "hinweise": list(hl["hinweise"])}
    tw = tww_temperaturen(e)
    tw.update(aktiv=bool(e["tww"].get("aktiv", True)), methode=tww_methode, kw_person=tww_kwp,
              qwb_person=tww_qwb_person(e) if e["tww"].get("bezug") != "flaeche" else None)
    r["tww"] = tw
    if qh <= 0:
        r["hinweise"].append("Heizlast eingeben.")

    serien = e.get("serien") or [s["id"] for s in daten["serien"]]
    # je Gerät die kleinste passende Anzahl (Kaskade bis kaskade_max)
    kandidaten = []
    for g in daten["geraete"]:
        sd = next(s for s in daten["serien"] if s["id"] == g["serie"])
        if g["serie"] not in serien or sd.get("quelle", "luft") != quelle:
            continue
        smax = sd["kaskade_max"]
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
    passend = [c for c in kandidaten if c["ok"] and qh > 0]
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
    if geraet is not None and qh > 0:
        r["gewaehlt"] = bewerte(geraet, n, vl, r, daten, katalog)
        r["kennlinien"] = kennlinien(geraet, n, vl, r) if r["gewaehlt"]["moeglich"] else None
        r["energie"] = energie(e, r, katalog)
    else:
        r["gewaehlt"], r["kennlinien"], r["energie"] = None, None, None
    r["leitung"] = leitung(e, r)
    r["erdreich"] = erdreich(e, r, katalog)
    return r


def leitung(e: dict, r: dict) -> dict | None:
    """Verbindungsleitung Außeneinheit ↔ Gebäude: Volumenstrom bei max. Leistung A-7, kleinstes Rohr mit
    v ≤ 1 m/s und R ≤ 200 Pa/m."""
    g = r.get("gewaehlt")
    a = e.get("aufstellung") or {}
    lang = float(a.get("entfernung_m") or 0)
    if not g or not g["moeglich"] or r["waermequelle"] != "luft" or lang <= 0:
        return None
    dt = float(a.get("spreizung") or 5)
    q = g["q_a7"]
    vs = q / (C_WASSER * dt)                     # m³/h
    for rohr in ROHRE:                           # sonst bleibt das größte Rohr
        wahl = (rohr, rohr_werte(rohr, vs))
        if wahl[1][0] <= V_MAX_ROHR + 1e-9 and wahl[1][1] <= R_MAX_ROHR + 1e-9:
            break
    (name, di, _), (v, rr) = wahl
    dp = rr * 2 * lang * ZUSCHLAG_EINZEL / 1000  # kPa (Vor- und Rücklauf)
    return {"laenge_m": lang, "spreizung": dt, "q_kw": q, "volumenstrom_m3h": vs, "rohr": name, "di_mm": di,
            "v_ms": v, "r_pa_m": rr, "dp_kpa": dp}


def rohr_werte(rohr: tuple, vs_m3h: float) -> tuple[float, float]:
    """(Geschwindigkeit m/s, Druckgefälle R Pa/m) – Darcy-Weisbach, λ nach Swamee-Jain, Wasser ca. 35 °C."""
    d = rohr[1] / 1000
    v = vs_m3h / 3600 / (math.pi * d * d / 4)
    re = v * d / 0.7e-6
    if re < 2300:
        lam = 64 / re if re > 0 else 0.0
    else:
        lam = 0.25 / math.log10(rohr[2] / 1000 / (3.7 * d) + 5.74 / re ** 0.9) ** 2
    return v, lam / d * 994 * v * v / 2


def erdreich(e: dict, r: dict, katalog: dict | None) -> dict | None:
    """Sole/Wasser: Entzugsleistung Q0 = Q · (1 − 1/COP B0/W35) und Sondenlänge als Richtwert (VDI 4640)."""
    g = r.get("gewaehlt")
    if not g or not g["moeglich"] or r["waermequelle"] != "sole":
        return None
    kat = (katalog or {}).get("geraete", {}).get(g["geraet"], {})
    cop = kat.get("cop_b0w35")
    if not cop:
        return None
    w_m = float((e.get("aufstellung") or {}).get("entzug_w_m") or 50)
    q0 = g["q_nat"] * (1 - 1 / cop)
    return {"cop": cop, "q_entzug_kw": q0, "entzug_w_m": w_m, "sondenlaenge_m": q0 * 1000 / w_m}


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
    q_ww = r["tww_kwh"] if r["tww"]["aktiv"] else 0.0
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

