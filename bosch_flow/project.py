"""Projektdateien laden/speichern – kompatibel mit „Projekt speichern/laden“ der HTML-Version."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, fields
from datetime import datetime, timezone

from .calc import Inputs, Strang

APP_NAME = "Bosch Flow – Netz- & Anlagenrechner"
SAVE_VERSION = 52  # wie index.html V54 (Dateiformat unverändert, + topoPos)
META_KEYS = ("projName", "projLoc", "projPlanner", "projDate", "montage", "heizkreis")  # letzte zwei: Katalog-Ausführung


def _convert(raw, default):
    if isinstance(default, str):
        return str(raw)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default
    return int(v) if isinstance(default, int) and v.is_integer() else v


def from_html_state(state: dict) -> tuple[Inputs, list[Strang], dict]:
    """JSON-Projekt (HTML- oder Python-Version) -> (Inputs, Stränge, Meta)."""
    if not isinstance(state, dict) or "fields" not in state:
        raise ValueError("Keine gültige Bosch-Flow-Projektdatei (Feld 'fields' fehlt).")
    f = state["fields"]
    defaults = Inputs()
    kwargs = {fld.name: _convert(f[fld.name], getattr(defaults, fld.name))
              for fld in fields(Inputs) if fld.name in f and f[fld.name] not in ("", None)}
    inp = Inputs(**kwargs)
    straenge = [Strang(s.get("floors", 1), s.get("split", "both"), s.get("cfg", [])).normalized()
                for s in state.get("straenge") or []] or [Strang.new()]
    meta = {k: f.get(k, "") for k in META_KEYS}
    meta["activeStrang"] = max(0, min(len(straenge) - 1, int(state.get("activeStrang") or 0)))
    # V54: Position der Wärmezentrale (top-level oder in fields; abwärtskompatibel)
    tp = state.get("topoPos", f.get("topoPos", 50))
    try:
        tp = float(tp)
    except (TypeError, ValueError):
        tp = 50.0
    meta["topoPos"] = max(0.0, min(100.0, tp if math.isfinite(tp) else 50.0))
    return inp, straenge, meta


def to_html_state(inp: Inputs, straenge: list[Strang], meta: dict) -> dict:
    """Projekt -> JSON-Struktur, die auch die HTML-Version laden kann."""
    active = meta.get("activeStrang", 0)
    flds = {k: meta.get(k, "") for k in META_KEYS}
    flds.update(inp.as_fields())
    flds["floors"] = str(straenge[active].floors)
    flds["split"] = straenge[active].split
    topo = meta.get("topoPos", 50)
    flds["topoPos"] = str(topo)
    return {"app": APP_NAME, "version": SAVE_VERSION,
            "savedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "fields": flds, "straenge": [asdict(s) for s in straenge], "activeStrang": active,
            "topoPos": topo}


def dumps(inp: Inputs, straenge: list[Strang], meta: dict) -> str:
    return json.dumps(to_html_state(inp, straenge, meta), ensure_ascii=False, indent=2)


def loads(text: str) -> tuple[Inputs, list[Strang], dict]:
    return from_html_state(json.loads(text))


def stand(inp: Inputs, straenge: list[Strang], meta: dict) -> str:
    """Vergleichbarer Projektstand (ohne Zeitstempel) – für Auto-Sicherung und Zwischenspeicher."""
    d = to_html_state(inp, straenge, meta)
    d.pop("savedAt", None)
    return json.dumps(d, ensure_ascii=False, sort_keys=True)
