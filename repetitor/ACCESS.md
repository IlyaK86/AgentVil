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

## 9. Репетитор — детали (проверено на 194.34.238.17)
- Бэкенд `/opt/repetitor`: `backend.py` (119 КБ, FastAPI), `db.py`, `rag.py`, `kb/` (база знаний), `data.db` (SQLite, обновлялась 2026-10-01), `__pycache__`.
- Запуск: `repetitor-api.service`, `ExecStart=/usr/local/lib/hermes-agent/venv/bin/python /opt/repetitor/backend.py`, `WorkingDirectory=/opt/repetitor`; active с 2026-09-12; внутренний порт 8097 (nginx `/repetitor-api/` -> 127.0.0.1:8097, timeouts 300s, body до 20m).
- Фронт: `/var/www/html/repetitor/` (nginx `alias`, SPA fallback на index.html); админка: `/repetitor-admin/` -> `/var/www/html/repetitor/admin.html`.
- Git: `/opt/repetitor` НЕ является git-репозиторием (нет истории, нет remote) — код живёт только на сервере. Рекомендуется завести репозиторий/бэкап.
- `.env` в `/opt/repetitor` нет; откуда берутся ключи LLM (переменные systemd/ Hermes venv) — не выяснено.
- Свежие проблемы в логах (2026-10-01):
  - `[auth_me interests] no such column: updated_at` (схема БД расходится с кодом);
  - `[chat] empty answer with KB, retrying without KB`;
  - `[insights] LLM error: Expecting value: line 1 column 1` (LLM вернул не-JSON/пусто).
  - внешние сканеры бьют по `/metrics`, `/` (404) — шум.
- kartunov.space: nginx server `kartunov.space`, root `/var/www/kartunov.space`; `/lead-ask/` -> 127.0.0.1:8098 (margin-offer-api); `/lead`, `/offer` редиректы. Деплой — копирование файлов в `/var/www/kartunov.space` (git/CI не проверялись).

## 10. Фронт и деплой (проверено)
- `/var/www/html/repetitor/`: ровно 2 файла — `index.html` (83 КБ, 2026-09-08) и `admin.html` (59 КБ, 2026-09-07). Одностраничный фронт, без сборки и без git.
- `/var/www/kartunov.space/`: `index.html`, `offer.html`, `reglament.html`, `lead/`, `offer/`. Тоже не git; скриптов деплоя нет — правка файлов прямо на сервере.
- Скрипты в `/root`: `conv_changes.sh`, `hermes-migrate-v0.20.0.sh`, `run_graphify.sh` (деплоя среди них нет). Соседние сайты в `/var/www/html`: `analyst`, `b24-secretary`, `project-manager`, `supply-chain`; у `index.html` есть бэкапы `.bak-*`.
- Итог: деплой = редактирование/копирование файлов по SSH; версионирования нет ни у фронта, ни у бэкенда.

## 11. Доступы Hermes на Mac mini (только имена, значения не читались)
`~/.hermes/.env` содержит переменные (статус «работает» не проверялся, проверено лишь наличие):
- Bitrix24: `BITRIX_WEBHOOK_URL`, `BITRIX_MCP_URL`
- Внешний API: `EXTERNAL_API_BASE_URL`, `EXTERNAL_API_TOKEN`
- Локальный API/MCP: `WEBHOOK_PORT`, `API_SERVER_ENABLED`, `API_SERVER_HOST`, `API_SERVER_KEY`, `MCP_SERVER_PORT`
- Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `TELEGRAM_GROUP_ALLOWED_CHATS`, `TELEGRAM_FALLBACK_IPS`, таймауты `HERMES_TELEGRAM_HTTP_*`
- LLM: `OPENROUTER_API_KEY`, `MINIMAX_API_KEY`, `OMNIROUTER_API_KEY` (`ANTHROPIC_API_KEY` закомментирован)
- Прочее: `GITHUB_TOKEN` (git/Pi CLI), `MCP_STITCH_API_KEY`, `GARANT_TOKEN`, `OBSIDIAN_VAULT_PATH`
- `~/.hermes/credentials/`: `hostkey_api.key`, `yandex_metrika.env`; также `~/.hermes/auth.json`, `google_client_secret.json`, `google_service_account.json`.
- `~/sshd-tunnel/`: собственный sshd (host-ключи, `sshd_config`, `sshd.log`) — вход на Mac mini снаружи; запущен ли — не проверено (в процессах не видно).
- ssh-agent пустой (ключи используются через `-i`, не через агент).

## 12. БД репетитора и окружение
- `/opt/repetitor/data.db` (SQLite), таблицы: `users`, `auth_tokens`, `chat_logs`, `learning_progress`, `learning_insights`, `topic_difficulty`, `subscription_events`.
- У `repetitor-api.service` переменные окружения заданы прямо в unit-файле (`Environment=...`, значения не читались) — ключи LLM, скорее всего, там.

## Итог Шага 1
Проверено и работает: сайты (200), SSH на оба сервера, туннели, сервис репетитора.

## 13. Изменения после Шага 1 (2026-10-02/03)
- Бэкапы на сервере: `/root/backups/` (`repetitor-data-*.db`, `repetitor-code-*.tgz`, `backend.py.pre-fix*`).
- Безопасность: `REPETITOR_SECRET` не был задан (токены подписывались ключом по умолчанию). Теперь задан случайный через drop-in `/etc/systemd/system/repetitor-api.service.d/secret.conf` (права 600, значение не в репозитории). Сессии пользователей сброшены.
- Код репетитора теперь в git: `repetitor/app/backend`, `repetitor/app/frontend` (без `data.db`).
- Исправлено: `updated_at` -> `generated_at`; `_llm_json` (устойчивый разбор JSON, повтор, `max_tokens=3000`) для `insights`. Задеплоено, сервис active, логи за 2 часа без ошибок.
- Деплой: `scp backend.py root@194.34.238.17:/opt/repetitor/` + `systemctl restart repetitor-api`; откат — из `/root/backups/backend.py.pre-fix2`. ВАЖНО: источник правды — git; перед правкой на сервере сверять с репозиторием.

## Не проверено / дальше
1. Работоспособность токенов Hermes (GitHub, Telegram, Bitrix, LLM) — проверять отдельно, без вывода значений.
2. Запущен ли sshd из `~/sshd-tunnel`, как Mac mini доступен снаружи (Tailscale?).
3. Назначение ключей `id_ed25519_agent`, `tunnel_key`.
4. Фронт и kartunov.space без git; kartunov.space не в репозитории.
