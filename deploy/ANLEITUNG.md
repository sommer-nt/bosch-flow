# Betrieb auf eigenem Server: flow.sommer-nt.de

Wie klima/climate: Die App läuft als Docker-Container und ist nur lokal auf **127.0.0.1:8504**
erreichbar. nginx leitet `flow.sommer-nt.de` dorthin, certbot holt das HTTPS-Zertifikat.

**1. DNS:** CNAME `flow` → `danisox.ddns.net` (wie `climate`).
Prüfen: `dig +short flow.sommer-nt.de` zeigt die Server-IP.

**2. Code holen und starten**

Das Repository ist **privat**. Der Server liest es über einen **Deploy Key** (SSH-Schlüssel nur für dieses Repo,
nur lesen, ohne Passwort; GitHub-Passwörter funktionieren für Git nicht):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/bosch_flow -N "" -C "webmin bosch-flow"
cat ~/.ssh/bosch_flow.pub          # Zeile kopieren
```

GitHub → `sommer-nt/bosch-flow` → **Settings → Deploy keys → Add deploy key**: Zeile einfügen,
„Allow write access“ **nicht** anhaken. Dann auf dem Server:

```bash
cat >> ~/.ssh/config <<'EOT'
Host github-flow
    HostName github.com
    User git
    IdentityFile ~/.ssh/bosch_flow
    IdentitiesOnly yes
EOT
chmod 600 ~/.ssh/config

cd ~
git clone git@github-flow:sommer-nt/bosch-flow.git
cd bosch-flow/deploy
cp .env.beispiel .env && nano .env          # Passwort setzen, APP_PORT=8504
docker compose -p flow up -d --build
curl http://127.0.0.1:8504/_stcore/health   # → ok
```

Fingerabdruck von github.com beim ersten Verbinden: `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU` → `yes`.

**3. nginx und HTTPS**
```bash
sudo cp nginx-flow.sommer-nt.de.conf /etc/nginx/sites-available/flow.sommer-nt.de
sudo ln -s /etc/nginx/sites-available/flow.sommer-nt.de /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d flow.sommer-nt.de
```

Fertig: **https://flow.sommer-nt.de** (zuerst die Passwortseite).

Wichtig in der nginx-Konfiguration sind die WebSocket-Zeilen (`Upgrade`/`Connection`) – ohne sie bleibt
die Seite weiß.

## Im Betrieb

| Aufgabe | Befehl (im Ordner `~/bosch-flow/deploy`) |
|---|---|
| Neue Version einspielen | `git pull && docker compose -p flow up -d --build` |
| Logs ansehen | `docker compose -p flow logs -f app` |
| Status | `docker compose -p flow ps` |
| Stoppen | `docker compose -p flow down` |

Das Projekt `-p flow` trennt den Container von klima/climate – deren Container bleiben unberührt.

## Fehlersuche

- **Seite weiß / lädt endlos:** WebSocket-Zeilen in der nginx-Konfiguration prüfen, danach
  `sudo nginx -t && sudo systemctl reload nginx`.
- **502 Bad Gateway:** Container läuft nicht → `docker compose -p flow ps` und `logs -f app`.
- **Port belegt:** in `.env` einen freien `APP_PORT` wählen und in der nginx-Datei `proxy_pass` anpassen.
- **Kein Zertifikat:** DNS-Eintrag prüfen (`dig +short flow.sommer-nt.de`), Port 80 offen?
