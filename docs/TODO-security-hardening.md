# TODO: Блокировка сканеров и вредоносных ботов

**Статус:** Ожидает
**Приоритет:** Средний
**Контекст:** Обнаружен массовый сканер (IP 172.190.142.176) — перебирает PHP-шеллы в `/images/`, `/css/`. Пустой UA, ~1 req/sec.

---

## 1. Gateway: блокировка подозрительных UA для public-клиентов

**Файл:** `gateway/app/middleware/auth.py`
**Где:** до rate_limit, сразу после определения `client_type = "public"`

Блокировать (403) public-запросы с:
- Пустым `User-Agent`
- UA содержит `python-requests`, `curl`, `wget`, `Go-http-client`, `scrapy`

Не трогать: `internal`, `admin_bot`, `tg_client` — у них свои заголовки.

## 2. Nginx: ранний отсечник .php

**Файл:** конфиг nginx на сервере

```nginx
location ~* \.php$ {
    return 444;
}
```

`444` — nginx молча закрывает соединение, не тратя ресурсы на ответ. Запросы не доходят до gateway.
