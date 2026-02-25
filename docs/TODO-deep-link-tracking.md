# TODO: Deep-link tracking — источник привлечения

## Контекст

Telegram поддерживает deep-link с параметрами:

- **Bot:** `https://t.me/your_bot?start=source_site` → параметр приходит в `/start {payload}`
- **MiniApp:** `https://t.me/your_bot/app?startapp=source_seo` → параметр приходит в `web_app_data.start_param`

Это позволяет отслеживать источник привлечения (SEO, реклама, соцсети, QR-код и т.д.).

## Что нужно

1. **Bot handler (`/start`)** — парсить payload из deep-link
2. **MiniApp** — передавать `startapp` параметр в backend
3. **Backend** — сохранять source

## Где хранить

Варианты (выбрать один или комбинацию):

| Вариант | Плюсы | Минусы |
|---------|-------|--------|
| `users.source` | Просто, сразу видно откуда пришёл | Только первый source, не трекает повторные |
| `audit_log` | Полная история всех входов | Нужна выборка для аналитики |
| `bookings.source` | Привязка к конкретной записи | Не все пользователи записываются |

## Примеры использования

```
https://t.me/upgrade_lpg_bot?start=yandex_seo
https://t.me/upgrade_lpg_bot?start=instagram_bio
https://t.me/upgrade_lpg_bot?start=qr_flyer
https://t.me/upgrade_lpg_bot/app?startapp=google_ads
```

## Решение

Отложено. Требует выбора схемы хранения и реализации парсинга в bot + miniapp.
