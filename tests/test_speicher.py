"""Speicherauswahl: Datenbasis, Auswahl-Logik und Gleichlauf mit speicher.html."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from bosch_flow import speicher as SP

WURZEL = Path(__file__).resolve().parent.parent
HTML = (WURZEL / "speicher.html").read_text(encoding="utf-8")
D = SP.laden()


def namen(gruppen, kat):
    return [SP.speicher_nach_id(e["id"])["name"] for e in gruppen[kat]]


def test_html_enthaelt_aktuelle_daten():
    m = re.search(r"const DATEN = (.*?);\nconst BILDER", HTML, re.S)
    assert m, "Datenblock in speicher.html fehlt – tools/speicher_import.py ausführen"
    assert json.loads(m.group(1)) == D, "speicher.html ist nicht aktuell – tools/speicher_import.py ausführen"


def test_bewertung():
    assert SP.bewertung("+") == ("ja", "")
    assert SP.bewertung("-") == ("nein", "")
    assert SP.bewertung("") == ("", "")
    assert SP.bewertung("++")[1] == "zwei Speichereinheiten"
    assert SP.bewertung("(-)*")[0] == "bedingt"
    assert SP.bewertung("+ /(-)*") == ("bedingt", "möglich, " + SP.WW_HINWEIS)


def test_beispiel_cs6800i_7():
    """Wie im Mockup: CS58/6800i AW 7 OR-S → u. a. WPS 390-1 und BPU 300-C."""
    wp = next(w for w in D["wp"] if w["familie"].startswith("CS58/6800i") and w["groesse"] == "7 OR-S")
    g = SP.speicher_fuer_wp(wp["id"])
    assert {"BST 50 Ehp", "BH 120-5 1 A"} <= set(namen(g, "puffer"))
    assert {"WP 290 EP 1C", "HR 200", "HR 300", "WP 300 KP 1 B"} <= set(namen(g, "ww"))
    assert namen(g, "biv") == ["WPS 390-1 EP 1 C"]
    assert set(namen(g, "kombi")) == {"BPU 300-C", "BPU 400-C"}
    assert "WP 300 KP 1 B" not in namen(SP.speicher_fuer_wp(wp["id"], alte=False), "ww")


def test_heizer_wps390():
    s = SP.speicher_nach_id(SP.suche("8732921683")[0])
    hz = SP.heizer_fuer_speicher(s["id"])
    assert [D["heizer"][e["id"]]["ttnr"] for e in hz["led"]] == [
        "7735502657", "7735502658", "7735502659", "7735502660", "7735502661"]
    assert len(hz["flh"]) == 4 and not hz["led_hd"] and not hz["cthk"]
    assert s["im"].startswith("https://")


def test_heizer_zusammengefuehrt_bpu():
    """BPU steht im Trinkwasser- und im Pufferblock: CTHK und „nur Heizungsunterstützung“ beide vorhanden."""
    hz = SP.heizer_fuer_speicher("bpu-300-c")
    assert {e["status"] for e in hz["led"]} == {"hzg"}
    assert len(hz["cthk"]) == 4


def test_suche_name_und_ttnr():
    assert SP.suche("bpu 300") == ["bpu-300-c"]
    assert not SP.suche("W 200-5")                           # nur Wärmepumpenspeicher (Matrix)
    assert SP.suche("WP 300 KP 1 B") == ["wp-300-p-1-b"]     # Name aus der E-Heizer-Liste


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js nicht installiert")
def test_html_logik_gleich_python():
    logik = re.search(r'<script id="logik">(.*?)</script>', HTML, re.S).group(1)
    js = logik + f"""
const d = {json.dumps(D)};
const out = {{wp: {{}}, sp: {{}}, hz: {{}}, suche: {{}}}};
for (const w of d.wp) out.wp[w.id] = [speicherFuerWp(d, w.id), speicherFuerWp(d, w.id, false, false),
                                      speicherFuerWp(d, w.id, true, true, true)];
for (const s of d.speicher) {{ out.sp[s.id] = [wpsFuerSpeicher(d, s.id), abweichungen(d, s.id)];
                              out.hz[s.id] = heizerFuerSpeicher(d, s.id); }}
for (const q of ["bpu", "7735", "WP 300", "x"]) out.suche[q] = suche(d, q);
out.pk = d.wp.map(w => pakete(d, w.id)).concat(d.speicher.map(s => pakete(d, null, s.id)));
process.stdout.write(JSON.stringify(out));
"""
    erg = json.loads(subprocess.run(["node", "-"], input=js, capture_output=True, text=True, check=True).stdout)
    for w in D["wp"]:
        assert erg["wp"][w["id"]] == [SP.speicher_fuer_wp(w["id"]), SP.speicher_fuer_wp(w["id"], False, False),
                                      SP.speicher_fuer_wp(w["id"], True, True, True)]
    for s in D["speicher"]:
        assert erg["sp"][s["id"]] == [SP.wps_fuer_speicher(s["id"]), SP.abweichungen(s["id"])]
        assert erg["hz"][s["id"]] == SP.heizer_fuer_speicher(s["id"])
    assert erg["pk"] == [SP.pakete(w["id"]) for w in D["wp"]] + [SP.pakete(sid=s["id"]) for s in D["speicher"]]
    for q, ids in erg["suche"].items():
        assert ids == SP.suche(q)


def test_katalog_eingebunden():
    s = SP.speicher_nach_id("wps-390-1-ep-1-c")
    k = s["katalog"]
    assert k["preis"] == 3073.0 and k["kern"]["volumen_l"] == "343,0" and k["kern"]["hoehe_mm"] == "1594"
    assert k["bilder"] and all(b.exists() for b in SP.bilder(s))
    assert any(z["ttnr"] == "8738212214" for z in k["zubehoer"])          # FLH 25 M
    # Katalog ergänzt Freigaben, die in der Matrix fehlen (CS3800iAW ↔ WPS 390)
    wp = next(w["id"] for w in D["wp"] if w["name"] == "CS3800iAW 4 O-S")
    assert "wps-390-1-ep-1-c" not in [e["id"] for e in SP.speicher_fuer_wp(wp)["biv"]]
    assert {"id": "wps-390-1-ep-1-c", "quelle": "katalog"}.items() <= next(
        e for e in SP.speicher_fuer_wp(wp, katalog=True)["biv"] if e["id"] == "wps-390-1-ep-1-c").items()


def test_abweichung_matrix_katalog():
    lw13 = next(w["id"] for w in D["wp"] if w["familie"].startswith("CS 7801i") and str(w["groesse"]) == "13")
    assert {"id": lw13, "matrix": "+", "katalog": "-"} in SP.abweichungen("bh-120-5-1-a")


def test_ergaenzungskatalog():
    """Ergänzungskatalog 07/2026: neue BP ...-7 aus der Matrix mit Daten; Nicht-WP-Speicher werden nicht angezeigt."""
    bp = SP.speicher_nach_id("bp-500-7-erz-1")
    assert bp["katalog"]["stand"] == "07/2026" and bp["katalog"]["preis"] == 2754.0
    assert bp["eheizer"]["quelle"] == "spies" and any(SP.heizer_fuer_speicher(bp["id"]).values())
    assert not SP.suche("8732990136")                                  # W 500-6 EKP 1: kein WP-Speicher
    assert D["heizer"]["led:7735502657"]["preis"] == 560.68           # neuester Preis


def test_nachfolger_namen_pakete():
    assert SP.speicher_nach_id("bh-500-6-erz-1-b")["nachfolger"] == "bp-500-7-erz-1"
    assert SP.speicher_nach_id("bp-500-7-erz-1")["vorgaenger"] == ["bh-500-6-erz-1-b"]
    bps = SP.speicher_nach_id("bps500-7-er")
    assert bps["name"] == "BPS 500-7 ER 1" and bps["name_excel"] == "BPS500-7 ER" and bps["info"] == "je nach Verwendung"
    cs3800_4 = next(w["id"] for w in D["wp"] if w["name"] == "CS3800iAW 4 O-S")
    assert {"bpu-400-c"} <= {i for p in SP.pakete(cs3800_4) for i in p["speicher_ids"]}


def test_rueckmeldung_spies():
    """WP 290/370 EP 1C = Nachfolger WH 290/370 LP 1 B; Daten vom Vorgänger; -7 mit Hinweis zur Planererfahrung."""
    wp290 = SP.speicher_nach_id("wp-290-ep-1c")
    assert "vorgaenger" not in wp290                                 # WH 290 LP 1 B ist kein Matrix-Speicher
    assert wp290["katalog"]["aus_im"] and wp290["katalog"]["preis"] is None
    assert wp290["name_im"] == "WP 290-2 KLP 1" and wp290["ttnr"] == ["8732973069", "8732973067"]
    assert wp290["katalog"]["kern"]["hoehe_mm"] == "1299"
    assert wp290["katalog"]["kombi"] == {} and SP.bilder(wp290)
    assert any(SP.heizer_fuer_speicher("wp-290-ep-1c").values())
    assert "Planererfahrung" in SP.speicher_nach_id("bp-500-7-erz-1")["hinweis_matrix"]


def test_eheizer_bp7_und_pf_solar():
    hz = SP.heizer_fuer_speicher("bp-500-7-erz-1")
    assert len(hz["led"]) == 5 and len(hz["cthk"]) == 6                 # CTHK 636 nicht für 500 l
    assert len(SP.heizer_fuer_speicher("bp-750-7-erz-1")["cthk"]) == 7
    assert SP.speicher_nach_id("bp-500-7-erz-1")["eheizer"]["tiefe_muffe_mm"] == 580
    assert not SP.suche("PF 500 solar")


def test_kommentar_baureihe_und_erklaerung():
    cs3800_10 = next(w["id"] for w in D["wp"] if w["name"] == "CS3800iAW 10 O-T")
    bh200 = SP.speicher_nach_id("bh-200-5-1-a")
    assert "4-Punkt" in bh200["notiz"][cs3800_10] and cs3800_10 in bh200["notiz_baureihe"]
    assert "Trennpuffer" in D["erklaerungen"]["4-Punkt"]


def test_nur_wp_speicher():
    assert D["nur_wp_speicher"] and all(s["matrix"] for s in D["speicher"])
    ids = {s["id"] for s in D["speicher"]}
    assert all(s.get("nachfolger", next(iter(ids))) in ids for s in D["speicher"])


def test_vergleichswerte():
    titel = [f["titel"] for f in D["vergleich_felder"]]
    assert {"Volumen", "Kippmaß", "Gewicht leer", "UVP"} <= set(titel)
    v = SP.speicher_nach_id("wps-390-1-ep-1-c")["vergleich"]
    assert v["Volumen"] == "343,0" and v["Höhe"] == "1594" and v["UVP"] == "3.073,00"
    assert all("vergleich" in s for s in D["speicher"])
