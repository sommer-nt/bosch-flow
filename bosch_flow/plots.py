"""Diagramme für die Streamlit-App (Plotly). Die Schemata stehen in ``schemata.py``."""
from __future__ import annotations

import plotly.graph_objects as go

from .calc import din_interp, gz_din, gz_tud, seg
from .data import DIN_MIT, DIN_OHNE

VL, RL = "#e20015", "#005691"          # Bosch Rot (Vorlauf) / Bosch Dunkelblau (Rücklauf)
INK, SOFT, GREEN, LINE = "#141e29", "#78889a", "#2e7d32", "#c4ccd4"
FONT = dict(family="Segoe UI, Roboto, Helvetica, Arial, sans-serif", color=INK)


def chart_volumenstrom(R: dict, dunkel: bool = False) -> go.Figure:
    P = R["P"]
    xs = list(range(1, max(2, R["totalWE"]) + 1))
    other = {**P, "glz": "din" if P["glz"] == "tud" else "tud"}
    names = ("TU Dresden", "DIN 4708") if P["glz"] == "tud" else ("DIN 4708", "TU Dresden")
    fig = go.Figure([
        go.Scatter(x=xs, y=[seg(k, P)["Vtot"] for k in xs], name=f"V̇ {names[0]}",
                   line=dict(color="#4fa3e0" if dunkel else "#0a3b5c", width=2.8)),
        go.Scatter(x=xs, y=[seg(k, other)["Vtot"] for k in xs], name=f"V̇ {names[1]}",
                   line=dict(color="#ff5a6a" if dunkel else "#c8102e", width=2.4, dash="dash")),
    ])
    return _chart(fig, "Volumenstrom [m³/h]", ".2f", dunkel)


def chart_gleichzeitigkeit(R: dict, dunkel: bool = False) -> go.Figure:
    xs = list(range(1, max(2, R["totalWE"]) + 1))
    fig = go.Figure([
        go.Scatter(x=xs, y=[gz_din(k) for k in xs], name="DIN 4708",
                   line=dict(color="#4fa3e0" if dunkel else "#0a3b5c", width=2.8)),
        go.Scatter(x=xs, y=[gz_tud(k) for k in xs], name="TU Dresden",
                   line=dict(color="#5cc26a" if dunkel else GREEN, width=2.4)),
    ])
    return _chart(fig, "Gleichzeitigkeit GZ", ".1f", dunkel)


def chart_din18015(n_we: int, dunkel: bool = False) -> go.Figure:
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
    fig = _chart(fig, "Leistung am Netzanschluss [kW]", ".0f", dunkel)
    fig.update_xaxes(title="Anzahl Wohneinheiten am Netzanschluss", range=[0.5, 30.5])
    fig.update_yaxes(range=[0, 150])
    return fig


def _chart(fig: go.Figure, ylab: str, yfmt: str, dunkel: bool = False) -> go.Figure:
    ink, gitter = ("#dbe4ec", "rgba(255,255,255,.08)") if dunkel else (INK, "#e9edf1")
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=36, b=10), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", font={**FONT, "color": ink}, hovermode="x unified", separators=",.",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=ink)),
                      hoverlabel=dict(bgcolor="#1b2733" if dunkel else "#ffffff", font=dict(color=ink)))
    fig.update_xaxes(title="kumulierte Wohneinheiten", gridcolor=gitter, zeroline=False, linecolor=gitter)
    fig.update_yaxes(title=ylab, gridcolor=gitter, zeroline=False, rangemode="tozero", hoverformat=yfmt)
    return fig
