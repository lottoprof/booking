# Deployment

---

## 1. Окружения

| Окружение | Способ запуска | Когда использовать |
|-----------|---------------|-------------------|
| Тестовый сервер | systemd + venv | Разработка, отладка, быстрый цикл |
| Боевой тест | Docker + volume mount | Проверка перед production |
| Production | Docker (без volume) | Финальный деплой |

---

## 2. Тестовый сервер: systemd + venv

Быстрый цикл обновления: `git pull && systemctl restart`.

### 2.1. Первоначальная настройка

```bash
# Зависимости
apt update && apt install -y python3.11 python3.11-venv redis-server nginx

# Проект
cd /opt
git clone <repo> booking
cd booking

# Виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# БД
python backend/migrate.py
python scripts/init_admin.py

# .env
cp .env.example .env
# Отредактировать: REDIS_URL, DATABASE_URL, TG_BOT_TOKEN, TG_WEBHOOK_SECRET
```

### 2.2. Systemd units

**`/etc/systemd/system/booking-backend.service`**

```ini
[Unit]
Description=Booking Backend API
After=redis.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/booking
Environment=PATH=/opt/booking/venv/bin
EnvironmentFile=/opt/booking/.env
ExecStart=/opt/booking/venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/booking-gateway.service`**

```ini
[Unit]
Description=Booking Gateway + Bot
After=redis.service booking-backend.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/booking
Environment=PATH=/opt/booking/venv/bin
EnvironmentFile=/opt/booking/.env
ExecStart=/opt/booking/venv/bin/uvicorn gateway.app.main:app --host 127.0.0.1 --port 8080
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable booking-backend booking-gateway
systemctl start booking-backend booking-gateway
```

### 2.3. Цикл обновления

```bash
cd /opt/booking
git pull

# Если изменились зависимости
source venv/bin/activate && pip install -r requirements.txt

# Если есть новые миграции
python backend/migrate.py

# Перезапуск
systemctl restart booking-backend booking-gateway
```

### 2.4. Логи

```bash
journalctl -u booking-backend -f
journalctl -u booking-gateway -f
journalctl -u booking-backend -u booking-gateway -f  # оба сразу
```

---

## 3. Боевой тест: Docker + volume mount

Код монтируется через volume — пересборка image только при изменении `requirements.txt`.

### 3.1. docker-compose.dev.yml

```yaml
version: "3.9"

services:
  redis:
    image: redis:7
    restart: unless-stopped
    ports:
      - "6379:6379"

  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    restart: unless-stopped
    env_file: .env
    environment:
      - REDIS_URL=redis://redis:6379/1
      - DATABASE_URL=sqlite:///./data/sqlite/booking.db
    depends_on:
      - redis
    ports:
      - "8000:8000"
    volumes:
      - .:/app
      - ./data/sqlite:/app/data/sqlite
    command: uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

  gateway:
    build:
      context: .
      dockerfile: gateway/Dockerfile
    restart: unless-stopped
    env_file: .env
    environment:
      - REDIS_URL=redis://redis:6379/1
      - DOMAIN_API_URL=http://backend:8000
    depends_on:
      - redis
      - backend
    ports:
      - "8080:8080"
    volumes:
      - .:/app
    command: uvicorn gateway.app.main:app --host 0.0.0.0 --port 8080 --reload
```

### 3.2. Dockerfile (общий)

Текущие Dockerfile в `backend/`, `gateway/`, `bot/` — для production. Для dev с volume mount нужен общий:

**`Dockerfile.dev`** (корень проекта)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код монтируется через volume, COPY не нужен
```

При использовании `Dockerfile.dev` в `docker-compose.dev.yml`:

```yaml
  backend:
    build:
      context: .
      dockerfile: Dockerfile.dev
    # ...
```

### 3.3. Запуск

```bash
# Первый запуск (сборка image)
docker-compose -f docker-compose.dev.yml up --build

# Обновление кода — просто сохранить файл, --reload подхватит
# Обновление зависимостей
docker-compose -f docker-compose.dev.yml up --build
```

### 3.4. .env для Docker

Переключить адреса на имена сервисов:

```
REDIS_URL=redis://redis:6379/1
DOMAIN_API_URL=http://backend:8000
```

---

## 4. NGINX (общее для обоих)

```nginx
server {
    listen 443 ssl;
    server_name upgradebot.online;

    ssl_certificate     /etc/letsencrypt/live/upgradebot.online/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/upgradebot.online/privkey.pem;

    location /tg/webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 5. Порядок запуска

```
1. Redis
2. Backend (port 8000)
3. Gateway + Bot (port 8080) — зависит от Redis и Backend
4. NGINX — проксирует в Gateway
```

---

## 6. Проверки

```bash
# Backend
curl http://127.0.0.1:8000/services/

# Gateway
curl http://127.0.0.1:8080/services/

# Redis events
redis-cli LLEN events:p2p

# Логи consumer loops
# systemd:
journalctl -u booking-gateway -f | grep consumer
# docker:
docker-compose -f docker-compose.dev.yml logs -f gateway | grep consumer
```
