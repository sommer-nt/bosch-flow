"""Streamlit-Startseite (static/index.html) im Container anpassen – wird im Dockerfile ausgeführt.

Bis Streamlit geladen ist, zeigt der Browser nur diese Seite: ohne Anpassung ist sie weiß, auch im Dunkelmodus.
Ergänzt werden Viewport ohne iOS-Auto-Zoom, Hintergrundfarbe passend zum gewählten Farbschema (localStorage) bzw. zum System, Theme-Farbe für die
Browserleiste, Titel und Angaben für „Zum Home-Bildschirm“ auf dem iPhone. Mehrfaches Ausführen ist unschädlich.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

MARKE = "<!-- bosch-flow -->"
HELL, DUNKEL = "#f3f5f8", "#0b1016"
KOPF = f"""{MARKE}
<meta name="theme-color" content="{HELL}" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="{DUNKEL}" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Bosch Flow">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<style>html,body{{background:{HELL}}}@media (prefers-color-scheme:dark){{html,body{{background:{DUNKEL}}}}}</style>
<script>try{{var t=localStorage.getItem("stActiveTheme-"+location.pathname+"-v2");if(t){{t=JSON.parse(t);
var n=(typeof t==="string"?t:(t&&t.name)||"")+"";var d=/dark/i.test(n);
document.documentElement.style.background=d?"{DUNKEL}":"{HELL}";document.documentElement.style.colorScheme=d?"dark":"light"}}}}catch(e){{}}</script>
"""


def patch(datei: Path) -> bool:
    html = datei.read_text(encoding="utf-8")
    if MARKE in html:
        return False
    html = html.replace("<title>Streamlit</title>", "<title>Bosch Flow</title>", 1)
    # iOS zoomt beim Antippen eines Felds in die Seite und bleibt vergrößert (Kacheln rechts abgeschnitten);
    # maximum-scale verhindert das Auto-Zoomen, Aufziehen mit zwei Fingern bleibt auf dem iPhone möglich.
    html, n = re.subn(r'name="viewport"\s+content="[^"]*"',
                      'name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, '
                      'viewport-fit=cover"', html, count=1)
    if not n:                                  # andere Streamlit-Version: eigenen Viewport ergänzen
        html = html.replace("</head>", '<meta name="viewport" content="width=device-width, initial-scale=1, '
                                        'maximum-scale=1, viewport-fit=cover"></head>', 1)
    datei.write_text(html.replace("</head>", KOPF + "</head>", 1), encoding="utf-8")
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ziel = Path(sys.argv[1])
    else:
        import streamlit
        ziel = Path(streamlit.__file__).parent / "static" / "index.html"
    print("index.html angepasst" if patch(ziel) else "index.html war schon angepasst", ziel)
