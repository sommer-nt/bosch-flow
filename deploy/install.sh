#!/usr/bin/env bash
# Einrichtung von Bosch Flow auf Ubuntu mit nginx.
#
#   sudo bash deploy/install.sh flow.example.de
#
# Aufruf aus dem entpackten bzw. geklonten Projektordner. Das Skript
#   1. installiert Python + venv (nginx muss schon laufen),
#   2. kopiert die App nach /opt/bosch-flow und legt den Benutzer 'boschflow' an,
#   3. installiert die Python-Pakete in /opt/bosch-flow/.venv,
#   4. richtet den systemd-Dienst und die nginx-Site ein.
# Mehrfaches Ausführen ist unschädlich (aktualisiert die App).
set -euo pipefail

DOMAIN="${1:-_}"                  # '_' = jeder Hostname / Zugriff per IP
APP_DIR=/opt/bosch-flow
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

[[ $EUID -eq 0 ]] || { echo "Bitte mit sudo ausführen."; exit 1; }
command -v nginx >/dev/null || { echo "nginx nicht gefunden: sudo apt install nginx"; exit 1; }

echo "==> Pakete"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip rsync curl >/dev/null

echo "==> Benutzer und Dateien"
id boschflow &>/dev/null || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin boschflow
mkdir -p "$APP_DIR"
rsync -a --delete --exclude .git --exclude .venv --exclude '__pycache__' "$SRC_DIR"/ "$APP_DIR"/

echo "==> Python-Umgebung"
[[ -d "$APP_DIR/.venv" ]] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R boschflow:boschflow "$APP_DIR"

echo "==> systemd-Dienst"
install -m 644 "$APP_DIR/deploy/bosch-flow.service" /etc/systemd/system/bosch-flow.service
systemctl daemon-reload
systemctl enable bosch-flow >/dev/null
systemctl restart bosch-flow

echo "==> nginx"
sed "s/server_name flow.example.de;/server_name $DOMAIN;/" "$APP_DIR/deploy/nginx-bosch-flow.conf" \
    > /etc/nginx/sites-available/bosch-flow
ln -sf /etc/nginx/sites-available/bosch-flow /etc/nginx/sites-enabled/bosch-flow
nginx -t
systemctl reload nginx

sleep 3
if curl -fs http://127.0.0.1:8501/_stcore/health >/dev/null; then
    echo "✓ Bosch Flow läuft: http://$([[ $DOMAIN == _ ]] && hostname -I | awk '{print $1}' || echo "$DOMAIN")/"
else
    echo "✗ App antwortet nicht – Log ansehen: journalctl -u bosch-flow -n 50"; exit 1
fi
