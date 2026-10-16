"""Gerätedaten aus dem Bosch Gesamtkatalog Wohnungsstationen (Deutschland, März 2026, Kapitel 11).

Der Rechenkern (V54) bleibt unverändert – dieses Modul ergänzt ihn um das, was der Katalog liefert:
Ausführung und Bestellnummer der Station, Produktbild, technische Daten am gewählten Vorlauf
(Primär-Volumenstrom, Primär-Druckverlust, Abmessungen), Netzpumpenmodule, Zubehörhinweise und eine
Stückliste mit unverbindlichen Preisempfehlungen (ohne MwSt.).
"""
from __future__ import annotations

from pathlib import Path

from .calc import Inputs, compute_all, dle_is_on, gesamt_anlage, project_headline

KATALOG = "Bosch Gesamtkatalog Wohnungsstationen, Deutschland, März 2026"
PREISHINWEIS = "Unverbindliche Preisempfehlung ohne MwSt. laut Katalog März 2026."
BILDER = Path(__file__).parent / "daten" / "produkte"

MONTAGE = {"ap": "Aufputz", "up": "Unterputz", "rs": "Thermentausch (RS, Aufputz)"}
HEIZKREIS = {"ungemischt": "ungemischt (Heizkörper)", "gemischt": "gemischt (Fußbodenheizung)"}

# Stationen: (Baureihe, Leistung, Ausführung) -> Typ, Bestell-Nr., UVP €, Bild
GERAETE = {
    # Flow 8000 – S/IS ungemischt, MS/IMS gemischt (S = Aufputz mit Glasgehäuse, IS = Unterputz ohne Gehäuse)
    ("flow8000", 35, "ap", "ungemischt"): ("F8001 35 S", "7735600464", 2050, "f8001_s"),
    ("flow8000", 35, "up", "ungemischt"): ("F8001 35 IS", "7735600465", 1934, "f8001_is"),
    ("flow8000", 50, "ap", "ungemischt"): ("F8001 50 S", "7735600466", 2240, "f8001_s"),
    ("flow8000", 50, "up", "ungemischt"): ("F8001 50 IS", "7735600467", 2108, "f8001_is"),
    ("flow8000", 35, "ap", "gemischt"): ("F8001 35 MS", "7735600577", 2677, "f8001_s"),
    ("flow8000", 35, "up", "gemischt"): ("F8001 35 IMS", "7735600578", 2590, "f8001_is"),
    ("flow8000", 50, "ap", "gemischt"): ("F8001 50 MS", "7735600579", 2825, "f8001_s"),
    ("flow8000", 50, "up", "gemischt"): ("F8001 50 IMS", "7735600580", 2692, "f8001_is"),
    # Flow 7000 – S ungemischt, MS gemischt (Auf- und Unterputz), RS Thermentausch
    ("flow7000", 35, "-", "ungemischt"): ("F7002 35 S", "7739624218", 1556, "f7002_s"),
    ("flow7000", 45, "-", "ungemischt"): ("F7002 45 S", "7739624220", 1673, "f7002_s"),
    ("flow7000", 35, "-", "gemischt"): ("F7002 35 MS", "7739624611", 1972, "f7002_s"),
    ("flow7000", 45, "-", "gemischt"): ("F7002 45 MS", "7739624224", 2089, "f7002_s"),
    ("flow7000", 35, "rs", "ungemischt"): ("F7002 35 RS basic", "7739624232", 2062, "f7002_rs"),
    ("flow7000", 45, "rs", "ungemischt"): ("F7002 45 RS basic", "7739624226", 2186, "f7002_rs"),
    # Flow 7000 HPS – mit nachgeschaltetem Durchlauferhitzer (DLE)
    ("hps", 35, "-", "ungemischt"): ("F7002 35 DHPS", "7739624221", 2329, "f7002_hps"),
    ("hps", 45, "-", "ungemischt"): ("F7002 45 DHPS", "7739624222", 2454, "f7002_hps"),
    ("hps", 35, "-", "gemischt"): ("F7002 35 MHPS", "7739624225", 2666, "f7002_hps"),
    ("hps", 45, "-", "gemischt"): ("F7002 45 MHPS", "7739624223", 2791, "f7002_hps"),
    # 4-Leiter: Frischwassermodul (nur Trinkwasser)
    ("fwm", 35, "-", "-"): ("F7002 35 S FWM", "7735600745", 1418, "f7002_s"),
    ("fwm", 45, "-", "-"): ("F7002 45 S FWM", "7735600747", 1535, "f7002_s"),
    ("fwmhps", 35, "-", "-"): ("F7002 35 FWMHPS", "7739624399", 2045, "f7002_hps"),
    ("fwmhps", 45, "-", "-"): ("F7002 45 FWMHPS", "7739624400", 2162, "f7002_hps"),
}

# Technische Daten je Leistungsklasse. Kennlinien: Vorlauf °C -> (Primär-Volumenstrom l/h, Primär-Δp mbar)
TECHNIK = {
    ("f8001", 35): {"kennlinie": {55: (1050, 702), 60: (859, 446), 65: (740, 434)}, "zapf": 14, "vlMin": 52,
                    "vlMax": 90, "heizKW": 15, "elW": 100, "kvs": 0.9},
    ("f8001", 50): {"kennlinie": {55: (1200, 784), 60: (923, 476), 65: (808, 437)}, "zapf": 21, "vlMin": 52,
                    "vlMax": 90, "heizKW": 15, "elW": 100, "kvs": 1.3},
    ("f7002", 35): {"kennlinie": {50: (1200, 600), 55: (1134, 518), 60: (947, 364)}, "zapf": 15, "vlMin": 50,
                    "vlMax": 90, "heizKW": 6, "elW": 14.9, "kvs": 1.6},
    ("f7002", 45): {"kennlinie": {50: (1470, 640), 55: (1375, 559), 60: (1071, 343)}, "zapf": 18, "vlMin": 50,
                    "vlMax": 90, "heizKW": 6, "elW": 14.9, "kvs": 1.8},
}
TECHNIK[("hps", 35)] = {**TECHNIK[("f7002", 35)], "vlMin": 35, "vlMax": 55, "elW": 66.9}
TECHNIK[("hps", 45)] = {**TECHNIK[("f7002", 45)], "vlMin": 35, "vlMax": 55, "elW": 66.9}

ABMESSUNGEN = {"f8001_s": "700 × 440 × 270 mm", "f8001_is": "629 × 434 × 190 mm",
               "f7002_s": "666 × 365 × 145 mm", "f7002_rs": "666 × 420 × 160 mm",
               "f7002_hps": "666 × 420 × 145 mm (ohne DLE)"}

# Netzpumpenmodule (Hocheffizienzpumpe MAGNA3): max. Volumenstrom bei Restförderhöhe 0,8 bar (in Klammern 0,7 bar)
NETZPUMPEN = [
    {"typ": "NM 3", "pumpe": "MAGNA3 32-120 F", "bestellnr": "7735600251", "uvp": 3656, "vmax": 9.9, "vmax07": 11.5},
    {"typ": "NM 6", "pumpe": "MAGNA3 40-120 F", "bestellnr": "7735600252", "uvp": 3952, "vmax": 12.6, "vmax07": 14.0},
    {"typ": "NM 10", "pumpe": "MAGNA3 50-120 F", "bestellnr": "7735600253", "uvp": 6675, "vmax": 15.1, "vmax07": 18.5},
]
RESTFOERDERHOEHE = 0.8   # bar

ZUBEHOER = {
    "bypass": ("Thermischer Bypass", "7733600132", 124),
    "verbruehschutz": ("Verbrühungsschutz Trinkwasser", "7735600799", 145),
    "wasserschlag": ("Wasserschlagdämpfer", "7733600118", 90),
    "cr11": ("Raumregler CR 11 (EMS 2)", "7738112963", 106),
    "cr10": ("Fernbedienung CR 10 (EMS 2)", "7738111104", None),
    "f8_mp_ap": ("Montageplatte Aufputz (inkl. Wartungshähne)", "7735600588", 192),
    "f8_mp_up": ("Montageplatte Unterputz (inkl. Wartungshähne)", "7735600586", 206),
    "f8_upk_kurz": ("Unterputzkasten kurz 850 × 470 × 195 mm", "7733600045", 347),
    "f8_upk_lang": ("Unterputzkasten lang 1350 × 800 × 195 mm", "7724002023", 602),
    "f7_mp": ("Montageplatte für Basis- und HK-Modul (8 Kugelhähne)", "7739620119", 250),
    "f7_mp_basis": ("Montageplatte Basismodul (5 Kugelhähne)", "7735600611", 156),
    "f7_aps_lang": ("Aufputzschrank lang 1580 × 710 × 200 mm", "7735600605", 459),
    "f7_ups_kurz": ("Unterputzschrank kurz 1000 × 710 × 150(-200) mm", "7735600642", 285),
    "f7_ups_lang": ("Unterputzschrank lang 1540 × 710 × 150(-200) mm", "7735600619", 336),
    "rs_rahmen": ("Montagerahmen basic inkl. 6 Kugelhähne", "7735600641", 213),
    "rs_gehaeuse": ("Aufputzgehäuse RS 980 × 440 × 225 mm", "7735600603", 227),
    "hps_mp": ("Montageplatte Modul HPS (7 Kugelhähne)", "7735600792", 195),
    "hps_mp_dle": ("Montageplatte Durchlauferhitzer", "7735600793", 75),
    "hps_aps": ("Aufputzschrank lang HPS 1400 × 900 × 200 mm", "7735600731", 476),
    "hps_ups_kurz": ("Unterputzschrank kurz HPS 1000 × 800 × 150-200 mm", "7735600729", 320),
    "hps_ups_lang": ("Unterputzschrank lang HPS 1400 × 900 × 150-200 mm", "7735600730", 353),
    "ibn_1_5": ("Inbetriebnahme Wohnungsstation, Standard 1–5 Stationen (je Station)", "8737804240", 140),
    "ibn_ab6": ("Inbetriebnahme Wohnungsstation, Standard ab 6 Stationen (je Station)", "8737804241", 99),
    "ibn_regler": ("Inbetriebnahme Systemregler (je Wohnungsstation)", "8737804267", 40),
    "pauschale": ("Auftragspauschale (Mo–Fr)", "7739607426", 151),
}


def _de(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def ausfuehrung(meta: dict) -> tuple[str, str]:
    """Montage ('ap'/'up'/'rs') und Heizkreis ('ungemischt'/'gemischt') aus den Projekt-Metadaten."""
    m = meta.get("montage") or "ap"
    h = meta.get("heizkreis") or "ungemischt"
    return (m if m in MONTAGE else "ap"), (h if h in HEIZKREIS else "ungemischt")


def _klasse(inp: Inputs) -> int:
    from .data import STATIONS
    stufen = STATIONS[inp.station]["stages"]
    return stufen[max(0, min(len(stufen) - 1, int(inp.wwstage)))]["kw"]


def baureihe(inp: Inputs) -> str:
    if inp.system == "4":
        return "fwmhps" if inp.zuheizer == "on" and inp.station == "flow7000" else "fwm"
    if inp.station == "flow7000" and dle_is_on(inp):
        return "hps"
    return inp.station


def geraet(inp: Inputs, meta: dict) -> dict:
    """Passende Station laut Katalog (Typ, Bestell-Nr., UVP, Bild, technische Daten, Hinweise)."""
    montage, hk = ausfuehrung(meta)
    reihe, kw = baureihe(inp), _klasse(inp)
    if reihe == "flow8000":
        key = (reihe, kw, "up" if montage == "up" else "ap", hk)
    elif reihe == "flow7000":
        key = (reihe, kw, "rs" if montage == "rs" and hk == "ungemischt" else "-", hk)
    elif reihe == "hps":
        key = (reihe, kw, "-", hk)
    else:
        key = (reihe, 35 if kw <= 35 else 45, "-", "-")
    typ, nr, uvp, bild = GERAETE[key]
    tkey = ("f8001" if inp.station == "flow8000" and reihe == "flow8000" else
            "hps" if reihe in ("hps", "fwmhps") else "f7002", 35 if kw <= 35 else (50 if reihe == "flow8000" else 45))
    tech = TECHNIK[tkey]
    v_prim, dp_prim, vl_punkt = kennlinie(tech, float(inp.tvl))
    return {"typ": typ, "bestellnr": nr, "uvp": uvp, "bild": BILDER / f"{bild}.png", "bildname": bild,
            "abmessungen": ABMESSUNGEN.get(bild, ""), "reihe": reihe, "montage": montage, "heizkreis": hk,
            "zapf": tech["zapf"], "vlMin": tech["vlMin"], "vlMax": tech["vlMax"], "heizKW": tech["heizKW"],
            "elW": tech["elW"], "vPrim": v_prim, "dpPrim": dp_prim, "vlPunkt": vl_punkt,
            "hinweise": hinweise(inp, reihe, montage, hk, tech)}


def kennlinie(tech: dict, vl: float) -> tuple[float, float, str]:
    """Primär-Volumenstrom (l/h) und Primär-Druckverlust (mbar) am Vorlauf – linear zwischen den Katalogpunkten,
    außerhalb auf den nächsten Katalogpunkt begrenzt."""
    pts = sorted(tech["kennlinie"].items())
    if vl in tech["kennlinie"]:
        return (*tech["kennlinie"][vl], f"{vl:.0f} °C")
    if vl <= pts[0][0]:
        return (*pts[0][1], f"{pts[0][0]} °C (nächster Katalogpunkt)")
    if vl >= pts[-1][0]:
        return (*pts[-1][1], f"{pts[-1][0]} °C (nächster Katalogpunkt)")
    for (t0, (v0, p0)), (t1, (v1, p1)) in zip(pts, pts[1:]):
        if t0 <= vl <= t1:
            f = (vl - t0) / (t1 - t0)
            return v0 + f * (v1 - v0), p0 + f * (p1 - p0), f"{vl:.0f} °C (zwischen {t0} und {t1} °C)"
    return (*pts[-1][1], f"{pts[-1][0]} °C")


def hinweise(inp: Inputs, reihe: str, montage: str, hk: str, tech: dict) -> list[tuple[str, str]]:
    """(Stufe, Text) – Stufe 'warn' oder 'info'."""
    out = []
    vl = float(inp.tvl)
    if vl < tech["vlMin"]:
        out.append(("warn", f"Versorgungstemperatur {vl:.0f} °C liegt unter der Katalog-Mindestvorlauftemperatur "
                            f"von {tech['vlMin']} °C für diese Station."))
    if vl > tech["vlMax"]:
        out.append(("warn", f"Versorgungstemperatur {vl:.0f} °C liegt über dem Katalog-Maximum von {tech['vlMax']} °C."))
    if reihe in ("flow7000", "hps", "fwm", "fwmhps") and vl >= 70:
        out.append(("warn", "Ab 70 °C Vorlauf ist der Verbrühungsschutz Trinkwasser (7735600799) einzubauen."))
    if inp.system == "4" and inp.station == "flow8000":
        out.append(("info", "Für das 4-Leiter-System führt der Katalog das Frischwassermodul F7002 FWM bzw. "
                            "FWMHPS (nur Trinkwasser) – die Stückliste verwendet dieses Modul."))
    if reihe == "flow8000":
        out.append(("info", "Regelung ist zwingend erforderlich (z. B. CR 11 bzw. CR 10 bei MS/IMS, CW 400 oder "
                            "EasyControl CT 200 mit Adapter)."))
        out.append(("info", "Thermischer Bypass im obersten Gerät je Steigstrang – oder in jedem Gerät, wenn die "
                            "Anschlussleitung zwischen Strang und Station länger als 5 m ist (Sommerbetrieb)."))
    if montage == "rs" and reihe != "flow7000":
        out.append(("info", "Die Thermentausch-Ausführung (RS) gibt es nur für Flow 7000 ohne DLE, ungemischt."))
    if hk == "gemischt" and reihe in ("flow7000", "hps"):
        out.append(("info", "Gemischter Heizkreis: Pumpenkennlinie der Station beachten; Schutzventil "
                            "Fußbodenheizung 55 °C (7735600574) je nach Ausführung erforderlich bzw. optional."))
    out.append(("info", "Wasserhärte < 20 °dH; ab 14 °dH wird eine Enthärtungsanlage empfohlen."))
    return out


def netzpumpe(v_m3h: float, dp_bar: float | None = None) -> dict | None:
    """Kleinstes Netzpumpenmodul für den Volumenstrom (None = keines passt).
    Ohne ``dp_bar`` gilt der Katalogpunkt bei 0,8 bar Restförderhöhe. Mit ``dp_bar`` (erforderliche Förderhöhe des
    Netzes inkl. Station) muss der Punkt unter der Kennlinie liegen: bis 0,7 bar gilt der größere Volumenstrom,
    bis 0,8 bar der kleinere, darüber passt keines der Module."""
    if dp_bar is None:
        return next((p for p in NETZPUMPEN if p["vmax"] >= v_m3h), None)
    if dp_bar > RESTFOERDERHOEHE:
        return None
    return next((p for p in NETZPUMPEN if (p["vmax07"] if dp_bar <= 0.7 else p["vmax"]) >= v_m3h), None)


def stueckliste(inp: Inputs, meta: dict, n_stationen: int, n_straenge: int, v_netz: float,
                zentralen: int = 1, dp_bar: float | None = None) -> list[dict]:
    """Material je Projekt aus dem Katalog (Stationen, Montage, Regelung, Zubehör, Netzpumpe, Inbetriebnahme)."""
    g = geraet(inp, meta)
    reihe, montage, hk = g["reihe"], g["montage"], g["heizkreis"]
    art = "Trinkwassermodul (4-Leiter)" if reihe in ("fwm", "fwmhps") else HEIZKREIS[hk]
    zeilen = [{"pos": "Wohnungsstation", "text": f"{g['typ']} – {art}",
               "nr": g["bestellnr"], "menge": n_stationen, "uvp": g["uvp"]}]

    def z(key, menge, pos="Zubehör"):
        text, nr, uvp = ZUBEHOER[key]
        zeilen.append({"pos": pos, "text": text, "nr": nr, "menge": menge, "uvp": uvp})

    if reihe == "flow8000":
        z("f8_mp_up" if montage == "up" else "f8_mp_ap", n_stationen, "Montage")
        if montage == "up":
            z("f8_upk_kurz", n_stationen, "Montage")
        z("cr10" if hk == "gemischt" else "cr11", n_stationen, "Regelung")
        z("bypass", n_straenge, "Zubehör")
    elif reihe == "flow7000" and montage == "rs":
        z("rs_rahmen", n_stationen, "Montage")
        z("rs_gehaeuse", n_stationen, "Montage")
    elif reihe == "flow7000":
        z("f7_mp", n_stationen, "Montage")
        z("f7_ups_lang" if montage == "up" else "f7_aps_lang", n_stationen, "Montage")
    elif reihe == "hps":
        z("hps_mp", n_stationen, "Montage")
        z("hps_mp_dle", n_stationen, "Montage")
        z(("hps_ups_lang" if hk == "gemischt" else "hps_ups_kurz") if montage == "up" else "hps_aps",
          n_stationen, "Montage")
    else:
        z("f7_mp_basis", n_stationen, "Montage")
    if reihe in ("flow7000", "hps", "fwm", "fwmhps") and float(inp.tvl) >= 70:
        z("verbruehschutz", n_stationen, "Zubehör")
    v_je = v_netz / max(1, zentralen)
    punkt = f"V̇ {_de(v_je, 2)} m³/h" + (f", Förderhöhe {_de(dp_bar, 2)} bar (≈ {_de(dp_bar * 10.2, 1)} m)"
                                         if dp_bar is not None else "")
    zeilen.append({"pos": "Netzpumpe", "text": f"Netzpumpe bauseits – Betriebspunkt {punkt}", "nr": "bauseits",
                   "menge": zentralen, "uvp": None})
    z("ibn_ab6" if n_stationen >= 6 else "ibn_1_5", n_stationen, "Dienstleistung")
    z("pauschale", 1, "Dienstleistung")
    for r in zeilen:
        r["summe"] = r["uvp"] * r["menge"] if r["uvp"] is not None else None
    return zeilen


def projekt_stueckliste(inp: Inputs, straenge: list, meta: dict) -> list[dict]:
    """Stückliste für das ganze Projekt (gemeinsame Zentrale = eine Netzpumpe, getrennt = eine je Strang)."""
    res = compute_all(inp, straenge)
    G = gesamt_anlage(inp, res)
    if G["getrennt"]:
        zentralen, v = len(res), max(r["vRows"][0]["Vtot"] for r in res) * len(res)
    else:
        zentralen, v = 1, project_headline(res[0], inp)["Vtot"]
    from .hydraulik import berechne
    return stueckliste(inp, meta, G["we"], len(res), v, zentralen, berechne(inp, straenge, meta)["bar"])
