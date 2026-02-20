# TODO: sort_order для service_packages

**Статус:** Ожидает
**Приоритет:** Низкий

---

## Проблема

Порядок карточек услуг/пакетов на прайсе, записи (web + miniapp + TG) определяется порядком `id` в таблице `service_packages`. Нет возможности управлять порядком отображения.

## Решение

### 1. Миграция

```sql
ALTER TABLE service_packages ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0;
UPDATE service_packages SET sort_order = id;
```

### 2. Бэкенд

- `services_cache_builder.py` — добавить `ORDER BY sort_order` в запрос packages
- Схемы `ServicePackageCreate/Update` — добавить поле `sort_order`

### 3. Сортировка карточек

Группировка по `name` уже есть. Нужно сортировать `result` по `min(sort_order)` группы перед return.
