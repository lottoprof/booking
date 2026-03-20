# Обход блокировки Telegram Bot API через SSH-туннели

Инструкция для ситуации, когда провайдер блокирует Telegram на уровне DPI/SNI и по IP-диапазонам. Бот не может ни отправлять сообщения, ни принимать webhook.

**Требования:**
- Сервер с ботом (Linux, SSH)
- VPS за пределами блокировки (Linux, SSH, socat)
- SSH-доступ с ключом между сервером и VPS

## Что блокируется

| Направление | Что происходит | Симптом |
|---|---|---|
| **Исходящее** (бот → Telegram API) | DPI по SNI `api.telegram.org` | `curl https://api.telegram.org` зависает на TLS handshake |
| **Входящее** (Telegram → webhook) | Блокировка IP-диапазонов Telegram (91.108.x.x, 149.154.x.x) | Webhook: `Connection timed out` / `Read timeout expired` |

## Топология

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  ИСХОДЯЩЕЕ — отправка сообщений бота                                    │
│                                                                         │
│  [Bot/aiogram]                                                          │
│       │ api.telegram.org:8443                                           │
│       ↓ (custom resolver → 127.0.0.1)                                   │
│  [localhost:8443] ──ssh -L──→ [VPS] ──→ [Telegram API 149.154.x.x:443] │
│       сервер                                                            │
│                                                                         │
│  • TLS SNI = api.telegram.org (cert валиден)                            │
│  • Провайдер видит только SSH-трафик к VPS                              │
│  • Утечка DNS исключена (resolver в памяти, tunnel по IP)               │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ВХОДЯЩЕЕ — приём webhook от Telegram                                   │
│                                                                         │
│  [Telegram servers]                                                     │
│       │ HTTPS                                                           │
│       ↓                                                                 │
│  [VPS:{webhook-port}] socat (TLS termination, self-signed cert)         │
│       │ plain HTTP                                                      │
│       ↓                                                                 │
│  [VPS:localhost:{tunnel-port}] ──ssh -R──→ [localhost:{gateway-port}]   │
│                                                 сервер (gateway)        │
│                                                                         │
│  • Self-signed cert для IP VPS (загружается в Telegram)                 │
│  • Nginx сервера не участвует                                           │
│  • Webhook URL: https://{vps-ip}:{webhook-port}/tg/webhook             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Порты (рекомендация)

| Порт | Где | Назначение |
|---|---|---|
| `{webhook-port}` (8443) | VPS, внешний | socat TLS — принимает webhook от Telegram |
| `{tunnel-port}` (18080) | VPS, localhost | Reverse tunnel endpoint |
| `{gateway-port}` (8080) | Сервер, localhost | Gateway (FastAPI/webhook handler) |
| `{outgoing-port}` (8443) | Сервер, localhost | Forward tunnel к Telegram API |

> Telegram принимает webhook на портах: 443, 80, 88, 8443.

## Настройка

### 1. Подготовка VPS (один раз, от root)

```bash
# SSH config: разрешить привязку к внешним интерфейсам
echo "GatewayPorts clientspecified" >> /etc/ssh/sshd_config
systemctl reload sshd

# Установить socat
apt install -y socat

# Открыть порт в firewall (если есть)
iptables -A INPUT -p tcp --dport {webhook-port} -j ACCEPT
# Сохранить правила (Debian/Ubuntu)
iptables-save > /etc/iptables/rules.v4

# Сгенерировать self-signed cert для IP VPS
openssl req -new -x509 -days 3650 -nodes \
  -out ~/tg-webhook.pem -keyout ~/tg-webhook.key \
  -subj "/CN={vps-ip}" -addext "subjectAltName=IP:{vps-ip}"
```

### 2. SSH-алиас на сервере

```bash
# ~/.ssh/config на сервере с ботом
Host {vps-alias}
  HostName {vps-ip}
  User {vps-user}
  Port {vps-ssh-port}
  IdentityFile ~/.ssh/{keyfile}
```

Проверка: `ssh {vps-alias} 'echo OK'`

### 3. Исходящий tunnel (ssh -L) — на сервере

Пробрасывает локальный порт на Telegram API через VPS.

```bash
# Узнать IP Telegram API
dig api.telegram.org +short
# Запомнить один из IP, например: {telegram-api-ip}

# Запустить tunnel
ssh -L {outgoing-port}:{telegram-api-ip}:443 -f -N \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  {vps-alias}

# Проверить
curl -s --max-time 5 \
  --resolve "api.telegram.org:{outgoing-port}:127.0.0.1" \
  "https://api.telegram.org:{outgoing-port}/" | head -1
# Ожидаемо: HTML с 302 Found
```

### 4. Входящий tunnel (ssh -R) — на сервере

Открывает порт на VPS, который ведёт в gateway на сервере.

```bash
ssh -R 0.0.0.0:{tunnel-port}:127.0.0.1:{gateway-port} -f -N \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  {vps-alias}

# Проверить что порт открылся на VPS
ssh {vps-alias} "ss -tlnp | grep {tunnel-port}"
# Ожидаемо: LISTEN 0.0.0.0:{tunnel-port}
```

### 5. socat на VPS (от root)

TLS-терминация на внешнем порту, форвард на tunnel.

```bash
socat \
  OPENSSL-LISTEN:{webhook-port},cert=/home/{vps-user}/tg-webhook.pem,key=/home/{vps-user}/tg-webhook.key,verify=0,reuseaddr,fork \
  TCP:127.0.0.1:{tunnel-port} &

# Проверить
curl -k --max-time 5 https://127.0.0.1:{webhook-port}/
# Ожидаемо: ответ от gateway (403 или аналогичный)
```

### 6. Сертификат и установка webhook

Self-signed сертификат создаётся на VPS (шаг 1), затем копируется на сервер
в `data/tg-webhook.pem` и загружается в Telegram при `setWebhook`.

```bash
# Скопировать cert с VPS на сервер (в постоянное место)
scp {vps-alias}:~/tg-webhook.pem {project-dir}/data/tg-webhook.pem
```

#### Автоматически (рекомендуется)

Скрипт `scripts/webhook.sh` определяет режим по переменным `.env`:
- `TG_PROXY_URL` задан → API-вызовы через tunnel (`--resolve`)
- `TG_PROXY_URL` + `TG_VPS_IP` заданы → webhook на `https://{vps-ip}:{port}/tg/webhook` + загрузка сертификата

```bash
# Проверка и автоматический сброс при проблемах
bash scripts/webhook.sh

# Скрипт сам:
# 1. Сравнит текущий webhook URL с ожидаемым (VPS или прямой)
# 2. Проверит ошибки и pending updates
# 3. При необходимости — вызовет setWebhook с -F certificate=@data/tg-webhook.pem
```

#### Вручную

```bash
# Установить webhook (через исходящий tunnel)
curl --resolve "api.telegram.org:{outgoing-port}:127.0.0.1" \
  -F "url=https://{vps-ip}:{webhook-port}/tg/webhook" \
  -F "secret_token={webhook-secret}" \
  -F "certificate=@{project-dir}/data/tg-webhook.pem" \
  -F 'allowed_updates=["message","edited_message","callback_query","channel_post","edited_channel_post","message_reaction","message_reaction_count"]' \
  "https://api.telegram.org:{outgoing-port}/bot{bot-token}/setWebhook"

# Ожидаемо: {"ok":true,"result":true,"description":"Webhook was set"}
```

> **Важно:** сертификат нужен только при первой установке или смене VPS.
> Telegram запоминает загруженный сертификат — повторные `setWebhook`
> с тем же URL не требуют повторной загрузки (но скрипт на всякий случай
> загружает его каждый раз).

### 7. Проверка

```bash
# Webhook info
curl -s --resolve "api.telegram.org:{outgoing-port}:127.0.0.1" \
  "https://api.telegram.org:{outgoing-port}/bot{bot-token}/getWebhookInfo" | jq .

# Ожидаемо:
# url: https://{vps-ip}:{webhook-port}/tg/webhook
# has_custom_certificate: true
# pending_update_count: 0
# last_error_message: null

# Отправить /start боту и проверить логи gateway
```

## Настройка кода бота (aiogram 3)

Для исходящего tunnel бот должен подключаться к `127.0.0.1:{outgoing-port}` вместо `api.telegram.org:443`. При этом TLS SNI должен остаться `api.telegram.org`.

### Переменные окружения

```env
# .env

# Порт исходящего tunnel (ssh -L) — бот подключается к localhost:{port}
TG_PROXY_URL={outgoing-port}

# IP адрес VPS — webhook будет https://{vps-ip}:{outgoing-port}/tg/webhook
# Если не задан — webhook остаётся на WEBHOOK_URL (прямое подключение)
TG_VPS_IP={vps-ip}

# Путь к self-signed сертификату VPS (по умолчанию: data/tg-webhook.pem)
#TG_VPS_CERT=data/tg-webhook.pem
```

### Кастомный resolver + TelegramAPIServer (aiogram 3 + aiohttp)

```python
import os
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiohttp.resolver import AbstractResolver

TG_PROXY_URL = os.getenv("TG_PROXY_URL")  # например "8443"

if TG_PROXY_URL:
    tunnel_port = int(TG_PROXY_URL)

    class TunnelResolver(AbstractResolver):
        """Resolve api.telegram.org → 127.0.0.1 for SSH tunnel."""

        async def resolve(self, host, port=0, family=0):
            if host == "api.telegram.org":
                return [{"hostname": host, "host": "127.0.0.1", "port": port,
                         "family": 2, "proto": 0, "flags": 0}]
            import socket
            infos = socket.getaddrinfo(host, port, family, socket.SOCK_STREAM)
            return [{"hostname": host, "host": i[4][0], "port": i[4][1],
                     "family": i[0], "proto": i[2], "flags": 0} for i in infos]

        async def close(self):
            pass

    server = TelegramAPIServer(
        base=f"https://api.telegram.org:{tunnel_port}/bot{{token}}/{{method}}",
        file=f"https://api.telegram.org:{tunnel_port}/file/bot{{token}}/{{path}}",
    )
    session = AiohttpSession(api=server)
    session._connector_init["resolver"] = TunnelResolver()
    bot = Bot(token=BOT_TOKEN, session=session)
else:
    bot = Bot(token=BOT_TOKEN)
```

**Почему это работает:**
- URL содержит `api.telegram.org` → TLS SNI корректный → cert валиден
- Resolver перенаправляет на `127.0.0.1` → соединение идёт в tunnel
- DNS-запрос к `api.telegram.org` не происходит (утечка DNS исключена)

## Автозапуск (systemd)

### Исходящий tunnel — systemd user service на сервере

```bash
# Prerequisite: разрешить user services без логина
sudo loginctl enable-linger {server-user}

mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/tg-tunnel-outgoing.service << 'EOF'
[Unit]
Description=SSH tunnel to Telegram API (outgoing)
After=network-online.target

[Service]
Environment=TG_API_IP={telegram-api-ip}
ExecStart=/usr/bin/ssh -L {outgoing-port}:${TG_API_IP}:443 -N \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  {vps-alias}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now tg-tunnel-outgoing
```

### Входящий tunnel — systemd user service на сервере

```bash
cat > ~/.config/systemd/user/tg-tunnel-incoming.service << 'EOF'
[Unit]
Description=Reverse SSH tunnel for Telegram webhook (incoming)
After=network-online.target

[Service]
ExecStart=/usr/bin/ssh -R 0.0.0.0:{tunnel-port}:127.0.0.1:{gateway-port} -N \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  {vps-alias}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now tg-tunnel-incoming
```

### socat — systemd system service на VPS

```bash
# На VPS, от root
cat > /etc/systemd/system/tg-webhook-socat.service << 'EOF'
[Unit]
Description=socat TLS proxy for Telegram webhook
After=network-online.target

[Service]
ExecStart=/usr/bin/socat \
  OPENSSL-LISTEN:{webhook-port},cert=/home/{vps-user}/tg-webhook.pem,key=/home/{vps-user}/tg-webhook.key,verify=0,reuseaddr,fork \
  TCP:127.0.0.1:{tunnel-port}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now tg-webhook-socat
```

## Диагностика

```bash
# === На сервере ===

# Исходящий tunnel жив?
pgrep -af 'ssh -L'
systemctl --user status tg-tunnel-outgoing

# Входящий tunnel жив?
pgrep -af 'ssh -R'
systemctl --user status tg-tunnel-incoming

# Telegram API отвечает через tunnel?
curl -s --max-time 5 \
  --resolve "api.telegram.org:{outgoing-port}:127.0.0.1" \
  "https://api.telegram.org:{outgoing-port}/" | head -1

# === На VPS ===

# Порты слушают?
ss -tlnp | grep -E "{webhook-port}|{tunnel-port}"

# socat жив?
pgrep -af socat
systemctl status tg-webhook-socat

# Webhook endpoint отвечает?
curl -k --max-time 5 https://127.0.0.1:{webhook-port}/

# === Telegram API ===

# Webhook info
curl -s --resolve "api.telegram.org:{outgoing-port}:127.0.0.1" \
  "https://api.telegram.org:{outgoing-port}/bot{bot-token}/getWebhookInfo" | jq .
```

## Безопасность

- **Утечка DNS исключена**: кастомный resolver возвращает `127.0.0.1`, tunnel по IP (не hostname)
- **Webhook secret**: Telegram отправляет `X-Telegram-Bot-Api-Secret-Token` — gateway проверяет
- **Self-signed cert**: загружается в Telegram при `setWebhook` — MITM невозможен
- **Провайдер видит**: SSH-трафик к VPS (не к Telegram)

Для блокировки этого соединения провайдеру нужно заблокировать SSH в целом или конкретный IP VPS.

### Эскалация при усилении блокировки

| Уровень блокировки | Решение |
|---|---|
| DPI по SNI `api.telegram.org` | ssh -L (текущее) |
| Блокировка IP Telegram (входящие) | ssh -R + socat (текущее) |
| SSH на стандартном порту | Перенести SSH VPS на порт 443 |
| DPI на SSH-протокол | stunnel (TLS-обёртка, неотличима от HTTPS) |
| Активное зондирование | obfs4 / shadowsocks |

## Отключение

```bash
# На сервере: остановить tunnels
systemctl --user stop tg-tunnel-outgoing tg-tunnel-incoming

# На VPS: остановить socat
systemctl stop tg-webhook-socat

# Вернуть webhook на прямой URL (если блокировки больше нет)
curl -F "url=https://{your-domain}/tg/webhook" \
     -F "secret_token={webhook-secret}" \
     "https://api.telegram.org/bot{bot-token}/setWebhook"

# Убрать TG_PROXY_URL и TG_VPS_IP из .env и перезапустить gateway
```
