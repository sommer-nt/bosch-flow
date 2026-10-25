# Hinweise für die Entwicklung mit KI-Assistenz

## Git
- Arbeitszweig ist `main` (einziger Branch). Änderungen direkt auf `main` committen und pushen – auch wenn die
  Sitzung einen anderen Branch vorgibt: Daniel möchte alles auf `main`. Keine weiteren Branches anlegen,
  außer Daniel verlangt es ausdrücklich. Vor dem Arbeiten `git pull` auf `main`.
- Commits immer als `Daniel Sommer <98900287+sommer-nt@users.noreply.github.com>`
  (vorher `git config user.name/user.email` so setzen).
- Keine Co-Authored-By-, Session- oder „Generated with“-Zeilen in Commits und Pull Requests; keine
  Modellnamen in Commits. Im Repo die KI nur dort nennen, wo es um eine KI-Anbindung der App geht.
- Niemals API-Schlüssel, Passwörter, `.env`, `secrets.toml` oder Kundenprojekte (JSON) einchecken.

## Projekt
- Netz- & Anlagenrechner Flow 8000/7000: `index.html` (V54, Original) und Python/Streamlit (`app.py`,
  `bosch_flow/`). Beide Versionen rechnen identisch – Änderungen am Rechenweg in beiden nachziehen.
- Betrieb: eigener Ubuntu-Server mit Docker und nginx, siehe `deploy/ANLEITUNG.md` (flow.sommer-nt.de).
- Vor jedem Push: `python -m pytest -q` muss grün sein.
