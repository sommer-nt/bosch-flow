"""Schemata als Szenen (siehe ``zeichnung``): Netzschema, Netztopologie, Anlagenschema, Diagramme.

Aufbau und Beschriftung folgen den Canvas-Zeichnungen der HTML-Version (drawSchema, drawTopoT, drawPlant,
drawChart).
"""
from __future__ import annotations

import math

from .calc import DN_SERIES, etage_label, gz_din, gz_tud, puffer_produkt, seg, topologie
from .report import fmt
from .zeichnung import Icon, Pfeil, Szene, farben


ZENTRALE = "#0a3b5c"   # Wärmezentrale in beiden Farbschemata dunkelblau mit weißer Schrift (Kontrast)


def _wdn(dn: str) -> float:
    i = next((k for k, s in enumerate(DN_SERIES) if s[0] == dn), 1)
    return max(0, i * 0.8)


def _status_farbe(r: dict, R: dict, F: dict) -> str:
    """Grün = v ≤ vmax, Orange = grenzwertig (≤ 1,2 · vmax), Rot = zu schnell – wie die Auslegungs-Tabelle."""
    vmax = R["P"]["vmax"]
    return F["dn"] if r["v"] <= vmax else F["warn"] if r["v"] <= vmax * 1.2 else F["vl"]


def _info(titel: str, r: dict, R: dict) -> str:
    vmax = R["P"]["vmax"]
    status = "OK" if r["v"] <= vmax else "grenzwertig" if r["v"] <= vmax * 1.2 else "zu schnell"
    return (f"<b>{titel}</b><br>{r['weCum']} WE · GZ {fmt(r['gz'], 1)}<br>V̇ = {fmt(r['Vtot'], 2)} m³/h"
            f"<br><b>{r['dim']}</b> ({r['raw']}) · di {fmt(r['di'], 1)} mm<br>v = {fmt(r['v'], 2)} m/s · "
            f"Δp = {fmt(r['dp'])} Pa/m<br>Status: <b>{status}</b> (v_max {fmt(vmax, 1)} m/s)")


# ====================================================================== Netzschema (ein Strang)
def netzschema(R: dict, dunkel: bool = False) -> Szene:
    F = farben(dunkel)
    cfg, floors = R["cfg"], R["floors"]
    both = R["split"] == "both"
    max_l = max([1] + [c["l"] for c in cfg])
    max_r = max([0] + [c["r"] for c in cfg]) if both else 0
    dx, fh, sw = 88, 100, 76                       # Stationsabstand, Etagenhöhe, Kartenbreite
    rand_l = 70
    xr = rand_l + 40 + max_l * dx                 # Steigstrang
    breite = xr + 40 + max(max_r, 0) * dx + 30
    top = 26
    hoehe = top + floors * fh + 70
    s = Szene(max(breite, 640), hoehe)
    if breite < 640:                              # schmale Stränge mittig
        off = (640 - breite) / 2
        rand_l += off
        xr += off

    def y_of(f):                                  # Rohrhöhe der Etage f (1 = EG unten)
        return top + (floors - f) * fh + 52

    for f, c in enumerate(cfg, start=1):
        y = y_of(f)
        s.text(rand_l - 12, y, etage_label(f), 11, F["soft"], fett=True, anker="end")
        for seite, n in (("l", c["l"]), ("r", c["r"] if both else 0)):
            if n <= 0:
                continue
            sg = -1 if seite == "l" else 1
            x_end = xr + sg * (40 + n * dx - dx / 2 + sw / 2 + 6)
            for off, col in ((-3, F["vl"]), (3, F["rl"])):
                s.linie(xr + sg * 7, y + off, x_end, y + off, col, 2.6)
            rows = R["perFloorRows"][f - 1][seite]
            for k in range(1, n + 1):
                xs = xr + sg * (40 + k * dx - dx / 2)
                s.rechteck(xs - sw / 2, y - 44, xs + sw / 2, y - 12, fuell=F["card"], rand=F["cardline"], radius=5)
                s.text(xs, y - 34, f"St. {k}", 10, F["ink"], fett=True)
                s.text(xs, y - 21, f"{fmt(R['singleStationV'], 2)} m³/h", 8, F["soft"])
                r = rows[n - k]                     # Abschnitt trägt n-k+1 WE
                we = n - k + 1
                if we > 1:
                    s.text(xs, y + 13, f"Σ {we} WE", 8, F["soft"], fett=True)
                s.text(xs, y + 25, f"{fmt(r['Vtot'], 2)} m³/h", 8, F["dn"] if we == 1 else F["ink"], fett=we > 1)
                s.text(xs, y + 37, r["dim"], 8.5, _status_farbe(r, R, F), fett=True)
                s.info(xs, y, _info(f"{etage_label(f)} · {'links' if seite == 'l' else 'rechts'} · Abschnitt an St. {k}", r, R))
    # Steigstrang
    y_top, y_bot = y_of(floors) - 6, hoehe - 52
    s.linie(xr - 5, y_top, xr - 5, y_bot, F["vl"], 5)
    s.linie(xr + 5, y_top, xr + 5, y_bot, F["rl"], 5)
    for r in R["vRows"]:
        yb = y_of(r["floor"]) + fh / 2 if r["floor"] > 1 else (y_of(1) + y_bot) / 2 + 4
        col = _status_farbe(r, R, F)
        s.rechteck(xr - 25, yb - 9, xr + 25, yb + 9, fuell=F["dnbg"] if col == F["dn"] else F["card"], rand=col,
                   breite=0.8 if col == F["dn"] else 1.6, radius=8)
        s.text(xr, yb, r["dim"], 9.5, col, fett=True)
        s.info(xr, yb, _info(f"Steigstrang unter {etage_label(r['floor'])}"
                             + (" · Strangfuß" if r["floor"] == 1 else ""), r, R))
    # Wärmezentrale
    s.rechteck(xr - 150, y_bot, xr + 150, y_bot + 30, fuell=ZENTRALE, radius=7)
    s.text(xr, y_bot + 15, "WÄRMEZENTRALE — Kessel · Puffer · Pumpe", 10.5, "#ffffff", fett=True)
    # Legende
    yl = hoehe - 10
    for i, (col, txt) in enumerate(((F["vl"], "Vorlauf"), (F["rl"], "Rücklauf"), (F["dnbg"], "Nennweite je Abschnitt"))):
        x = 14 + i * 110
        s.rechteck(x, yl - 5, x + 10, yl + 5, fuell=col, rand=F["dn"] if i == 2 else None, radius=2)
        s.text(x + 15, yl, txt, 9, F["soft"], anker="start")
    return s


# ====================================================================== Netztopologie (alle Stränge, V54)
def topologie_szene(results: list, pos: float = 50, gross: bool = False, dunkel: bool = False) -> Szene:
    """Hauptstrang mit Strang-Abzweigen und Wärmezentrale an der gewählten Position (drawTopoT)."""
    F = farben(dunkel)
    W, H = 1000, (360 if gross else 290)
    s = Szene(W, H)
    n = len(results)
    T = topologie(results, pos)
    P = results[0]["P"]
    main_y = H * 0.36
    zw, zh = 118, 90
    lane_l, lane_r = zw + 40, W - 24
    bx = [lane_l + 40 + (i + 0.5) * ((lane_r - lane_l - 40) / n) for i in range(n)]
    left = T["links"]
    zcx = lane_l - 6 if left <= 0 else lane_r + 6 if left >= n else (bx[left - 1] + bx[left]) / 2
    s.rechteck(lane_l - 8, main_y - 13, lane_r, main_y + 13, fuell=F["bg"], radius=13)
    xs = sorted([lane_l, *bx, lane_r])
    for a, b in zip(xs, xs[1:]):
        mid = (a + b) / 2
        load = (sum(r["totalWE"] for i, r in enumerate(results) if bx[i] <= a + 0.5) if mid < zcx
                else sum(r["totalWE"] for i, r in enumerate(results) if bx[i] >= b - 0.5))
        if load <= 0:
            continue
        lw = max(3, min(11, 2.5 + _wdn(seg(load, P)["dim"])))
        s.linie(a, main_y - lw / 2 - 1, b, main_y - lw / 2 - 1, F["vl"], lw)
        s.linie(a, main_y + lw / 2 + 1, b, main_y + lw / 2 + 1, F["rl"], lw)
    bw, bh = (104, 46) if gross else (92, 42)
    for i, r in enumerate(results):
        x = bx[i]
        stub = main_y - 46
        byy = stub - bh
        s.linie(x - 4, main_y, x - 4, stub, F["vl"], 3)
        s.linie(x + 4, main_y, x + 4, stub, F["rl"], 3)
        s.kreis(x, main_y, 4, fuell=F["navy"])
        s.rechteck(x - bw / 2, byy, x + bw / 2, byy + bh, fuell=F["card"], rand=F["cardline"], breite=1.2, radius=7)
        s.rechteck(x - bw / 2, byy + 7, x - bw / 2 + 4, byy + bh - 7, fuell=F["navy"])
        s.text(x + 2, byy + bh / 2 - 7, f"Strang {i + 1}", 12 if gross else 11, F["ink"], fett=True)
        s.text(x + 2, byy + bh / 2 + 9, f"{r['totalWE']} WE · {r['vRows'][0]['dim']}", 10 if gross else 9.5,
               F["soft"], fett=True)
        f0 = r["vRows"][0]
        s.info(x, byy + bh / 2, f"<b>Strang {i + 1}</b><br>{r['floors']} Etagen · {r['totalWE']} WE · "
                                f"{'beidseitig' if r['split'] == 'both' else 'einseitig'}<br>Strangfuß <b>{f0['dim']}</b> · "
                                f"{fmt(f0['Vtot'], 2)} m³/h · v {fmt(f0['v'], 2)} m/s")
    cr = 11 if gross else 10
    for a in T["abschnitte"]:
        x = bx[a["strang"] - 1]
        cy = main_y + (24 if gross else 22)
        s.kreis(x, cy, cr, fuell=F["warn"] if a["kritisch"] else F["accent"], rand=F["papier"], breite=2)
        s.text(x, cy, str(a["strang"]), 12 if gross else 11, "#ffffff", fett=True)
        s.info(x, cy, f"<b>Hauptstrang · Abschnitt {a['strang']}</b><br>{a['load']} WE kumuliert<br>"
                      f"V̇ = {fmt(a['V'], 2)} m³/h<br><b>{a['dn']}</b> · v = {fmt(a['v'], 2)} m/s"
                      + ("<br><b>◆ maßgeblich (höchste Geschwindigkeit)</b>" if a["kritisch"] else ""))
    zx = max(6, min(W - zw - 6, zcx - zw / 2))
    zy = main_y + 64
    mlw = max(4, min(11, 2.5 + _wdn(T["gesamt"]["dim"])))
    s.linie(zcx - 5, main_y - mlw / 2 - 1, zcx - 5, zy, F["vl"], 4)
    s.linie(zcx + 5, main_y + mlw / 2 + 1, zcx + 5, zy, F["rl"], 4)
    s.rechteck(zx, zy, zx + zw, zy + zh, fuell=ZENTRALE, radius=10)
    s.rechteck(zx + zw / 2 - 16, zy + 12, zx + zw / 2 + 16, zy + 42, fuell="#2c6f99", rand="#ffffff", breite=2,
               radius=5)
    s.kreis(zx + zw / 2, zy + 27, 4, rand="#ffffff", breite=2)
    s.text(zx + zw / 2, zy + 55, "Wärmezentrale", 11, "#ffffff", fett=True)
    s.text(zx + zw / 2, zy + 69, "Erzeuger · Puffer · Pumpe", 8, "#d5e2ec")
    s.text(zx + zw / 2, zy + 82, f"Σ {T['gesamtWE']} WE · {T['gesamt']['dim']}", 9.5, "#ffffff", fett=True)
    g = T["gesamt"]
    s.info(zx + zw / 2, zy + zh / 2, f"<b>Wärmezentrale</b> ({T['label']})<br>Σ {T['gesamtWE']} WE · "
                                     f"V̇ = {fmt(g['Vtot'], 2)} m³/h<br>Anschluss <b>{g['dim']}</b> · v {fmt(g['v'], 2)} m/s")
    s.text(lane_l - 8, main_y + 16, "Hauptstrang", 11, F["soft"], fett=True, anker="start", vanker="top")
    return s


# ====================================================================== Anlagenschema (Heizzentrale)
QUELLE_NAME = {"kessel": "Brennwertkessel", "fernwaerme": "Fernwärme", "wp": "Wärmepumpe"}


def _karte(s: Szene, x0, y0, x1, y1, F):
    s.rechteck(x0, y0, x1, y1, fuell=F["card"], rand=F["cardline"], breite=1.2, radius=12, unten=True)


def _komponente(s: Szene, cx, cy, w, h, icon, titel, wert, unter, F, ib=52):
    """Einheitliche Karte: Icon oben, Titel, Kennwert, Unterzeile – Raster für alle Bauteile."""
    _karte(s, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, F)
    y0 = cy - (ib + 80) / 2 - 14                        # Inhalt senkrecht mittig, auch in hohen Karten
    s.add(Icon(icon, cx - ib / 2, y0 + 14, cx + ib / 2, y0 + 14 + ib, F["icon_invert"]))
    s.text(cx, y0 + ib + 30, titel, 11, F["ink"], fett=True)
    s.text(cx, y0 + ib + 50, wert, 14, F["accent"], fett=True)
    if unter:
        s.text(cx, y0 + ib + 68, unter, 9, F["soft"])


def _temperatur(s: Szene, cx, y_karte, temp, farbe, beschriftung, F):
    """Temperatur-Plakette über einem Puffer (wie in der HTML-Version): farbige Pille mit Thermometer-Punkt,
    Zeiger nach unten auf die Karte, Beschriftung darüber."""
    txt = f"{fmt(temp)} °C"
    w, h = 30 + len(txt) * 7.2, 22
    y0 = y_karte - 34
    s.add(Pfeil(cx, y0 + h - 2, cx, y_karte - 1, farbe, 2.5))
    s.rechteck(cx - w / 2, y0, cx + w / 2, y0 + h, fuell=farbe, radius=11)
    s.kreis(cx - w / 2 + 12, y0 + h / 2, 4, fuell="#ffffff")
    s.text(cx - w / 2 + 21, y0 + h / 2, txt, 11.5, "#ffffff", fett=True, anker="start")
    if beschriftung:
        s.text(cx, y0 - 9, beschriftung, 9, F["soft"])


def _leitung(s: Szene, x0, x1, y, farbe, F, oben: str = "", unten: str = "", pfeil: bool = True):
    """Vorlauf (Farbe, mit Pfeil) über Rücklauf (blau); Beschriftung mittig über bzw. unter dem Leitungspaar."""
    yv, yr = y - 8, y + 8
    if pfeil:
        s.add(Pfeil(x0, yv, x1, yv, farbe, 3))
    else:
        s.linie(x0, yv, x1, yv, farbe, 3)
    s.linie(x0, yr, x1, yr, F["rl"], 3)
    if oben:
        s.text((x0 + x1) / 2, yv - 9, oben, 9.5, farbe, fett=True, vanker="bottom")
    if unten:
        s.text((x0 + x1) / 2, yr + 9, unten, 9, F["soft"], vanker="top")


def anlagenschema(R: dict, headline: dict, dunkel: bool = False, quelle: str = "") -> Szene:
    """Heizzentrale als aufgeräumtes Schema: Erzeuger → Puffer → Netzpumpe → Wohnungsstationen.
    2-Leiter: ein Leitungspaar; 4-Leiter: je ein Strang für Heizung (rot) und Trinkwasser (gold)."""
    F = farben(dunkel)
    A, st = R["anlage"], R["st"]
    four = A["four"]
    W = 1000
    n_we = A["weForZentrale"]
    zapf = fmt(A["zapfLmin"], 1).removesuffix(",0")
    name = "Flow 7000 (F7002 HPS)" if A["zuheizerOn"] else st["name"]
    # Raster: Spalten-Mitten und Kartenmaße
    X_ERZ, X_PUF, X_PMP = 95, 330, 520
    KW, KH = 150, 180                                   # Erzeuger-/Pufferkarte
    SX0, SX1 = 700, W - 30                              # Stationskarte
    if not four:
        pp = puffer_produkt(A["pufferVol"])
        reihen = [dict(y=175, farbe=F["vl"], titel="Bereitschaftspuffer", vol=A["pufferVol"], prod=pp,
                       pumpe=headline["Vtot"], temp=A["vlKeller"], temp_txt="Versorgungs-VL",
                       netz=f"{headline['dim']} · {fmt(headline['Vtot'], 2)} m³/h",
                       netz2=f"v {fmt(headline['v'], 2)} m/s · an Station {fmt(A['netzTemp'])} °C")]
        H, top, bot = 315, 85, 265
    else:
        reihen = [dict(y=170, farbe=F["vl"], titel="Puffer Heizung", vol=A["heizPufferVol"],
                       prod=puffer_produkt(A["heizPufferVol"]), pumpe=A["heizPumpV"], temp=R["P"]["vlhk"],
                       temp_txt="Heizungs-VL",
                       netz="Heizungsnetz", netz2=""),
                  dict(y=420, farbe=F["gold"], titel="Puffer Trinkwasser", vol=A["wwPufferVol"],
                       prod=puffer_produkt(A["wwPufferVol"]), pumpe=A["wwPumpV"], temp=A["vlKeller"],
                       temp_txt="TWW-VL Keller",
                       netz="Trinkwassernetz", netz2="")]
        H, top, bot = 560, 80, 510
    s = Szene(W, H)
    # Erzeuger: eine Karte, über alle Reihen
    ym = (reihen[0]["y"] + reihen[-1]["y"]) / 2
    eh = reihen[-1]["y"] - reihen[0]["y"] + KH         # bündig mit den Pufferkarten
    _komponente(s, X_ERZ, ym, KW, eh, "erzeuger", QUELLE_NAME.get(quelle, "Wärmeerzeuger"),
                f"{fmt(A['kesselQ'])} kW", "Erzeugerleistung", F)
    s.info(X_ERZ, ym, f"<b>Wärmeerzeuger</b><br>Kessel-/FW-Leistung <b>{fmt(A['kesselQ'])} kW</b><br>"
                      f"Q theoretisch {fmt(A['Qtheor'], 1)} kW · GZ {fmt(A['gz'], 1)}<br>Totzeit {fmt(A['tTot'])} min · "
                      f"Wiederaufheizzeit {fmt(A['tWied'])} min")
    for r in reihen:
        y = r["y"]
        _komponente(s, X_PUF, y, KW, KH, "puffer", r["titel"], f"{fmt(r['vol'])} l",
                    f"Auswahl {r['prod']['text']}" if r["prod"]["liter"] else "nächste Normgröße", F)
        _temperatur(s, X_PUF, y - KH / 2, r["temp"], r["farbe"], r["temp_txt"], F)
        s.info(X_PUF, y, f"<b>{r['titel']}</b><br>berechnet {fmt(r['vol'])} l<br>Auswahl <b>{r['prod']['text']}</b>"
                         f"<br>{r['temp_txt']} {fmt(r['temp'])} °C")
        # Netzpumpe im Rücklauf; der Vorlauf läuft über der Pumpe durch
        g = 26
        s.add(Icon("pumpe", X_PMP - g / 2, y + 8 - g / 2, X_PMP + g / 2, y + 8 + g / 2, F["icon_invert"]))
        s.linie(X_PMP - g / 2 - 4, y - 8, X_PMP + g / 2 + 10, y - 8, r["farbe"], 3)
        s.text(X_PMP, y + 28, "Netzpumpe", 10.5, F["ink"], fett=True, vanker="top")
        s.text(X_PMP, y + 44, f"Rücklauf · {fmt(r['pumpe'], 2)} m³/h", 9, F["soft"], vanker="top")
        s.info(X_PMP, y + 8, f"<b>Netzpumpe</b> (Rücklauf)<br>V̇ = {fmt(r['pumpe'], 2)} m³/h")
        # Leitungen: Erzeuger → Puffer → Pumpe → Stationen
        _leitung(s, X_ERZ + KW / 2, X_PUF - KW / 2, y, r["farbe"], F)
        _leitung(s, X_PUF + KW / 2, X_PMP - g / 2 - 2, y, r["farbe"], F, pfeil=False)
        _leitung(s, X_PMP + g / 2 + 2, SX0, y, r["farbe"], F, oben=r["netz"], unten=r["netz2"])
    # Wohnungsstationen
    _karte(s, SX0, top, SX1, bot, F)
    sx = (SX0 + SX1) / 2
    s.text(sx, top + 22, f"{n_we}× Wohnungsstation", 12.5, F["ink"], fett=True)
    s.text(sx, top + 40, f"{name} · {st['mode']}", 9, F["soft"])
    ib = 50
    if not four:
        kreise = [(sx - 72, reihen[0]["y"] - 14, "heizkreis", "Heizkreis", f"≤ {st['maxHeatKW']} kW"),
                  (sx + 72, reihen[0]["y"] - 14, "trinkwasser", "Trinkwasser", f"{fmt(A['stationKW'])} kW · {zapf} l/min")]
    else:
        kreise = [(sx, reihen[0]["y"] - 4, "heizkreis", "Heizkreis", f"≤ {st['maxHeatKW']} kW"),
                  (sx, reihen[1]["y"] - 4, "trinkwasser", "Trinkwasser", f"{fmt(A['stationKW'])} kW · {zapf} l/min")]
    for cx, cy, icon, titel, unter in kreise:
        s.add(Icon(icon, cx - ib / 2, cy - ib / 2, cx + ib / 2, cy + ib / 2, F["icon_invert"]))
        s.text(cx, cy + ib / 2 + 14, titel, 10.5, F["ink"], fett=True)
        s.text(cx, cy + ib / 2 + 29, unter, 9, F["soft"])
    if A["zuheizerOn"]:
        s.rechteck(sx - 100, bot - 30, sx + 100, bot - 10, fuell=F["gold"], radius=10)
        s.text(sx, bot - 20, f"DLE {fmt(A['zuheizerMaxKW'])} kW · Stufe {fmt(A['dleStufe'])} °C", 9.5, "#ffffff",
               fett=True)
    s.info(sx, (top + bot) / 2, f"<b>{n_we}× {name}</b><br>{st['mode']}<br>Heizung ≤ {st['maxHeatKW']} kW · "
                                f"WW {fmt(A['stationKW'])} kW / {fmt(A['zapfLmin'], 1)} l/min @ {fmt(A['zapfTemp'])} °C"
                                f"<br>Netztemperatur an Station {fmt(A['netzTemp'])} °C")
    # Legende: eine ruhige Zeile
    yl = H - 22
    eintraege = ([(F["vl"], "Heizungsvorlauf"), (F["gold"], "Trinkwasservorlauf"), (F["rl"], "Rücklauf")] if four
                 else [(F["vl"], "Vorlauf"), (F["rl"], "Rücklauf")])
    x = 20
    for farbe, txt in eintraege:
        s.linie(x, yl, x + 22, yl, farbe, 3)
        s.text(x + 28, yl, txt, 9.5, F["soft"], anker="start")
        x += 40 + len(txt) * 5.6
    s.text(W - 30, yl, "4-Leiter-System · Heizung und Trinkwasser getrennt" if four
           else "2-Leiter-System · Heizung und Trinkwasser über ein Leitungspaar", 9.5, F["soft"], anker="end")
    return s


# ====================================================================== Pufferspeicher
PUFFER_FORM = {500: (60, 150), 750: (72, 165), 1000: (82, 180), 1500: (100, 195)}   # Breite, Höhe (px)


def puffer_szene(A: dict, dunkel: bool = False) -> Szene:
    """Gewählte Bosch-Puffer als Behälter nebeneinander; der Füllstand zeigt den berechneten Bedarf
    im Verhältnis zum gewählten Volumen (2-Leiter: Bereitschaftspuffer, 4-Leiter: Heizung und Trinkwasser)."""
    F = farben(dunkel)
    gruppen = ([("Puffer Heizung", A["heizPufferVol"], F["vl"]), ("Puffer Trinkwasser", A["wwPufferVol"], F["gold"])]
               if A["four"] else [("Bereitschaftspuffer", A["pufferVol"], F["accent"])])
    W, H = 1000, 330
    s = Szene(W, H)
    boden = 260
    breite_gr = W / len(gruppen)
    for g, (titel, bedarf, farbe) in enumerate(gruppen):
        pp = puffer_produkt(bedarf)
        combo = sorted(pp["combo"], reverse=True)
        anteil = min(1.0, bedarf / pp["liter"]) if pp["liter"] else 0
        cx = breite_gr * (g + 0.5)
        s.text(cx, 24, titel, 12.5, F["ink"], fett=True)
        s.text(cx, 44, f"Bedarf {fmt(bedarf)} l · Auswahl {pp['text']} = {fmt(pp['liter'])} l · "
                       f"Reserve {fmt(pp['liter'] - bedarf)} l", 9.5, F["soft"])
        formen = [PUFFER_FORM.get(l, (90, 190)) for l in combo]
        luecke = 26
        gesamt = sum(w for w, _ in formen) + luecke * (len(formen) - 1)
        skala = min(1.0, (breite_gr - 60) / gesamt) if gesamt else 1
        x = cx - gesamt * skala / 2
        for liter, (w, h) in zip(combo, formen):
            w, h = w * skala, h * min(1.0, skala * 1.4)
            x0, x1, y0 = x, x + w, boden - h
            # Behälter: Mantel, Füllstand, Deckel
            s.rechteck(x0, y0, x1, boden, fuell=F["panel"], rand=F["cardline"], breite=1.5, radius=w / 5,
                       unten=True)
            hf = (h - 10) * anteil
            if hf > 2:
                s.rechteck(x0 + 5, boden - 5 - hf, x1 - 5, boden - 5, fuell=farbe, radius=min(w / 7, hf / 2),
                           unten=True)
                s.linie(x0 - 6, boden - 5 - hf, x1 + 6, boden - 5 - hf, farbe, 1.5, "dot")
            s.text((x0 + x1) / 2, boden + 16, f"{liter} l", 11, F["ink"], fett=True)
            s.info((x0 + x1) / 2, (y0 + boden) / 2, f"<b>Bosch-Puffer {liter} l</b><br>{titel}<br>"
                                                     f"Füllung nach Bedarf {fmt(anteil * 100)} %")
            x = x1 + luecke * skala
        s.text(cx, boden + 40, f"{fmt(anteil * 100)} % des gewählten Volumens werden gebraucht", 9.5, farbe, fett=True)
    return s


# ====================================================================== Diagramme
def diagramm(reihen: list, ylab: str, xlab: str = "kumulierte Wohneinheiten", W: float = 560,
             H: float = 300) -> Szene:
    """reihen: [(name, farbe, gestrichelt, [(x, y), ...]), ...]"""
    F = farben(False)
    s = Szene(W, H)
    L, Rr, T, B = 56, 16, 40, 42
    w, h = W - L - Rr, H - T - B
    xs = [x for _, _, _, pts in reihen for x, _ in pts]
    ys = [y for _, _, _, pts in reihen for _, y in pts]
    x0, x1 = min(xs), max(xs) if max(xs) > min(xs) else min(xs) + 1
    ymax = math.ceil(max(ys) * 1.1 * 10) / 10 or 1

    def px(x):
        return L + (x - x0) / (x1 - x0) * w

    def py(y):
        return T + h - y / ymax * h

    for i in range(6):
        yy = ymax * i / 5
        s.linie(L, py(yy), L + w, py(yy), F["grid"], 1)
        s.text(L - 6, py(yy), fmt(yy, 1), 9, F["soft"], anker="end")
    schritt = max(1, math.ceil((x1 - x0 + 1) / 12))
    for x in range(int(x0), int(x1) + 1):
        if (x - int(x0)) % schritt == 0 or x == int(x1):
            s.text(px(x), T + h + 12, str(x), 9, F["soft"])
    s.text(L + w / 2, H - 8, xlab, 9.5, F["soft"])
    s.text(14, T + h / 2, ylab, 9.5, F["soft"], anker="middle")
    lx = L
    for name, col, strich, pts in reihen:
        for (a, b), (c, d) in zip(pts, pts[1:]):
            s.linie(px(a), py(b), px(c), py(d), col, 2.2, "dash" if strich else None)
        s.linie(lx, 16, lx + 18, 16, col, 2.6, "dash" if strich else None)
        s.text(lx + 23, 16, name, 10, F["ink"], fett=True, anker="start")
        lx += 30 + len(name) * 6.4
    return s


def diagramm_volumenstrom(P: dict, n_we: int) -> Szene:
    xs = list(range(1, max(2, n_we) + 1))
    other = {**P, "glz": "din" if P["glz"] == "tud" else "tud"}
    a, b = ("TU Dresden", "DIN 4708") if P["glz"] == "tud" else ("DIN 4708", "TU Dresden")
    return diagramm([(f"V̇ {a}", "#0a3b5c", False, [(k, seg(k, P)["Vtot"]) for k in xs]),
                     (f"V̇ {b}", "#c8102e", True, [(k, seg(k, other)["Vtot"]) for k in xs])], "Volumenstrom [m³/h]")


def diagramm_gleichzeitigkeit(n_we: int) -> Szene:
    xs = list(range(1, max(2, n_we) + 1))
    return diagramm([("DIN 4708", "#0a3b5c", False, [(k, gz_din(k)) for k in xs]),
                     ("TU Dresden", "#2f7d32", False, [(k, gz_tud(k)) for k in xs])], "Gleichzeitigkeit GZ")
