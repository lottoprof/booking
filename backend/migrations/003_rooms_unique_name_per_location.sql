-- 004_rooms_unique_name_per_location.sql
-- Уникальность названия комнаты в рамках локации

-- 1. Проверка на дубликаты (для ручной проверки перед применением)
-- Если запрос вернёт строки — миграцию применять НЕЛЬЗЯ
-- SELECT location_id, name, COUNT(*)
-- FROM rooms
-- GROUP BY location_id, name
-- HAVING COUNT(*) > 1;

-- 2. Добавляем составное ограничение уникальности
CREATE UNIQUE INDEX IF NOT EXISTS uq_rooms_location_name
ON rooms (location_id, name);

-- 3. Фиксируем версию миграции
INSERT INTO schema_migrations (version)
VALUES (4);
