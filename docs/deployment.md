# Deployment

## 1. Архитектура

```
Client → NGINX (443) → Gateway (8080) → Bot (aiogram, in-process)
                                       → Backend (8000) → SQLite + Redis
```

| Компонент | Порт  | Роль                                 |
|-----------|-------|--------------------------------------|
| NGINX     | 443   | TLS-терминация, проксирование        |
| Gateway   | 8080  | Webhook, middleware, event consumers  |
| Backend   | 8000  | Бизнес-логика, API, slot engine      |
| Redis     | 6379  | FSM, кеш, очереди событий, блокировки|
| SQLite    | —     | Единственное хранилище данных        |

### Фоновые задачи

**Gateway (lifespan):**
- `p2p_consumer_loop` — мгновенная доставка из `events:p2p`
- `broadcast_consumer_loop` — доставка из `events:broadcast` (30 msg/s throttle)
- `retry_consumer_loop` — повторная доставка из `events:*:retry`
- `web_booking_consumer_loop` — обработка pending bookings из Redis

**Backend (lifespan):**
- `completion_checker_loop` — каждые 60с, завершение прошедших букингов
- `reminder_checker_loop` — каждые 60с, напоминания о предстоящих букингах
- Warmup `rebuild_services_cache()` — заполнение Redis-кеша сервисов

### SSG-рендеры (ручной запуск)

```bash
# Промо-блок на главной
python -m backend.app.services.ssg.render_promo

# Блог: статьи, индекс, sitemap
python -m backend.app.services.ssg.renderer
```

На проде — добавить в cron или вызывать после обновления контента.

---

## 2. Структура на сервере

```
/home/{user}/upgrade/
├── backend/
├── bot/
├── gateway/
├── frontend/
├── scripts/
├── deploy/              # шаблоны (systemd, hooks)
├── data/sqlite/         # БД (вне git)
├── venv/                # виртуальное окружение (вне git)
├── .env                 # секреты (вне git)
├── bare_git/
│   └── upgrade.git/     # bare repo для push-деплоя
│       └── hooks/
│           └── post-update
└── ...
```

`bare_git/` — голый git-репо, принимает `git push` и через hook раскатывает код в рабочую директорию.

---

## 3. Первоначальная настройка

### 3.1. Системные зависимости

```bash
sudo apt update && sudo apt install -y python3 python3-venv redis-server nginx jq
```

### 3.2. Проект и venv

```bash
mkdir -p /home/{user}/upgrade
cd /home/{user}/upgrade

python3 -m venv venv
source venv/bin/activate
```

### 3.3. Bare git repo

```bash
mkdir -p bare_git
git init --bare bare_git/upgrade.git
```

### 3.4. Push с локалки (первый раз)

```bash
# На локальной машине:
git remote add {server} ssh://{user}@{host}/home/{user}/upgrade/bare_git/upgrade.git
git push {server} master
```

После первого push код появится в `/home/{user}/upgrade/` через hook.

### 3.5. Hook

```bash
cp deploy/post-update bare_git/upgrade.git/hooks/post-update
chmod +x bare_git/upgrade.git/hooks/post-update
```

### 3.6. Зависимости Python

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 3.7. Окружение

```bash
cp template_env .env
# Отредактировать .env — см. раздел 9
```

### 3.8. База данных

```bash
mkdir -p data/sqlite
python backend/migrate.py
python scripts/init_admin.py
```

---

## 4. Деплой через git push

Рабочий процесс:

```
локалка: git push {server} master
  → bare_git/upgrade.git/hooks/post-update
    → checkout в /tmp + rsync в рабочую директорию
```

Hook (`deploy/post-update`) выполняет:
1. `git checkout` из bare repo во временную директорию
2. `rsync` из временной директории в рабочую
3. Очистка временной директории

После push — перезапустить серверы (tmux или systemd).

### Полный цикл обновления

```bash
# 1. Push
git push {server} master

# 2. На сервере: миграции (если есть новые)
source venv/bin/activate
python backend/migrate.py

# 3. Зависимости (если изменились)
pip install -r requirements.txt

# 4. Перезапуск — см. раздел 5 (tmux) или 6 (systemd)
```

---

## 5. Запуск (tmux)

Подходит для первого запуска, отладки, тестирования.

### Скрипт `scripts/tmux-upgrade.sh`

```bash
# Запуск сессии:
./scripts/tmux-upgrade.sh start

# Остановка:
./scripts/tmux-upgrade.sh stop

# Статус:
./scripts/tmux-upgrade.sh status

# Рестарт:
./scripts/tmux-upgrade.sh restart
```

### Раскладка tmux

```
Session: upgrade
├── Window 1 "servers"
│   ├── Pane 1: gateway  (port 8080)
│   └── Pane 2: backend  (port 8000)
└── Window 2 "db"
    └── Pane 1: sqlite3
```

### Ручной перезапуск серверов

Gateway запускается из `gateway/`, backend из `backend/`, `PYTHONPATH` указывает на корень проекта.

```bash
P=/home/{user}/upgrade

# Gateway
tmux send-keys -t upgrade:1.1 C-c
sleep 1
tmux send-keys -t upgrade:1.1 "find $P -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; cd $P/gateway && PYTHONPATH=$P $P/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080" Enter

# Backend
tmux send-keys -t upgrade:1.2 C-c
sleep 1
tmux send-keys -t upgrade:1.2 "find $P -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; cd $P/backend && PYTHONPATH=$P $P/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000" Enter
```

### Проверка логов

```bash
tmux capture-pane -t upgrade:1.1 -p | tail -20   # gateway
tmux capture-pane -t upgrade:1.2 -p | tail -20   # backend
```

---

## 6. Запуск (systemd user-level)

Для долгосрочного запуска. User-level units — не нужен root.

### 6.1. Установка unit-файлов

```bash
mkdir -p ~/.config/systemd/user/
cp deploy/booking-backend.service ~/.config/systemd/user/
cp deploy/booking-gateway.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

### 6.2. Enable-linger (чтобы сервисы работали без залогиненной сессии)

```bash
sudo loginctl enable-linger {user}
```

### 6.3. Запуск

```bash
systemctl --user enable booking-backend booking-gateway
systemctl --user start booking-backend booking-gateway
```

### 6.4. Управление

```bash
# Статус
systemctl --user status booking-backend booking-gateway

# Перезапуск после деплоя
systemctl --user restart booking-backend booking-gateway

# Логи
journalctl --user -u booking-backend -f
journalctl --user -u booking-gateway -f
```

---

## 7. NGINX

Конфиг (создать `/etc/nginx/sites-available/upgrade`):

```nginx
server {
    listen 80;
    server_name upgradebot.online;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name upgradebot.online;

    ssl_certificate     /etc/letsencrypt/live/upgradebot.online/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/upgradebot.online/privkey.pem;

    # Security headers
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;

    # Block .php requests
    location ~* \.php$ {
        return 444;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/upgrade /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### SSL (после DNS)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d upgradebot.online
```

---

## 8. Фоновые задачи

### Lifespan loops

Запускаются автоматически при старте gateway/backend — ничего настраивать не нужно.

### SSG-рендеры (cron)

```bash
crontab -e
```

```cron
# Промо — раз в день в 03:00
0 3 * * * cd /home/{user}/upgrade && PYTHONPATH=/home/{user}/upgrade venv/bin/python -m backend.app.services.ssg.render_promo

# Блог — раз в день в 03:10
10 3 * * * cd /home/{user}/upgrade && PYTHONPATH=/home/{user}/upgrade venv/bin/python -m backend.app.services.ssg.renderer
```

### Webhook check

```bash
# Webhook — раз в час
0 * * * * cd /home/{user}/upgrade && bash scripts/webhook.sh
```

---

## 9. Переменные окружения

Все переменные определены в `template_env`. Ключевые:

| Переменная           | Описание                                      | Пример                                |
|----------------------|-----------------------------------------------|---------------------------------------|
| `DATABASE_URL`       | Путь к SQLite                                 | `sqlite:///./data/sqlite/booking.db`  |
| `REDIS_URL`          | Redis (обязательно DB 1)                      | `redis://127.0.0.1:6379/1`           |
| `TG_BOT_TOKEN`       | Токен Telegram бота                           | `123456:ABC...`                       |
| `TG_WEBHOOK_SECRET`  | Секрет для проверки webhook                   | `openssl rand -hex 32`               |
| `WEBHOOK_URL`        | Полный URL webhook                            | `https://upgradebot.online/tg/webhook`|
| `DOMAIN_API_URL`     | URL бэкенда (для gateway)                     | `http://127.0.0.1:8000`              |
| `GATEWAY_URL`        | URL gateway (для bot)                         | `http://127.0.0.1:8080`              |
| `INTERNAL_TOKEN`     | Токен внутренней аутентификации               | `openssl rand -hex 32`               |
| `ADMIN_TG_ID`        | Telegram ID администратора                    | `123456789`                           |
| `COMPANY_NAME`       | Название компании (init_admin)                | `UPGRADE`                             |
| `SUPPORT_TG_ID`      | Telegram ID для обращений                     | `123456789`                           |
| `CHANNEL_URL`        | Ссылка на Telegram-канал                      | `https://t.me/channel`               |
| `TG_BOT_URL`         | Ссылка на бота                                | `https://t.me/upgradelpgbot`         |
| `GOOGLE_CLIENT_ID`   | Google OAuth client ID                        | `xxx.apps.googleusercontent.com`     |
| `GOOGLE_CLIENT_SECRET`| Google OAuth secret                          | `xxx`                                 |
| `GOOGLE_REDIRECT_URI`| Google OAuth redirect                         | `https://example.com/oauth/google/callback` |
| `MINIAPP_URL`        | URL Telegram Mini App                         | `https://upgradebot.online/miniapp`  |
| `TG_PROXY_URL`       | Порт SSH-tunnel к Telegram API (опционально)  | `8443`                                |

---

## 10. Telegram API Proxy (SSH tunnel)

Если провайдер блокирует исходящий трафик к `api.telegram.org` (DPI по SNI), бот не сможет отправлять сообщения. Входящий webhook при этом работает (Telegram → nginx → gateway).

### Диагностика блокировки

```bash
# TLS к Telegram API проходит?
curl -sv --max-time 10 https://api.telegram.org/ 2>&1 | head -15

# Если зависает на "Encrypted Extensions" — провайдер блокирует по SNI
```

### Решение: SSH port forward через VPS

Требуется VPS с доступом к Telegram API и SSH-алиас для подключения (в `~/.ssh/config`).

**Принцип работы:**
```
aiogram → api.telegram.org:8443 → (custom resolver: 127.0.0.1) → SSH tunnel → VPS → Telegram API (443)
```

- SSH tunnel (`ssh -L`) пробрасывает локальный порт 8443 на IP Telegram API (443) через VPS
- Кастомный aiohttp resolver в `bot/app/main.py` направляет `api.telegram.org` на `127.0.0.1`
- SNI в TLS = `api.telegram.org` (правильный) → сертификат валиден, API отвечает
- Провайдер видит только зашифрованный SSH-трафик к VPS

### Настройка

```bash
# 1. SSH-ключ для VPS (если ещё нет)
ssh-keygen -t ed25519 -C "{server}-proxy"
ssh-copy-id {vps-alias}

# 2. Запустить SSH tunnel
ssh -L 8443:{telegram-api-ip}:443 -f -N {vps-alias}

# 3. Проверить
curl -s --max-time 10 --resolve 'api.telegram.org:8443:127.0.0.1' \
  https://api.telegram.org:8443/ | head -3

# 4. Добавить в .env
echo 'TG_PROXY_URL=8443' >> /home/{user}/upgrade/.env

# 5. Перезапустить gateway (через tmux!)
```

Актуальный IP Telegram API: `dig api.telegram.org +short`

### Как работает в коде

При наличии `TG_PROXY_URL` в `.env` (`bot/app/main.py`):

1. `TelegramAPIServer` с URL `https://api.telegram.org:{port}/bot{token}/{method}`
2. Кастомный aiohttp resolver (`_TgLocalResolver`): `api.telegram.org` → `127.0.0.1`
3. Трафик: `127.0.0.1:{port}` → SSH tunnel → VPS → Telegram API

Без `TG_PROXY_URL` — прямое подключение как обычно.

### Автозапуск tunnel (systemd user service)

Tunnel должен подниматься автоматически при старте сервера и перезапускаться при обрыве.

**Prerequisite:** enable-linger для пользователя (чтобы user services работали без активной сессии):

```bash
sudo loginctl enable-linger {user}
```

**Unit-файл:**

```bash
mkdir -p ~/.config/systemd/user/

cat > ~/.config/systemd/user/tg-tunnel.service << 'EOF'
[Unit]
Description=SSH tunnel to Telegram API
After=network-online.target

[Service]
Environment=TG_API_IP={telegram-api-ip}
ExecStart=/usr/bin/ssh -L 8443:${TG_API_IP}:443 -N \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  {vps-alias}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF
```

- `Environment=TG_API_IP` — IP Telegram API вынесен в переменную; при смене IP не нужно править весь юнит
- `ServerAliveInterval=30` + `ServerAliveCountMax=3` — если VPS не отвечает 90с, SSH умирает → systemd рестартит
- `ExitOnForwardFailure=yes` — если порт занят, сразу падает → restart
- При смене VPS достаточно обновить `~/.ssh/config` — юнит использует SSH-алиас
- При смене IP Telegram API: `systemctl --user edit tg-tunnel` → добавить `[Service]` + `Environment=TG_API_IP=новый_ip`

**Управление:**

```bash
systemctl --user daemon-reload
systemctl --user enable --now tg-tunnel
systemctl --user status tg-tunnel

# Логи
journalctl --user -u tg-tunnel -f

# Перезапуск
systemctl --user restart tg-tunnel
```

**Перед включением** — убить ручной tunnel:

```bash
pkill -f 'ssh -L 8443'
```

### Диагностика tunnel

```bash
# Tunnel жив?
pgrep -af 'ssh -L 8443'

# Telegram API отвечает через tunnel?
curl -s --max-time 5 --resolve 'api.telegram.org:8443:127.0.0.1' \
  https://api.telegram.org:8443/bot${TG_BOT_TOKEN}/getWebhookInfo | jq .

# Ручной перезапуск (если не через systemd)
pkill -f 'ssh -L 8443'
ssh -L 8443:{telegram-api-ip}:443 -f -N {vps-alias}

# Через systemd
systemctl --user restart tg-tunnel
```

### webhook.sh

Скрипт `scripts/webhook.sh` также поддерживает tunnel. При наличии `TG_PROXY_URL` в `.env` curl использует `--resolve api.telegram.org:{port}:127.0.0.1` для обхода блокировки.

### Отключение

Закомментировать или удалить `TG_PROXY_URL` из `.env` и перезапустить gateway — бот пойдёт напрямую.

### Запасной вариант: stunnel (при блокировке SSH)

Если провайдер начнёт блокировать SSH-протокол (DPI на SSH handshake), SSH tunnel перестанет работать. Следующий шаг — stunnel: обёртка трафика в обычный TLS, неотличимый от HTTPS.

**Эскалация:**

| Уровень блокировки | Решение | Что менять |
|---|---|---|
| Блокировка по SNI | SSH -L (текущее) | — |
| SSH на стандартном порту | SSH -L через порт 443 VPS | `ssh -L 8443:...:443 -p 443 {vps-alias}` |
| DPI на SSH-протокол | stunnel | см. ниже |

**Схема stunnel:**
```
server:8443 → stunnel(client) :8443→{vps-ip}:443 → stunnel(server) → 149.154.166.110:443
```

Провайдер видит обычный TLS-трафик на порт 443 VPS — неотличим от HTTPS.

#### Настройка VPS (server-side)

```bash
apt install stunnel4

# Сгенерировать самоподписанный сертификат (или использовать Let's Encrypt)
openssl req -new -x509 -days 3650 -nodes \
  -out /etc/stunnel/stunnel.pem \
  -keyout /etc/stunnel/stunnel.pem \
  -subj "/CN={vps-hostname}"

cat > /etc/stunnel/stunnel.conf << 'EOF'
pid = /var/run/stunnel4/stunnel.pid
setuid = stunnel4
setgid = stunnel4

[tg-proxy]
accept = 0.0.0.0:443
connect = {telegram-api-ip}:443
cert = /etc/stunnel/stunnel.pem
EOF

systemctl enable --now stunnel4
```

> Если на VPS уже занят порт 443 (nginx/другой сервис), использовать другой порт (например, 8443) и пробросить через iptables или использовать свободный порт.

#### Настройка сервера (client-side)

```bash
apt install stunnel4

cat > /etc/stunnel/stunnel.conf << 'EOF'
pid = /var/run/stunnel4/stunnel.pid
setuid = stunnel4
setgid = stunnel4

[tg-proxy]
client = yes
accept = 127.0.0.1:8443
connect = {vps-ip}:443
# Для самоподписанного сертификата:
verifyChain = no
EOF

systemctl enable --now stunnel4
```

#### systemd user service (альтернатива системному stunnel)

Если нет root-доступа, stunnel можно запустить как user service:

```bash
cat > ~/.config/systemd/user/tg-stunnel.service << 'EOF'
[Unit]
Description=stunnel to Telegram API via VPS
After=network-online.target

[Service]
ExecStart=/usr/bin/stunnel /home/{user}/.config/stunnel/stunnel.conf
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

mkdir -p ~/.config/stunnel
cat > ~/.config/stunnel/stunnel.conf << 'EOF'
foreground = yes
pid =

[tg-proxy]
client = yes
accept = 127.0.0.1:8443
connect = {vps-ip}:443
verifyChain = no
EOF

systemctl --user daemon-reload
systemctl --user enable --now tg-stunnel
```

> `foreground = yes` и пустой `pid =` — обязательны для работы под systemd.

#### Переключение SSH → stunnel

1. Остановить SSH tunnel: `systemctl --user stop tg-tunnel` (или `pkill -f 'ssh -L 8443'`)
2. Запустить stunnel (systemd или вручную)
3. Проверить: `curl -s --max-time 5 --resolve 'api.telegram.org:8443:127.0.0.1' https://api.telegram.org:8443/`
4. Код бота и `.env` менять **не нужно** — `TG_PROXY_URL=8443` работает с любым транспортом на `127.0.0.1:8443`

---

## 11. Логи и диагностика

### tmux

```bash
# Последние строки
tmux capture-pane -t upgrade:1.1 -p | tail -20    # gateway
tmux capture-pane -t upgrade:1.2 -p | tail -20    # backend

# Поиск ошибок
tmux capture-pane -t upgrade:1.1 -p -S -1000 | grep -i 'error\|traceback'
tmux capture-pane -t upgrade:1.2 -p -S -1000 | grep -i 'error\|traceback'
```

### systemd

```bash
journalctl --user -u booking-backend -f
journalctl --user -u booking-gateway -f
journalctl --user -u booking-backend -u booking-gateway --since "1 hour ago"
```

### Проверка здоровья

```bash
# Backend API
curl -s http://127.0.0.1:8000/services/ | jq .

# Gateway
curl -s http://127.0.0.1:8080/ -o /dev/null -w "%{http_code}"

# Redis
redis-cli -n 1 PING

# Redis очереди
redis-cli -n 1 LLEN events:p2p
redis-cli -n 1 LLEN events:broadcast

# Webhook
bash scripts/webhook.sh
```

---

## 12. Docker (справка)

Docker не является основным способом деплоя, но может использоваться при необходимости.

```bash
docker-compose up --build
```

Для Docker — переключить в `.env`:

```
REDIS_URL=redis://redis:6379/1
DOMAIN_API_URL=http://backend:8000
```
