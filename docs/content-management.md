# Управление контентом: промо и блог

Руководство по размещению промо-карточек на главной и статей в блоге.

## Промо-карточки (главная страница)

### Как это работает

1. Промо хранятся в таблице `promotions`
2. CRUD API: `POST/GET/PATCH/DELETE /promotions/`
3. При любом изменении через API автоматически запускается SSG-рендер (`render_promo_all`)
4. Дополнительно: крон каждый день в 03:00 перерендеривает `index.html`
5. Истёкшие промо (`end_date < today`) автоматически исключаются из рендера

### Создание промо

```bash
ssh backup8t 'python3 -c "
import urllib.request, json
data = json.dumps({
    \"badge_type\": \"gift\",
    \"badge_text\": \"※ Подарок\",
    \"title\": \"С 8 Марта — скидка 20%!\",
    \"description\": \"Любая процедура со скидкой 20% до конца марта.\",
    \"end_date\": \"2026-03-31\",
    \"cta_text\": \"Записаться →\",
    \"cta_url\": \"/book\"
}).encode()
req = urllib.request.Request(\"http://127.0.0.1:8000/promotions/\", data=data, headers={\"Content-Type\": \"application/json\"})
resp = urllib.request.urlopen(req)
print(resp.read().decode())
"'
```

### Поля промо

| Поле | Тип | Обязательное | Описание |
|------|-----|:---:|----------|
| `badge_type` | string | — | CSS-класс бейджа: `sale`, `gift`, `new` (default: `sale`) |
| `badge_text` | string | да | Текст бейджа: `☆ Акция`, `※ Подарок`, `✧ Новинка` |
| `title` | string | да | Заголовок карточки |
| `description` | string | да | Описание, 1–2 предложения |
| `price_new` | int | — | Новая цена (null — без цены) |
| `price_old` | int | — | Старая цена, зачёркнутая (null — скрыта) |
| `end_date` | string | — | Дата окончания `YYYY-MM-DD` (null — бессрочная) |
| `cta_text` | string | — | Текст кнопки: `Записаться →` |
| `cta_url` | string | — | Ссылка кнопки: `/book`, `/book?service=lpg` |
| `is_active` | int | — | 1 = активна, 0 = скрыта (default: 1) |
| `sort_order` | int | — | Порядок сортировки (меньше = выше, default: 0) |

### Редактирование промо

```bash
# Изменить заголовок и описание промо id=4
ssh backup8t 'python3 -c "
import urllib.request, json
data = json.dumps({
    \"title\": \"Новый заголовок\",
    \"description\": \"Новое описание.\"
}).encode()
req = urllib.request.Request(\"http://127.0.0.1:8000/promotions/4\", data=data, method=\"PATCH\", headers={\"Content-Type\": \"application/json\"})
resp = urllib.request.urlopen(req)
print(resp.read().decode())
"'
```

### Деактивация / удаление промо

```bash
# Деактивировать (скрыть, но оставить в БД)
ssh backup8t 'python3 -c "
import urllib.request, json
data = json.dumps({\"is_active\": 0}).encode()
req = urllib.request.Request(\"http://127.0.0.1:8000/promotions/4\", data=data, method=\"PATCH\", headers={\"Content-Type\": \"application/json\"})
urllib.request.urlopen(req)
print(\"OK\")
"'

# Удалить полностью
ssh backup8t 'python3 -c "
import urllib.request
req = urllib.request.Request(\"http://127.0.0.1:8000/promotions/4\", method=\"DELETE\")
urllib.request.urlopen(req)
print(\"OK\")
"'
```

### Просмотр всех промо

```bash
ssh backup8t 'curl -s http://127.0.0.1:8000/promotions/ | python3 -m json.tool'
```

### Жизненный цикл промо

```
Создание (POST) → автоматический рендер → карточка на сайте
                                        ↓
                          end_date наступил → крон 03:00 перерендерит → карточка исчезает
                                        ↓
                   (опционально) PATCH is_active=0 или DELETE → рендер → карточка исчезает
```

Максимум **3 активных промо** одновременно. Рендер берёт записи с `is_active=1` и `end_date >= today` (или `end_date IS NULL`).

---

## Статьи блога

### Как это работает

1. Статьи хранятся в таблице `articles`, категории — в `categories`
2. Нет CRUD API — статьи создаются напрямую через SQLite на сервере
3. SSG-рендерер (`renderer.py`) генерирует:
   - `frontend/blog/{slug}.html` — страница статьи
   - `frontend/blog/index.html` — листинг с пагинацией (9 статей/страница)
   - `frontend/sitemap.xml` — карта сайта
4. Крон: каждый день в 03:10
5. Изображения: JPG/PNG в `frontend/images/blog/` автоконвертируются в WebP

### Создание статьи

```bash
ssh backup8t 'sqlite3 /home/backup/upgrade/data/sqlite/booking.db "
INSERT INTO articles (slug, title, meta_description, category_id, body_html, is_published, sort_order, published_at)
VALUES (
    \"my-article-slug\",
    \"Заголовок статьи\",
    \"Мета-описание для SEO (до 160 символов)\",
    1,
    \"<p>HTML-контент статьи.</p><h2>Подзаголовок</h2><p>Текст...</p>\",
    1,
    0,
    datetime(\"now\")
);
"'
```

### Поля статьи

| Поле | Тип | Обязательное | Описание |
|------|-----|:---:|----------|
| `slug` | string | да | URL-slug (уникальный): `my-article` → `/blog/my-article.html` |
| `title` | string | да | Заголовок |
| `meta_description` | string | — | SEO-описание (до 160 символов) |
| `category_id` | int | — | FK на `categories.id` |
| `body_html` | string | да | HTML-контент статьи |
| `image_url` | string | — | URL обложки (или автоопределение по slug, см. ниже) |
| `is_published` | int | — | 1 = опубликована, 0 = черновик (default: 0) |
| `sort_order` | int | — | Порядок (больше = выше в списке, default: 0) |
| `published_at` | string | — | Дата публикации `YYYY-MM-DD HH:MM:SS` |

### Категории (предзаполнены)

| id | slug | name |
|----|------|------|
| 1 | procedures | Процедуры |
| 2 | body-care | Уход за телом |
| 3 | results | Результаты |
| 4 | faq | Ответы на вопросы |
| 5 | news | Новости |

### Изображения статей

Приоритет выбора обложки:
1. `frontend/images/blog/{slug}.webp` — автоконвертированный WebP
2. `frontend/images/blog/{slug}.jpg` (или `.png`) — автоконвертируется в WebP при рендере
3. Значение поля `image_url` из БД
4. Fallback: `/logo/logo.svg`

Чтобы добавить обложку:
```bash
# Скопировать изображение на сервер
scp my-image.jpg backup8t:/home/backup/upgrade/frontend/images/blog/my-article-slug.jpg
```
Рендерер автоконвертирует в WebP при следующем запуске.

### Ручной запуск рендера

```bash
# Блог
ssh backup8t 'cd /home/backup/upgrade && PYTHONPATH=/home/backup/upgrade venv/bin/python -m backend.app.services.ssg.renderer'

# Промо
ssh backup8t 'cd /home/backup/upgrade && PYTHONPATH=/home/backup/upgrade venv/bin/python -m backend.app.services.ssg.render_promo'
```

### Жизненный цикл статьи

```
INSERT в articles (is_published=1) → крон 03:10 (или ручной запуск) → HTML в frontend/blog/
                                                                     → sitemap.xml обновлён
                                                                     → blog/index.html обновлён
```

---

## Крон-расписание (продакшен)

| Время | Задача | Команда |
|-------|--------|---------|
| 03:00 | Рендер промо → `index.html` | `python -m backend.app.services.ssg.render_promo` |
| 03:10 | Рендер блога → `frontend/blog/` + `sitemap.xml` | `python -m backend.app.services.ssg.renderer` |
| каждый час | Проверка вебхука | `webhook.sh` |

## Важно

- Промо: **только через API** (`curl` / `urllib`), не через `sqlite3` напрямую
- Статьи: через `sqlite3` (CRUD API для статей не реализован)
- После изменения промо рендер срабатывает мгновенно; для блога — ждать крон или запустить вручную
- Промо с истёкшим `end_date` убираются автоматически при следующем рендере (крон 03:00)
- `PYTHONPATH=/home/backup/upgrade` обязателен при ручном запуске рендеров
