"""Anlagenschema als SVG – gleiche Ausgabe wie schemaSvg() in index.html (tests/test_rechnen.py vergleicht beide).

Raster: oben Legende und Heizkreise mit Verteilerbalken, darunter ein Korridor für die Speicherladung, unten die
Geräte. Unter den Geräten liegt nur das Beschriftungsband – dort verlaufen keine Rohre, Texte überdecken keine Linien.
Piktogramme im Stil der Systemkonfiguration (SysCon): Fußbodenheizung mit Wärmewellen, Heizkörper, Dusche,
Außeneinheit mit Ventilator, nummerierte Abschnitte 1 Wärmeerzeuger · 2 Heizkreise · 3 Warmwasser · 4 Puffer.
"""
from __future__ import annotations

import math

# Farben für Ausdruck/PDF (die HTML-Seite nutzt CSS-Variablen für Hell/Dunkel)
FARBEN_DRUCK = {"vl": "#e20015", "rl": "#005691", "ww": "#e98300", "kw": "#2e9a3e", "so": "#7a3e9d", "ink": "#141e29",
                "soft": "#4a5866", "faint": "#78889a", "paper": "#ffffff", "panel": "#eaf0f5", "badge": "#0a6fb3"}


def z(x) -> str:
    """Zahl wie JavaScript String(x)."""
    if isinstance(x, bool):
        return str(x).lower()
    if isinstance(x, (int, float)):
        return str(int(x)) if float(x).is_integer() else repr(float(x))
    return str(x)


def esc(s) -> str:
    return (str("" if s is None else s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def zahl(x: float, d: int) -> str:
    """Wie schemaZahl() in index.html: kaufmännisch runden, Tausenderpunkt, Dezimalkomma."""
    v = math.floor(abs(x) * 10 ** d + 0.5) / 10 ** d
    ganz, _, rest = f"{v:.{d}f}".partition(".")
    ganz = f"{int(ganz):,}".replace(",", ".")
    return ("-" if x < 0 and v != 0 else "") + ganz + ("," + rest if d else "")


def schema_svg(r: dict, ie: dict | None, kreise: list[dict], F: dict, W: int = 900) -> str:
    g = r.get("gewaehlt")
    if not g:
        return ""
    H = 470
    sole, friwa, ww = r["waermequelle"] == "sole", r["tww"]["system"] == "friwa", r["tww"]["aktiv"]
    kaskade = not sole and (g["n"] > 1 or g["serie"] == "CS5001")
    integriert = (not friwa) and bool(ie) and ie.get("speicher") == "integriert"
    puffermodul = bool(ie) and "Puffer" in ie.get("art", "")
    mit_puffer = kaskade or friwa or not (integriert or puffermodul)
    yB, hB, hkY, yK1, yK2 = 300, 80, 160, 228, 244
    yLab = yB + hB + 22
    xW, xP, xIE, wIE, xAE, xV0, xV1 = 50, W - 500, W - 330, 64, W - 150, W - 360, W - 20

    def t(x, y, s, a):
        return f'<text x="{z(x)}" y="{z(y)}" {a}>{esc(s)}</text>'

    def lab(cx, s1, s2, s3):
        out = t(cx, yLab, s1, f'font-size="11.5" font-weight="700" text-anchor="middle" fill="{F["ink"]}"')
        if s2:
            out += t(cx, yLab + 14, s2, f'font-size="10.5" text-anchor="middle" fill="{F["soft"]}"')
        if s3:
            out += t(cx, yLab + 27, s3, f'font-size="10.5" text-anchor="middle" fill="{F["soft"]}"')
        return out

    def ln(d, c, dash=False):
        return f'<path class="rohr" d="{d}" fill="none" stroke="{c}" stroke-width="2.4"' + (' stroke-dasharray="5 4"' if dash else "") + "/>"

    def box(x, y, w, h, rr):
        return f'<rect x="{z(x)}" y="{z(y)}" width="{z(w)}" height="{z(h)}" rx="{z(rr)}" fill="{F["paper"]}" stroke="{F["ink"]}" stroke-width="2.2"/>'

    def nummer(x, y, n):
        return (f'<circle cx="{z(x)}" cy="{z(y)}" r="11" fill="{F["badge"]}"/>' +
                t(x, y + 4.5, str(n), 'font-size="12" font-weight="700" text-anchor="middle" fill="#ffffff"'))

    def luefter(cx, cy):
        out = f'<circle cx="{z(cx)}" cy="{z(cy)}" r="22" fill="none" stroke="{F["ink"]}" stroke-width="2.2"/>'
        for w in (0, 120, 240):
            out += (f'<path d="M{z(cx)},{z(cy)} C{z(cx - 7)},{z(cy - 6)} {z(cx - 6)},{z(cy - 17)} {z(cx)},{z(cy - 18)} '
                    f'C{z(cx + 6)},{z(cy - 17)} {z(cx + 7)},{z(cy - 6)} {z(cx)},{z(cy)} Z" fill="{F["ink"]}" '
                    f'transform="rotate({w} {z(cx)} {z(cy)})"/>')
        return out + f'<circle cx="{z(cx)}" cy="{z(cy)}" r="4" fill="{F["paper"]}" stroke="{F["ink"]}" stroke-width="1.6"/>'

    s = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         'font-family="Helvetica, Arial, sans-serif" class="schema">')
    leg = [(F["vl"], "Vorlauf Heizung", 0), (F["rl"], "Rücklauf Heizung", 1), (F["ww"], "Warmwasser", 0),
           (F["kw"], "Kaltwasser", 0)] + ([(F["so"], "Sole", 0)] if sole else [])
    for i, (c, txt, d) in enumerate(leg):
        x = W - len(leg) * 125 + i * 125
        s += (f'<line x1="{x}" x2="{x + 25}" y1="12" y2="12" stroke="{c}" stroke-width="2.4"' +
              (' stroke-dasharray="5 4"' if d else "") + "/>" + t(x + 30, 16, txt, f'font-size="11" fill="{F["soft"]}"'))

    # ---- 2 Heizkreise
    br = (xV1 - xV0 - 30) / len(kreise)
    s += (f'<path class="rohr" d="M{xV0},{hkY} L{xV1},{hkY}" stroke="{F["vl"]}" stroke-width="8"/>'
          f'<path class="rohr" d="M{xV0},{hkY + 18} L{xV1},{hkY + 18}" stroke="{F["rl"]}" stroke-width="8"/>')
    s += t(xV1, hkY + 40, f"Heizkreisverteiler · max. {zahl(r['vl'], 0)} °C", f'font-size="10.5" text-anchor="end" fill="{F["soft"]}"')
    s += nummer(xV0 + 14, hkY - 62, 2)
    for i, h in enumerate(kreise):
        cx = xV0 + 30 + i * br + br / 2
        xv, xr, y0 = cx - 10, cx + 10, hkY - 80
        s += ln(f"M{z(xv)},{hkY - 4} L{z(xv)},{y0 + 28}", F["vl"]) + ln(f"M{z(xr)},{hkY + 14} L{z(xr)},{y0 + 28}", F["rl"], True)
        s += (f'<circle cx="{z(xv)}" cy="{hkY - 18}" r="5.5" fill="{F["paper"]}" stroke="{F["ink"]}" stroke-width="1.4"/>'
              f'<path d="M{z(xv - 3)},{hkY - 15} L{z(xv)},{hkY - 21} L{z(xv + 3)},{hkY - 15}" fill="none" stroke="{F["ink"]}" stroke-width="1.1"/>')
        if h["gemischt"]:
            s += (ln(f"M{z(xr)},{hkY - 38} L{z(xv + 6)},{hkY - 38}", F["rl"], True) +
                  f'<path d="M{z(xv - 6)},{hkY - 44} L{z(xv + 6)},{hkY - 32} L{z(xv + 6)},{hkY - 44} L{z(xv - 6)},{hkY - 32} Z" '
                  f'fill="{F["paper"]}" stroke="{F["ink"]}" stroke-width="1.3"/>' +
                  t(xv - 9, hkY - 35, "M", f'font-size="9" text-anchor="end" fill="{F["soft"]}"'))
        if h["typ"] == "fbh":
            s += (f'<path d="M{z(cx - 22)},{y0 + 28} L{z(cx + 22)},{y0 + 28} L{z(cx + 15)},{y0 + 15} L{z(cx - 15)},{y0 + 15} Z" '
                  f'fill="{F["paper"]}" stroke="{F["ink"]}" stroke-width="2"/>')
            for dx in (-9, 0, 9):
                s += f'<path d="M{z(cx + dx)},{y0 + 12} c-4,-3 4,-6 0,-9 c-4,-3 4,-6 0,-9" fill="none" stroke="{F["ink"]}" stroke-width="1.8"/>'
        elif h["typ"] == "hk":
            s += f'<rect x="{z(cx - 20)}" y="{y0}" width="40" height="28" rx="3" fill="{F["paper"]}" stroke="{F["ink"]}" stroke-width="2"/>'
            for j in range(5):
                s += f'<line x1="{z(cx - 12 + j * 6)}" x2="{z(cx - 12 + j * 6)}" y1="{y0 + 5}" y2="{y0 + 23}" stroke="{F["ink"]}" stroke-width="2.6"/>'
        else:
            s += f'<rect x="{z(cx - 20)}" y="{y0}" width="40" height="28" rx="3" fill="{F["paper"]}" stroke="{F["ink"]}" stroke-width="2"/>'
            for j in range(3):
                s += f'<line x1="{z(cx - 14)}" x2="{z(cx - 2)}" y1="{y0 + 8 + j * 6}" y2="{y0 + 8 + j * 6}" stroke="{F["ink"]}" stroke-width="1.6"/>'
            s += f'<circle cx="{z(cx + 9)}" cy="{y0 + 14}" r="6" fill="none" stroke="{F["ink"]}" stroke-width="1.6"/>'
        art = {"hk": "Heizkörper", "fbh": "FBH", "konvektor": "Konvektor"}[h["typ"]] + (
            (" · gem." if br < 90 else " · gemischt") if h["gemischt"] else "")
        s += (t(cx, y0 - 26, f"HK {h['nr']}", f'font-size="10.5" font-weight="700" text-anchor="middle" fill="{F["ink"]}"') +
              t(cx, y0 - 14, art, f'font-size="9.5" text-anchor="middle" fill="{F["soft"]}"'))

    # ---- 1 Wärmeerzeuger
    if sole:
        s += f'<rect x="{xAE - 6}" y="{yB - 12}" width="116" height="{hB + 18}" fill="{F["panel"]}" stroke="none"/>'
        s += ln(f"M{xIE + wIE},{yB + 25} L{xAE + 65},{yB + 25} L{xAE + 65},{yB + hB - 8} Q{xAE + 50},{yB + hB + 4} "
                f"{xAE + 35},{yB + hB - 8} L{xAE + 35},{yB + 50} L{xIE + wIE},{yB + 50}", F["so"])
        er = r.get("erdreich")
        s += lab(xAE + 52, "Erdwärmesonde", f"ca. {zahl(er['sondenlaenge_m'], 0)} m (Richtwert)" if er else "oder Flächenkollektor", "")
        s += nummer(xAE + 122, yB - 14, 1)
    else:
        n_ae = min(g["n"], 3)
        for i in range(n_ae):
            y, x = yB - (n_ae - 1) * 8 + i * 8, xAE + i * 8
            s += box(x, y, 105, hB, 12)
            if i == n_ae - 1:
                s += luefter(x + 52, y + hB / 2)
        lt = r.get("leitung")
        s += lab(xAE + 56, (f"{g['n']} × " if g["n"] > 1 else "") + "Außeneinheit", g["geraet"],
                 f"{zahl(lt['laenge_m'], 0)} m · {lt['rohr']}" if lt else "")
        s += nummer(xAE + 128, yB - 14, 1)

    # ---- Inneneinheit / Sole-WP / Kaskadenregler
    if kaskade:
        s += (f'<rect x="{xIE - 13}" y="{yB + 18}" width="90" height="38" rx="6" fill="{F["paper"]}" stroke="{F["ink"]}" stroke-width="1.6"/>' +
              t(xIE + 32, yB + 34, ie["typ"] if ie and ie.get("ab_anzahl") else "HPC 301",
                f'font-size="10.5" font-weight="700" text-anchor="middle" fill="{F["ink"]}"') +
              t(xIE + 32, yB + 48, "Kaskadenregler" if g["n"] > 1 else "WP-Manager", f'font-size="9.5" text-anchor="middle" fill="{F["soft"]}"'))
        s += f'<path d="M{xIE + 77},{yB + 37} L{xAE},{yB + 37}" stroke="{F["faint"]}" stroke-dasharray="1 4" stroke-width="2" fill="none"/>'
    else:
        s += box(xIE, yB - 10, wIE, hB + 20, 10) + f'<circle cx="{z(xIE + wIE / 2)}" cy="{yB + 66}" r="8" fill="none" stroke="{F["ink"]}" stroke-width="2"/>'
        if integriert:
            s += (f'<rect x="{xIE + 8}" y="{yB + 2}" width="{wIE - 16}" height="40" rx="5" fill="none" stroke="{F["ww"]}" stroke-width="1.6"/>' +
                  t(xIE + wIE / 2, yB + 26, "WW", f'font-size="10" font-weight="700" text-anchor="middle" fill="{F["ww"]}"'))
        if puffermodul:
            s += (f'<rect x="{xIE + 8}" y="{yB + 2}" width="{wIE - 16}" height="40" rx="5" fill="none" stroke="{F["soft"]}" stroke-width="1.6"/>' +
                  t(xIE + wIE / 2, yB + 26, "Puffer", f'font-size="9.5" text-anchor="middle" fill="{F["soft"]}"'))
        s += lab(xIE + wIE / 2, "Sole/Wasser-WP" if sole else "Inneneinheit", g["geraet"] if sole else (ie["typ"] if ie else ""),
                 "mit WW-Speicher" if integriert else ("mit Puffer" if puffermodul else ""))
        if not sole:
            s += ln(f"M{xIE + wIE},{yB + 25} L{xAE},{yB + 25}", F["vl"]) + ln(f"M{xIE + wIE},{yB + 50} L{xAE},{yB + 50}", F["rl"], True)

    # ---- 4 Pufferspeicher
    if mit_puffer:
        s += box(xP, yB - 20, 50, hB + 20, 10) + f'<rect x="{xP + 13}" y="{yB - 6}" width="24" height="{hB - 8}" rx="5" fill="none" stroke="{F["ink"]}" stroke-width="2"/>'
        s += lab(xP + 25, "Trennpuffer" if kaskade else "Pufferspeicher",
                 f"≥ {zahl(r['tww']['t_speicher'], 0)} °C für FriWa" if friwa else ("hydraulische Weiche" if kaskade else "Reihen-/Trennpuffer"), "")
        s += nummer(xP + 68, yB - 32, 4)
        if kaskade:
            s += ln(f"M{xP + 50},{yB - 4} L{xAE},{yB - 4}", F["vl"]) + ln(f"M{xP + 50},{yB + 70} L{xAE},{yB + 70}", F["rl"], True)
        else:
            s += ln(f"M{xP + 50},{yB + 5} L{xIE},{yB + 5}", F["vl"]) + ln(f"M{xP + 50},{yB + 70} L{xIE},{yB + 70}", F["rl"], True)
        s += (ln(f"M{xP + 18},{yB - 20} L{xP + 18},{hkY} L{xV0},{hkY}", F["vl"]) +
              ln(f"M{xP + 32},{yB - 20} L{xP + 32},{hkY + 18} L{xV0},{hkY + 18}", F["rl"], True))
    else:
        s += (ln(f"M{xIE + 20},{yB - 10} L{xIE + 20},{hkY} L{xV0},{hkY}", F["vl"]) +
              ln(f"M{xIE + 44},{yB - 10} L{xIE + 44},{hkY + 18}", F["rl"], True))

    # ---- 3 Warmwasser
    def dusche(x, y, xk):
        """Dusche/Zapfstelle: Leitung von (x, y) nach oben, Brausekopf bei xk."""
        out = (ln(f"M{x},{y} L{x},70 L{xk},70 L{xk},78", F["ww"]) +
               f'<line x1="{xk - 14}" x2="{xk + 14}" y1="80" y2="80" stroke="{F["ink"]}" stroke-width="3.5"/>')
        for zz in range(3):
            for k in range(3 + zz):
                out += f'<circle cx="{z(xk + (k - (2 + zz) / 2) * 9)}" cy="{88 + zz * 7}" r="1.6" fill="{F["ink"]}"/>'
        return out + t(min(x, xk) - 4, 52, "Dusche / Zapfstelle", f'font-size="10.5" fill="{F["soft"]}"')

    def kalt(y_in):
        return ln(f"M{xW},{y_in} L{xW - 34},{y_in} L{xW - 34},{H - 14}", F["kw"]) + t(xW - 30, H - 4, "Kaltwasser", f'font-size="10.5" fill="{F["soft"]}"')

    if friwa and ww:
        s += box(xW, yB, 80, 60, 8) + "".join(
            f'<line x1="{xW + 15}" x2="{xW + 65}" y1="{yB + dy}" y2="{yB + dy}" stroke="{F["ink"]}" stroke-width="1.6"/>' for dy in (15, 30, 45))
        s += lab(xW + 40, "Frischwasserstation", f"Zapftemperatur {zahl(r['tww']['t_zapf'], 0)} °C", "")
        s += nummer(xW - 14, yB - 14, 3)
        s += ln(f"M{xP},{yB + 10} L{xW + 80},{yB + 10}", F["vl"]) + ln(f"M{xP},{yB + 50} L{xW + 80},{yB + 50}", F["rl"], True)
        s += dusche(xW + 20, yB, xW + 60) + kalt(yB + 45)
    elif not integriert and ww:
        s += box(xW, yB - 20, 80, hB + 20, 10)
        zick = " ".join(f"L{xW + 18},{yB + 35 + j * 7} L{xW + 62},{yB + 39 + j * 7}" for j in range(4))
        s += (f'<path d="M{xW + 80},{yB + 30} L{xW + 62},{yB + 30} {zick} L{xW + 62},{yB + 62} L{xW + 80},{yB + 62}" '
              f'fill="none" stroke="{F["vl"]}" stroke-width="2"/>')
        s += lab(xW + 40, "Warmwasserspeicher", ("WW-Modul · " if kaskade else "Heizwendel · ") + zahl(r["tww"]["t_speicher"], 0) + " °C", "")
        s += nummer(xW - 14, yB - 34, 3)
        if kaskade:
            qv, qr = f"L{xAE - 22},{yK1} L{xAE - 22},{yB - 4}", f"L{xAE - 36},{yK2} L{xAE - 36},{yB + 70}"
        elif sole:
            qv, qr = f"L{xP + 86},{yK1} L{xP + 86},{yB + 5}", f"L{xP + 100},{yK2} L{xP + 100},{yB + 70}"
        else:
            qv, qr = (f"L{xIE + wIE + 22},{yK1} L{xIE + wIE + 22},{yB + 25}", f"L{xIE + wIE + 36},{yK2} L{xIE + wIE + 36},{yB + 50}")
        s += (ln(f"M{xW + 80},{yB + 30} L{xW + 100},{yB + 30} L{xW + 100},{yK1} {qv}", F["vl"]) +
              ln(f"M{xW + 80},{yB + 62} L{xW + 114},{yB + 62} L{xW + 114},{yK2} {qr}", F["rl"], True))
        s += dusche(xW + 20, yB - 20, xW + 60) + kalt(yB + hB - 6)
    elif integriert and ww:
        s += dusche(xIE + 10, yB - 10, xIE - 40)
    return s + "</svg>"
