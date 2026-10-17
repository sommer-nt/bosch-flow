"""Vergleicht den Python-Rechenkern mit Referenzwerten aus der Original-HTML-Version.

tests/golden.json wird mit tools/make_golden.py direkt aus index.html erzeugt.
"""
import json
import math
from pathlib import Path

import pytest

from bosch_flow.calc import (Inputs, Strang, compute, compute_all, dle_table, gz_din, gz_tud, project_headline,
                             puffer_produkt, topologie)
from bosch_flow.project import from_html_state

HERE = Path(__file__).parent
SCENARIOS = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))
GOLDEN = {g["name"]: g for g in json.loads((HERE / "golden.json").read_text(encoding="utf-8"))}


def assert_close(py, js, path=""):
    """Rekursiver Vergleich (Zahlen relativ 1e-9, alles andere exakt)."""
    if isinstance(js, dict):
        for k, v in js.items():
            assert k in py, f"{path}.{k} fehlt in Python"
            assert_close(py[k], v, f"{path}.{k}")
    elif isinstance(js, list):
        assert len(py) == len(js), f"{path}: Länge {len(py)} != {len(js)}"
        for i, (a, b) in enumerate(zip(py, js)):
            assert_close(a, b, f"{path}[{i}]")
    elif isinstance(js, bool) or js is None:
        assert bool(py) == bool(js), f"{path}: {py!r} != {js!r}"
    elif isinstance(js, (int, float)):
        assert py is not None and math.isclose(py, js, rel_tol=1e-9, abs_tol=1e-9), f"{path}: {py!r} != {js!r}"
    else:
        assert py == js, f"{path}: {py!r} != {js!r}"


def build(sc):
    state = {"fields": sc["fields"], "straenge": sc["straenge"]}
    return from_html_state(state)


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_strang_ergebnisse_wie_html(sc):
    inp, straenge, _ = build(sc)
    gold = GOLDEN[sc["name"]]
    for i, (s, g) in enumerate(zip(straenge, gold["results"])):
        R = compute(inp, s, straenge, i)
        for key in ("P", "anlage", "hRows", "vRows", "totalWE", "allWE", "govN", "singleStationV", "perStationDim"):
            assert_close(R[key], g[key], f"Strang{i + 1}.{key}")
        assert_close(puffer_produkt(R["anlage"]["pufferVol"]), g["kpiPuffer"], f"Strang{i + 1}.puffer")


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_kpi_kopfzeile_wie_html(sc):
    inp, straenge, _ = build(sc)
    R = compute(inp, straenge[0], straenge, 0)
    assert_close(project_headline(R, inp), GOLDEN[sc["name"]]["headline"])


@pytest.mark.parametrize("sc", [s for s in SCENARIOS if GOLDEN[s["name"]]["dleTable"]],
                         ids=lambda s: s["name"])
def test_dle_auslegungshilfe_wie_html(sc):
    from bosch_flow.report import dle_rows_text
    inp, straenge, _ = build(sc)
    R = compute(inp, straenge[0], straenge, 0)
    assert dle_rows_text(dle_table(R["anlage"])) == GOLDEN[sc["name"]]["dleTable"]


def test_gleichzeitigkeit():
    assert gz_din(1) == 1 and gz_din(10) == 3.1 and gz_din(18) == 4.3
    assert math.isclose(gz_din(40), 4.3 + 22 * 0.1)
    assert gz_tud(40) == 4.9


@pytest.mark.parametrize("vol,text,liter", [
    (0, "–", 0), (480, "500 l", 500), (1001, "1500 l", 1500), (1673, "1500 + 500 l", 2000),
    (3100, "2 × 1500 + 500 l", 3500), (2900, "2 × 1500 l", 3000),
])
def test_pufferauswahl(vol, text, liter):
    p = puffer_produkt(vol)
    assert (p["text"], p["liter"]) == (text, liter)


def test_standardfall_eckwerte():
    """Die Eckwerte des Ausgangsprojekts (40 WE, Flow 8000, DIN 4708, Stahl)."""
    R = compute(Inputs(), Strang.new(4, "both", 5))
    foot = R["vRows"][0]
    assert foot["dim"] == "DN 65" and round(foot["Vtot"], 2) == 10.64
    assert R["anlage"]["kesselQ"] == 173 and round(R["anlage"]["pufferVol"]) == 1673


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_waermezentrale_tabelle_wie_html(sc):
    from bosch_flow.report import anlage_rows
    inp, straenge, _ = build(sc)
    R = compute(inp, straenge[0], straenge, 0)
    py = [list(r) for r in anlage_rows(R["anlage"])]
    js = GOLDEN[sc["name"]]["anlageTable"][1:]          # ohne Kopfzeile
    assert len(py) == len(js)
    for p, j in zip(py, js):
        if p[0] == "WW-Leistung je Station":
            # HTML gibt die Zapfmenge hier ungerundet aus (z. B. 12.539409572943535) – Python formatiert sie.
            assert p[:3] == j[:3]
        else:
            assert p == j


def test_projektdatei_roundtrip():
    from bosch_flow.project import dumps, loads
    inp = Inputs(system="4", station="flow7000", wwstage=1, mat="kupfer", qhk=5.5, zentral="getrennt")
    straenge = [Strang.new(5, "both", 3), Strang(2, "one", [{"l": 4, "r": 0}, {"l": 6, "r": 0}])]
    meta = {"projName": "Wohnanlage Süd", "projLoc": "Stuttgart", "projPlanner": "", "projDate": "2026-10-01",
            "montage": "up", "heizkreis": "gemischt", "activeStrang": 1, "topoPos": 30.0}
    inp2, straenge2, meta2 = loads(dumps(inp, straenge, meta))
    assert inp2 == inp and straenge2 == straenge and meta2 == meta


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_netztopologie_wie_html(sc):
    """Hauptstrang-Abschnitte je Position der Wärmezentrale (V54, drawTopoT)."""
    inp, straenge, _ = build(sc)
    results = compute_all(inp, straenge)
    for pos, erwartet in GOLDEN[sc["name"]]["topo"].items():
        t = topologie(results, float(pos))
        py = [{"num": a["strang"], "side": a["seite"], "load": a["load"], "V": a["V"], "dn": a["dn"], "v": a["v"]}
              for a in t["abschnitte"]]
        assert_close(py, erwartet, f"pos{pos}")


def test_topopos_aus_html_datei():
    """V54 speichert topoPos top-level und in fields; ältere Dateien ohne topoPos -> mittig."""
    from bosch_flow.project import from_html_state
    basis = {"fields": {}, "straenge": SCENARIOS[0]["straenge"]}
    assert from_html_state(basis)[2]["topoPos"] == 50
    assert from_html_state({**basis, "topoPos": 20})[2]["topoPos"] == 20
    assert from_html_state({"fields": {"topoPos": "80"}, "straenge": []})[2]["topoPos"] == 80
    assert from_html_state({**basis, "topoPos": 250})[2]["topoPos"] == 100


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_pdf_bericht(sc):
    """Der PDF-Auslegungsbericht entsteht für jeden Prüffall (inkl. Topologie, DLE, 4-Leiter, getrennt)."""
    from bosch_flow.bericht import pdf_bericht
    inp, straenge, meta = build(sc)
    pdf = pdf_bericht(inp, straenge, {**meta, "projName": "Test Süd"}, compute_all(inp, straenge), "15.10.2026 10:00")
    assert pdf.startswith(b"%PDF") and len(pdf) > 20000


def test_export_ohne_preise():
    """Ohne Preise enthalten PDF und Excel keine UVP und keine Summen (Weitergabe nach außen)."""
    import io
    import shutil
    import subprocess

    import openpyxl
    from bosch_flow.bericht import pdf_bericht
    from bosch_flow.report import excel_bytes
    inp, straenge, meta = build(SCENARIOS[0])
    res = compute_all(inp, straenge)
    for preise in (True, False):
        mappe = openpyxl.load_workbook(io.BytesIO(excel_bytes(inp, meta, res, straenge, preise)))
        text = " ".join(str(c.value) for zeile in mappe["Stückliste"].iter_rows() for c in zeile if c.value is not None)
        assert ("UVP" in text) == preise
        if shutil.which("pdftotext"):
            pdf = pdf_bericht(inp, straenge, meta, res, preise=preise)
            text = subprocess.run(["pdftotext", "-", "-"], input=pdf, capture_output=True).stdout.decode()
            assert ("UVP" in text) == preise and ("€" in text) == preise


def test_3d_haushuelle():
    """Die Haushülle ergänzt nur Flächen und Linien – Rohre, Stationen und Hover-Punkte bleiben gleich."""
    from bosch_flow.modell3d import modell
    inp, straenge, meta = build(SCENARIOS[0])
    res = compute_all(inp, straenge)
    ohne, mit = modell(res, 50), modell(res, 50, huelle=True)
    assert len(mit.data) > len(ohne.data)
    assert list(mit.data[-1].hovertext) == list(ohne.data[-1].hovertext)
    assert all(t.hoverinfo == "skip" for t in mit.data if t.type == "mesh3d")


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_3d_modell(sc):
    """Jedes Rohrstück (Steigstrang, Etagenleitungen, Hauptstrang) hat genau einen Hover-Punkt mit seinen Daten."""
    from bosch_flow.calc import topologie
    from bosch_flow.modell3d import modell
    inp, straenge, meta = build(sc)
    res = compute_all(inp, straenge)
    for modus in ("v", "dn"):
        fig = modell(res, meta["topoPos"], modus)
        erwartet = sum(len(r["vRows"]) + sum(c["l"] + (c["r"] if r["split"] == "both" else 0) for c in r["cfg"])
                       for r in res)
        erwartet += len(topologie(res, meta["topoPos"])["abschnitte"]) if len(res) > 1 else 1   # 1 = Zuleitung
        hover = fig.data[-1]
        assert len(hover.hovertext) == erwartet
        stationen = next(t for t in fig.data if t.name == "Wohnungsstation")
        assert len(stationen.x) == sum(r["totalWE"] for r in res)
    einzel = modell(res, 50, "v", dunkel=True, nur_strang=len(res) - 1)
    assert len(einzel.data[-1].hovertext) == 1 + len(res[-1]["vRows"]) + sum(
        c["l"] + (c["r"] if res[-1]["split"] == "both" else 0) for c in res[-1]["cfg"])


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_variantenvergleich(sc):
    """Basiszeile = aktuelle Planung (Bewertung 1,0); Varianten rechnen den unveränderten Kern mit geänderten Feldern."""
    from bosch_flow.varianten import anwenden, kennzahlen, vergleich
    inp, straenge, meta = build(sc)
    V = vergleich(inp, straenge, meta["topoPos"])
    assert V["zeilen"][0]["variante"].gruppe == "Planung"
    assert V["zeilen"][0]["wert"] == pytest.approx(1.0)
    best = V["empfehlung"]
    assert best["wert"] <= 1.0 + 1e-9
    if best["variante"].gruppe != "Planung":
        assert best["variante"].empfehlbar and best["k"]["zuSchnell"] == 0
    for z in V["zeilen"][1:]:
        neu = anwenden(inp, z["variante"].aenderung)
        assert kennzahlen(neu, straenge, meta["topoPos"]) == z["k"]
        res = compute_all(neu, straenge)
        assert z["k"]["we"] == sum(r["totalWE"] for r in res)


def test_katalog_geraete_und_stueckliste():
    """Katalog 03/2026: jede Kombination liefert ein Gerät mit Bild; Kennlinie trifft die Katalogpunkte."""
    from bosch_flow import katalog as KA
    for station in ("flow8000", "flow7000"):
        for stufe in (0, 1):
            for system in ("2", "4"):
                for zh in ("off", "on"):
                    for mo in KA.MONTAGE:
                        for hk in KA.HEIZKREIS:
                            inp = Inputs(station=station, wwstage=stufe, system=system, zuheizer=zh,
                                         tvl=45 if zh == "on" else 60)
                            g = KA.geraet(inp, {"montage": mo, "heizkreis": hk})
                            assert g["bild"].exists() and g["bestellnr"] and g["uvp"] > 0
                            zeilen = KA.stueckliste(inp, {"montage": mo, "heizkreis": hk}, 12, 2, 8.0)
                            assert zeilen[0]["menge"] == 12 and any(z["pos"] == "Netzpumpe" for z in zeilen)
    g = KA.geraet(Inputs(station="flow8000", wwstage=0, tvl=60), {})
    assert g["typ"] == "F8001 35 S" and g["vPrim"] == 859 and g["dpPrim"] == 446
    g = KA.geraet(Inputs(station="flow7000", wwstage=1, tvl=55), {"heizkreis": "gemischt"})
    assert g["typ"] == "F7002 45 MS" and g["vPrim"] == 1375 and g["dpPrim"] == 559
    assert KA.netzpumpe(9.9)["typ"] == "NM 3" and KA.netzpumpe(10)["typ"] == "NM 6"
    assert KA.netzpumpe(15.2) is None


def test_hydraulik_druckverlust_und_rohrmengen():
    """Erweiterung: R im realen Rohr, Längen aus der Geometrie, Summen und Pumpenwahl."""
    from bosch_flow import hydraulik as HY
    from bosch_flow import katalog as KA
    # Stahl DN 25 (dᵢ 28,5 mm) bei 1 m/s: λ ≈ 0,0231 → R ≈ 404 Pa/m
    assert HY.r_pa_m({"v": 1.0, "di": 28.5}) == pytest.approx(404, rel=0.02)
    h = HY.berechne(Inputs(), [Strang.new()], {})
    # 4 Etagen, je Seite 5 Stationen: Etagenleitungen 4·2·(3 + 4·5) + Steigstrang 4·3 + Zuleitung 8 = 204 m, VL + RL
    assert h["laenge"] == pytest.approx(408)
    assert h["dpGes"] == pytest.approx(h["dpRohr"] + h["dpEinzel"] + h["dpStation"] + h["dpZentrale"])
    assert h["dpEinzel"] == pytest.approx(h["dpRohr"] * 0.30)
    assert h["dpRohr"] == pytest.approx(2 * sum(s["dp"] for s in h["pfad"]))
    assert h["dpStation"] == pytest.approx(70200)                       # F8001 35 bei 55 °C: 702 mbar (Katalog)
    assert h["pfad"][-1]["we"] == 1                                      # endet an der letzten Station
    lang = HY.berechne(Inputs(), [Strang.new()], {"aSt": 10, "zuschlag": 0, "dpZen": 0})
    assert lang["laenge"] > h["laenge"] and lang["dpEinzel"] == 0 and lang["dpZentrale"] == 0
    mehr = HY.berechne(Inputs(), [Strang.new(), Strang.new(6), Strang.new(3)], {"topoPos": 50})
    assert any(s["art"] == "Hauptstrang" for s in mehr["pfad"]) and mehr["pumpen"] == 1
    getrennt = HY.berechne(Inputs(zentral="getrennt"), [Strang.new(), Strang.new()], {})
    assert getrennt["pumpen"] == 2 and getrennt["laenge"] == pytest.approx(2 * h["laenge"])
    assert KA.netzpumpe(10, 0.9) is None
    assert KA.netzpumpe(10, 0.75)["typ"] == "NM 6"
    assert KA.netzpumpe(11, 0.6)["typ"] == "NM 3"


def test_hydraulik_geometrie_im_projekt():
    from bosch_flow.project import dumps, loads
    meta = {"projName": "", "projLoc": "", "projPlanner": "", "projDate": "2026-10-16", "hG": 3.5, "aSt": 6.0,
            "activeStrang": 0, "topoPos": 50.0}
    _, _, meta2 = loads(dumps(Inputs(), [Strang.new()], meta))
    assert meta2 == meta


@pytest.mark.parametrize("name", ["standard", "vierleiter"])
def test_puffer_szene(name):
    """Pufferbild: je gewähltem Bosch-Puffer ein Behälter mit Hover-Info (4-Leiter: Heizung + Trinkwasser)."""
    from bosch_flow import schemata as SC
    from bosch_flow.calc import puffer_produkt
    sc = next(s for s in SCENARIOS if s["name"] == name)
    inp, straenge, _ = build(sc)
    A = compute_all(inp, straenge)[0]["anlage"]
    vols = [A["heizPufferVol"], A["wwPufferVol"]] if A["four"] else [A["pufferVol"]]
    assert len(SC.puffer_szene(A).hover) == sum(len(puffer_produkt(v)["combo"]) for v in vols)
