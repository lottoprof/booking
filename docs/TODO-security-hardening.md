# TODO: Блокировка сканеров и вредоносных ботов

**Статус:** Частично выполнено
**Приоритет:** Средний
**Контекст:** Обнаружен массовый сканер (IP 172.190.142.176) — перебирает PHP-шеллы в `/images/`, `/css/`. Пустой UA, ~1 req/sec.

---

## 1. ~~Gateway: блокировка подозрительных UA + .php~~ DONE

**Коммит:** `589cc61`
**Файл:** `gateway/app/middleware/auth.py`

Реализовано:
- Блокировка (403) public-запросов с пустым `User-Agent`
- Блокировка UA: `curl/`, `python-requests`, `wget`, `go-http-client`, `scrapy`
- Блокировка `*.php` путей для public-клиентов
- Возврат `JSONResponse(403)` напрямую (не `raise HTTPException` — не работает в Starlette middleware)
- `internal`, `admin_bot`, `tg_client` не затронуты

## 2. Nginx: ранний отсечник .php

**Файл:** конфиг nginx на сервере

```nginx
location ~* \.php$ {
    return 444;
}
```

`444` — nginx молча закрывает соединение, не тратя ресурсы на ответ. Запросы не доходят до gateway.
