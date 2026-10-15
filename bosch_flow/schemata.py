"""Schemata als Szenen (siehe ``zeichnung``): Netzschema, Netztopologie, Anlagenschema, Diagramme.

Aufbau und Beschriftung folgen den Canvas-Zeichnungen der HTML-Version (drawSchema, drawTopoT, drawPlant,
drawChart).
"""
from __future__ import annotations

import math

from .calc import DN_SERIES, etage_label, gz_din, gz_tud, puffer_produkt, seg, topologie
from .report import fmt
from .zeichnung import Icon, Pfeil, Szene, farben


def _wdn(dn: str) -> float:
    i = next((k for k, s in enumerate(DN_SERIES) if s[0] == dn), 1)
    return max(0, i * 0.8)


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
                s.text(xs, y + 37, r["dim"], 8.5, F["dn"], fett=True)
    # Steigstrang
    y_top, y_bot = y_of(floors) - 6, hoehe - 52
    s.linie(xr - 5, y_top, xr - 5, y_bot, F["vl"], 5)
    s.linie(xr + 5, y_top, xr + 5, y_bot, F["rl"], 5)
    for r in R["vRows"]:
        yb = y_of(r["floor"]) + fh / 2 if r["floor"] > 1 else (y_of(1) + y_bot) / 2 + 4
        s.rechteck(xr - 25, yb - 9, xr + 25, yb + 9, fuell=F["dnbg"], rand=F["dn"], breite=0.8, radius=8)
        s.text(xr, yb, r["dim"], 9.5, F["dn"], fett=True)
    # Wärmezentrale
    s.rechteck(xr - 150, y_bot, xr + 150, y_bot + 30, fuell=F["navy"], radius=7)
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
    cr = 11 if gross else 10
    for a in T["abschnitte"]:
        x = bx[a["strang"] - 1]
        cy = main_y + (24 if gross else 22)
        s.kreis(x, cy, cr, fuell=F["warn"] if a["kritisch"] else F["accent"], rand=F["papier"], breite=2)
        s.text(x, cy, str(a["strang"]), 12 if gross else 11, "#ffffff", fett=True)
    zx = max(6, min(W - zw - 6, zcx - zw / 2))
    zy = main_y + 64
    mlw = max(4, min(11, 2.5 + _wdn(T["gesamt"]["dim"])))
    s.linie(zcx - 5, main_y - mlw / 2 - 1, zcx - 5, zy, F["vl"], 4)
    s.linie(zcx + 5, main_y + mlw / 2 + 1, zcx + 5, zy, F["rl"], 4)
    s.rechteck(zx, zy, zx + zw, zy + zh, fuell=F["navy"], radius=10)
    s.rechteck(zx + zw / 2 - 16, zy + 12, zx + zw / 2 + 16, zy + 42, fuell="#2c6f99", rand="#ffffff", breite=2,
               radius=5)
    s.kreis(zx + zw / 2, zy + 27, 4, rand="#ffffff", breite=2)
    s.text(zx + zw / 2, zy + 55, "Wärmezentrale", 11, "#ffffff", fett=True)
    s.text(zx + zw / 2, zy + 69, "Erzeuger · Puffer · Pumpe", 8, "#d5e2ec")
    s.text(zx + zw / 2, zy + 82, f"Σ {T['gesamtWE']} WE · {T['gesamt']['dim']}", 9.5, "#ffffff", fett=True)
    s.text(lane_l - 8, main_y + 16, "Hauptstrang", 11, F["soft"], fett=True, anker="start", vanker="top")
    return s


# ====================================================================== Anlagenschema (Heizzentrale)
def _tap(s: Szene, x0, y0, w, h, col):
    """Wasserhahn (Trinkwasser) – Ersatz für das fehlende icons/tap-water.svg der HTML-Version."""
    s.rechteck(x0 + w * .30, y0 + h * .18, x0 + w * .62, y0 + h * .34, rand=col, breite=2, radius=3)
    s.linie(x0 + w * .46, y0 + h * .06, x0 + w * .46, y0 + h * .18, col, 2)
    s.linie(x0 + w * .34, y0 + h * .06, x0 + w * .58, y0 + h * .06, col, 2)
    s.linie(x0 + w * .62, y0 + h * .26, x0 + w * .78, y0 + h * .26, col, 2.4)
    s.linie(x0 + w * .78, y0 + h * .26, x0 + w * .78, y0 + h * .44, col, 2.4)
    for i, dy in enumerate((.58, .74)):
        s.kreis(x0 + w * .78, y0 + h * dy, w * (.06 - i * .01), fuell=col)


def _pumpe(s: Szene, x, y, r, F):
    s.kreis(x, y, r, fuell=F["card"], rand=F["ink"], breite=2)
    s.text(x + 1, y, "▶", r * 0.95, F["ink"])


def _badge(s: Szene, x, y, txt, col, caption, F):
    w = 18 + len(txt) * 6.2
    s.text(x, y - 18, caption, 8.5, F["soft"])
    s.rechteck(x - w / 2, y - 9, x + w / 2, y + 9, fuell=col, radius=9)
    s.text(x, y, f"● {txt}", 10, "#ffffff", fett=True)


def anlagenschema(R: dict, headline: dict, dunkel: bool = False) -> Szene:
    F = farben(dunkel)
    A, st = R["anlage"], R["st"]
    four = A["four"]
    W = 1000
    H = 430 if four else 350
    s = Szene(W, H)
    inv = F["icon_invert"]
    X_ERZ, X_PUF, X_PMP, X_STA = 100, 305, 470, W - 165
    n_we = A["weForZentrale"]
    mid = 140 if not four else 190
    ib = 80
    # Erzeuger
    s.add(Icon("erzeuger", X_ERZ - ib / 2, mid - ib / 2, X_ERZ + ib / 2, mid + ib / 2, inv))
    s.text(X_ERZ, mid + ib / 2 + 16, "Wärmeerzeuger", 12, F["ink"], fett=True)
    s.text(X_ERZ, mid + ib / 2 + 31, "Kessel / FW / WP", 10, F["soft"])
    s.text(X_ERZ, mid + ib / 2 + 50, f"{fmt(A['kesselQ'])} kW", 15, F["accent"], fett=True)
    net_end = X_STA - 150
    if not four:
        pp = puffer_produkt(A["pufferVol"])
        s.add(Icon("puffer", X_PUF - ib / 2, mid - ib / 2 - 6, X_PUF + ib / 2, mid + ib / 2 + 6, inv))
        _badge(s, X_PUF, mid - 66, f"{fmt(A['vlKeller'])} °C", F["vl"], "Versorgungs-VL", F)
        s.text(X_PUF, mid + ib / 2 + 16, "Bereitschaftspuffer", 12, F["ink"], fett=True)
        s.text(X_PUF, mid + ib / 2 + 33, f"{fmt(A['pufferVol'])} l", 13, F["accent"], fett=True)
        s.text(X_PUF, mid + ib / 2 + 49, f"Auswahl {pp['text']}" if pp["liter"] else "nächste Normgröße", 9, F["soft"])
        _pumpe(s, X_PMP, mid, 22, F)
        s.text(X_PMP, mid + ib / 2 + 16, "Netzpumpe", 12, F["ink"], fett=True)
        yv, yr = mid - 6, mid + 6
        for x0, x1 in ((X_ERZ + 44, X_PUF - 44), (X_PUF + 44, X_PMP - 24), (X_PMP + 24, net_end)):
            s.add(Pfeil(x0, yv, x1, yv, F["vl"], 3))
            s.linie(x1, yr, x0, yr, F["rl"], 3)
        s.text(X_PMP + 34, yv - 14, "Versorgungsnetz · Vorlauf", 10.5, F["vl"], fett=True, anker="start")
        s.text((X_PMP + net_end) / 2 + 10, yr + 18, "Rücklauf", 10.5, F["rl"], fett=True)
        s.text((X_PMP + net_end) / 2 + 10, mid - 34,
               f"{headline['dim']} · {fmt(headline['Vtot'], 2)} m³/h · v {fmt(headline['v'], 2)} m/s", 10, F["ink"],
               fett=True)
        _badge(s, net_end - 30, mid + 40, f"{fmt(A['netzTemp'])} °C", F["vl"], "an Station", F)
    else:
        ww, hz = puffer_produkt(A["wwPufferVol"]), puffer_produkt(A["heizPufferVol"])
        for yy, titel, vol, prod, pump, netz, col in (
                (mid - 85, "Puffer Heizung", A["heizPufferVol"], hz, A["heizPumpV"], "Heizungsnetz · Vorlauf", F["vl"]),
                (mid + 85, "Puffer Trinkwasser", A["wwPufferVol"], ww, A["wwPumpV"], "Trinkwassernetz · Vorlauf", F["gold"])):
            s.add(Icon("puffer", X_PUF - 30, yy - 34, X_PUF + 30, yy + 34, inv))
            s.text(X_PUF, yy - 44, titel, 10.5, F["ink"], fett=True)
            s.text(X_PUF, yy + 46, f"{fmt(vol)} l · Auswahl {prod['text']}", 9, F["soft"])
            _pumpe(s, X_PMP, yy, 18, F)
            s.text(X_PMP, yy - 30, "Netzpumpe " + ("Heizung" if "Heiz" in titel else "Trinkwasser"), 9.5, F["ink"],
                   fett=True)
            s.text(X_PMP, yy + 32, f"{fmt(pump, 1)} m³/h", 9, F["soft"])
            for x0, x1 in ((X_ERZ + 44, X_PUF - 32), (X_PUF + 32, X_PMP - 20), (X_PMP + 20, net_end)):
                s.add(Pfeil(x0, yy - 5, x1, yy - 5, col, 3))
                s.linie(x1, yy + 5, x0, yy + 5, F["rl"], 3)
            s.text((X_PMP + net_end) / 2 + 10, yy - 16, netz, 10, col, fett=True)
        _badge(s, X_PUF + 70, mid + 85 - 50, f"{fmt(A['vlKeller'])} °C", F["gold"], "TWW VL Keller", F)
    # Station
    bx0, bx1 = X_STA - 140, X_STA + 140
    by0, by1 = (mid - 75, mid + 85) if not four else (mid - 135, mid + 135)
    s.rechteck(bx0, by0, bx1, by1, fuell=F["panel"], rand=F["cardline"], breite=1.4, radius=10, unten=True)
    s.text(X_STA, by0 - 14, f"{n_we}× Wohnungsstation", 12.5, F["ink"], fett=True)
    name = "Flow 7000 (F7002 HPS)" if A["zuheizerOn"] else st["name"]
    s.text(X_STA, by0 + 16, f"{name} · {fmt(A['stationKW'])} kW bis {fmt(A['zapfLmin'], 1).removesuffix(',0')} l/min",
           9.5, F["soft"])
    s.text(X_STA, by0 + 30, st["mode"], 9.5, F["soft"])
    if not four:
        hx, tx, iy = X_STA - 65, X_STA + 65, by0 + 46
    else:
        hx, tx, iy = X_STA, X_STA, None
    if not four:
        s.add(Icon("heizkreis", hx - 28, iy, hx + 28, iy + 56, inv))
        s.text(hx, iy + 70, "Heizkreis", 10, F["ink"], fett=True)
        s.text(hx, iy + 84, f"≤ {st['maxHeatKW']} kW", 8.5, F["soft"])
        s.rechteck(tx - 34, iy - 4, tx + 34, iy + 60, fuell=F["card"], rand=F["rl"], breite=1, radius=8)
        _tap(s, tx - 28, iy, 56, 56, F["rl"])
        s.text(tx, iy + 70, "Trinkwasser", 10, F["ink"], fett=True)
        s.text(tx, iy + 84, f"{fmt(A['stationKW'])} kW · {fmt(A['zapfLmin'], 1).removesuffix(',0')} l/min", 8.5, F["soft"])
    else:
        s.add(Icon("heizkreis", X_STA - 28, mid - 110, X_STA + 28, mid - 54, inv))
        s.text(X_STA, mid - 40, "Heizkreis", 10, F["ink"], fett=True)
        _tap(s, X_STA - 28, mid + 30, 56, 56, F["rl"])
        s.text(X_STA, mid + 100, "Trinkwasser", 10, F["ink"], fett=True)
    if A["zuheizerOn"]:
        s.rechteck(X_STA - 95, by1 - 26, X_STA + 95, by1 - 8, fuell=F["gold"], radius=9)
        s.text(X_STA, by1 - 17, f"⚡ DLE {fmt(A['zuheizerMaxKW'])} kW · Stufe {fmt(A['dleStufe'])} °C", 9.5, "#ffffff",
               fett=True)
    # Hinweisbox
    y0 = H - 54
    s.rechteck(60, y0, W - 60, y0 + 44, fuell=F["panel"], rand=F["cardline"], radius=6)
    if four:
        sys_txt = ("4-Leiter-System: Heizung und Trinkwasser hydraulisch getrennt – je eigener Puffer, eigene "
                   "Netzpumpe und eigenes Leitungspaar.")
        leg = "Rot = Heizungsvorlauf · Gold = Trinkwasservorlauf · Blau = Rücklauf"
    else:
        sys_txt = ("2-Leiter-System: Heizung UND Trinkwasser werden über EIN Leitungspaar (Vor-/Rücklauf) zur "
                   "Station geführt.")
        leg = "Rot = Vorlauf (warm) · Blau = Rücklauf · Gold = Warmwasser-Zapfung an der Station"
    s.text(75, y0 + 15, sys_txt, 11, F["ink"], fett=True, anker="start")
    s.text(75, y0 + 31, leg, 10, F["soft"], anker="start")
    return s


# ====================================================================== Liniendiagramm (für das PDF)
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
