"""Grafiken für die Streamlit-App (Plotly): Netzschema, Anlagenschema, Diagramme."""
from __future__ import annotations

import plotly.graph_objects as go

from .calc import din_interp, etage_label, gz_din, gz_tud, seg
from .data import DIN_MIT, DIN_OHNE
from .report import fmt

VL, RL = "#e20015", "#005691"          # Bosch Rot (Vorlauf) / Bosch Dunkelblau (Rücklauf)
INK, SOFT, GREEN, LINE = "#141e29", "#78889a", "#2e7d32", "#c4ccd4"
FONT = dict(family="Segoe UI, Roboto, Helvetica, Arial, sans-serif", color=INK)


def _blank(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="white",
                      paper_bgcolor="white", font=FONT, showlegend=False, dragmode=False)
    fig.update_xaxes(visible=False, fixedrange=True)
    fig.update_yaxes(visible=False, fixedrange=True, scaleanchor=None)
    return fig


def _pipe(fig, x0, y0, x1, y1, gap=0.06, width=3):
    """Doppelleitung Vorlauf (oben/links) + Rücklauf (unten/rechts)."""
    if y0 == y1:
        fig.add_shape(type="line", x0=x0, y0=y0 + gap, x1=x1, y1=y1 + gap, line=dict(color=VL, width=width))
        fig.add_shape(type="line", x0=x0, y0=y0 - gap, x1=x1, y1=y1 - gap, line=dict(color=RL, width=width))
    else:
        fig.add_shape(type="line", x0=x0 - gap, y0=y0, x1=x1 - gap, y1=y1, line=dict(color=VL, width=width + 2))
        fig.add_shape(type="line", x0=x0 + gap, y0=y0, x1=x1 + gap, y1=y1, line=dict(color=RL, width=width + 2))


def _text(fig, x, y, txt, size=11, color=INK, bold=False, **kw):
    fig.add_annotation(x=x, y=y, text=f"<b>{txt}</b>" if bold else txt, showarrow=False,
                       font=dict(size=size, color=color), **kw)


def _dn_badge(fig, x, y, dn):
    fig.add_annotation(x=x, y=y, text=f"<b>{dn}</b>", showarrow=False, font=dict(size=10, color=GREEN),
                       bgcolor="#e4f1e5", bordercolor="#b9dcbc", borderpad=2)


def netzschema(R: dict) -> go.Figure:
    """Netzschema eines Strangs: Steigstrang in der Mitte, je Etage Stationen links/rechts."""
    P, cfg, floors = R["P"], R["cfg"], R["floors"]
    both = R["split"] == "both"
    max_l = max([1] + [c["l"] for c in cfg])
    max_r = max([0] + [c["r"] for c in cfg]) if both else 0
    dx, fh = 1.15, 1.0
    fig = go.Figure()
    x_left, x_right = -0.9 - max_l * dx, 0.9 + max(max_r, 0) * dx

    for f, c in enumerate(cfg, start=1):
        y = f * fh
        _text(fig, x_left - 0.35, y, etage_label(f), size=11, color=SOFT, bold=True, xanchor="right")
        for side, n in (("l", c["l"]), ("r", c["r"] if both else 0)):
            if n <= 0:
                continue
            sgn = -1 if side == "l" else 1
            x_end = sgn * (0.35 + n * dx)
            _pipe(fig, sgn * 0.12, y, x_end, y, gap=0.045, width=2.5)
            for k in range(1, n + 1):
                xs = sgn * (0.35 + k * dx) + (-sgn) * dx / 2
                s1 = R["perFloorRows"][f - 1][side][n - k]           # Abschnitt trägt n-k+1 WE
                fig.add_shape(type="rect", x0=xs - 0.42, x1=xs + 0.42, y0=y + 0.12, y1=y + 0.42,
                              line=dict(color=LINE, width=1), fillcolor="white")
                _text(fig, xs, y + 0.32, f"St. {k}", size=10, bold=True)
                _text(fig, xs, y + 0.2, f"{fmt(R['singleStationV'], 2)} m³/h", size=8, color=SOFT)
                lab = f"<b>{fmt(s1['Vtot'], 2)} m³/h</b><br>{s1['dim']}"
                if n - k + 1 > 1:
                    lab = f"Σ {n - k + 1} WE<br>" + lab
                _text(fig, xs, y - 0.27, lab, size=8, color=GREEN if n - k + 1 == 1 else INK)

    # Steigstrang
    _pipe(fig, 0, 0.15, 0, floors * fh + 0.05, gap=0.07, width=4)
    for r in R["vRows"]:
        _dn_badge(fig, 0, r["floor"] * fh - 0.5, r["dim"])
    # Wärmezentrale
    fig.add_shape(type="rect", x0=-2.2, x1=2.2, y0=-0.35, y1=0.15, fillcolor="#0a3b5c", line=dict(width=0))
    _text(fig, 0, -0.1, "WÄRMEZENTRALE — Kessel · Puffer · Pumpe", size=11, color="white", bold=True)

    fig.update_xaxes(range=[x_left - 1.1, x_right + 0.4])
    fig.update_yaxes(range=[-0.5, floors * fh + 0.6])
    return _blank(fig, height=max(320, 110 * floors + 90))


def anlagenschema(R: dict, headline: dict) -> go.Figure:
    """Vereinfachtes Anlagenschema der Heizzentrale."""
    A, P, st = R["anlage"], R["P"], R["st"]
    from .calc import puffer_produkt
    fig = go.Figure()

    def box(x, y, w, h, title, lines, fill="white", border=LINE):
        fig.add_shape(type="rect", x0=x - w / 2, x1=x + w / 2, y0=y - h / 2, y1=y + h / 2,
                      fillcolor=fill, line=dict(color=border, width=1.5))
        _text(fig, x, y + h / 2 - 0.18, title, size=12, bold=True)
        for i, ln in enumerate(lines):
            _text(fig, x, y + h / 2 - 0.45 - i * 0.24, ln, size=10, color=SOFT)

    def flow(x0, x1, y, label=None):
        _pipe(fig, x0, y, x1, y, gap=0.08, width=3)
        fig.add_annotation(x=x1, y=y + 0.08, ax=x1 - 0.25, ay=y + 0.08, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=2, arrowcolor=VL, arrowwidth=2, text="")
        if label:
            _text(fig, (x0 + x1) / 2, y + 0.3, label, size=10, color=INK)

    n_we = A["weForZentrale"]
    four = A["four"]
    erz = f"{fmt(A['kesselQ'])} kW"
    if not four:
        pp = puffer_produkt(A["pufferVol"])
        box(1, 1.5, 1.6, 1.3, "Wärmeerzeuger", ["Kessel / FW / WP", erz])
        flow(1.8, 3.2, 1.5)
        box(4, 1.5, 1.6, 1.3, "Bereitschaftspuffer", [f"{fmt(A['pufferVol'])} l berechnet", f"Auswahl {pp['text']}",
                                                       f"VL {fmt(A['vlKeller'])} °C"])
        flow(4.8, 5.7, 1.5)
        fig.add_shape(type="circle", x0=5.75, x1=6.25, y0=1.25, y1=1.75, line=dict(color=INK, width=2), fillcolor="white")
        _text(fig, 6, 1.5, "▶", size=14)
        _text(fig, 6, 1.0, "Netzpumpe", size=10, bold=True)
        flow(6.25, 8.2, 1.5, f"{headline['dim']} · {fmt(headline['Vtot'], 2)} m³/h · v = {fmt(headline['v'], 2)} m/s")
        sub = [f"{st['name']}", f"Heizung ≤ {st['maxHeatKW']} kW", f"WW {fmt(A['stationKW'])} kW · {fmt(A['zapfLmin'], 1)} l/min"]
        if A["zuheizerOn"]:
            sub.append(f"+ DLE {fmt(A['zuheizerMaxKW'])} kW · Stufe {fmt(A['dleStufe'])} °C")
        box(9.4, 1.5, 2.2, 1.6, f"{n_we}× Wohnungsstation", sub, fill="#f4f7fa")
        fig.update_yaxes(range=[0.4, 2.5])
        note = "2-Leiter: Heizung UND Trinkwasser über EIN Leitungspaar zur Station."
    else:
        ww, hz = puffer_produkt(A["wwPufferVol"]), puffer_produkt(A["heizPufferVol"])
        box(1, 1.5, 1.6, 2.4, "Wärmeerzeuger", ["Kessel / FW / WP", erz])
        for y, name, vol, prod, pump in ((2.3, "Puffer Trinkwasser", A["wwPufferVol"], ww, A["wwPumpV"]),
                                         (0.7, "Puffer Heizung", A["heizPufferVol"], hz, A["heizPumpV"])):
            flow(1.8, 3.2, y)
            box(4, y, 1.6, 1.2, name, [f"{fmt(vol)} l berechnet", f"Auswahl {prod['text']}"])
            flow(4.8, 5.7, y)
            fig.add_shape(type="circle", x0=5.75, x1=6.25, y0=y - 0.25, y1=y + 0.25, line=dict(color=INK, width=2),
                          fillcolor="white")
            _text(fig, 6, y, "▶", size=14)
            flow(6.25, 8.2, y, f"{fmt(pump, 1)} m³/h")
        box(9.4, 1.5, 2.2, 2.6, f"{n_we}× Wohnungsstation", [st["name"], f"Heizung ≤ {st['maxHeatKW']} kW",
                                                             f"WW {fmt(A['stationKW'])} kW"], fill="#f4f7fa")
        fig.update_yaxes(range=[-0.1, 3.1])
        note = "4-Leiter: Heizung und Trinkwasser getrennt – je eigener Puffer und eigene Netzpumpe."
    _text(fig, 5.4, fig.layout.yaxis.range[0] + 0.05, note, size=10, color=SOFT, yanchor="bottom")
    fig.update_xaxes(range=[0, 10.6])
    return _blank(fig, height=330 if not four else 420)


def chart_volumenstrom(R: dict) -> go.Figure:
    P = R["P"]
    xs = list(range(1, max(2, R["totalWE"]) + 1))
    other = {**P, "glz": "din" if P["glz"] == "tud" else "tud"}
    names = ("TU Dresden", "DIN 4708") if P["glz"] == "tud" else ("DIN 4708", "TU Dresden")
    fig = go.Figure([
        go.Scatter(x=xs, y=[seg(k, P)["Vtot"] for k in xs], name=f"V̇ {names[0]}", line=dict(color="#0a3b5c", width=2.6)),
        go.Scatter(x=xs, y=[seg(k, other)["Vtot"] for k in xs], name=f"V̇ {names[1]}",
                   line=dict(color="#c8102e", width=2.4, dash="dash")),
    ])
    return _chart(fig, "Volumenstrom [m³/h]", ".2f")


def chart_gleichzeitigkeit(R: dict) -> go.Figure:
    xs = list(range(1, max(2, R["totalWE"]) + 1))
    fig = go.Figure([
        go.Scatter(x=xs, y=[gz_din(k) for k in xs], name="DIN 4708", line=dict(color="#0a3b5c", width=2.6)),
        go.Scatter(x=xs, y=[gz_tud(k) for k in xs], name="TU Dresden", line=dict(color=GREEN, width=2.4)),
    ])
    return _chart(fig, "Gleichzeitigkeit GZ", ".1f")


def chart_din18015(n_we: int) -> go.Figure:
    xs = [x / 2 for x in range(2, 61)]
    n = max(1, min(30, n_we))
    fig = go.Figure([
        go.Scatter(x=xs, y=[din_interp(DIN_MIT, x) for x in xs], name="MIT elektr. WW-Bereitung (HPS)",
                   line=dict(color=RL, width=2.6)),
        go.Scatter(x=xs, y=[din_interp(DIN_OHNE, x) for x in xs], name="OHNE elektr. WW-Bereitung",
                   line=dict(color=VL, width=2.4)),
        go.Scatter(x=[n, n], y=[din_interp(DIN_MIT, n), din_interp(DIN_OHNE, n)], mode="markers",
                   marker=dict(size=10, color=[RL, VL], line=dict(color="white", width=1.5)), showlegend=False,
                   hoverinfo="skip"),
    ])
    fig.add_vline(x=n, line=dict(color=SOFT, dash="dot", width=1))
    fig = _chart(fig, "Leistung am Netzanschluss [kW]", ".0f")
    fig.update_xaxes(title="Anzahl Wohneinheiten am Netzanschluss", range=[0.5, 30.5])
    fig.update_yaxes(range=[0, 150])
    return fig


def _chart(fig: go.Figure, ylab: str, yfmt: str) -> go.Figure:
    fig.update_layout(height=330, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="white", paper_bgcolor="white",
                      font=FONT, hovermode="x unified", separators=",.",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_xaxes(title="kumulierte Wohneinheiten", gridcolor="#e9edf1", zeroline=False)
    fig.update_yaxes(title=ylab, gridcolor="#e9edf1", zeroline=False, rangemode="tozero", hoverformat=yfmt)
    return fig
