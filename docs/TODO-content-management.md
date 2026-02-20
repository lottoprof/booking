# TODO: Управление контентом (блог)

**Статус:** Ожидает
**Приоритет:** Средний

---

## Текущий процесс (ручной)

1. Написать статью (body_html)
2. `scp photo.jpg swertefun:~/booking/frontend/images/blog/{slug}.jpg`
3. `curl -X POST backend:8000/articles/ -d '{...}'` (или sqlite3)
4. `python3 -m backend.app.services.ssg.renderer` — конвертит JPG→WebP + генерит HTML

## Целевой процесс (API)

### 1. CRUD API для статей

**Роутер:** `backend/app/routers/articles.py`

- `GET /articles/` — список (с пагинацией, фильтр по category_id, is_published)
- `GET /articles/{id}` — одна статья
- `POST /articles/` — создать + trigger SSG render
- `PATCH /articles/{id}` — обновить + trigger SSG render
- `DELETE /articles/{id}` — удалить + trigger SSG render

### 2. Upload картинок

**Эндпоинт:** `POST /articles/{id}/image`
- Multipart upload JPG/PNG
- Сохранение: `frontend/images/blog/{slug}.jpg`
- Конвертация в WebP (Pillow) — автоматически при рендере
- Обновление `articles.image_url`

### 3. CRUD API для категорий

**Роутер:** `backend/app/routers/categories.py`
- Стандартный CRUD, сидирование из миграции

### 4. Админ-панель (бот или web)

- Создание/редактирование статей
- Превью перед публикацией
- Управление категориями
