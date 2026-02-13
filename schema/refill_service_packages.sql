-- Refill service_packages: 7 services × 3 qty + 10 combos × 3 qty = 51 rows
-- Description rule:
--   single service → services.description
--   combo          → join of service package-names via ", "
-- WARNING: client_packages id=2 references package_id=2 (open, 0 used) — will become dangling

BEGIN TRANSACTION;

DELETE FROM service_packages;
DELETE FROM sqlite_sequence WHERE name='service_packages';

-- ═══════════════════════════════════════════
-- SINGLE SERVICES (7 × 3 = 21 rows)
-- description = services.description
-- show_on_booking=1 for qty=1, show_on_pricing=1 for all
-- ═══════════════════════════════════════════

-- 1. LPG (service_id=1, services.description="по костюму")
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'LPG', 'по костюму', '[{"service_id":1,"quantity":1}]', 1, 1),
  (1, 'LPG', 'по костюму', '[{"service_id":1,"quantity":5}]', 1, 0),
  (1, 'LPG', 'по костюму', '[{"service_id":1,"quantity":10}]', 1, 0);

-- 2. Сфера (костюм) (service_id=2, services.description="по костюму")
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Сфера (костюм)', 'по костюму', '[{"service_id":2,"quantity":1}]', 1, 1),
  (1, 'Сфера (костюм)', 'по костюму', '[{"service_id":2,"quantity":5}]', 1, 0),
  (1, 'Сфера (костюм)', 'по костюму', '[{"service_id":2,"quantity":10}]', 1, 0);

-- 3. Сфера (масло) (service_id=3, services.description="по маслу")
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Сфера (масло)', 'по маслу', '[{"service_id":3,"quantity":1}]', 1, 1),
  (1, 'Сфера (масло)', 'по маслу', '[{"service_id":3,"quantity":5}]', 1, 0),
  (1, 'Сфера (масло)', 'по маслу', '[{"service_id":3,"quantity":10}]', 1, 0);

-- 4. Прессотерапия (service_id=4, services.description="живот+ноги")
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Прессотерапия', 'живот+ноги', '[{"service_id":4,"quantity":1}]', 1, 1),
  (1, 'Прессотерапия', 'живот+ноги', '[{"service_id":4,"quantity":5}]', 1, 0),
  (1, 'Прессотерапия', 'живот+ноги', '[{"service_id":4,"quantity":10}]', 1, 0);

-- 5. Обёртывание (service_id=5, services.description="Обёртывание")
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Обёртывание', 'Обёртывание', '[{"service_id":5,"quantity":1}]', 1, 1),
  (1, 'Обёртывание', 'Обёртывание', '[{"service_id":5,"quantity":5}]', 1, 0),
  (1, 'Обёртывание', 'Обёртывание', '[{"service_id":5,"quantity":10}]', 1, 0);

-- 6. Indiba живот (service_id=6, services.description="зона-живот")
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Indiba живот', 'зона-живот', '[{"service_id":6,"quantity":1}]', 1, 1),
  (1, 'Indiba живот', 'зона-живот', '[{"service_id":6,"quantity":5}]', 1, 0),
  (1, 'Indiba живот', 'зона-живот', '[{"service_id":6,"quantity":10}]', 1, 0);

-- 7. Indiba ягодицы (service_id=7, services.description="зона-ягодицы")
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Indiba ягодицы', 'зона-ягодицы', '[{"service_id":7,"quantity":1}]', 1, 1),
  (1, 'Indiba ягодицы', 'зона-ягодицы', '[{"service_id":7,"quantity":5}]', 1, 0),
  (1, 'Indiba ягодицы', 'зона-ягодицы', '[{"service_id":7,"quantity":10}]', 1, 0);

-- ═══════════════════════════════════════════
-- COMBO PACKS (10 × 3 = 30 rows)
-- description = join of service package-names via ", "
-- ═══════════════════════════════════════════

-- Pack1: services 6+4
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Pack1', 'Indiba живот, Прессотерапия', '[{"service_id":6,"quantity":1},{"service_id":4,"quantity":1}]', 1, 1),
  (1, 'Pack1', 'Indiba живот, Прессотерапия', '[{"service_id":6,"quantity":5},{"service_id":4,"quantity":5}]', 1, 0),
  (1, 'Pack1', 'Indiba живот, Прессотерапия', '[{"service_id":6,"quantity":10},{"service_id":4,"quantity":10}]', 1, 0);

-- Pack2: services 6+1
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Pack2', 'Indiba живот, LPG', '[{"service_id":6,"quantity":1},{"service_id":1,"quantity":1}]', 1, 1),
  (1, 'Pack2', 'Indiba живот, LPG', '[{"service_id":6,"quantity":5},{"service_id":1,"quantity":5}]', 1, 0),
  (1, 'Pack2', 'Indiba живот, LPG', '[{"service_id":6,"quantity":10},{"service_id":1,"quantity":10}]', 1, 0);

-- Pack3: services 6+7+1
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Pack3', 'Indiba живот, Indiba ягодицы, LPG', '[{"service_id":6,"quantity":1},{"service_id":7,"quantity":1},{"service_id":1,"quantity":1}]', 1, 1),
  (1, 'Pack3', 'Indiba живот, Indiba ягодицы, LPG', '[{"service_id":6,"quantity":5},{"service_id":7,"quantity":5},{"service_id":1,"quantity":5}]', 1, 0),
  (1, 'Pack3', 'Indiba живот, Indiba ягодицы, LPG', '[{"service_id":6,"quantity":10},{"service_id":7,"quantity":10},{"service_id":1,"quantity":10}]', 1, 0);

-- Pack4: services 7+1
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Pack4', 'Indiba ягодицы, LPG', '[{"service_id":7,"quantity":1},{"service_id":1,"quantity":1}]', 1, 1),
  (1, 'Pack4', 'Indiba ягодицы, LPG', '[{"service_id":7,"quantity":5},{"service_id":1,"quantity":5}]', 1, 0),
  (1, 'Pack4', 'Indiba ягодицы, LPG', '[{"service_id":7,"quantity":10},{"service_id":1,"quantity":10}]', 1, 0);

-- Pack5: services 6+1+5
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Pack5', 'Indiba живот, LPG, Обёртывание', '[{"service_id":6,"quantity":1},{"service_id":1,"quantity":1},{"service_id":5,"quantity":1}]', 1, 1),
  (1, 'Pack5', 'Indiba живот, LPG, Обёртывание', '[{"service_id":6,"quantity":5},{"service_id":1,"quantity":5},{"service_id":5,"quantity":5}]', 1, 0),
  (1, 'Pack5', 'Indiba живот, LPG, Обёртывание', '[{"service_id":6,"quantity":10},{"service_id":1,"quantity":10},{"service_id":5,"quantity":10}]', 1, 0);

-- Pack6: services 7+1+5
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Pack6', 'Indiba ягодицы, LPG, Обёртывание', '[{"service_id":7,"quantity":1},{"service_id":1,"quantity":1},{"service_id":5,"quantity":1}]', 1, 1),
  (1, 'Pack6', 'Indiba ягодицы, LPG, Обёртывание', '[{"service_id":7,"quantity":5},{"service_id":1,"quantity":5},{"service_id":5,"quantity":5}]', 1, 0),
  (1, 'Pack6', 'Indiba ягодицы, LPG, Обёртывание', '[{"service_id":7,"quantity":10},{"service_id":1,"quantity":10},{"service_id":5,"quantity":10}]', 1, 0);

-- Pack7: services 7+4+1+5
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Pack7', 'Indiba ягодицы, Прессотерапия, LPG, Обёртывание', '[{"service_id":7,"quantity":1},{"service_id":4,"quantity":1},{"service_id":1,"quantity":1},{"service_id":5,"quantity":1}]', 1, 1),
  (1, 'Pack7', 'Indiba ягодицы, Прессотерапия, LPG, Обёртывание', '[{"service_id":7,"quantity":5},{"service_id":4,"quantity":5},{"service_id":1,"quantity":5},{"service_id":5,"quantity":5}]', 1, 0),
  (1, 'Pack7', 'Indiba ягодицы, Прессотерапия, LPG, Обёртывание', '[{"service_id":7,"quantity":10},{"service_id":4,"quantity":10},{"service_id":1,"quantity":10},{"service_id":5,"quantity":10}]', 1, 0);

-- Pack8: services 5+1
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Pack8', 'Обёртывание, LPG', '[{"service_id":5,"quantity":1},{"service_id":1,"quantity":1}]', 1, 1),
  (1, 'Pack8', 'Обёртывание, LPG', '[{"service_id":5,"quantity":5},{"service_id":1,"quantity":5}]', 1, 0),
  (1, 'Pack8', 'Обёртывание, LPG', '[{"service_id":5,"quantity":10},{"service_id":1,"quantity":10}]', 1, 0);

-- Pack9: services 5+2
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Pack9', 'Обёртывание, Сфера (костюм)', '[{"service_id":5,"quantity":1},{"service_id":2,"quantity":1}]', 1, 1),
  (1, 'Pack9', 'Обёртывание, Сфера (костюм)', '[{"service_id":5,"quantity":5},{"service_id":2,"quantity":5}]', 1, 0),
  (1, 'Pack9', 'Обёртывание, Сфера (костюм)', '[{"service_id":5,"quantity":10},{"service_id":2,"quantity":10}]', 1, 0);

-- Pack10: services 5+4
INSERT INTO service_packages (company_id, name, description, package_items, show_on_pricing, show_on_booking) VALUES
  (1, 'Pack10', 'Обёртывание, Прессотерапия', '[{"service_id":5,"quantity":1},{"service_id":4,"quantity":1}]', 1, 1),
  (1, 'Pack10', 'Обёртывание, Прессотерапия', '[{"service_id":5,"quantity":5},{"service_id":4,"quantity":5}]', 1, 0),
  (1, 'Pack10', 'Обёртывание, Прессотерапия', '[{"service_id":5,"quantity":10},{"service_id":4,"quantity":10}]', 1, 0);

COMMIT;
