# render_promo.py — Точки рендера в index.html

Три фрагмента генерируются из таблицы `promotions`.
При **0 активных промо** — все три удаляются целиком.

---

## Точка 1 — Offer Schema (ld+json)

### Координаты

```
Строки 86–128
Между: </script> (конец FAQ schema, строка 84)
И:     <!-- Fonts --> (строка 130)
```

### Маркеры (текущие)

```html
<!-- Structured Data: Offers
     SSG: regenerated from promotions table.
     If 0 active promos — this script tag is omitted. -->
<script type="application/ld+json">
  ...
</script>
```

### Предлагаемые SSG-маркеры

```html
<!-- SSG:OFFERS_SCHEMA_START -->
<script type="application/ld+json">...</script>
<!-- SSG:OFFERS_SCHEMA_END -->
```

### Что генерируется

```json
{
  "@context": "https://schema.org",
  "@type": "HealthAndBeautyBusiness",
  "name": "UPGRADE",
  "url": "https://upgradelpg.site",
  "hasOfferCatalog": {
    "@type": "OfferCatalog",
    "name": "Акции",
    "itemListElement": [ ...Offer[] ]
  }
}
```

Каждый Offer:

| Поле           | Источник DB        | Правила                                |
|----------------|--------------------|----------------------------------------|
| name           | title              | Как есть                               |
| description    | description        | Как есть                               |
| price          | price_new          | Строка без пробелов: `"1990"`, не null → включаем |
| priceCurrency  | —                  | Всегда `"RUB"`                         |
| validThrough   | end_date           | ISO 8601 date. **NULL → поле опускается** |
| url            | cta_url            | Абсолютный: `https://upgradelpg.site` + cta_url |

### Edge cases

- **0 промо** → весь блок `<!-- SSG:OFFERS_SCHEMA_START -->...<!-- SSG:OFFERS_SCHEMA_END -->` → пустая строка
- **price_new = NULL** → поле `price` опускается в Offer (дарственные промо)
- **end_date = NULL** → поле `validThrough` опускается (бессрочные)
- JSON должен быть валидным (без trailing commas)

### Сложность

**Средняя.** Генерация JSON из списка dict'ов. Одна тонкость — условные поля (price, validThrough). `json.dumps` справляется нативно: формируем dict, пропуская None-поля, потом сериализуем.

---

## Точка 2 — Promo Section (HTML)

### Координаты

```
Строки 911–963
Между: </section> (конец SEO TEXT, строка 894 + пустая строка)
И:     <!-- ═══ SERVICES ═══ --> (строка 965)
```

### Предлагаемые SSG-маркеры

```html
<!-- SSG:PROMOS_SECTION_START -->
<section class="promos" id="promos">
  ...
</section>
<!-- SSG:PROMOS_SECTION_END -->
```

### Практическая модель

В таблице `promotions` может быть любое количество записей, но **активных — от 0 до 3**.
SQL-фильтр:

```sql
SELECT * FROM promotions
WHERE is_active = 1
  AND (end_date IS NULL OR end_date >= date('now'))
ORDER BY sort_order
```

Результат — список из 0–3 записей. Рендер работает с этим списком как есть:

| Результат | Поведение                                          |
|-----------|----------------------------------------------------|
| 0 записей | Все 3 точки рендера → пустая строка (удаляются)    |
| 1 запись  | 1 карточка. CSS `:has(> :last-child:nth-child(1))` → `max-width: 480px` |
| 2 записи  | 2 карточки. CSS `:has(> :last-child:nth-child(2))` → 2 колонки, `760px` |
| 3 записи  | 3 карточки. Дефолтный грид `repeat(3, 1fr)`        |

Типы badge (`sale` / `gift` / `new`) — это данные из БД, не логика рендера.
Рендер не знает про типы, он просто кладёт `badge_type` в CSS-класс.

Сезонность:
- **Сезон** — 1–3 активных промо, ротация по `is_active` и `end_date`
- **Межсезон** — 0 промо, секция исчезает целиком
- **Редко** — все 3 активны одновременно

### Что генерируется (при count ≥ 1)

```html
<section class="promos" id="promos">
  <div class="section-inner">
    <div class="section-label reveal">Спецпредложения</div>
    <h2 class="section-title reveal">Актуальные <em>акции</em></h2>

    <div class="promos-grid stagger reveal">
      <!-- 1–3 promo-card, по одной на каждый активный badge_type -->
    </div>
    <div class="promo-dots" id="promoDots"></div>
  </div>
</section>
```

Поля карточки:

| Элемент          | Источник DB   | Правила                                          |
|------------------|---------------|--------------------------------------------------|
| `.promo-badge`   | badge_type    | CSS-класс: `sale` / `gift` / `new`               |
| badge text       | badge_text    | Контент: «☆ Акция», «※ Подарок», «✧ Новинка»   |
| `h3`             | title         | Заголовок карточки                                |
| `.promo-card-desc` | description | 1–2 предложения                                  |
| `.promo-price-new` | price_new   | Форматирование: `3 700 ₽` (с пробелом-разрядом) |
| `.promo-price-old` | price_old   | Зачёркнутая цена                                 |
| `.promo-deadline`  | deadline    | Текст: «Действует до **31 марта**» или «Постоянное предложение» |
| `.promo-cta`     | cta_text, cta_url | Кнопка-ссылка                                |

### Edge cases

- **0 промо** → весь блок `<!-- SSG:PROMOS_SECTION_START -->...<!-- SSG:PROMOS_SECTION_END -->` → пустая строка
- **price_new = NULL** → скрыть `.promo-price` целиком
- **price_old = NULL** → скрыть `.promo-price-old` (нет перечёркнутой цены)
- **end_date = NULL** → «Постоянное предложение» (без `<strong>`)
- **end_date есть** → «Действует до <strong>{{deadline}}</strong>»
- `.promo-dots` — контейнер для JS мобильных dot-индикаторов, всегда пустой в HTML

### Форматирование цены

```python
def format_price(value: int) -> str:
    """1990 → '1 990 ₽', 23000 → '23 000 ₽'"""
    return f"{value:,}".replace(",", " ") + " ₽"
```

### Сложность

**Низкая.** Итерация по 0–3 записям из SQL, одинаковый HTML-шаблон карточки для каждой. Условная логика только в price/deadline внутри карточки.

---

## Точка 3 — Promo Bar

### Координаты (НОВЫЙ ЭЛЕМЕНТ)

```
Вставка: между <body> (строка 798) и <!-- ═══ NAVIGATION ═══ --> (строка 800)
```

### Предлагаемые SSG-маркеры

```html
<!-- SSG:PROMO_BAR_START -->
<div class="promo-bar">...</div>
<!-- SSG:PROMO_BAR_END -->
```

### Что генерируется (при count ≥ 1)

```html
<div class="promo-bar">
  <div class="promo-bar-inner">
    <span class="promo-bar-text">{{badge_text}} {{title}} — <strong>{{deadline}}</strong></span>
    <a href="{{cta_url}}" class="promo-bar-link">Подробнее →</a>
  </div>
</div>
```

Источник: **первая** промо по `sort_order` из активных.

### Edge cases

- **0 промо** → весь блок `<!-- SSG:PROMO_BAR_START -->...<!-- SSG:PROMO_BAR_END -->` → пустая строка
- **Nav смещение**: `.nav { top: 0 }` → при наличии promo-bar нужен `top: <bar-height>`. Два варианта:
  - A) CSS `:has(.promo-bar)` → `body:has(> .promo-bar) .nav { top: 36px }`
  - B) JS: если `.promo-bar` существует, добавить offset
  - **Рекомендация:** вариант A (CSS-only, консистентно с подходом promos-grid)
- **Длинный текст** — нужен `overflow: hidden; text-overflow: ellipsis; white-space: nowrap` или обрезка на этапе рендера

### CSS (новое, нужно добавить в shared.css)

```css
/* ═══ PROMO BAR ═══ */
.promo-bar {
  background: var(--teal);
  color: #fff;
  font-size: 0.78rem;
  font-weight: 500;
  text-align: center;
  padding: 8px 1rem;
  letter-spacing: 0.02em;
}
.promo-bar-inner {
  max-width: 1120px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
}
.promo-bar-link {
  color: #fff;
  text-decoration: underline;
  text-underline-offset: 2px;
  font-weight: 600;
  white-space: nowrap;
}

/* Nav offset when promo-bar present */
body:has(> .promo-bar) .nav { top: 36px; }
body:has(> .promo-bar) .mobile-menu { top: 36px; }

@media (max-width: 768px) {
  .promo-bar { font-size: 0.7rem; padding: 6px 0.75rem; }
  .promo-bar-inner { gap: 0.5rem; }
  body:has(> .promo-bar) .nav { top: 32px; }
}
```

### Сложность

**Низкая.** Одна промо, линейная подстановка 3–4 полей. Но требует: нового маркера в HTML + нового CSS-блока.

---

## Сводная карта

```
index.html (1309 строк)

<head>
  ├── LocalBusiness schema        (строки 21–42)  — СТАТИКА, не трогаем
  ├── FAQPage schema              (строки 44–84)  — СТАТИКА, не трогаем
  ├── ★ ТОЧКА 1: Offer schema    (строки 86–128) — SSG: 0 промо → удалить
  ├── Fonts + CSS                 (строки 130+)   — СТАТИКА
  └── <style>...</style>          (inline styles)  — СТАТИКА
</head>
<body>
  ├── ★ ТОЧКА 3: Promo bar       (НОВЫЙ, перед nav) — SSG: 0 промо → удалить
  ├── <nav>                       (строки 801–821) — СТАТИКА
  ├── Mobile menu                 (строки 823–832) — СТАТИКА
  ├── Hero                        (строки 834–849) — СТАТИКА
  ├── About                       (строки 851–894) — СТАТИКА
  ├── SEO Text                    (строки 896–909) — СТАТИКА
  ├── ★ ТОЧКА 2: Promos section  (строки 911–963) — SSG: 0 промо → удалить
  ├── Services                    (строки 965–1033)— СТАТИКА
  ├── Specialists                 (строки 1035–1056)— СТАТИКА
  ├── FAQ                         (строки 1058–1159)— СТАТИКА
  ├── CTA Bottom                  (строки 1161–1170)— СТАТИКА
  ├── Footer                      (строки 1172–1202)— СТАТИКА
  └── <script>                    (строки 1204–1305)— СТАТИКА (JS для dots безопасен)
</body>
```

---

## Инструменты

```
render_promo.py  → str.replace по SSG-маркерам (3 пары) + json.dumps для schema
render_blog.py   → regex-замена плейсхолдеров (уже работает)
render_sitemap.py → строковая конкатенация (уже работает)
```

Без внешних зависимостей. Только stdlib: `sqlite3`, `json`, `re`, `pathlib`.

`render_promo.py` — три функции-генератора (schema, section, bar) + одна функция-склейка по маркерам.
