# TODO: Разобраться с полем `service_id` в bookings

## Контекст

После перехода на package-first подход, `service_id` в таблице `bookings` заполняется автоматически первой услугой из пакета (`_resolve_preset_services()[0].id`) исключительно для обратной совместимости.

Все flow записи (client bot, admin bot, web) передают `service_package_id`, а не `service_id`.

## Вопрос

Нужен ли `service_id` в bookings? Варианты:

1. **Удалить** — если нигде не используется напрямую
2. **Оставить как deprecated** — если есть внешние зависимости (отчёты, аналитика)
3. **Оставить** — если нужна быстрая связь с основной услугой без резолва пакета

## Где используется `booking.service_id`

- `backend/app/routers/integrations.py` — Google Calendar sync (fallback если нет пакета)
- `backend/app/routers/bookings.py` — автозаполнение при создании
- `bot/app/events/formatters.py` — fallback для старых записей без пакета
- `bot/app/flows/common/booking_edit.py` — reschedule (legacy fallback)

## Решение

Отложено. Требует аудита всех мест использования и миграции данных.
