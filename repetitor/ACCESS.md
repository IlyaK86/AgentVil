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
- Вход на `194.34.238.17`, способ деплоя, панель, git — не проверено.
- На Mac mini есть launchd `space.kartunov.*` (claude-proxy-http, podcast-review).

## 6. Туннели к/через сервер
- `com.hermes-tunnel`: `ssh -p 8443 -L 1080:localhost:1081 root@147.45.147.124` (SOCKS через microsocks), ключ `id_ed25519_vilavi_server`. localhost:1080 — работает.
- `ai.hermes.freeqwen-tunnel`: `ssh -L 3264:localhost:3264 root@147.45.147.124`, ключ `id_ed25519`. localhost:3264 — работает.
- Оба под launchd KeepAlive; в логах периодические «Broken pipe / Operation timed out», перезапускаются сами.
- Туннель «снаружи к Mac mini» (reverse) не найден; запущен Tailscale. Есть папка `~/sshd-tunnel` (не изучалась).

## Не проверено / дальше
1. DNS `hermes.vilavi.tech` и кто отдаёт `/repetitor/` (порты 8080/8081/8082/8501 на сервере или `194.34.238.17`).
2. Вход на `194.34.238.17` и деплой kartunov.space.
3. Доступы Hermes по пунктам (ключи, БД, Google, Telegram).
4. Содержимое `~/sshd-tunnel`, `~/.hermes/hermes_gateway.sh`.
