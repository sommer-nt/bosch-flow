"""Gemeinsame Zeichenschicht für Bildschirm (Plotly) und PDF (fpdf2).

Eine ``Szene`` beschreibt ein Schema in Pixel-Koordinaten (Ursprung oben links, y nach unten – wie das
Canvas der HTML-Version). Dieselbe Szene wird für die App als Plotly-Grafik und für den PDF-Bericht als
Vektorgrafik ausgegeben, damit beide exakt gleich aussehen.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import plotly.graph_objects as go

ICONS = Path(__file__).parent / "daten" / "icons"

HELL = {"vl": "#e20015", "rl": "#005691", "navy": "#004975", "ink": "#12181f", "soft": "#7a848f",
        "card": "#ffffff", "cardline": "#c4ccd4", "bg": "#eef2f6", "accent": "#005691", "warn": "#b26a00",
        "ok": "#2e7d32", "gold": "#c98a00", "dn": "#2f7d32", "dnbg": "#e4f1e5", "panel": "#f4f7fa",
        "papier": "#ffffff", "grid": "#e9edf1", "icon_invert": False}
DUNKEL = {"vl": "#ff4d5e", "rl": "#4fa3e0", "navy": "#5fb8e8", "ink": "#e6edf3", "soft": "#9fb0c0",
          "card": "#151d25", "cardline": "#3a4a58", "bg": "#1b242d", "accent": "#4fa3e0", "warn": "#e0a83a",
          "ok": "#5cc26a", "gold": "#e0a83a", "dn": "#5cc26a", "dnbg": "#1d3322", "panel": "#1b242d",
          "papier": "#0e1117", "grid": "#2a3742", "icon_invert": True}


def farben(dunkel: bool = False) -> dict:
    return DUNKEL if dunkel else HELL


@dataclass
class Linie:
    x0: float
    y0: float
    x1: float
    y1: float
    farbe: str
    breite: float = 2
    strich: str | None = None      # None | "dash" | "dot"


@dataclass
class Rechteck:
    x0: float
    y0: float
    x1: float
    y1: float
    fuell: str | None = None
    rand: str | None = None
    breite: float = 1
    radius: float = 0
    unten: bool = False            # Hintergrundfläche: unter Bildern/Icons zeichnen


@dataclass
class Kreis:
    cx: float
    cy: float
    r: float
    fuell: str | None = None
    rand: str | None = None
    breite: float = 1


@dataclass
class Text:
    x: float
    y: float
    text: str
    groesse: float = 11
    farbe: str = "#12181f"
    fett: bool = False
    anker: str = "middle"          # start | middle | end
    vanker: str = "middle"         # top | middle | bottom
    hintergrund: str | None = None


@dataclass
class Icon:
    name: str                      # Datei in daten/icons (ohne .svg)
    x0: float
    y0: float
    x1: float
    y1: float
    invert: bool = False


@dataclass
class Pfeil:
    x0: float
    y0: float
    x1: float
    y1: float
    farbe: str
    breite: float = 2


@dataclass
class Szene:
    breite: float
    hoehe: float
    elemente: list = field(default_factory=list)
    hover: list = field(default_factory=list)      # (x, y, text) – Infos beim Überfahren mit der Maus

    def info(self, x: float, y: float, text: str) -> None:
        self.hover.append((x, y, text))

    def add(self, *el):
        self.elemente.extend(el)
        return self

    # Kurzformen
    def linie(self, *a, **k):
        self.elemente.append(Linie(*a, **k))

    def rechteck(self, *a, **k):
        self.elemente.append(Rechteck(*a, **k))

    def kreis(self, *a, **k):
        self.elemente.append(Kreis(*a, **k))

    def text(self, *a, **k):
        self.elemente.append(Text(*a, **k))


# ====================================================================== Plotly
@lru_cache(maxsize=16)
def _icon_uri(name: str, invert: bool) -> str:
    svg = (ICONS / f"{name}.svg").read_text(encoding="utf-8")
    if invert:
        svg = svg.replace("#1D1D1B", "#E6EDF3").replace("#1d1d1b", "#e6edf3")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _rund(x0, y0, x1, y1, r) -> str:
    r = min(r, abs(x1 - x0) / 2, abs(y1 - y0) / 2)
    return (f"M{x0 + r},{y0} L{x1 - r},{y0} Q{x1},{y0} {x1},{y0 + r} L{x1},{y1 - r} Q{x1},{y1} {x1 - r},{y1} "
            f"L{x0 + r},{y1} Q{x0},{y1} {x0},{y1 - r} L{x0},{y0 + r} Q{x0},{y0} {x0 + r},{y0} Z")


_DASH = {None: "solid", "dash": "dash", "dot": "dot"}
_XANCHOR = {"start": "left", "middle": "center", "end": "right"}
_YANCHOR = {"top": "top", "middle": "middle", "bottom": "bottom"}


def als_plotly(s: Szene, papier: str = "rgba(0,0,0,0)", max_hoehe: int | None = None,
              breite_px: int = 1000) -> go.Figure:
    """Szene -> Plotly-Figur (y nach unten, Seitenverhältnis fest)."""
    shapes, notes, images = [], [], []
    for e in s.elemente:
        if isinstance(e, Linie):
            shapes.append(dict(type="line", x0=e.x0, y0=e.y0, x1=e.x1, y1=e.y1, layer="above",
                               line=dict(color=e.farbe, width=e.breite, dash=_DASH[e.strich])))
        elif isinstance(e, Rechteck):
            line = dict(color=e.rand, width=e.breite) if e.rand else dict(width=0)
            if e.radius:
                shapes.append(dict(type="path", path=_rund(e.x0, e.y0, e.x1, e.y1, e.radius),
                                   fillcolor=e.fuell or "rgba(0,0,0,0)", line=line,
                                   layer="below" if e.unten else "above"))
            else:
                shapes.append(dict(type="rect", x0=e.x0, y0=e.y0, x1=e.x1, y1=e.y1,
                                   layer="below" if e.unten else "above",
                                   fillcolor=e.fuell or "rgba(0,0,0,0)", line=line))
        elif isinstance(e, Kreis):
            line = dict(color=e.rand, width=e.breite) if e.rand else dict(width=0)
            shapes.append(dict(type="circle", x0=e.cx - e.r, y0=e.cy - e.r, x1=e.cx + e.r, y1=e.cy + e.r,
                               fillcolor=e.fuell or "rgba(0,0,0,0)", line=line, layer="above"))
        elif isinstance(e, Pfeil):
            notes.append(dict(x=e.x1, y=e.y1, ax=e.x0, ay=e.y0, xref="x", yref="y", axref="x", ayref="y",
                              showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=e.breite, arrowcolor=e.farbe,
                              text=""))
        elif isinstance(e, Text):
            t = e.text.replace("\n", "<br>")
            notes.append(dict(x=e.x, y=e.y, text=f"<b>{t}</b>" if e.fett else t, showarrow=False,
                              xanchor=_XANCHOR[e.anker], yanchor=_YANCHOR[e.vanker],
                              font=dict(size=e.groesse, color=e.farbe),
                              bgcolor=e.hintergrund or "rgba(0,0,0,0)", borderpad=2 if e.hintergrund else 0))
        elif isinstance(e, Icon):
            images.append(dict(source=_icon_uri(e.name, e.invert), xref="x", yref="y", x=e.x0, y=e.y0,
                               sizex=e.x1 - e.x0, sizey=e.y1 - e.y0, xanchor="left", yanchor="top",
                               sizing="contain", layer="above"))
    fig = go.Figure()
    if s.hover:
        fig.add_trace(go.Scatter(
            x=[h[0] for h in s.hover], y=[h[1] for h in s.hover], mode="markers", text=[h[2] for h in s.hover],
            hovertemplate="%{text}<extra></extra>", showlegend=False,
            marker=dict(size=22, color="rgba(0,0,0,0)", line=dict(width=0))))
        fig.update_layout(hoverlabel=dict(bgcolor="#ffffff", bordercolor="#005691", font=dict(color="#12181f", size=12)))
    # Höhe passend zur erwarteten Darstellungsbreite – sonst bleibt über/unter dem Schema Leerraum
    hoehe = int(s.hoehe * min(1.0, breite_px / s.breite)) + 4
    if max_hoehe is not None:
        hoehe = min(hoehe, max_hoehe)
    fig.update_layout(shapes=shapes, annotations=notes, images=images, height=hoehe, showlegend=False,
                      margin=dict(l=0, r=0, t=0, b=0), plot_bgcolor=papier, paper_bgcolor=papier,
                      dragmode=False, hovermode="closest",
                      font=dict(family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"))
    fig.update_xaxes(range=[0, s.breite], visible=False, fixedrange=True)
    fig.update_yaxes(range=[s.hoehe, 0], visible=False, fixedrange=True, scaleanchor="x", scaleratio=1)
    return fig


# ====================================================================== PDF (fpdf2)
def _rgb(farbe: str) -> tuple:
    f = farbe.lstrip("#")
    if len(f) == 3:
        f = "".join(c * 2 for c in f)
    return tuple(int(f[i:i + 2], 16) for i in (0, 2, 4))


def in_pdf(pdf, s: Szene, x: float, y: float, w: float, h: float | None = None) -> float:
    """Szene in den Rahmen (x, y, w[, h]) in mm zeichnen – maßstäblich, oben bündig. Gibt die Höhe zurück."""
    k = w / s.breite if h is None else min(w / s.breite, h / s.hoehe)
    ox = x + (w - s.breite * k) / 2

    def X(v):
        return ox + v * k

    def Y(v):
        return y + v * k

    for e in s.elemente:
        if isinstance(e, Linie):
            pdf.set_draw_color(*_rgb(e.farbe))
            pdf.set_line_width(max(0.1, e.breite * k * 0.9))
            if e.strich:
                pdf.set_dash_pattern(dash=1.2 if e.strich == "dash" else 0.4, gap=0.8)
            pdf.line(X(e.x0), Y(e.y0), X(e.x1), Y(e.y1))
            if e.strich:
                pdf.set_dash_pattern()
        elif isinstance(e, Rechteck):
            stil = ("F" if e.fuell else "") + ("D" if e.rand else "")
            if not stil:
                continue
            if e.fuell:
                pdf.set_fill_color(*_rgb(e.fuell))
            if e.rand:
                pdf.set_draw_color(*_rgb(e.rand))
                pdf.set_line_width(max(0.1, e.breite * k))
            x0, x1 = sorted((X(e.x0), X(e.x1)))
            y0, y1 = sorted((Y(e.y0), Y(e.y1)))
            if e.radius:
                pdf.rect(x0, y0, x1 - x0, y1 - y0, style=stil, round_corners=True,
                         corner_radius=min(e.radius * k, (x1 - x0) / 2, (y1 - y0) / 2))
            else:
                pdf.rect(x0, y0, x1 - x0, y1 - y0, style=stil)
        elif isinstance(e, Kreis):
            stil = ("F" if e.fuell else "") + ("D" if e.rand else "")
            if e.fuell:
                pdf.set_fill_color(*_rgb(e.fuell))
            if e.rand:
                pdf.set_draw_color(*_rgb(e.rand))
                pdf.set_line_width(max(0.1, e.breite * k))
            pdf.circle(x=X(e.cx), y=Y(e.cy), radius=e.r * k, style=stil or "D")
        elif isinstance(e, Pfeil):
            pdf.set_draw_color(*_rgb(e.farbe))
            pdf.set_fill_color(*_rgb(e.farbe))
            pdf.set_line_width(max(0.1, e.breite * k))
            pdf.line(X(e.x0), Y(e.y0), X(e.x1), Y(e.y1))
            import math
            ang = math.atan2(Y(e.y1) - Y(e.y0), X(e.x1) - X(e.x0))
            L = 2.2
            p1 = (X(e.x1) - L * math.cos(ang - 0.45), Y(e.y1) - L * math.sin(ang - 0.45))
            p2 = (X(e.x1) - L * math.cos(ang + 0.45), Y(e.y1) - L * math.sin(ang + 0.45))
            pdf.polygon([(X(e.x1), Y(e.y1)), p1, p2], style="F")
        elif isinstance(e, Icon):
            farbe = (255, 255, 255) if e.invert else (0x1D, 0x1D, 0x1B)   # SVG-Pfade ohne eigene Füllung
            pdf.set_fill_color(*farbe)
            pdf.set_draw_color(*farbe)
            try:
                pdf.image(str(ICONS / f"{e.name}.svg"), x=X(e.x0), y=Y(e.y0), w=(e.x1 - e.x0) * k,
                          h=(e.y1 - e.y0) * k, keep_aspect_ratio=True)
            except Exception:  # noqa: BLE001 – Icon fehlt/nicht lesbar: Schema bleibt vollständig
                pass
        elif isinstance(e, Text):
            pt = max(3.5, e.groesse * k * 2.6)
            pdf.set_font(pdf.schrift, "B" if e.fett else "", pt)
            pdf.set_text_color(*_rgb(e.farbe))
            zeilen = e.text.split("\n")
            lh = pt * 0.3528 * 1.18
            gesamt = lh * len(zeilen)
            y0 = Y(e.y) - (0 if e.vanker == "top" else gesamt if e.vanker == "bottom" else gesamt / 2)
            for i, z in enumerate(zeilen):
                z = pdf.t(z)
                tw = pdf.get_string_width(z)
                xx = X(e.x) - (0 if e.anker == "start" else tw if e.anker == "end" else tw / 2)
                if e.hintergrund:
                    pdf.set_fill_color(*_rgb(e.hintergrund))
                    pdf.rect(xx - 0.6, y0 + i * lh - 0.2, tw + 1.2, lh + 0.2, style="F")
                pdf.text(xx, y0 + i * lh + lh * 0.78, z)
    pdf.set_text_color(0, 0, 0)
    return s.hoehe * k
