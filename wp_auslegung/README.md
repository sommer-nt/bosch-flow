# Bosch WP-Schnellauslegung

Schnellauslegung von Luft/Wasser-Wärmepumpen für den Außendienst – auch für Großanlagen (Compress 5000 AW / CS5001AW
als Kaskade), die der Heat Pump Advisor nicht abdeckt. Ersetzt das interne Excel-Werkzeug „WP-Auslegung_S“ für die
Weitergabe; das Zubehör plant weiterhin die Systemkonfiguration (SysCon).

Zwei Versionen mit **identischem Rechenweg** (Test vergleicht beide):

| | `index.html` | Python / Streamlit (`app.py`, `wp/`) |
|---|---|---|
| Start | Datei im Browser öffnen, läuft offline | `streamlit run wp_auslegung/app.py` |
| Ausdruck | „Drucken / PDF“ (A4, 3 Seiten) | „Auslegung als PDF“ (fpdf2, gleicher Aufbau) |
| Projektdatei | `.json` | dasselbe `.json`, in beide Richtungen austauschbar |

## Rechenweg

1. **Heizlast QH** – Vorgabe (DIN EN 12831), Wohnfläche × W/m², Gebäudehülle (Transmission + Lüftung) oder
   **Jahresverbrauch** wie Excel-Blatt „DIN EN 12831 Heizlast nach Verbrauch“:
   Eg,in = Verbrauch · Hu · Ehg,in = Eg,in − Ew,g,in · Øh,g = Ehg,in · η / th (th nach VDI 2067, η = 1 wie Excel).
2. **Warmwasser QTW** – Personen × 0,10/0,20/0,25 kW oder Ew,g,in / (td · 365) mit Nachheizzeit 4/3/2 h.
3. **Sperrzeit** 2/4/6 h → +5/10/15 %. QGES = QH + QTW + QSperr.
4. **Kriterium** bei A-7: monoenergetisch 0,7 · QGES, monovalent QGES bei θe, GEG-Hybrid 0,3 · QH.
5. Je Gerät und Kaskade die maximale Heizleistung beim Auslegungsvorlauf (zwischen 35/45/55/65 °C interpoliert):
   Bivalenzpunkt mit der Gebäudekennlinie (Heizung linear bis Heizgrenze, Warmwasser konstant), Leistung und
   Heizstab-Bedarf bei θe, Deckungsanteil nach VDI 4650 (Luft/Wasser, parallel), Taktgrenze über die Mindestleistung.
6. Empfehlung: kleinste passende Größe je Baureihe, gesamt Einzelgerät vor Kaskade in Reihenfolge der Baureihen.
7. Jahresbilanz (Schätzung) über SCOP aus dem Katalog.

## Daten

- `daten/geraete.json` – Leistungskurven (max./min.) aus dem Excel-Werkzeug 2.8.3, VDI-4650-Tabelle.
- `daten/klima.json` – PLZ → Ort, Norm-Außentemperatur (Blatt „Klimadaten“).
- `daten/katalog.json` – von Hand aus dem Gesamtkatalog März 2026: Bestell-Nr., UVP, Technische Daten,
  Inneneinheiten mit E-Heizer.

Neue Excel-Version übernehmen (die Excel-Datei wird nicht eingecheckt):

```bash
python wp_auslegung/tools/excel_import.py PFAD/WP-Auslegung_S.xlsm
```

Nach Änderungen an `katalog.json`: `python wp_auslegung/tools/excel_import.py --nur-einbetten` (bettet alle Daten in
`index.html` ein). Tests: `python -m pytest -q` (vergleicht Python und HTML über `node`).

## Offen

- CS3800iAW 10/13 O-T: Kurven aus dem Excel, Katalogdaten (SCOP, Schall) noch offen.
- CS5001AW 30: keine Leistungsdaten. CS7000i/CS7400i nur als Kurven (Katalog: Paketlösungen).
- Eigener Container/Subdomain wie flow.sommer-nt.de, falls gewünscht.
