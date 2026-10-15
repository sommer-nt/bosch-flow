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

import plotly.graph_objects as go

from .calc import DN_SERIES, etage_label, seg, topologie
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


def modell(results: list, pos: float = 50, modus: str = "v", dunkel: bool = False, nur_strang: int | None = None,
           hoehe: int = 680) -> go.Figure:
    """3D-Figur. ``modus``: "v" = Farbe nach Geschwindigkeit, "dn" = nach Nennweite.
    ``nur_strang``: Index eines einzelnen Strangs (ohne Hauptstrang) oder None für das ganze Projekt."""
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
        for f in range(1, floors + 1):
            z = f * ETAGE - 0.25
            flaechen.append(go.Mesh3d(x=[x_min, x_max, x_max, x_min],
                                      y=[-TIEFE, -TIEFE, TIEFE, TIEFE], z=[z] * 4, i=[0, 0], j=[1, 2], k=[2, 3],
                                      color=platte, opacity=1, hoverinfo="skip", showscale=False, flatshading=True))
        # Strangbeschriftung oben
        stat_label = dict(x=[xr], y=[0], z=[floors * ETAGE + 1.6], text=[f"Strang {i + 1}"])
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
        fig.add_trace(go.Scatter3d(x=[zx], y=[0], z=[-0.6], mode="markers",
                                   marker=dict(size=14, symbol="square", color="#0a3b5c",
                                               line=dict(color="#ffffff", width=2)),
                                   hovertext=[f"<b>Wärmezentrale</b> ({T['label']})<br>Σ {T['gesamtWE']} WE · "
                                              f"V̇ = {fmt(T['gesamt']['Vtot'], 2)} m³/h<br>Anschluss "
                                              f"<b>{T['gesamt']['dim']}</b> · v {fmt(T['gesamt']['v'], 2)} m/s"],
                                   hoverinfo="text", showlegend=False))
    else:
        fig.add_trace(go.Scatter3d(x=[xs[0]], y=[0], z=[-0.6], mode="markers",
                                   marker=dict(size=12, symbol="square", color="#0a3b5c"), hoverinfo="skip",
                                   showlegend=False))
    zx_text = zx if nur_strang is None and len(results) > 1 else xs[0]
    fig.add_trace(go.Scatter3d(x=[zx_text], y=[-TIEFE], z=[-3.4], mode="text", text=["Wärmezentrale"],
                               textfont=dict(color=ink, size=12), hoverinfo="skip", showlegend=False))
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
    achse = dict(visible=False, showbackground=False, showgrid=False, zeroline=False, showspikes=False)
    fig.update_layout(
        height=hoehe, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=ink, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"),
        legend=dict(orientation="h", yanchor="bottom", y=0.0, x=0.0, font=dict(color=soft, size=11),
                    title=dict(text="Ausnutzung v / v_max: " if modus == "v" else "Nennweite: ",
                               font=dict(color=soft, size=11)), itemclick="toggleothers", bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#005691", font=dict(color="#12181f", size=12)),
        scene=dict(xaxis=achse, yaxis=achse, zaxis=achse, aspectmode="manual", aspectratio=_seiten(fig),
                   bgcolor="rgba(0,0,0,0)", dragmode="turntable",
                   camera=dict(eye=dict(x=0.3, y=-1.35, z=0.4), center=dict(x=0, y=0, z=-0.1),
                               up=dict(x=0, y=0, z=1))))
    return fig
