# bosch-flow

Netz- & Anlagenrechner für Wohnungsstationen (Flow 8000 / Flow 7000): Gleichzeitigkeit nach DIN 4708 bzw.
TU Dresden, Rohrdimensionierung je Strang, Wärmezentrale (Kessel-/FW-Leistung, Pufferspeicher nach
Bosch-HIU-Methodik) und DLE-Auslegungshilfe (Flow 7000 HPS).

![Streamlit-Version](docs/streamlit.png)

Es gibt zwei Versionen mit identischem Rechenweg:

| | `index.html` | Python / Streamlit |
|---|---|---|
| Start | Datei im Browser öffnen, läuft offline | `streamlit run app.py` |
| Oberfläche | Original mit Canvas-Schemata und PDF-Export | Web-App mit Plotly-Schemata und Excel-Export |
| Projektdateien | `.json` | dasselbe `.json`-Format, in beide Richtungen austauschbar |

## Python-Version starten

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Die App öffnet sich unter <http://localhost:8501>.

## Auf eigenem Server (Ubuntu + nginx)

Im Ordner `deploy/` liegt alles für den Dauerbetrieb: ein systemd-Dienst (startet die App automatisch, auch
nach Neustart oder Absturz) und eine nginx-Site als Reverse Proxy inklusive WebSocket-Weiterleitung.

```bash
git clone -b claude/lucid-archimedes-j2yw8g https://github.com/sommer-nt/bosch-flow.git
cd bosch-flow
sudo bash deploy/install.sh flow.example.de     # eigenen Hostnamen einsetzen, ohne Angabe: Zugriff per IP
sudo certbot --nginx -d flow.example.de          # optional: HTTPS (Let's Encrypt)
```

Die App liegt danach in `/opt/bosch-flow` und läuft als Benutzer `boschflow` nur auf `127.0.0.1:8501`.
Nach außen erreichbar ist sie ausschließlich über nginx.

| Aufgabe | Befehl |
|---|---|
| Neue Version einspielen | `git pull && sudo bash deploy/update.sh` |
| Status / Log | `systemctl status bosch-flow` · `journalctl -u bosch-flow -f` |
| Neustart | `sudo systemctl restart bosch-flow` |

## Aufbau

```
app.py                  Streamlit-Oberfläche
bosch_flow/
  data.py               Datenbasis (Rohrreihen, Stationen, DIN 4708, Puffergrößen …)
  calc.py               Rechenkern – 1:1 aus index.html übertragen
  report.py             Tabellen, Herleitungstexte, Excel-Export
  plots.py              Netzschema, Anlagenschema, Diagramme (Plotly)
  project.py            Projektdateien laden/speichern (kompatibel mit index.html)
tests/
  scenarios.json        14 Prüffälle (2-/4-Leiter, DLE, manuell, Mehrstrang, Hochhaus …)
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

Die Tests prüfen alle Zwischen- und Endwerte (Volumenströme, Dimensionen, Geschwindigkeiten, Druckverluste,
Kessel, Puffer, DLE-Tabelle, Herleitungstexte) gegen die HTML-Version. Wenn `index.html` geändert wird,
die Referenzwerte mit `python tools/make_golden.py` neu erzeugen und die Abweichungen prüfen.

---

Werkzeug zur Vorplanung – ersetzt keine verbindliche Rohrnetzberechnung. Prüfung obliegt Planer, Installateur
oder Bauherr. Entwickelt von Daniel Sommer · HC/SDE3-PSD.
