"""Projektdatei (.json) – dasselbe Format wie die HTML-Version (Schlüssel „wp_auslegung“)."""
from __future__ import annotations

import copy
import json

FORMAT = "wp_auslegung"
VERSION = 1

STANDARD: dict = {
    "projekt": {"name": "", "kunde": "", "plz": "", "ort": "", "bearbeiter": "", "datum": "", "notiz": ""},
    "klima": {"nat": -12.0, "heizgrenze": 15.0, "innen": 20.0},
    "heizlast": {
        "methode": "vorgabe", "vorgabe_kw": 10.0,
        "flaeche_m2": 150.0, "spez_w_m2": 60.0,
        "huell_a_m2": 0.0, "ht": 0.0, "volumen_m3": 0.0, "luftwechsel": 0.6,
        "energietraeger": "gas", "menge": 0.0, "heizwert": 10.42, "gebaeudeart": "EFH", "vbh": 2100,
        "nutzungsgrad": 1.0, "ww_im_verbrauch": True,
    },
    "tww": {"aktiv": True, "personen": 4, "kw_person": 0.1, "methode": "personen", "td": 4,
            "nutzung": "Wohngebäude", "bezug": "personen", "qwb": 1.1, "flaeche_m2": 0.0},
    "sperrzeit_h": 0,
    "auslegung": "monoenergetisch",
    "vl": 55.0,
    "serien": [],
    "auswahl": {"geraet": "", "anzahl": 1, "inneneinheit": ""},
    "preise_drucken": False,
}


def neu() -> dict:
    return copy.deepcopy(STANDARD)


def ergaenzen(e: dict) -> dict:
    """Fehlende Schlüssel (ältere Dateien) mit Standardwerten auffüllen."""
    def mische(ziel, quelle):
        for k, v in quelle.items():
            if k not in ziel:
                ziel[k] = copy.deepcopy(v)
            elif isinstance(v, dict) and isinstance(ziel[k], dict):
                mische(ziel[k], v)
        return ziel
    return mische(copy.deepcopy(e), STANDARD)


def dumps(e: dict) -> str:
    return json.dumps({"format": FORMAT, "version": VERSION, "eingaben": e}, ensure_ascii=False, indent=1)


def loads(text: str) -> dict:
    d = json.loads(text)
    if d.get("format") != FORMAT:
        raise ValueError("Keine Projektdatei der Wärmepumpen-Schnellauslegung.")
    return ergaenzen(d["eingaben"])
