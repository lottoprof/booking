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

---

## 10. Логи и диагностика

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

## 11. Docker (справка)

Docker не является основным способом деплоя, но может использоваться при необходимости.

```bash
docker-compose up --build
```

Для Docker — переключить в `.env`:

```
REDIS_URL=redis://redis:6379/1
DOMAIN_API_URL=http://backend:8000
```
