-- 016_promotions.sql
-- Promotions table for SSG-rendered promo sections on index.html

CREATE TABLE IF NOT EXISTS promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    badge_type TEXT NOT NULL DEFAULT 'sale',
    badge_text TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    price_new INTEGER,
    price_old INTEGER,
    end_date TEXT,
    cta_text TEXT,
    cta_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Seed: 3 rows matching current mock data in index.html
INSERT INTO promotions (badge_type, badge_text, title, description, price_new, price_old, end_date, cta_text, cta_url, is_active, sort_order)
VALUES
    ('sale', '☆ Акция', 'Первый сеанс LPG — со скидкой', 'Попробуйте аппаратный массаж по специальной цене. Для новых клиентов студии.', 1990, 3000, '2026-03-31', 'Записаться →', '/book?service=lpg', 1, 1),
    ('gift', '※ Подарок', 'Курс 10 сеансов = 2 в подарок', 'Купите курс из 10 процедур LPG-массажа и получите 2 дополнительных сеанса бесплатно.', 23000, 30000, '2026-03-31', 'Подробнее →', '/book?service=lpg', 1, 2),
    ('new', '✧ Новинка', 'Прессотерапия + обёртывание', 'Комбинированная программа: лимфодренаж и детокс-обёртывание за один визит. Экономия 30 минут и 800 ₽.', 3700, 4500, NULL, 'Записаться →', '/book?service=pressotherapy', 1, 3);
