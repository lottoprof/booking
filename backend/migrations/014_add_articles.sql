-- Blog: categories and articles tables

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    meta_description TEXT,
    category_id INTEGER REFERENCES categories(id),
    body_html TEXT NOT NULL,
    image_url TEXT,
    is_published INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    published_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Initial categories
INSERT INTO categories (slug, name, sort_order) VALUES ('lpg', 'LPG-массаж', 1);
INSERT INTO categories (slug, name, sort_order) VALUES ('pressotherapy', 'Прессотерапия', 2);
INSERT INTO categories (slug, name, sort_order) VALUES ('body-care', 'Уход за телом', 3);
INSERT INTO categories (slug, name, sort_order) VALUES ('results', 'Результаты', 4);
INSERT INTO categories (slug, name, sort_order) VALUES ('faq', 'Ответы на вопросы', 5);
