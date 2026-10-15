# bosch-flow

Netz- & Anlagenrechner für Wohnungsstationen (Flow 8000 / Flow 7000): Gleichzeitigkeit nach DIN 4708 bzw.
TU Dresden, Rohrdimensionierung je Strang, Wärmezentrale (Kessel-/FW-Leistung, Pufferspeicher nach
Bosch-HIU-Methodik) und DLE-Auslegungshilfe (Flow 7000 HPS).

![Streamlit-Version](docs/streamlit.png)

Es gibt zwei Versionen mit identischem Rechenweg:

| | `index.html` (V54) | Python / Streamlit |
|---|---|---|
| Start | Datei im Browser öffnen, läuft offline | `streamlit run app.py` |
| Oberfläche | Original mit Canvas-Schemata | gleicher Aufbau: Eingabekarten ①②③ links, Ergebniskarten rechts |
| Sicherung | automatisch im Browser | automatisch im Browser + „Zwischenspeichern“, Wiederherstellen beim Öffnen |
| Hell/Dunkel | Schalter ☾/☀ | Schalter ☾/☀ in der Kopfzeile |
| Export | PDF (Druck), Projekt-JSON | PDF-Auslegungsbericht, Projekt-JSON, Excel |
| Projektdateien | `.json` | dasselbe `.json`-Format, in beide Richtungen austauschbar |

## Python-Version starten

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Die App öffnet sich unter <http://localhost:8501>.

## Bedienung (Kurzüberblick)

- **Sicherung:** Jede Eingabe wird automatisch im Browser gesichert und beim nächsten Öffnen wiederhergestellt
  (auch nach dem Hell/Dunkel-Umschalten). „Zwischenspeichern“ sichert sofort; „Speichern“ lädt eine Projektdatei
  (.json) herunter, die auch die HTML-Version öffnet. Die Browser-Sicherung bleibt im jeweiligen Browser.
- **Netzschema:** Mit der Maus über Stationen und DN-Marken fahren – zeigt WE, Gleichzeitigkeit, Volumenstrom, Rohr,
  Geschwindigkeit, Druckverlust und Status. DN-Farbe: grün = OK, orange = grenzwertig, rot = über v_max.
  „📌 Anheften“ hält das Schema beim Scrollen sichtbar.
- **Alle Stränge:** Netztopologie mit Regler für die Position der Wärmezentrale (wird mitgespeichert), „⤢ Vollbild“,
  Hauptstrang je Abschnitt mit maßgeblichem Abschnitt, Gesamt-Kennzahlen und Diagramme.
- **PDF:** „Planung als PDF exportieren“ erzeugt den Auslegungsbericht (A4 quer) mit allen Schemata und Tabellen.

## Streamlit Cloud

Repository `sommer-nt/bosch-flow`, Branch wählen, Main file `app.py`. `requirements.txt` und `packages.txt`
(Schrift für Umlaute im PDF) werden automatisch installiert. Optional unter **Settings → Secrets** ein Passwort
setzen (Vorlage: `.streamlit/secrets.toml.beispiel`):

```toml
APP_PASSWORT = "..."
```

## Aufbau

```
app.py                  Streamlit-Oberfläche (Aufbau wie index.html)
browser.py              Auto-Sicherung im Browser (localStorage) und Hell/Dunkel-Schalter
bosch_flow/
  data.py               Datenbasis (Rohrreihen, Stationen, DIN 4708, Puffergrößen …)
  calc.py               Rechenkern – 1:1 aus index.html übertragen
  report.py             Tabellen, Herleitungstexte, Excel-Export
  schemata.py           Netzschema, Netztopologie, Anlagenschema (wie die Canvas-Zeichnungen der HTML)
  zeichnung.py          Zeichenschicht: dieselbe Grafik für Bildschirm (Plotly) und PDF
  bericht.py            PDF-Auslegungsbericht (A4 quer, wie „Planung als PDF exportieren“)
  plots.py              Diagramme (Plotly)
  daten/icons/          Piktogramme: Erzeuger, Puffer, Heizkreis (aus der HTML) + Pumpe, Trinkwasser, Station
  project.py            Projektdateien laden/speichern (kompatibel mit index.html)
tests/
  scenarios.json        15 Prüffälle (2-/4-Leiter, DLE, manuell, Mehrstrang, Hochhaus …)
  golden.json           Referenzwerte, direkt aus index.html berechnet
  test_calc.py          vergleicht Python mit den Referenzwerten
tools/make_golden.py    erzeugt golden.json neu aus index.html (Headless-Chromium)
```

Den Rechenkern kann man auch ohne Oberfläche nutzen:

```python
from bosch_flow import Inputs, Strang, compute

R = compute(Inputs(glz="tud", mat="kupfer"), Strang.new(floors=4, split="both", seed=5))
print(R["vRows"][0]["dim"], R["anlage"]["kesselQ"], "kW")
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Die Tests prüfen alle Zwischen- und Endwerte (Volumenströme, Dimensionen, Geschwindigkeiten, Druckverluste, Hauptstrang je Position der Wärmezentrale,
Kessel, Puffer, DLE-Tabelle, Herleitungstexte) gegen die HTML-Version. Wenn `index.html` geändert wird,
die Referenzwerte mit `python tools/make_golden.py` neu erzeugen und die Abweichungen prüfen.

---

Werkzeug zur Vorplanung – ersetzt keine verbindliche Rohrnetzberechnung. Prüfung obliegt Planer, Installateur
oder Bauherr. Entwickelt von Daniel Sommer · HC/SDE3-PSD.
