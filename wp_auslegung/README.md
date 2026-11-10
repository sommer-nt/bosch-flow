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

## Bedienung (Reihenfolge der Schnellauslegung)

1. Neubau oder Sanierung, Gebäudeart, Raumtemperatur, PLZ → Norm-Außentemperatur, Heizgrenze (Neubau 12 °C, Bestand 15 °C)
2. Wärmebedarf: Heizlast in kW, W/m² (Gebäudestandard je Neubau/Bestand) oder Jahresverbrauch
3. Heizkreise (bis 4): Heizkörper (55 °C), FBH (35 °C), Konvektoren (45 °C) → max. Vorlauf aus dem höchsten Kreis,
   Kreise mit niedrigerem Vorlauf gemischt (z. B. Sanierung: Heizkörperkreis + FBH-Kreis); im Schema mit Pumpe/Mischer
4. Warmwasser: Personen, Speichersystem oder Frischwasserstation, Zapftemperatur, Liter je Person bei 45 °C
5. Wärmequelle Luft/Wasser (Außenaufstellung, Entfernung zum Gebäude) oder Sole/Wasser (Innenaufstellung)
6. Beste Lösung oder Produkt wählen (Kaskade nur, wo die Baureihe es erlaubt)

**Expertenmodus:** Gebäudehülle, Heizwert, Vollbenutzungsstunden, Nutzungsgrad, Warmwasser nach DIN V 18599-10,
Lastprofil/Nachheizzeit, Kaltwassertemperatur, Sperrzeit, Betriebsweise, Spreizung, Entzugsleistung, Baureihen.

## Rechenweg

1. **Heizlast QH** – Vorgabe (DIN EN 12831), Wohnfläche × W/m², Gebäudehülle (Transmission + Lüftung) oder
   **Jahresverbrauch** wie Excel-Blatt „DIN EN 12831 Heizlast nach Verbrauch mit TWW“:
   Eg,in = Verbrauch · Hu · Ehg,in = Eg,in − Ew,g,in · Øh,g = Ehg,in · η / th · Øh,in = Øh,g + Ew,g,in / (td · 365)
   (th nach VDI 2067, η = 1 wie Excel). Beim Jahresverbrauch ist QGES = Øh,in.
2. **Warmwasser** – Qw,b = V · 1,163 Wh/(l·K) · (45 °C − ϑKW) je Person (oder DIN V 18599-10), Ew,g,in = Qw,b · np · 365.
   Zuschlag QTW automatisch: Jahresverbrauch → Nachheizzeit wie oben, sonst Personen × Lastprofil aus der Literzahl
   (≤ 30 l: 0,10 · ≤ 50 l: 0,20 · darüber 0,25 kW/P). Speicher = Zapftemperatur + 5 K, Puffer für Frischwasserstation
   + 10 K, Ladevorlauf + 5 K (Hinweis, wenn über dem max. Vorlauf des Geräts). Hinweis auf Großanlage nach DVGW W 551.
3. **Sperrzeit** 2/4/6 h → +5/10/15 %. QGES = QH + QTW + QSperr.
4. **Kriterium**: monoenergetisch 0,7 · QGES bei A-7, monovalent QGES bei θe (Standard bei Sole), GEG-Hybrid 0,3 · QH.
5. Je Gerät und Kaskade (CS3800 und CS7400 nicht kaskadierbar, CS5800/6800, CS8800, CS7000 2er, CS5001 bis 14):
   max. Heizleistung beim Auslegungsvorlauf (zwischen 35/45/55/65 °C interpoliert), Bivalenzpunkt mit der
   Gebäudekennlinie (Heizung linear bis Heizgrenze, Warmwasser konstant), Heizstab-Bedarf bei θe, Deckungsanteil nach
   VDI 4650 (Luft- bzw. Sole/Wasser, parallel), Taktgrenze über die Mindestleistung. Kurven werden nur im Bereich der
   Herstellerdaten gezeichnet. Sole/Wasser: Leistung konstant (B0), Entzugsleistung und Sondenlänge als Richtwert.
6. Luft/Wasser: Verbindungsleitung Außeneinheit – Gebäude (kleinstes Rohr mit v ≤ 1 m/s und R ≤ 200 Pa/m, Δp mit 30 %
   Einzelwiderständen).
7. Empfehlung: kleinste passende Größe je Baureihe, gesamt Einzelgerät vor Kaskade. Jahresbilanz über SCOP.

Die Kurven sind maximale Heizleistungen; bei A-7/W35 stimmen sie auf ±6 % mit „Max. Heizleistung“ im Katalog überein
(Test). Die A2/A7-Werte im Katalog sind Teillastpunkte nach EN 14511 und deshalb kleiner.

## Daten

- `daten/geraete.json` – Leistungskurven (max./min.) aus dem Excel-Werkzeug 2.8.3, VDI-4650-Tabelle.
- `daten/klima.json` – PLZ → Ort, Norm-Außentemperatur (Blatt „Klimadaten“).
- `daten/katalog.json` – von Hand aus dem Gesamtkatalog März 2026: Bestell-Nr., UVP, Technische Daten,
  Inneneinheiten mit E-Heizer, Sole/Wasser (Compress 7800i LW, Supraeco T).

- `daten/bilder/*.jpg` – Produktbilder aus dem Gesamtkatalog (CS3800 O-S aus dem Heat-Pump-Advisor-Ausdruck), erzeugt mit
  `python wp_auslegung/tools/bilder_import.py KATALOG.pdf [HPA.pdf]` (braucht `pdfimages` aus poppler-utils).

Der Rechenkern stammt aus den Zellformeln des Excel-Werkzeugs; die VBA-Makros enthalten nur Navigation, Druck und
Eingabeprüfung.

Neue Excel-Version übernehmen (die Excel-Datei wird nicht eingecheckt):

```bash
python wp_auslegung/tools/excel_import.py PFAD/WP-Auslegung_S.xlsm
```

Nach Änderungen an `katalog.json`: `python wp_auslegung/tools/excel_import.py --nur-einbetten` (bettet alle Daten in
`index.html` ein). Tests: `python -m pytest -q` (vergleicht Python und HTML über `node`).

## Offen

- CS3800iAW 10/13 O-T: Kurven aus dem Excel, Katalogdaten (SCOP, Schall) noch offen.
- CS5001AW 30 und CS5000 AW 22/38: keine Leistungsdaten im Excel. CS7000i/CS7400i nur als Kurven (Katalog: Pakete).
- Sole/Wasser bei 55 °C: Nennwärmeleistung (ErP) statt max. Leistung angesetzt; Kaskaden bei Sole noch nicht freigegeben.
- Eigener Container/Subdomain wie flow.sommer-nt.de, falls gewünscht.
