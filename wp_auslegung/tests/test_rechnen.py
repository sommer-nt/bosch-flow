"""Rechenkern der WP-Schnellauslegung: Excel-Referenzwerte und Gleichheit Python ↔ HTML (node)."""
import copy
import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from wp import daten as D
from wp import projekt as P
from wp import rechnen as R

HIER = Path(__file__).resolve().parent
ROOT = HIER.parent


def e_mit(**aend):
    e = P.neu()
    for pfad, wert in aend.items():
        ziel = e
        teile = pfad.split("__")
        for t in teile[:-1]:
            ziel = ziel[t]
        ziel[teile[-1]] = wert
    return e


def szenarien():
    return [
        {"name": "vorgabe_efh", "eingaben": e_mit(heizlast__vorgabe_kw=6.34, klima__nat=-11.5, tww__aktiv=False, vl=50)},
        {"name": "excel_verbrauch", "eingaben": e_mit(heizlast__methode="verbrauch", heizlast__menge=8830, heizlast__heizwert=10.42,
                                                      tww__personen=5, tww__bezug="personen", tww__qwb=1.1, tww__td=4)},
        {"name": "flaeche_sperrzeit", "eingaben": e_mit(heizlast__methode="flaeche", heizlast__flaeche_m2=180, heizlast__spez_w_m2=70,
                                                        sperrzeit_h=4, tww__kw_person=0.25, vl=55)},
        {"name": "huelle_monovalent", "eingaben": e_mit(heizlast__methode="huelle", heizlast__huell_a_m2=420, heizlast__ht=0.45,
                                                        heizlast__volumen_m3=480, auslegung="monovalent", vl=35, klima__nat=-14)},
        {"name": "mfh_gross_5001", "eingaben": e_mit(heizlast__vorgabe_kw=95, tww__personen=40, vl=65, serien=["CS5001", "CS8800"])},
        {"name": "hybrid", "eingaben": e_mit(heizlast__vorgabe_kw=30, auslegung="hybrid", vl=60)},
        {"name": "manuell_kaskade", "eingaben": e_mit(heizlast__vorgabe_kw=18, auswahl__geraet="CS8800iAW 11 O-T", auswahl__anzahl=2,
                                                      sperrzeit_h=6, tww__bezug="flaeche", tww__qwb=0.0343, tww__flaeche_m2=200,
                                                      tww__methode="nachheizzeit", tww__td=3)},
        {"name": "vl_zu_hoch", "eingaben": e_mit(heizlast__vorgabe_kw=12, vl=70, auswahl__geraet="CS3800iAW 7 O-S")},
        {"name": "leer", "eingaben": e_mit(heizlast__vorgabe_kw=0, tww__aktiv=False)},
        {"name": "sole_monovalent", "eingaben": e_mit(heizlast__vorgabe_kw=11, waermequelle="sole", auslegung="monovalent", vl=45,
                                                      tww__system="friwa", tww__zapftemp=50, tww__liter_p=60)},
        {"name": "sole_gross", "eingaben": e_mit(heizlast__vorgabe_kw=40, waermequelle="sole", auslegung="monovalent", vl=35)},
        {"name": "liter_grossanlage", "eingaben": e_mit(heizlast__vorgabe_kw=60, tww__personen=30, tww__liter_p=40,
                                                        aufstellung__entfernung_m=25, vl=50)},
        {"name": "din18599_personen", "eingaben": e_mit(heizlast__vorgabe_kw=8, tww__bezug="personen", tww__qwb=1.1,
                                                        tww__methode="auto", aufstellung__entfernung_m=0)},
    ]


def sz(name):
    return next(s["eingaben"] for s in szenarien() if s["name"] == name)


def rechne(e):
    return R.rechne(e, D.geraete(), D.katalog())


def test_excel_heizlast_nach_verbrauch():
    """Excel-Blatt „DIN EN 12831 Heizlast nach Verbrauch“: 8830 m³ Gas, 5 Personen → 42,86 kW / 44,23 kW."""
    r = rechne(szenarien()[1]["eingaben"])
    h = r["heizlast"]
    assert h["eg_kwh"] == pytest.approx(92008.6)
    assert h["ew_kwh"] == pytest.approx(2007.5)
    assert h["ehg_kwh"] == pytest.approx(90001.1)
    assert round(r["qh"], 2) == 42.86
    assert round(h["oh_in_kw"], 2) == 44.23
    assert round(r["qges"], 2) == 44.23


def test_excel_huelle_und_sperrzeit():
    e = e_mit(heizlast__methode="huelle", heizlast__huell_a_m2=400, heizlast__ht=0.5, heizlast__volumen_m3=500,
              sperrzeit_h=2, tww__personen=4, tww__methode="personen", tww__kw_person=0.1, klima__nat=-12)
    r = rechne(e)
    assert r["heizlast"]["transmission_kw"] == pytest.approx(32 * 400 * 0.5 / 1000)
    assert r["heizlast"]["lueftung_kw"] == pytest.approx(1.8)   # AUFRUNDEN(1,728; 1)
    assert r["qsperr"] == pytest.approx((6.4 + 1.8 + 0.4) * 0.05)


def test_kurven_wie_excel():
    """Leistung bei A-7/W55 wie Excel-Blatt A-7_W55."""
    g = D.geraet("CS3800iAW 6 O-S")
    assert R.kurve_bei_vl(g["max"], 55)[0](-7) == pytest.approx(5.84, abs=0.01)
    assert R.kurve_bei_vl(D.geraet("CS5001 AW42")["max"], 55)[0](-7) == pytest.approx(41.48)
    assert R.kurve_bei_vl(D.geraet("CS8800iAW 15 O-T")["max"], 55)[0](-7) == pytest.approx(14.39, abs=0.01)


def test_empfehlung_efh_wie_hpa():
    """6,34 kW bei −11,5 °C, 50 °C: Heat Pump Advisor schlägt CS3800iAW 6 O-S vor."""
    r = rechne(szenarien()[0]["eingaben"])
    assert r["empfehlung"] == "CS3800iAW 6 O-S|1"
    g = r["gewaehlt"]
    assert g["ok"] and g["bivalenz_art"] == "punkt" and -10 < g["bivalenz"] < -7
    assert g["deckung"] >= 0.98


def test_kaskaden_wie_excel_navigation():
    """CS3800 und CS7400 sind nicht kaskadierbar; CS5800/6800, CS8800, CS7000 als 2er-Kaskade, CS5001 bis 14."""
    km = {s["id"]: s["kaskade_max"] for s in D.geraete()["serien"]}
    assert km["CS3800"] == 1 and km["CS7400"] == 1
    assert km["CS5800"] == km["CS8800"] == km["CS7000"] == 2 and km["CS5001"] == 14
    r = rechne(e_mit(heizlast__vorgabe_kw=14, serien=["CS3800"]))
    assert all(c["n"] == 1 for c in r["kandidaten"])


def test_kurven_gegen_katalog():
    """Max. Heizleistung A-7/W35 der Kurven = Katalogwert (±6 %)."""
    for gid, k in D.katalog()["geraete"].items():
        g = D.geraet(gid)
        if g and k.get("a_7w35_max") and D.serie(g["serie"])["quelle"] == "luft":
            assert R.kurve_bei_vl(g["max"], 35)[0](-7) == pytest.approx(k["a_7w35_max"], rel=0.06), gid


def test_kennlinien_nur_im_datenbereich():
    r = rechne(e_mit(heizlast__vorgabe_kw=9, klima__nat=-16, serien=["CS5800"]))
    k, ts = r["kennlinien"], r["kennlinien"]["t"]
    assert k["max"][ts.index(-17.0)] is None and k["max"][ts.index(-15.0)] is not None


def test_tww_liter_und_friwa():
    e = e_mit(tww__liter_p=50, tww__personen=4, tww__system="friwa", tww__zapftemp=45)
    r = rechne(e)
    assert r["tww"]["qwb_person"] == pytest.approx(50 * 1.163 * 35 / 1000)
    assert r["tww"]["t_speicher"] == 55 and r["tww"]["vl_tww"] == 60
    assert r["qtw"] == pytest.approx(4 * 0.2)


def test_verbrauch_mit_tww_wie_excel_blatt():
    """Beim Jahresverbrauch ergibt QGES = Øh,in des Excel-Blatts (Zuschlag automatisch über Nachheizzeit)."""
    r = rechne(szenarien()[1]["eingaben"])
    assert r["tww"]["methode"] == "nachheizzeit"
    assert r["qges"] == pytest.approx(r["heizlast"]["oh_in_kw"])


def test_sole():
    r = rechne(sz("sole_gross"))
    assert r["gewaehlt"]["serie"] in ("CS7800LW", "SupraecoT") and r["gewaehlt"]["ok"]
    assert r["erdreich"]["sondenlaenge_m"] > 100
    assert all(D.serie(c["serie"])["quelle"] == "sole" for c in r["kandidaten"])


def test_leitung():
    l_ = rechne(sz("liter_grossanlage"))["leitung"]
    assert l_["v_ms"] <= 1.0 and l_["r_pa_m"] <= 200


def test_grossanlage_kaskade():
    r = rechne(szenarien()[4]["eingaben"])
    g = r["gewaehlt"]
    assert g["serie"] == "CS5001" and g["n"] >= 2 and g["ok"]
    assert all(not c["moeglich"] for c in r["kandidaten"] if c["serie"] == "CS8800") is False  # 8800 kann 65 °C


def test_vorlauf_ueber_datenbereich():
    r = rechne(szenarien()[7]["eingaben"])
    assert not r["gewaehlt"]["moeglich"]
    assert "Vorlauf" in r["gewaehlt"]["grund"]


def test_projektdatei_rundlauf():
    e = szenarien()[2]["eingaben"]
    assert P.loads(P.dumps(e)) == e


def test_plz():
    assert D.plz_suche("70563") == ("Stuttgart", -12.0)
    assert D.plz_suche("1067")[0] == "Dresden"


def test_html_daten_aktuell():
    """In index.html eingebettete Daten = daten/*.json (sonst: tools/excel_import.py --nur-einbetten)."""
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    for name, datei in (("GERAETE_DATEN", "geraete.json"), ("KATALOG_DATEN", "katalog.json"), ("KLIMA_DATEN", "klima.json")):
        teil = html.split(f"const {name} = ", 1)[1].split(";\n", 1)[0]
        assert json.loads(teil) == json.loads((ROOT / "daten" / datei).read_text(encoding="utf-8")), name


def gleich(py, js, pfad=""):
    if isinstance(js, dict):
        assert isinstance(py, dict), pfad
        for k in set(py) | set(js):
            assert k in py and k in js, f"{pfad}.{k} fehlt ({'Python' if k not in py else 'HTML'})"
            gleich(py[k], js[k], f"{pfad}.{k}")
    elif isinstance(js, list):
        assert len(py) == len(js), pfad
        for i, (a, b) in enumerate(zip(py, js)):
            gleich(a, b, f"{pfad}[{i}]")
    elif isinstance(js, bool) or js is None or isinstance(py, bool) or py is None:
        assert py == js, f"{pfad}: {py!r} != {js!r}"
    elif isinstance(js, (int, float)):
        assert math.isclose(py, js, rel_tol=1e-9, abs_tol=1e-9), f"{pfad}: {py!r} != {js!r}"
    else:
        assert py == js, f"{pfad}: {py!r} != {js!r}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht installiert")
def test_python_gleich_html(tmp_path):
    sz = szenarien()
    datei = tmp_path / "sz.json"
    datei.write_text(json.dumps(sz, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run(["node", str(HIER / "rechne_html.js"), str(ROOT / "index.html"), str(datei)],
                         capture_output=True, text=True, check=True).stdout
    js = json.loads(out)
    for s, j in zip(sz, js):
        py = json.loads(json.dumps(rechne(copy.deepcopy(s["eingaben"]))))
        gleich(py, j, s["name"])


def test_pdf_alle_szenarien():
    from wp import bericht as B
    for s in szenarien():
        e = s["eingaben"]
        e["preise_drucken"] = True
        pdf = B.pdf_bytes(e, rechne(e), D.geraete(), D.katalog())
        assert pdf[:5] == b"%PDF-" and len(pdf) > 5000, s["name"]
