"""Interaktives 3D-Modell des Rohrnetzes (Plotly).

Aufbau (schematisch, nicht maßstäblich gegenüber dem realen Grundriss):
- Keller (z = 0): horizontaler Hauptstrang entlang x, Wärmezentrale an der gewählten Position (wie die
  Netztopologie der V54).
- Je Strang ein Steigrohr (senkrecht), je Etage die Etagenleitung nach links und rechts (entlang x) mit den
  Wohnungsstationen – wie eine Gebäudeansicht, die sich frei drehen lässt.
- Rohrdicke nach Nennweite, Farbe wahlweise nach Geschwindigkeit (Ausnutzung v / v_max) oder nach Nennweite.
Alle Werte kommen aus dem Rechenkern; jedes Rohrstück zeigt beim Überfahren seine Daten.
"""
from __future__ import annotations

import math

import plotly.graph_objects as go

from .calc import DN_SERIES, etage_label, puffer_produkt, seg, topologie
from .report import fmt

ETAGE = 3.0          # m Geschosshöhe (Darstellung)
STATION = 2.6        # m Abstand der Stationen entlang der Etagenleitung (Darstellung)
GANG = 2.2           # m Abstand der ersten Station vom Steigrohr
LUECKE = 4.0         # m Lücke zwischen zwei Strängen (Darstellung)
TIEFE = 4.5          # m halbe Gebäudetiefe der Geschossplatten (Darstellung)
UEBERHOEHUNG = 1.6   # Geschosse optisch höher, damit die Etagen lesbar bleiben

# Ausnutzung v / v_max → Farbe (grün = Reserve, gelb = nahe Grenze, orange = grenzwertig, rot = zu schnell)
STUFEN = [(0.6, "#2b9348", "≤ 60 % v_max"), (0.85, "#80b918", "60–85 %"), (1.0, "#e9c46a", "85–100 %"),
          (1.2, "#f4a261", "grenzwertig ≤ 120 %"), (99, "#e63946", "zu schnell > 120 %")]
DN_FARBEN = ["#4cc9f0", "#4895ef", "#4361ee", "#3f37c9", "#3a0ca3", "#480ca8", "#560bad", "#7209b7", "#b5179e",
             "#f72585", "#ff4d6d", "#ff8fa3", "#ffb3c1", "#ffccd5"]


def _dn_index(dn: str) -> int:
    return next((i for i, s in enumerate(DN_SERIES) if s[0] == dn), 0)


def _farbe(r: dict, vmax: float, modus: str) -> tuple[str, str]:
    if modus == "dn":
        return DN_FARBEN[_dn_index(r["dim"]) % len(DN_FARBEN)], r["dim"]
    q = r["v"] / vmax if vmax else 0
    for grenze, farbe, name in STUFEN:
        if q <= grenze:
            return farbe, name
    return STUFEN[-1][1], STUFEN[-1][2]


def _breite(dn: str) -> float:
    return 3 + _dn_index(dn) * 1.15


def _info(titel: str, r: dict, vmax: float) -> str:
    status = "OK" if r["v"] <= vmax else "grenzwertig" if r["v"] <= vmax * 1.2 else "zu schnell"
    return (f"<b>{titel}</b><br>{r['weCum']} WE · GZ {fmt(r['gz'], 1)}<br>V̇ = {fmt(r['Vtot'], 2)} m³/h<br>"
            f"<b>{r['dim']}</b> ({r['raw']}) · v = {fmt(r['v'], 2)} m/s<br>Δp = {fmt(r['dp'])} Pa/m · {status}")


def _seiten(fig: go.Figure) -> dict:
    """Seitenverhältnis aus den Daten, Höhe leicht überhöht."""
    xs, ys, zs = [], [], []
    for t in fig.data:
        for wert, ziel in ((getattr(t, "x", None), xs), (getattr(t, "y", None), ys), (getattr(t, "z", None), zs)):
            if wert is not None:
                ziel.extend(v for v in wert if v is not None)
    dx = (max(xs) - min(xs)) or 1
    dy = (max(ys) - min(ys)) or 1
    dz = ((max(zs) - min(zs)) or 1) * UEBERHOEHUNG
    lang = dx / max(dy, dz)                 # lange, flache Gebäude größer darstellen, damit sie die Breite nutzen
    m = max(dx, dy, dz) / min(1.75, 1.3 * max(1.0, lang / 2.4))
    return dict(x=dx / m, y=dy / m, z=dz / m)


LICHT = dict(ambient=0.7, diffuse=0.6, specular=0.3, roughness=0.5, fresnel=0.1)
PUFFER_MASS = {500: (0.33, 1.65), 750: (0.40, 1.8), 1000: (0.45, 1.95), 1500: (0.55, 2.1)}   # Radius, Höhe (Darstellung)
QUELLEN = {"kessel": "Brennwertkessel", "fernwaerme": "Fernwärme-Übergabestation", "wp": "Wärmepumpe"}


def _quader(x0, x1, y0, y1, z0, z1, farbe: str) -> go.Mesh3d:
    return go.Mesh3d(x=[x0, x1, x1, x0] * 2, y=[y0, y0, y1, y1] * 2, z=[z0] * 4 + [z1] * 4,
                     i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3], j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4],
                     k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7], color=farbe, opacity=1, flatshading=True,
                     hoverinfo="skip", showscale=False, lighting=LICHT)


def _zylinder(cx: float, cm: float, a0: float, a1: float, r: float, farbe: str, achse: str = "z",
              n: int = 32) -> go.Mesh3d:
    """Zylinder mit Deckeln. achse "z": Mittelpunkt (cx, cm), Höhe a0…a1 in z; achse "y": Mitte (cx, z=cm), a0…a1 in y."""
    pts = []
    for t in (a0, a1):
        for q in range(n):
            w = 2 * math.pi * q / n
            u, v = r * math.cos(w), r * math.sin(w)
            pts.append((cx + u, cm + v, t) if achse == "z" else (cx + u, t, cm + v))
    c0 = len(pts)
    pts += [(cx, cm, a0), (cx, cm, a1)] if achse == "z" else [(cx, a0, cm), (cx, a1, cm)]
    ii, jj, kk = [], [], []
    for q in range(n):
        a, b = q, (q + 1) % n
        ii += [a, a, c0, c0 + 1]
        jj += [b, b + n, b, a + n]
        kk += [b + n, a + n, a, b + n]
    x, y, z = zip(*pts)
    return go.Mesh3d(x=x, y=y, z=z, i=ii, j=jj, k=kk, color=farbe, opacity=1, flatshading=False,
                     hoverinfo="skip", showscale=False, lighting=LICHT)


def _flaeche(ecken: list, farbe: str, deckkraft: float) -> go.Mesh3d:
    """Ebenes Vieleck (Ecken im Umlauf) als Dreiecksfächer."""
    x, y, z = zip(*ecken)
    n = len(ecken)
    return go.Mesh3d(x=x, y=y, z=z, i=[0] * (n - 2), j=list(range(1, n - 1)), k=list(range(2, n)), color=farbe,
                     opacity=deckkraft, flatshading=True, hoverinfo="skip", showscale=False, lighting=LICHT)


def _haus(x0: float, x1: float, y0: float, y1: float, zg: float, zt: float, fenster: list, dunkel: bool,
          kanten: dict, rahmen: dict) -> list:
    """Durchscheinende Gebäudehülle: Wände (zg…zt), Satteldach (First entlang x) und Fenster an der Vorderseite.
    Die Vorderwand (y0, zur Kamera) ist nur als Umriss mit Fenstern gezeichnet („Puppenhaus-Schnitt“): Flächen liegen
    in WebGL im Pick-Puffer und würden sonst die Hover-Werte der Rohre dahinter verdecken.
    ``fenster``: (x, z_boden) je Fenster; Kanten und Fensterrahmen werden in ``kanten``/``rahmen`` gesammelt."""
    wand = "#9fb3c8" if dunkel else "#c9b9a0"
    dach = "#c0644d" if dunkel else "#a8452f"
    first = zt + min(3.2, 0.32 * (y1 - y0))
    ue = 0.4                                                     # Dachüberstand
    teile = [_flaeche([(x0, y1, zg), (x1, y1, zg), (x1, y1, zt), (x0, y1, zt)], wand, 0.10),
             _flaeche([(x0, y0, zg), (x0, y1, zg), (x0, y1, zt), (x0, (y0 + y1) / 2, first), (x0, y0, zt)], wand, 0.10),
             _flaeche([(x1, y0, zg), (x1, y1, zg), (x1, y1, zt), (x1, (y0 + y1) / 2, first), (x1, y0, zt)], wand, 0.10),
             _flaeche([(x0 - ue, y0 - ue, zt - 0.25), (x1 + ue, y0 - ue, zt - 0.25), (x1 + ue, (y0 + y1) / 2, first),
                       (x0 - ue, (y0 + y1) / 2, first)], dach, 0.42),
             _flaeche([(x0 - ue, y1 + ue, zt - 0.25), (x1 + ue, y1 + ue, zt - 0.25), (x1 + ue, (y0 + y1) / 2, first),
                       (x0 - ue, (y0 + y1) / 2, first)], dach, 0.42)]
    def linie(*pkte, ziel=kanten):
        for p in pkte:
            ziel["x"].append(p[0]), ziel["y"].append(p[1]), ziel["z"].append(p[2])
        ziel["x"].append(None), ziel["y"].append(None), ziel["z"].append(None)
    ym = (y0 + y1) / 2
    for y in (y0, y1):
        linie((x0, y, zg), (x1, y, zg), (x1, y, zt), (x0, y, zt), (x0, y, zg))
    for x in (x0, x1):
        linie((x, y0, zt), (x, ym, first), (x, y1, zt))
    linie((x0 - ue, ym, first), (x1 + ue, ym, first))
    for fx, fz in fenster:
        linie((fx - 0.6, y0, fz + 0.9), (fx + 0.6, y0, fz + 0.9), (fx + 0.6, y0, fz + 2.2), (fx - 0.6, y0, fz + 2.2),
              (fx - 0.6, y0, fz + 0.9), ziel=rahmen)
    return teile


def _waermezentrale(ax: float, A: dict, quelle: str, dunkel: bool, pumpe_info: str | None,
                    massstab: float = 1.0) -> tuple[list, dict]:
    """Erzeuger, Pufferspeicher und Netzpumpe im Keller, verrohrt bis zum Hauptstrang bei x = ax.
    ``massstab`` vergrößert die Zentrale bei großen Gebäuden (um x = ax, y = 0, z = 0), damit sie erkennbar bleibt."""
    teile, hover = [], {"x": [], "y": [], "z": [], "t": []}
    boden, ym = -2.6, -2.7                         # Kellerboden, Aufstellreihe vor dem Hauptstrang
    pp = puffer_produkt(A["pufferVol"])
    combo = sorted(pp["combo"], reverse=True)[:4]
    # Netzpumpe direkt an der Steigleitung zum Hauptstrang, links davon Puffer, ganz links der Erzeuger
    px = ax - 0.9
    x = px - 0.9
    puffer = []
    for liter in combo:
        r, h = PUFFER_MASS.get(liter, (0.5, 2.0))
        x -= r
        puffer.append((x, r, h, liter))
        x -= r + 0.45
    breite, tiefe = 1.3, 1.0
    hoch = {"kessel": 1.9, "fernwaerme": 1.5, "wp": 1.35}.get(quelle, 1.9)
    gx = x - breite / 2
    x0, x1, y0, y1 = gx - breite / 2, gx + breite / 2, ym - tiefe / 2, ym + tiefe / 2
    if quelle == "wp":
        teile.append(_quader(x0, x1, y0, y1, boden, boden + hoch, "#c3ccd4" if dunkel else "#dfe4e9"))
        teile.append(_zylinder(gx, boden + hoch * 0.52, y0 - 0.06, y0 + 0.02, 0.42, "#2b3036", achse="y"))
        teile.append(_zylinder(gx, boden + hoch * 0.52, y0 - 0.08, y0 - 0.05, 0.12, "#8a96a3", achse="y"))
    elif quelle == "fernwaerme":
        teile.append(_quader(x0, x1, y0, y1, boden, boden + hoch, "#e6ebf0" if dunkel else "#f4f6f8"))
        teile.append(_quader(x0, x1, y0 - 0.02, y0, boden + hoch - 0.28, boden + hoch - 0.16, "#005691"))
        teile.append(_quader(gx - 0.3, gx + 0.3, y0 - 0.03, y0, boden + hoch - 0.75, boden + hoch - 0.45, "#2b3036"))
    else:
        teile.append(_quader(x0, x1, y0, y1, boden, boden + hoch, "#4a525c" if dunkel else "#2f353c"))
        teile.append(_quader(x0, x1, y0 - 0.02, y0, boden + hoch - 0.3, boden + hoch - 0.18, "#e20015"))
        teile.append(_quader(gx - 0.25, gx + 0.25, y0 - 0.03, y0, boden + hoch - 0.7, boden + hoch - 0.45, "#cfe3f2"))
    hover["x"].append(gx), hover["y"].append(ym), hover["z"].append(boden + hoch / 2)
    hover["t"].append(f"<b>Wärmeerzeuger</b> · {QUELLEN.get(quelle, 'Wärmeerzeuger')}<br>{fmt(A['kesselQ'])} kW")
    for cx, r, h, liter in puffer:
        teile.append(_zylinder(cx, ym, boden, boden + h, r, "#aab5c0" if dunkel else "#d9dfe5"))
        teile.append(_zylinder(cx, ym, boden + h, boden + h + 0.06, r * 0.98, "#8996a3" if dunkel else "#b9c3cc"))
        hover["x"].append(cx), hover["y"].append(ym), hover["z"].append(boden + h / 2)
        hover["t"].append(f"<b>Pufferspeicher</b> {liter} l<br>Auswahl {pp['text']} · Bedarf {fmt(A['pufferVol'])} l")
    # Netzpumpe: Pumpengehäuse (Zylinder) + Motor
    teile.append(_zylinder(px, -1.25, ym - 0.22, ym + 0.22, 0.24, "#005691", achse="y"))
    teile.append(_zylinder(px, -1.25, ym - 0.5, ym - 0.22, 0.16, "#1b2733" if not dunkel else "#9fb0c0", achse="y"))
    hover["x"].append(px), hover["y"].append(ym), hover["z"].append(-1.25)
    hover["t"].append("<b>Netzpumpe</b>" + (f"<br>{pumpe_info}" if pumpe_info else ""))
    # Verrohrung: Vorlauf (rot) oben, Rücklauf (blau) darunter – vom Erzeuger über Puffer und Pumpe zum Hauptstrang
    oben_e = boden + hoch
    vl = dict(x=[gx, gx] + [c for c, *_ in puffer] + [px, ax, ax, ax],
              y=[ym, ym] + [ym] * len(puffer) + [ym, ym, ym, 0], z=[oben_e, -0.45] + [-0.45] * len(puffer)
              + [-0.45, -0.45, 0, 0])
    rl = dict(x=[gx + 0.3, gx + 0.3, ax + 0.35, ax + 0.35], y=[ym + 0.3] * 3 + [0.0],
              z=[boden + 0.3, -0.85, -0.85, -0.3])
    teile.append(go.Scatter3d(mode="lines", line=dict(color="#e20015", width=7), hoverinfo="skip", showlegend=False,
                              **vl))
    teile.append(go.Scatter3d(mode="lines", line=dict(color="#005691" if not dunkel else "#4fa3e0", width=7),
                              hoverinfo="skip", showlegend=False, **rl))
    teile.append(go.Scatter3d(x=[px, px], y=[ym, ym], z=[-1.0, -0.45], mode="lines", hoverinfo="skip",
                              line=dict(color="#e20015", width=7), showlegend=False))
    m = massstab
    for t in teile:
        t.update(x=[ax + (v - ax) * m for v in t.x], y=[v * m for v in t.y], z=[v * m for v in t.z])
    hover.update(x=[ax + (v - ax) * m for v in hover["x"]], y=[v * m for v in hover["y"]],
                 z=[v * m for v in hover["z"]])
    return teile, hover | {"links": ax + (x0 - ax) * m, "boden": boden * m, "ym": ym * m}


def modell(results: list, pos: float = 50, modus: str = "v", dunkel: bool = False, nur_strang: int | None = None,
           hoehe: int = 680, quelle: str = "kessel", pumpe_info: str | None = None, huelle: bool = False) -> go.Figure:
    """3D-Figur. ``modus``: "v" = Farbe nach Geschwindigkeit, "dn" = nach Nennweite.
    ``nur_strang``: Index eines einzelnen Strangs (ohne Hauptstrang) oder None für das ganze Projekt.
    ``huelle``: durchscheinende Gebäudehülle (Wände, Fenster, Satteldach, Keller) um die Stränge."""
    P = results[0]["P"]
    vmax = P["vmax"]
    ink = "#e6edf3" if dunkel else "#12181f"
    soft = "#9fb0c0" if dunkel else "#6b7785"
    platte = "rgba(120,140,160,0.10)" if dunkel else "rgba(0,86,145,0.06)"
    auswahl = [nur_strang] if nur_strang is not None else list(range(len(results)))

    # Strang-Positionen entlang x: Breite je Strang nach der breitesten Etage
    breite = []
    for i in auswahl:
        r = results[i]
        n_l = max([0] + [c["l"] for c in r["cfg"]])
        n_r = max([0] + [c["r"] for c in r["cfg"]]) if r["split"] == "both" else 0
        breite.append((n_l, n_r))
    xs, x = [], 0.0
    for n_l, n_r in breite:
        x += GANG + max(n_l - 1, 0) * STATION
        xs.append(x)
        x += (GANG + max(n_r - 1, 0) * STATION if n_r else 0) + LUECKE
    linien: dict = {}          # (farbe, breite, legende) -> [x], [y], [z]
    infos = {"x": [], "y": [], "z": [], "t": []}
    stat = {"x": [], "y": [], "z": [], "t": []}
    flaechen = []
    haeuser = []               # je Strang: x_min, x_max, Geschosse, Fenster

    def rohr(p0, p1, r, titel):
        farbe, name = _farbe(r, vmax, modus)
        key = (farbe, _breite(r["dim"]), name)
        lx, ly, lz = linien.setdefault(key, ([], [], []))
        lx += [p0[0], p1[0], None]
        ly += [p0[1], p1[1], None]
        lz += [p0[2], p1[2], None]
        infos["x"].append((p0[0] + p1[0]) / 2)
        infos["y"].append((p0[1] + p1[1]) / 2)
        infos["z"].append((p0[2] + p1[2]) / 2)
        infos["t"].append(_info(titel, r, vmax))

    for (i, xr), (n_l, n_r) in zip(zip(auswahl, xs), breite):
        R = results[i]
        floors = R["floors"]
        # Steigrohr: Abschnitt unter Etage f trägt vRows[f-1]
        for row in R["vRows"]:
            f = row["floor"]
            z0 = (f - 1) * ETAGE if f > 1 else 0.0
            rohr((xr, 0, z0), (xr, 0, f * ETAGE), row, f"Strang {i + 1} · Steigstrang unter {etage_label(f)}"
                 + (" · Strangfuß" if f == 1 else ""))
        # Etagenleitungen + Stationen
        for f, c in enumerate(R["cfg"], start=1):
            z = f * ETAGE
            for seite, n_s, sg in (("l", c["l"], -1), ("r", c["r"] if R["split"] == "both" else 0, 1)):
                rows = R["perFloorRows"][f - 1][seite]
                for k in range(1, n_s + 1):
                    y0 = 0 if k == 1 else sg * (GANG + (k - 2) * STATION)
                    y1 = sg * (GANG + (k - 1) * STATION)
                    rohr((xr + y0, 0, z), (xr + y1, 0, z), rows[n_s - k],
                         f"Strang {i + 1} · {etage_label(f)} {'links' if sg < 0 else 'rechts'} · zu St. {k}")
                    stat["x"].append(xr + y1)
                    stat["y"].append(0)
                    stat["z"].append(z)
                    stat["t"].append(f"<b>Wohnungsstation</b><br>Strang {i + 1} · {etage_label(f)} · "
                                     f"{'links' if sg < 0 else 'rechts'} St. {k}<br>V̇ = {fmt(R['singleStationV'], 2)} m³/h "
                                     f"· {R['perStationDim']}")
        # Geschossplatten (transparent) je Strang
        x_min = xr - (GANG + max(n_l - 1, 0) * STATION) - 1.2
        x_max = xr + ((GANG + max(n_r - 1, 0) * STATION) + 1.2 if n_r else 1.2)
        haeuser.append((x_min, x_max, floors, [(sx, sz) for sx, sz in zip(stat["x"], stat["z"])
                                               if x_min <= sx <= x_max]))
        for f in range(1, floors + 1):
            z = f * ETAGE - 0.25
            flaechen.append(go.Mesh3d(x=[x_min, x_max, x_max, x_min],
                                      y=[-TIEFE, -TIEFE, TIEFE, TIEFE], z=[z] * 4, i=[0, 0], j=[1, 2], k=[2, 3],
                                      color=platte, opacity=1, hoverinfo="skip", showscale=False, flatshading=True))
        # Geschossbeschriftung links am ersten Strang
        if xr == xs[0]:
            flaechen.append(go.Scatter3d(x=[x_min - 1.6] * floors, y=[0] * floors,
                                         z=[f * ETAGE for f in range(1, floors + 1)], mode="text",
                                         text=[etage_label(f) for f in range(1, floors + 1)],
                                         textfont=dict(color=soft, size=11), hoverinfo="skip", showlegend=False))
        # Strangbeschriftung oben
        stat_label = dict(x=[xr], y=[0], z=[(floors + 1) * ETAGE + 3.0 if huelle else floors * ETAGE + 1.6], text=[f"<b>Strang {i + 1}</b> · {R['totalWE']} WE"])
        flaechen.append(go.Scatter3d(mode="text", textfont=dict(color=ink, size=13), hoverinfo="skip",
                                     showlegend=False, **stat_label))

    fig = go.Figure(flaechen)
    # Hauptstrang im Keller + Wärmezentrale
    if nur_strang is None and len(results) > 1:
        T = topologie(results, pos)
        left = T["links"]
        zx = xs[0] - 3 if left <= 0 else xs[-1] + 3 if left >= len(results) else (xs[left - 1] + xs[left]) / 2
        for a in T["abschnitte"]:
            i = a["strang"] - 1
            if i < left:     # links der Zentrale: von Strang i nach rechts bis zum nächsten Abzweig / zur Zentrale
                p0, p1 = xs[i], (xs[i + 1] if i + 1 < left else zx)
            else:            # rechts der Zentrale: von Strang i nach links
                p0, p1 = xs[i], (xs[i - 1] if i - 1 >= left else zx)
            r = seg(a["load"], P)
            rohr((p0, 0, 0), (p1, 0, 0), r, f"Hauptstrang · Abschnitt {a['strang']}"
                 + (" · ◆ maßgeblich" if a["kritisch"] else ""))
        fig.add_trace(go.Scatter3d(x=[zx], y=[0], z=[-1.5], mode="markers",
                                   marker=dict(size=18, symbol="square", color="rgba(0,0,0,0)"),
                                   hovertext=[f"<b>Wärmezentrale</b> ({T['label']})<br>Σ {T['gesamtWE']} WE · "
                                              f"V̇ = {fmt(T['gesamt']['Vtot'], 2)} m³/h<br>Anschluss "
                                              f"<b>{T['gesamt']['dim']}</b> · v {fmt(T['gesamt']['v'], 2)} m/s"],
                                   hoverinfo="text", showlegend=False))
    else:
        rf = results[nur_strang if nur_strang is not None else 0]["vRows"][0]
        rohr((xs[0], 0, -0.4), (xs[0], 0, 0), rf, "Zuleitung Wärmezentrale → Strangfuß")
    zx_text = zx if nur_strang is None and len(results) > 1 else xs[0]
    # Wärmezentrale: Erzeuger, Pufferspeicher, Netzpumpe mit Verrohrung; darunter der Kellerboden
    A = results[nur_strang if nur_strang is not None else 0]["anlage"]
    spann = (max(xs) - min(xs)) + 2 * (GANG + 4 * STATION)
    teile, zh = _waermezentrale(zx_text, A, quelle, dunkel, pumpe_info, max(1.0, min(2.0, spann / 34)))
    for t in teile:
        fig.add_trace(t)
    fig.add_trace(go.Scatter3d(x=zh["x"], y=zh["y"], z=zh["z"], mode="markers", hovertext=zh["t"], hoverinfo="text",
                               showlegend=False, marker=dict(size=16, color="rgba(0,0,0,0)")))
    alle_x = [v for t in fig.data for v in (getattr(t, "x", None) or []) if v is not None]
    k0, k1 = min(alle_x) - 2, max(alle_x) + 2
    fig.add_trace(go.Mesh3d(x=[k0, k1, k1, k0], y=[min(-TIEFE - 1.5, zh["ym"] * 1.6)] * 2 + [TIEFE + 1] * 2, z=[zh["boden"] - 0.02] * 4,
                            i=[0, 0], j=[1, 2], k=[2, 3], color="rgba(120,140,160,0.18)" if dunkel else "rgba(16,24,40,0.07)",
                            opacity=1, hoverinfo="skip", showscale=False, flatshading=True))
    if huelle:
        zg = ETAGE - 0.25                                      # Oberkante Gelände = Fußboden EG
        kanten, rahmen = {"x": [], "y": [], "z": []}, {"x": [], "y": [], "z": []}
        for x_min, x_max, floors, fenster in haeuser:
            for t in _haus(x_min - 0.3, x_max + 0.3, -TIEFE, TIEFE, zg, (floors + 1) * ETAGE - 0.25,
                           [(fx, fz - 0.25) for fx, fz in fenster], dunkel, kanten, rahmen):
                fig.add_trace(t)
        # Keller unter allen Strängen, umschließt Hauptstrang und Wärmezentrale (Vorderseite offen, s. _haus)
        ky0, ky1 = min(-TIEFE - 1.5, zh["ym"] * 1.6), TIEFE + 1
        keller = "#7d8fa3" if dunkel else "#8c99a6"
        for ecken in ([(k0, ky1, zh["boden"]), (k1, ky1, zh["boden"]), (k1, ky1, zg), (k0, ky1, zg)],
                      [(k0, ky0, zh["boden"]), (k0, ky1, zh["boden"]), (k0, ky1, zg), (k0, ky0, zg)],
                      [(k1, ky0, zh["boden"]), (k1, ky1, zh["boden"]), (k1, ky1, zg), (k1, ky0, zg)]):
            fig.add_trace(_flaeche(ecken, keller, 0.07))
        for y in (ky0, ky1):
            kanten["x"] += [k0, k1, None]
            kanten["y"] += [y, y, None]
            kanten["z"] += [zg, zg, None]
        kanten["x"] += [k0, k0, k1, k1, None]                   # offene Kellervorderseite als Umriss
        kanten["y"] += [ky0] * 4 + [None]
        kanten["z"] += [zg, zh["boden"], zh["boden"], zg, None]
        fig.add_trace(go.Scatter3d(mode="lines", hoverinfo="skip", showlegend=False,
                                   line=dict(color="rgba(200,215,230,0.30)" if dunkel else "rgba(90,70,50,0.40)",
                                             width=2), **kanten))
        fig.add_trace(go.Scatter3d(mode="lines", hoverinfo="skip", showlegend=False,
                                   line=dict(color="rgba(200,215,230,0.22)" if dunkel else "rgba(90,70,50,0.25)",
                                             width=1.5), **rahmen))
    fig.add_trace(go.Scatter3d(x=[zh["links"] - 0.4], y=[zh["ym"]], z=[zh["boden"] / 2], mode="text",
                               text=["<b>Wärmezentrale</b>"],
                               textposition="middle left", textfont=dict(color=ink, size=12), hoverinfo="skip",
                               showlegend=False))
    # Rohre: eine Spur je Farbe/Breite (schnell), Legende je Farbstufe einmal
    gezeigt = set()
    reihenfolge = [s[2] for s in STUFEN] if modus == "v" else [d[0] for d in DN_SERIES]
    for (farbe, w, name), (lx, ly, lz) in sorted(linien.items(), key=lambda kv: (
            reihenfolge.index(kv[0][2]) if kv[0][2] in reihenfolge else 99, kv[0][1])):
        fig.add_trace(go.Scatter3d(x=lx, y=ly, z=lz, mode="lines", line=dict(color=farbe, width=w), hoverinfo="skip",
                                   name=name, legendgroup=name, showlegend=name not in gezeigt))
        gezeigt.add(name)
    fig.add_trace(go.Scatter3d(x=stat["x"], y=stat["y"], z=stat["z"], mode="markers", hovertext=stat["t"],
                               hoverinfo="text", name="Wohnungsstation",
                               marker=dict(size=5, symbol="square", color="#ffffff" if not dunkel else "#151d25",
                                           line=dict(color="#005691" if not dunkel else "#4fa3e0", width=2))))
    fig.add_trace(go.Scatter3d(x=infos["x"], y=infos["y"], z=infos["z"], mode="markers", hovertext=infos["t"],
                               hoverinfo="text", showlegend=False, marker=dict(size=7, color="rgba(0,0,0,0)")))
    seiten = _seiten(fig)
    # mit Dach bei hohen, kompakten Gebäuden etwas weiter weg, damit der First nicht abgeschnitten wird
    zoom = 1 + 0.32 * min(1.0, max(0.0, (seiten["z"] / seiten["x"] - 0.45) / 0.55)) if huelle else 1.0
    achse = dict(visible=False, showbackground=False, showgrid=False, zeroline=False, showspikes=False)
    fig.update_layout(
        height=hoehe, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=ink, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"),
        legend=dict(orientation="h", yanchor="bottom", y=0.0, x=0.0, font=dict(color=soft, size=11),
                    title=dict(text="Ausnutzung v / v_max: " if modus == "v" else "Nennweite: ",
                               font=dict(color=soft, size=11)), itemclick="toggleothers", bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#005691", font=dict(color="#12181f", size=12)),
        scene=dict(xaxis=achse, yaxis=achse, zaxis=achse, aspectmode="manual", aspectratio=seiten,
                   bgcolor="rgba(0,0,0,0)", dragmode="turntable",
                   camera=dict(eye=dict(x=0.3 * zoom, y=-1.35 * zoom, z=0.4 * zoom), center=dict(x=0, y=0, z=0.0 if huelle else -0.1),
                               up=dict(x=0, y=0, z=1))))
    return fig
