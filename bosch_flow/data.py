"""Datenbasis – 1:1 aus index.html (Bosch-HIU-Tool + Kunststoff/Verbund)."""

# Rohrreihen je Material: (Bezeichnung, Innendurchmesser mm, max. Volumenstrom m³/h)
PIPES = {
    "stahl": [("DN 20", 22.3, 1.41), ("DN 25", 28.5, 2.3), ("DN 32", 37.2, 3.91), ("DN 40", 43.1, 5.25),
              ("DN 50", 54.5, 8.4), ("DN 65", 70.3, 13.97), ("DN 80", 82.5, 19.24), ("DN 100", 107.1, 32.43),
              ("DN 125", 131.7, 49.04), ("DN 150", 159.3, 71.75), ("DN 200", 206.5, 120.57)],
    "kupfer": [("22 x 1", 21, 1.25), ("28 x 1,5", 25, 1.77), ("35 x 1,5", 32, 2.9), ("42 x 1,5", 39, 4.3),
               ("54 x 2", 50, 7.07), ("64 x 2", 60, 10.18), ("76,1 x 2", 72.1, 14.7), ("88,9 x 2", 84.9, 20.38),
               ("108 x 2,5", 103, 30)],
    "verbund": [("16 x 2", 12, 0.41), ("20 x 2", 16, 0.72), ("25 x 2,5", 20, 1.13), ("32 x 3", 26, 1.91),
                ("40 x 3,5", 33, 3.08), ("50 x 4,5", 41, 4.75), ("63 x 6", 51, 7.35), ("75 x 7,5", 60, 10.18),
                ("90 x 8,5", 73, 15.07)],
    "ppr": [("20 x 2,8", 14.4, 0.59), ("25 x 3,5", 18, 0.92), ("32 x 4,4", 23.2, 1.52), ("40 x 5,5", 29, 2.38),
            ("50 x 6,9", 36.2, 3.71), ("63 x 8,6", 45.8, 5.93), ("75 x 10,3", 54.4, 8.37),
            ("90 x 12,3", 65.4, 12.09), ("110 x 15,1", 79.8, 18.01)],
}
ROUGH_BY_MAT = {"stahl": 0.04, "kupfer": 0.0015, "verbund": 0.007, "ppr": 0.007}  # mm
MATNAME = {"stahl": "Stahl", "kupfer": "Kupfer", "verbund": "Mehrschichtverbund PE-X/Al", "ppr": "PP-R (Kunststoff)"}
NU, RHO = 0.894, 996.87  # Stoffwerte HIU (Daten-Blatt)

# Geräte laut Datenblatt (F8001 / F7002)
STATIONS = {
    "flow8000": {"name": "Flow 8000 (F8001)", "maxHeatKW": 15, "wwVorrang": True, "mode": "WW-Vorrangschaltung",
                 "zuheizerFaehig": False, "stages": [{"kw": 35, "lmin": 14}, {"kw": 50, "lmin": 21}]},
    "flow7000": {"name": "Flow 7000 (F7002)", "maxHeatKW": 6, "wwVorrang": False, "mode": "WW-Parallelbetrieb",
                 "zuheizerFaehig": True, "stages": [{"kw": 35, "lmin": 15}, {"kw": 45, "lmin": 18}]},
}

DIN4708 = {1: 1, 2: 1.6, 3: 1.8, 4: 1.9, 5: 2.1, 6: 2.3, 7: 2.5, 8: 2.7, 9: 2.9, 10: 3.1, 11: 3.3, 12: 3.4,
           13: 3.6, 14: 3.7, 15: 3.9, 16: 4.0, 17: 4.1, 18: 4.3}

PUFFER_SIZES = [500, 750, 1000, 1500]

DN_SERIES = [("DN 10", 10), ("DN 15", 15), ("DN 20", 20), ("DN 25", 25), ("DN 32", 32), ("DN 40", 40),
             ("DN 50", 50), ("DN 65", 65), ("DN 80", 80), ("DN 100", 100), ("DN 125", 125), ("DN 150", 150),
             ("DN 200", 200), ("DN 250", 250)]

# DIN 18015-1 Anhang A – Leistung am Netzanschluss (kW) über Wohneinheiten
DIN_MIT = [(1, 34), (2, 50), (5, 72), (10, 96), (15, 110), (20, 122), (25, 132), (30, 140)]
DIN_OHNE = [(1, 15), (2, 25), (5, 40), (10, 55), (15, 64), (20, 71), (25, 77), (30, 80)]

# Wärmequelle -> typische Kesseltotzeit / Wiederaufheizzeit (min) + Hinweis
WAERMEQUELLEN = {
    "kessel": {"name": "Konventioneller Wärmeerzeuger (Brennwertkessel)", "tot": 5, "wied": 30,
               "txt": "Konventioneller Brennwertkessel: Totzeit je nach Bauart (wandhängend 2–3 min, bodenstehend 5–7 min)."},
    "fernwaerme": {"name": "Nah-/Fernwärmeanschluss", "tot": 2, "wied": 30,
                   "txt": "Nah-/Fernwärme: kompakte Übergabestation, geringe Totzeit."},
    "wp": {"name": "Wärmepumpe / Hybridsystem", "tot": 3, "wied": 45,
           "txt": "Wärmepumpe/Hybrid: Niedertemperatur, längere Wiederaufheizzeit. Für getrennte Trinkwasserführung ggf. 4-Leiter wählen."},
}
