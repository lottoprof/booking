-- Таблица: organizations
CREATE TABLE organizations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE organizations IS 'Организации, владельцы локаций и пользователей.';
COMMENT ON COLUMN organizations.id IS 'Уникальный идентификатор организации.';
COMMENT ON COLUMN organizations.name IS 'Название организации.';
COMMENT ON COLUMN organizations.description IS 'Описание организации.';
COMMENT ON COLUMN organizations.created_at IS 'Дата создания записи.';


-- Таблица: roles
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

COMMENT ON TABLE roles IS 'Справочник ролей пользователей.';
COMMENT ON COLUMN roles.id IS 'Уникальный идентификатор роли.';
COMMENT ON COLUMN roles.name IS 'Название роли (admin, manager, staff, client).';

INSERT INTO roles (name) VALUES 
('admin'),
('manager'),
('staff'),
('client');


-- Таблица: users
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT,
    middle_name TEXT,
    email TEXT,
    phone TEXT,
    tg_id BIGINT, -- Telegram ID пользователя
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE users IS 'Пользователи системы (админы, менеджеры, сотрудники, клиенты).';
COMMENT ON COLUMN users.id IS 'Уникальный идентификатор пользователя.';
COMMENT ON COLUMN users.organization_id IS 'FK → organizations.id. Организация, к которой относится пользователь.';
COMMENT ON COLUMN users.username IS 'Уникальный логин для входа.';
COMMENT ON COLUMN users.password_hash IS 'Хэш пароля.';
COMMENT ON COLUMN users.first_name IS 'Имя пользователя.';
COMMENT ON COLUMN users.last_name IS 'Фамилия пользователя.';
COMMENT ON COLUMN users.middle_name IS 'Отчество пользователя.';
COMMENT ON COLUMN users.email IS 'Адрес электронной почты.';
COMMENT ON COLUMN users.phone IS 'Номер телефона.';
COMMENT ON COLUMN users.tg_id IS 'Telegram ID пользователя для интеграции с ботами.';
COMMENT ON COLUMN users.is_active IS 'Флаг активности учетной записи.';
COMMENT ON COLUMN users.created_at IS 'Дата создания записи.';
COMMENT ON COLUMN users.updated_at IS 'Дата последнего обновления записи.';


-- Таблица: locations
CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    country TEXT,
    region TEXT,
    city TEXT NOT NULL,
    street TEXT,
    house TEXT,
    building TEXT,
    office TEXT,
    postal_code TEXT,
    capacity INT NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT
);

COMMENT ON TABLE locations IS 'Справочник локаций (адреса, филиалы, отделения).';
COMMENT ON COLUMN locations.id IS 'Уникальный идентификатор локации.';
COMMENT ON COLUMN locations.name IS 'Название локации (например, Студия №1).';
COMMENT ON COLUMN locations.country IS 'Страна.';
COMMENT ON COLUMN locations.region IS 'Регион или область.';
COMMENT ON COLUMN locations.city IS 'Город.';
COMMENT ON COLUMN locations.street IS 'Улица.';
COMMENT ON COLUMN locations.house IS 'Номер дома.';
COMMENT ON COLUMN locations.building IS 'Корпус/строение (если есть).';
COMMENT ON COLUMN locations.office IS 'Офис/кабинет (если есть).';
COMMENT ON COLUMN locations.postal_code IS 'Почтовый индекс.';
COMMENT ON COLUMN locations.capacity IS 'Вместимость (количество клиентов/помещений по умолчанию).';
COMMENT ON COLUMN locations.is_active IS 'Флаг активности локации.';
COMMENT ON COLUMN locations.notes IS 'Заметки или дополнительные комментарии по локации.';


-- Таблица: workplaces
CREATE TABLE workplaces (
    id SERIAL PRIMARY KEY,
    location_id INT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('cabinet','chair','couch','massage_table','booth','device','other')),
    capacity INT NOT NULL DEFAULT 1,
    equipment TEXT,
    is_mobile BOOLEAN NOT NULL DEFAULT FALSE,
    display_order INT,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE workplaces IS 'Рабочие места (кабинет/кресло/кушетка/массажный стол и т.п.) внутри локации.';
COMMENT ON COLUMN workplaces.id IS 'Уникальный идентификатор рабочего места.';
COMMENT ON COLUMN workplaces.location_id IS 'FK → locations.id. Локация, где находится рабочее место.';
COMMENT ON COLUMN workplaces.name IS 'Человеко-читаемое имя места (например: "Кабинет 2", "Кресло #1").';
COMMENT ON COLUMN workplaces.type IS 'Тип рабочего места: cabinet, chair, couch, massage_table, booth, device, other.';
COMMENT ON COLUMN workplaces.capacity IS 'Сколько клиентов одновременно можно обслуживать на месте (обычно 1).';
COMMENT ON COLUMN workplaces.equipment IS 'Оборудование, доступное на месте (свободный текст).';
COMMENT ON COLUMN workplaces.is_mobile IS 'Флаг: место мобильное/переносное (TRUE) или стационарное (FALSE).';
COMMENT ON COLUMN workplaces.display_order IS 'Порядок сортировки при отображении в UI.';
COMMENT ON COLUMN workplaces.notes IS 'Дополнительные комментарии/ограничения по использованию.';
COMMENT ON COLUMN workplaces.is_active IS 'Флаг активности рабочего места.';


-- Таблица: location_schedules
CREATE TABLE location_schedules (
    id SERIAL PRIMARY KEY,
    location_id INT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TIME,
    end_time TIME,
    is_day_off BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(location_id, day_of_week)
);

COMMENT ON TABLE location_schedules IS 'Расписание работы локации по дням недели.';
COMMENT ON COLUMN location_schedules.location_id IS 'FK → locations.id. Локация.';
COMMENT ON COLUMN location_schedules.day_of_week IS 'День недели (0=Пн … 6=Вс, возможны несколько интервалов в день (например, вторник 9–12 и 15–19).';
COMMENT ON COLUMN location_schedules.start_time IS 'Время начала работы.';
COMMENT ON COLUMN location_schedules.end_time IS 'Время окончания работы.';
COMMENT ON COLUMN location_schedules.is_day_off IS 'Признак целого не рабочего дня.';


-- Таблица: user_roles
CREATE TABLE user_roles (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE CASCADE,
    UNIQUE(user_id, role_id, location_id)
);

COMMENT ON TABLE user_roles IS 'Привязка ролей к пользователям и (опционально) к локациям.';


-- Таблица: services
CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    duration_min INT NOT NULL,
    break_min INT NOT NULL DEFAULT 0,
    price NUMERIC(10,2) NOT NULL,
    color_code TEXT,
    min_age INT,
    max_age INT,
    is_package BOOLEAN NOT NULL DEFAULT FALSE,
    package_quantity INT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE services IS 'Справочник услуг (включая пакеты услуг).';
COMMENT ON COLUMN services.id IS 'Уникальный идентификатор услуги.';
COMMENT ON COLUMN services.name IS 'Название услуги или пакета.';
COMMENT ON COLUMN services.description IS 'Описание услуги или пакета.';
COMMENT ON COLUMN services.category IS 'Категория (например: диагностика, терапия, абонементы).';
COMMENT ON COLUMN services.duration_min IS 'Длительность услуги (в минутах). Для пакетов можно оставить NULL.';
COMMENT ON COLUMN services.break_min IS 'Перерыв после выполнения услуги (в минутах). Для пакетов можно оставить 0.';
COMMENT ON COLUMN services.price IS 'Цена услуги или полная цена пакета.';
COMMENT ON COLUMN services.color_code IS 'Цветовая метка для интерфейса.';
COMMENT ON COLUMN services.min_age IS 'Минимальный возраст клиента.';
COMMENT ON COLUMN services.max_age IS 'Максимальный возраст клиента.';
COMMENT ON COLUMN services.is_package IS 'Флаг: TRUE = это пакет услуг.';
COMMENT ON COLUMN services.package_quantity IS 'Количество услуг, входящих в пакет (актуально только если is_package = TRUE).';
COMMENT ON COLUMN services.is_active IS 'Флаг активности услуги/пакета.';


-- Таблица: service_packages
CREATE TABLE service_packages (
    id SERIAL PRIMARY KEY,
    organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    quantity INT NOT NULL,
    package_price NUMERIC(10,2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE service_packages IS 'Пакеты услуг со скидкой (например: 5 массажей по цене 4).';
COMMENT ON COLUMN service_packages.id IS 'Уникальный идентификатор пакета.';
COMMENT ON COLUMN service_packages.name IS 'Название пакета.';
COMMENT ON COLUMN service_packages.description IS 'Описание пакета услуг.';
COMMENT ON COLUMN service_packages.service_id IS 'FK → services.id. Услуга, на которую распространяется пакет.';
COMMENT ON COLUMN service_packages.quantity IS 'Количество услуг в пакете.';
COMMENT ON COLUMN service_packages.package_price IS 'Общая цена пакета со скидкой.';
COMMENT ON COLUMN service_packages.is_active IS 'Флаг активности пакета.';


-- Таблица: workplace_services
CREATE TABLE workplace_services (
    id SERIAL PRIMARY KEY,
    workplace_id INT NOT NULL REFERENCES workplaces(id) ON DELETE CASCADE,
    service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    UNIQUE(workplace_id, service_id)
);

COMMENT ON TABLE workplace_services IS 'Привязка услуг к рабочим местам.';
COMMENT ON COLUMN workplace_services.id IS 'Уникальный идентификатор записи.';
COMMENT ON COLUMN workplace_services.workplace_id IS 'FK → workplaces.id. Рабочее место.';
COMMENT ON COLUMN workplace_services.service_id IS 'FK → services.id. Услуга.';
COMMENT ON COLUMN workplace_services.is_active IS 'Флаг активности услуги в данном рабочем месте.';
COMMENT ON COLUMN workplace_services.notes IS 'Комментарии и ограничения (например: кабинет оснащён только частично).';


-- Таблица: specialists
CREATE TABLE specialists (
    id SERIAL PRIMARY KEY,
    organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    iname TEXT,
    description TEXT,
    photo_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE specialists IS 'Справочник специалистов. Расширение users';
COMMENT ON COLUMN specialists.id IS 'Уникальный идентификатор специалиста.';
COMMENT ON COLUMN specialists.iname IS 'Отображаемое имя (ник) для сайта/бота.';
COMMENT ON COLUMN specialists.description IS 'Заметки по специалисту (особенности, комментарии).';
COMMENT ON COLUMN specialists.is_active IS 'Флаг активности специалиста.';


-- Таблица: specialist_services
CREATE TABLE specialist_services (
    service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    specialist_id INT NOT NULL REFERENCES specialists(id) ON DELETE CASCADE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    UNIQUE(service_id, specialist_id)
);

COMMENT ON TABLE specialist_services IS 'Компетенции специалистов (какие услуги они могут оказывать).';
COMMENT ON COLUMN specialist_services.service_id IS 'FK → services.id. Услуга.';
COMMENT ON COLUMN specialist_services.specialist_id IS 'FK → specialists.id. Специалист.';
COMMENT ON COLUMN specialist_services.is_default IS 'Флаг: специалист основной для данной услуги.';
COMMENT ON COLUMN specialist_services.is_active IS 'Флаг активности компетенции.';
COMMENT ON COLUMN specialist_services.notes IS 'Комментарии к компетенции (условия, ограничения, примечания).';


-- Таблица: specialist_schedules
CREATE TABLE specialist_schedules (
    id SERIAL PRIMARY KEY,
    specialist_id INT NOT NULL REFERENCES specialists(id) ON DELETE CASCADE,
    location_id INT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    workplace_id INT REFERENCES workplaces(id) ON DELETE CASCADE,
    day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TIME,
    end_time TIME,
    is_day_off BOOLEAN NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE specialist_schedules IS 'Базовое расписание работы специалиста по дням недели, локациям и рабочим местам (поддерживает несколько интервалов в день).';
COMMENT ON COLUMN specialist_schedules.id IS 'Уникальный идентификатор записи расписания.';
COMMENT ON COLUMN specialist_schedules.specialist_id IS 'FK → specialists.id. Специалист.';
COMMENT ON COLUMN specialist_schedules.location_id IS 'FK → locations.id. Локация, где работает специалист.';
COMMENT ON COLUMN specialist_schedules.workplace_id IS 'FK → workplaces.id. Конкретное рабочее место (если требуется).';
COMMENT ON COLUMN specialist_schedules.day_of_week IS 'День недели (0=Пн … 6=Вс).';
COMMENT ON COLUMN specialist_schedules.start_time IS 'Время начала рабочего интервала. NULL, если выходной.';
COMMENT ON COLUMN specialist_schedules.end_time IS 'Время окончания рабочего интервала. NULL, если выходной.';
COMMENT ON COLUMN specialist_schedules.is_day_off IS 'Флаг: специалист полностью не работает в этот день.';


-- Таблица: breaks
CREATE TABLE breaks (
    id SERIAL PRIMARY KEY,
    specialist_id INT NOT NULL REFERENCES specialists(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    reason TEXT
);

COMMENT ON TABLE breaks IS 'Индивидуальные перерывы специалистов (корректировка графика).';
COMMENT ON COLUMN breaks.specialist_id IS 'FK → specialists.id. Специалист.';
COMMENT ON COLUMN breaks.date IS 'Дата перерыва.';
COMMENT ON COLUMN breaks.start_time IS 'Начало перерыва.';
COMMENT ON COLUMN breaks.end_time IS 'Окончание перерыва.';
COMMENT ON COLUMN breaks.reason IS 'Причина перерыва (обед, личное, вызов).';


-- Таблица: holidays
CREATE TABLE holidays (
    id SERIAL PRIMARY KEY,
    location_id INT REFERENCES locations(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    is_working BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT
);

COMMENT ON TABLE holidays IS 'Праздничные/особые дни для локаций.';
COMMENT ON COLUMN holidays.location_id IS 'FK → locations.id. Локация (NULL = общий праздник).';
COMMENT ON COLUMN holidays.date IS 'Дата праздника/особого дня.';
COMMENT ON COLUMN holidays.is_working IS 'Флаг: работает ли локация в этот день.';
COMMENT ON COLUMN holidays.description IS 'Описание (например, Новый год).';


-- Таблица: clients
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    iname TEXT,
    birth_date DATE,
    gender TEXT CHECK (gender IN ('male','female','other')),
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE clients IS 'Справочник клиентов.';
COMMENT ON COLUMN clients.id IS 'Уникальный идентификатор клиента.';
COMMENT ON COLUMN clients.iname IS 'Отображаемое имя (ник) для сайта/бота.';
COMMENT ON COLUMN clients.birth_date IS 'Дата рождения клиента (для проверки возрастных ограничений).';
COMMENT ON COLUMN clients.gender IS 'Пол клиента (male/female/other).';
COMMENT ON COLUMN clients.notes IS 'Примечания о клиенте (комментарии, особенности).';
COMMENT ON COLUMN clients.is_active IS 'Флаг активности клиента.';


-- Таблица: client_discounts
CREATE TABLE client_discounts (
    id SERIAL PRIMARY KEY,
    client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
    valid_from DATE,
    valid_to DATE,
    description TEXT
);

COMMENT ON TABLE client_discounts IS 'Персональные скидки клиентов.';
COMMENT ON COLUMN client_discounts.id IS 'Уникальный идентификатор скидки.';
COMMENT ON COLUMN client_discounts.client_id IS 'FK → clients.id. Клиент.';
COMMENT ON COLUMN client_discounts.discount_percent IS 'Скидка в процентах.';
COMMENT ON COLUMN client_discounts.valid_from IS 'Дата начала действия скидки.';
COMMENT ON COLUMN client_discounts.valid_to IS 'Дата окончания действия скидки.';
COMMENT ON COLUMN client_discounts.description IS 'Описание скидки (например: постоянный клиент, акция).';


-- Таблица: client_packages
CREATE TABLE client_packages (
    id SERIAL PRIMARY KEY,
    client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    package_id INT NOT NULL REFERENCES service_packages(id) ON DELETE CASCADE,
    used_quantity INT NOT NULL DEFAULT 0,
    purchased_at TIMESTAMP NOT NULL DEFAULT now(),
    valid_to DATE,
    notes TEXT
);

COMMENT ON TABLE client_packages IS 'Купленные клиентами пакеты услуг.';
COMMENT ON COLUMN client_packages.id IS 'Уникальный идентификатор покупки пакета.';
COMMENT ON COLUMN client_packages.used_quantity IS 'Сколько уже использовано.';
COMMENT ON COLUMN client_packages.purchased_at IS 'Дата покупки пакета.';
COMMENT ON COLUMN client_packages.valid_to IS 'Дата окончания действия пакета (если ограничен по сроку).';
COMMENT ON COLUMN client_packages.notes IS 'Примечания к пакету.';


-- Таблица: client_wallets
CREATE TABLE client_wallets (
    id SERIAL PRIMARY KEY,
    client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    balance NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'RUB',
    is_blocked BOOLEAN NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE client_wallets IS 'Кошельки клиентов.Текущий баланс';
COMMENT ON COLUMN client_wallets.balance IS 'Остаток средств на счету клиента.';


-- Таблица: appointments
CREATE TABLE appointments (
    id SERIAL PRIMARY KEY,
    organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    location_id INT NOT NULL REFERENCES locations(id),
    service_id INT NOT NULL REFERENCES services(id),
    workplace_id INT REFERENCES workplaces(id),
    client_user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    specialist_user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','cancelled','done')),
    final_price NUMERIC(10,2),
    notes TEXT,
    cancel_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

COMMENT ON TABLE appointments IS 'Записи клиентов на услуги.';
COMMENT ON COLUMN appointments.id IS 'Уникальный идентификатор записи.';
COMMENT ON COLUMN appointments.location_id IS 'FK → locations.id. Локация, где будет оказана услуга.';
COMMENT ON COLUMN appointments.service_id IS 'FK → services.id. Заказанная услуга.';
COMMENT ON COLUMN appointments.workplace_id IS 'FK → workplaces.id. Рабочее место, где будет оказана услуга.';
COMMENT ON COLUMN appointments.specialist_user_id IS 'FK → specialists.id. Специалист, который оказывает услугу.';
COMMENT ON COLUMN appointments.client_user_id IS 'FK → clients.id. Клиент, записанный на услугу.';
COMMENT ON COLUMN appointments.start_time IS 'Дата и время начала услуги.';
COMMENT ON COLUMN appointments.end_time IS 'Дата и время окончания услуги.';
COMMENT ON COLUMN appointments.status IS 'Статус записи (pending/confirmed/cancelled/done).';
COMMENT ON COLUMN appointments.final_price IS 'Фактическая цена услуги на момент бронирования.';
COMMENT ON COLUMN appointments.notes IS 'Комментарии администратора или клиента.';
COMMENT ON COLUMN appointments.cancel_reason IS 'Причина отмены записи (если применимо).';
COMMENT ON COLUMN appointments.created_at IS 'Время создания записи.';
COMMENT ON COLUMN appointments.updated_at IS 'Время последнего обновления записи.';


-- Таблица: appointment_discounts
CREATE TABLE appointment_discounts (
    id SERIAL PRIMARY KEY,
    appointment_id INT NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
    discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
    discount_reason TEXT
);

COMMENT ON TABLE appointment_discounts IS 'Фиксация скидок, применённых к конкретным записям.';
COMMENT ON COLUMN appointment_discounts.id IS 'Уникальный идентификатор записи скидки.';
COMMENT ON COLUMN appointment_discounts.appointment_id IS 'FK → appointments.id. Запись, к которой применена скидка.';
COMMENT ON COLUMN appointment_discounts.discount_percent IS 'Скидка в процентах.';
COMMENT ON COLUMN appointment_discounts.discount_reason IS 'Причина применения скидки (акция, персональная скидка и т.п.).';


-- Таблица: wallet_transactions
CREATE TABLE wallet_transactions (
    id SERIAL PRIMARY KEY,
    wallet_id INT NOT NULL REFERENCES client_wallets(id) ON DELETE CASCADE,
    appointment_id INT REFERENCES appointments(id) ON DELETE SET NULL,
    amount NUMERIC(12,2) NOT NULL,
    type TEXT NOT NULL DEFAULT 'payment'
        CHECK (type IN ('deposit','withdraw','payment','refund','correction')),
    description TEXT,
    created_by TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

COMMENT ON TABLE wallet_transactions IS 'Финансовые операции по клиентским кошелькам.';
COMMENT ON COLUMN wallet_transactions.id IS 'Уникальный идентификатор транзакции.';
COMMENT ON COLUMN wallet_transactions.wallet_id IS 'FK → client_wallets.id. Кошелек клиента.';
COMMENT ON COLUMN wallet_transactions.appointment_id IS 'FK → appointments.id. Запись, с которой связана транзакция.';
COMMENT ON COLUMN wallet_transactions.amount IS 'Сумма транзакции (положительная = пополнение, отрицательная = списание).';
COMMENT ON COLUMN wallet_transactions.type IS 'Тип транзакции: deposit, withdraw, payment, refund, correction.';
COMMENT ON COLUMN wallet_transactions.description IS 'Описание транзакции.';
COMMENT ON COLUMN wallet_transactions.created_by IS 'Кем создана транзакция (system, admin, client).';
COMMENT ON COLUMN wallet_transactions.created_at IS 'Дата и время транзакции.';


-- Таблица: push_subscriptions
CREATE TABLE push_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    auth TEXT,
    p256dh TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

COMMENT ON TABLE push_subscriptions IS 'Подписки клиентов на WebPush (VAPID).';
COMMENT ON COLUMN push_subscriptions.user_id IS 'FK → users.id. Пользователь, связанный с подпиской.';
COMMENT ON COLUMN push_subscriptions.endpoint IS 'Уникальный endpoint браузера для Web Push.';
COMMENT ON COLUMN push_subscriptions.auth IS 'Auth secret клиента для Web Push.';
COMMENT ON COLUMN push_subscriptions.p256dh IS 'Публичный ключ клиента для шифрования сообщений (Base64).';
COMMENT ON COLUMN push_subscriptions.created_at IS 'Дата добавления подписки.';

