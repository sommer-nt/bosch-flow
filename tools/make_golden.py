"""Erzeugt tests/golden.json: Referenzwerte aus der ORIGINAL-HTML-Version (index.html).

Lädt index.html im Headless-Chromium, setzt je Szenario aus tests/scenarios.json die Eingaben,
ruft die JavaScript-Rechnung auf und speichert die Ergebnisse. Die Python-Tests vergleichen
den Rechenkern dagegen. Nur nötig, wenn sich index.html oder die Szenarien ändern:

    python tools/make_golden.py
"""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
CHROMIUM = "/opt/pw-browsers/chromium"

JS = """
(sc) => {
  const set=(id,v)=>{const el=document.getElementById(id); if(el) el.value=v;};
  STRAENGE = JSON.parse(JSON.stringify(sc.straenge)); ACTIVE_STRANG = 0;
  set('floors', String(STRAENGE[0].floors)); set('split', STRAENGE[0].split);
  for(const [k,v] of Object.entries(sc.fields)) set(k,v);
  fillStationDropdowns();
  if('wwstage' in sc.fields) set('wwstage', sc.fields.wwstage);
  const results = STRAENGE.map(s=>compute(s));
  const head = projectHeadline(results[0]);
  render();
  const rowsOf = sel => Array.from(document.querySelectorAll(sel+' tr'))
      .map(tr=>Array.from(tr.children).map(td=>td.textContent.trim()));
  const strip = R => ({P:R.P, anlage:R.anlage, hRows:R.hRows, vRows:R.vRows, totalWE:R.totalWE, allWE:R.allWE,
                       govN:R.govN, singleStationV:R.singleStationV, perStationDim:R.perStationDim,
                       kpiPuffer:pufferProdukt(R.anlage.pufferVol)});
  return {name:sc.name, results:results.map(strip), headline:head,
          anlageTable:rowsOf('#anlageBody'), dleTable:rowsOf('#dleHelpTbl tbody')};
}
"""


def main():
    scenarios = json.loads((ROOT / "tests" / "scenarios.json").read_text(encoding="utf-8"))
    with sync_playwright() as p:
        kw = {"executable_path": CHROMIUM} if os.path.exists(CHROMIUM) else {}
        browser = p.chromium.launch(**kw)
        out = []
        for sc in scenarios:
            ctx = browser.new_context()          # frischer Kontext: kein Autosave/localStorage
            page = ctx.new_page()
            page.goto((ROOT / "index.html").as_uri())
            page.wait_for_timeout(500)
            out.append(page.evaluate(JS, sc))
            ctx.close()
        browser.close()
    (ROOT / "tests" / "golden.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)} Szenarien -> tests/golden.json")


if __name__ == "__main__":
    main()
