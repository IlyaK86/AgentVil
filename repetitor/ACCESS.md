# ACCESS — отчёт по Шагу 1 (только чтение, без секретов)

Дата: 2026-10-03. Собрано на Mac mini (пользователь `ilya`) частично вручную владельцем.

## 1. Где что лежит (Mac mini)
- Hermes: `~/.hermes` (конфиг `~/.hermes/config.yaml`, логи `~/.hermes/logs/`), CLI `~/.local/bin/hermes`, сорцы `~/.hermes/hermes-agent`.
- Другие папки: `~/hermes-workspace`, `~/hermes-tracker`.
- launchd-сервисы: `ai.hermes.gateway` (запущен), `ai.hermes.dashboard` (запущен), `com.hermes-tunnel`, `ai.hermes.freeqwen-tunnel`, `space.kartunov.claude-proxy-http`, `space.kartunov.podcast-review` (порт 8080, `~/Cloude Code/podcast-project`).
- Каталога/репозитория «repetitor» на Mac mini НЕ найдено (поиск по имени и содержимому в `~/.hermes`, `~/hermes-workspace`, `~/code`, `~/work`, `~/workspace`, `~/scripts`, `~/bin`, `~/config`, `~/agents`, `~/Cloude Code`).
- Единственный след: в логе Hermes от 2026-09-07 владелец отправил боту ссылку `https://hermes.vilavi.tech/repetitor/` (Telegram, сессия `20260826_084727_c1e21642`).

## 2. HTTP
- https://hermes.vilavi.tech/repetitor/ — 200 (работает)
- https://kartunov.space — 200 (работает)

## 3. Доступы Hermes
Не проверено подробно (API-ключи/БД/хранилища). Видно по именам файлов в `~/.hermes`: `auth.json`, `credentials/`, `google_client_secret.json`, `google_service_account.json`, `hermes.db`, `kanban.db`, `cron.db`. В `config.yaml` есть `MSSQL_1C_USER` (БД 1С). В `ai.hermes.gateway.plist` ключ API задан в EnvironmentVariables (значение не копировалось). Статус каждого — не проверено.

## 4. Сервер `147.45.147.124` (Новосибирск, RU, Adman LLC; hostname `nsk-1-vm-4lod`)
- Вход работает (`ssh -o BatchMode=yes ... true`):
  - порт 8443, пользователь `root`, ключ `~/.ssh/id_ed25519_vilavi_server`
  - порт 22, пользователь `root`, ключ `~/.ssh/id_ed25519`
- Другие ключи в `~/.ssh`: `id_ed25519_agent`, `id_ed25519_new_server`, `tunnel_key` (назначение не выяснено). `~/.ssh/config` нет.
- Сервисы systemd: `hermes-gateway`, `hermes-ask` (API :8090 для VILAVI Hub).
- Слушающие порты: 22, 8443 (sshd), 8080 (python3), 8081/8082 (gunicorn), 8090 (python3), 8501 (python3), 10050 (zabbix), 6379 (redis, localhost), 1080 (sshd, localhost), 1081 (microsocks, localhost).
- nginx/caddy/docker на этом сервере нет. Данные: `/opt/vilavi-hub`, `/opt/vilavi-api`, `/opt/vilavi-dashboard`, `/opt/vilavi-snapshots`, `/opt/hermes`, `/opt/buildplan`, `/opt/hub-backups`, `/root/hermes-docker`, `/root/obsidian-vault`, `/var/www/html`.
- Файлов/каталогов с «repetitor» на этом сервере НЕ найдено (по имени до глубины 7 и по содержимому в /etc, /opt, /srv, /var/www, /root). Откуда отдаётся `/repetitor/` — не выяснено.
- Примечание: в задании сервер назван «в Германии» — этот находится в РФ; сервер в Германии, если он другой, не обнаружен.

## 5. kartunov.space
- DNS: `194.34.238.17` (другой сервер), отдаёт nginx/1.24.0 (Ubuntu), HTTP 200.
- Вход на `194.34.238.17` РАБОТАЕТ: `root`, порт 22, ключ `~/.ssh/id_ed25519_new_server`, hostname `12700.example.de` (вероятно, сервер «в Германии»). Ключи `id_ed25519` и `id_ed25519_vilavi_server` туда не подходят (Permission denied).
- Способ деплоя, конфиг nginx, git — не проверено.
- На Mac mini есть launchd `space.kartunov.*` (claude-proxy-http, podcast-review).

## 6. Туннели к/через сервер
- `com.hermes-tunnel`: `ssh -p 8443 -L 1080:localhost:1081 root@147.45.147.124` (SOCKS через microsocks), ключ `id_ed25519_vilavi_server`. localhost:1080 — работает.
- `ai.hermes.freeqwen-tunnel`: `ssh -L 3264:localhost:3264 root@147.45.147.124`, ключ `id_ed25519`. localhost:3264 — работает.
- Оба под launchd KeepAlive; в логах периодические «Broken pipe / Operation timed out», перезапускаются сами.
- Туннель «снаружи к Mac mini» (reverse) не найден; запущен Tailscale. Есть папка `~/sshd-tunnel` (не изучалась).

## 7. Где живёт репетитор (вывод)
- DNS `hermes.vilavi.tech` -> `194.34.238.17` (тот же сервер, что kartunov.space; вход есть, ключ `id_ed25519_new_server`). Значит `/repetitor/` раздаётся с него, а НЕ с `147.45.147.124`.
- На `147.45.147.124` порты 8080/8081/8082/8501 на `/repetitor/` не отвечают как сайт (000/404/404/301); сервисы VILAVI (hub, dashboard, Streamlit :8501). `/var/www/html` там: `reports`, `stock-risk.html`.

## 8. Основной сервер `194.34.238.17` (12700.example.de) — репетитор и сайты
Вход: `ssh -i ~/.ssh/id_ed25519_new_server root@194.34.238.17` (порт 22) — работает.

- Репетитор:
  - фронт: `/var/www/html/repetitor` (nginx `location /repetitor/`, `= /repetitor`);
  - бэкенд: `/opt/repetitor`, systemd `repetitor-api.service` (FastAPI), запущен; nginx `location /repetitor-api/` и `/repetitor-admin/`;
  - скиллы Hermes: `/root/.hermes/skills/vilavi/vilavi-repetitor`, `vilavi-repetitor-admin`; тест `/tmp/test_repetitor_socratic.py`.
- nginx `/etc/nginx/sites-enabled`: `hermes` (server_name hermes.vilavi.tech; бэкапы `hermes.bak-*`, в т.ч. `hermes.bak-20260720`), `kartunov.space`, `podcast.kartunov.space`, плюс `admin.vilavi.tech`. Прокси на 127.0.0.1: 8081, 8090–8097, 8443, 8501, 8502.
- Другие сервисы systemd (запущены): `hermes-ask*` (analyst, b24_secretary :8092, lawyer :8096, orchestrator :8095, pm :8093, supply :8094, основной :8090), `margin-offer-api` (для kartunov.space/lead), `vilavi-api`, `vilavi-dashboard` (:8501), `dispatcher`, `ollama` (:11434), `redis`, `tailscaled`, `fail2ban`, `nginx`.
- Tailscale на сервере активен (100.71.157.74).
- kartunov.space: nginx сайт `kartunov.space` на этом же сервере (корень/прокси — детали конфига не смотрели); `margin-offer-api` обслуживает /lead.
- В `/root`: `hardening-backup-20261001` (недавний hardening — учесть при смене доступов), `hermes-migrate-v0.20.0.sh`.

## Не проверено / дальше
1. Содержимое `/opt/repetitor` (код, БД, `.env` — только имена переменных), статус `repetitor-api` (логи, порт).
2. Конфиг nginx `kartunov.space` (root/прокси) и способ деплоя сайта (git/rsync/панель).
3. Доступы Hermes по пунктам (ключи, БД, Google, Telegram).
4. Назначение ключей `id_ed25519_agent`, `tunnel_key`; папка `~/sshd-tunnel`.
