#!/usr/bin/env bash
# Neue Version einspielen: im aktualisierten Projektordner (git pull oder neues ZIP) ausführen.
#
#   sudo bash deploy/update.sh
set -euo pipefail
APP_DIR=/opt/bosch-flow
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
[[ $EUID -eq 0 ]] || { echo "Bitte mit sudo ausführen."; exit 1; }

rsync -a --delete --exclude .git --exclude .venv --exclude '__pycache__' "$SRC_DIR"/ "$APP_DIR"/
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R boschflow:boschflow "$APP_DIR"
systemctl restart bosch-flow
sleep 3
if curl -fs http://127.0.0.1:8501/_stcore/health >/dev/null; then
    echo "✓ aktualisiert und neu gestartet"
else
    echo "✗ App antwortet nicht – Log ansehen: journalctl -u bosch-flow -n 50"; exit 1
fi
