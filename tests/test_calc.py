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
            "activeStrang": 1, "topoPos": 30.0}
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
        if len(res) > 1:
            erwartet += len(topologie(res, meta["topoPos"])["abschnitte"])
        hover = fig.data[-1]
        assert len(hover.hovertext) == erwartet
        stationen = next(t for t in fig.data if t.name == "Wohnungsstation")
        assert len(stationen.x) == sum(r["totalWE"] for r in res)
    einzel = modell(res, 50, "v", dunkel=True, nur_strang=len(res) - 1)
    assert len(einzel.data[-1].hovertext) == len(res[-1]["vRows"]) + sum(
        c["l"] + (c["r"] if res[-1]["split"] == "both" else 0) for c in res[-1]["cfg"])
