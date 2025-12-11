CREATE TABLE company (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE company IS 'Компания-владелец локаций и пользователей.';
COMMENT ON COLUMN company.id IS 'Уникальный идентификатор компании.';
COMMENT ON COLUMN company.name IS 'Название компании.';
COMMENT ON COLUMN company.description IS 'Описание компании.';
COMMENT ON COLUMN company.created_at IS 'Дата создания записи.';

CREATE TABLE locations (
y    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    country TEXT,
    region TEXT,
    city TEXT NOT NULL,
    street TEXT,
    house TEXT,
    building TEXT,
    office TEXT,
    postal_code TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    work_schedule JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT
);

COMMENT ON TABLE locations IS 'Справочник локаций (адреса, филиалы, студии).';
COMMENT ON COLUMN locations.id IS 'Уникальный идентификатор локации.';
COMMENT ON COLUMN locations.company_id IS 'FK → company.id.';
COMMENT ON COLUMN locations.name IS 'Название локации.';
COMMENT ON COLUMN locations.country IS 'Страна.';
COMMENT ON COLUMN locations.region IS 'Регион или область.';
COMMENT ON COLUMN locations.city IS 'Город.';
COMMENT ON COLUMN locations.street IS 'Улица.';
COMMENT ON COLUMN locations.house IS 'Номер дома.';
COMMENT ON COLUMN locations.building IS 'Корпус или строение.';
COMMENT ON COLUMN locations.office IS 'Офис или кабинет.';
COMMENT ON COLUMN locations.postal_code IS 'Почтовый индекс.';
COMMENT ON COLUMN locations.is_active IS 'Флаг активности.';
COMMENT ON COLUMN locations.work_schedule IS 'График работы локации в формате JSON: интервалы по дням недели.';
COMMENT ON COLUMN locations.notes IS 'Дополнительные комментарии.';

CREATE TABLE rooms (
    id SERIAL PRIMARY KEY,
    location_id INT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    display_order INT,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE rooms IS 'Кабинеты / комнаты внутри локации.';
COMMENT ON COLUMN rooms.id IS 'Уникальный идентификатор комнаты.';
COMMENT ON COLUMN rooms.location_id IS 'FK → locations.id. Локация, к которой относится комната.';
COMMENT ON COLUMN rooms.name IS 'Название комнаты (например: Кабинет №1).';
COMMENT ON COLUMN rooms.display_order IS 'Порядок отображения в UI.';
COMMENT ON COLUMN rooms.notes IS 'Дополнительные комментарии.';
COMMENT ON COLUMN rooms.is_active IS 'Флаг активности комнаты.';

-- Таблица: roles
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

COMMENT ON TABLE roles IS 'Справочник ролей пользователей.';
COMMENT ON COLUMN roles.id IS 'Уникальный идентификатор роли.';
COMMENT ON COLUMN roles.name IS 'Название роли (admin, manager, specialist, client).';

INSERT INTO roles (name) VALUES
('admin'),
('manager'),
('specialist'),
('client');

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE,
    first_name TEXT NOT NULL,
    last_name TEXT,
    middle_name TEXT,
    email TEXT,
    phone TEXT,
    tg_id BIGINT,
    tg_username TEXT,
    birth_date DATE,
    gender TEXT CHECK (gender IN ('male','female','other')),
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE users IS 'Пользователи системы (админ, специалист, клиент).';
COMMENT ON COLUMN users.company_id IS 'FK → company.id. Компания, к которой относится пользователь.';
COMMENT ON COLUMN users.first_name IS 'Имя пользователя.';
COMMENT ON COLUMN users.last_name IS 'Фамилия пользователя.';
COMMENT ON COLUMN users.middle_name IS 'Отчество пользователя.';
COMMENT ON COLUMN users.email IS 'Адрес электронной почты.';
COMMENT ON COLUMN users.phone IS 'Телефон пользователя.';
COMMENT ON COLUMN users.tg_id IS 'Telegram ID пользователя.';
COMMENT ON COLUMN users.tg_username IS 'Telegram username (@username).';
COMMENT ON COLUMN users.birth_date IS 'Дата рождения клиента (для проверки возрастных ограничений).';
COMMENT ON COLUMN users.gender IS 'Пол клиента (male/female/other).';
COMMENT ON COLUMN users.notes IS 'Примечания о клиенте (комментарии, особенности).';
COMMENT ON COLUMN users.is_active IS 'Флаг активности.';
COMMENT ON COLUMN users.created_at IS 'Дата создания записи.';
COMMENT ON COLUMN users.updated_at IS 'Дата последнего обновления.';

CREATE TABLE user_roles (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE CASCADE,
    UNIQUE(user_id, role_id, location_id)
);

COMMENT ON TABLE user_roles IS 'Назначение ролей пользователю. Для специалистов и менеджеров может содержать привязку к конкретной локации.';

CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    duration_min INT NOT NULL,
    break_min INT NOT NULL DEFAULT 0,
    price NUMERIC(10,2) NOT NULL,
    color_code TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE services IS 'Справочник услуг для записи.';
COMMENT ON COLUMN services.company_id IS 'FK → company.id.';
COMMENT ON COLUMN services.name IS 'Название услуги.';
COMMENT ON COLUMN services.description IS 'Описание услуги.';
COMMENT ON COLUMN services.category IS 'Категория услуги.';
COMMENT ON COLUMN services.duration_min IS 'Длительность услуги (минуты).';
COMMENT ON COLUMN services.break_min IS 'Перерыв после услуги (минуты).';
COMMENT ON COLUMN services.price IS 'Стоимость услуги.';
COMMENT ON COLUMN services.color_code IS 'Цветовая метка для UI.';
COMMENT ON COLUMN services.is_active IS 'Флаг активности услуги.';

CREATE TABLE service_packages (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    package_items JSONB NOT NULL,               -- состав пакета
    package_price NUMERIC(10,2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE service_packages IS 'Пакеты услуг (комплексы из одной или нескольких услуг).';
COMMENT ON COLUMN service_packages.id IS 'Уникальный идентификатор пакета.';
COMMENT ON COLUMN service_packages.company_id IS 'FK → company.id.';
COMMENT ON COLUMN service_packages.name IS 'Название пакета.';
COMMENT ON COLUMN service_packages.description IS 'Описание пакета.';
COMMENT ON COLUMN service_packages.package_items IS 'JSON-массив: service_id + quantity.';
COMMENT ON COLUMN service_packages.package_price IS 'Общая цена пакета.';
COMMENT ON COLUMN service_packages.is_active IS 'Флаг активности пакета.';

CREATE TABLE service_rooms (
    id SERIAL PRIMARY KEY,
    room_id INT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    UNIQUE(room_id, service_id)
);

COMMENT ON TABLE service_rooms IS 'Привязка услуг к комнатам (кабинетам).';
COMMENT ON COLUMN service_rooms.id IS 'Уникальный идентификатор записи.';
COMMENT ON COLUMN service_rooms.room_id IS 'FK → rooms.id. Комната/кабинет.';
COMMENT ON COLUMN service_rooms.service_id IS 'FK → services.id. Услуга.';
COMMENT ON COLUMN service_rooms.is_active IS 'Флаг активности услуги в данной комнате.';
COMMENT ON COLUMN service_rooms.notes IS 'Ограничения или дополнительные комментарии.';

CREATE TABLE specialists (
    id SERIAL PRIMARY KEY,
    user_id INT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    display_name TEXT,
    description TEXT,
    photo_url TEXT,
    work_schedule JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE specialists IS 'Профили специалистов. Расширение данных users.';
COMMENT ON COLUMN specialists.id IS 'Уникальный идентификатор специалиста.';
COMMENT ON COLUMN specialists.user_id IS 'FK → users.id. Один пользователь = один специалист.';
COMMENT ON COLUMN specialists.display_name IS 'Отображаемое имя специалиста.';
COMMENT ON COLUMN specialists.description IS 'Описание, заметки.';
COMMENT ON COLUMN specialists.photo_url IS 'Фото специалиста.';
COMMENT ON COLUMN specialists.work_schedule IS 'График работы в формате JSON: интервалы по дням недели.';
COMMENT ON COLUMN specialists.is_active IS 'Флаг активности.';

CREATE TABLE specialist_services (
    service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    specialist_id INT NOT NULL REFERENCES specialists(id) ON DELETE CASCADE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    UNIQUE(service_id, specialist_id)
);

COMMENT ON TABLE specialist_services IS 'Компетенции специалистов: какие услуги они оказывают.';
COMMENT ON COLUMN specialist_services.service_id IS 'FK → services.id.';
COMMENT ON COLUMN specialist_services.specialist_id IS 'FK → specialists.id (профиль специалиста).';
COMMENT ON COLUMN specialist_services.is_default IS 'Основной специалист для услуги.';
COMMENT ON COLUMN specialist_services.is_active IS 'Флаг активности компетенции.';
COMMENT ON COLUMN specialist_services.notes IS 'Ограничения или примечания.';

CREATE TABLE calendar_overrides (
    id SERIAL PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (
        target_type IN ('location','room','specialist','service','system')
    ),
    target_id INT,
    date_start TIMESTAMP NOT NULL,
    date_end TIMESTAMP NOT NULL,
    override_kind TEXT NOT NULL CHECK (
        override_kind IN (
            'day_off',
            'block',
            'cleaning',
            'maintenance',
            'admin_hold'
        )
    ),
    reason TEXT,
    created_by INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE calendar_overrides IS 'Универсальная таблица блокировок времени.';
COMMENT ON COLUMN calendar_overrides.target_type IS 'Тип цели блокировки: location, room, specialist, service, system.';
COMMENT ON COLUMN calendar_overrides.target_id IS 'ID цели блокировки (может быть NULL для system).';
COMMENT ON COLUMN calendar_overrides.date_start IS 'Начало блокировки.';
COMMENT ON COLUMN calendar_overrides.date_end IS 'Окончание блокировки.';
COMMENT ON COLUMN calendar_overrides.override_kind IS 'Тип блокировки (выходной, блокировка времени, уборка, обслуживание, ручная).';
COMMENT ON COLUMN calendar_overrides.reason IS 'Причина блокировки.';
COMMENT ON COLUMN calendar_overrides.created_by IS 'Пользователь, создавший блокировку.';
COMMENT ON COLUMN calendar_overrides.created_at IS 'Дата создания записи.';

CREATE TABLE bookings (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE,
    location_id INT NOT NULL REFERENCES locations(id),
    service_id INT NOT NULL REFERENCES services(id),
    room_id INT REFERENCES rooms(id),
    client_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    specialist_id INT NOT NULL REFERENCES specialists(id) ON DELETE CASCADE,
    date_start TIMESTAMP NOT NULL,
    date_end   TIMESTAMP NOT NULL,
    duration_minutes INT NOT NULL,
    break_minutes INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending','confirmed','cancelled','done')
    ),
    final_price NUMERIC(10,2),
    notes TEXT,
    cancel_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

COMMENT ON TABLE bookings IS 'Записи клиентов на услуги.';
COMMENT ON COLUMN bookings.id IS 'Уникальный идентификатор записи.';
COMMENT ON COLUMN bookings.company_id IS 'FK → company.id.';
COMMENT ON COLUMN bookings.location_id IS 'FK → locations.id.';
COMMENT ON COLUMN bookings.service_id IS 'FK → services.id.';
COMMENT ON COLUMN bookings.room_id IS 'FK → rooms.id.';
COMMENT ON COLUMN bookings.client_id IS 'FK → users.id (клиент).';
COMMENT ON COLUMN bookings.specialist_id IS 'FK → specialists.id (специалист).';
COMMENT ON COLUMN bookings.date_start IS 'Дата и время начала услуги.';
COMMENT ON COLUMN bookings.date_end IS 'Дата и время окончания услуги (duration + break).';
COMMENT ON COLUMN bookings.duration_minutes IS 'Фактическая длительность услуги на момент брони.';
COMMENT ON COLUMN bookings.break_minutes IS 'Перерыв после услуги, сохранённый в момент брони.';
COMMENT ON COLUMN bookings.status IS 'Статус записи.';
COMMENT ON COLUMN bookings.final_price IS 'Фактическая цена услуги.';
COMMENT ON COLUMN bookings.notes IS 'Комментарии.';
COMMENT ON COLUMN bookings.cancel_reason IS 'Причина отмены.';
COMMENT ON COLUMN bookings.created_at IS 'Время создания записи.';
COMMENT ON COLUMN bookings.updated_at IS 'Время обновления записи.';

CREATE TABLE client_packages (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    package_id INT NOT NULL REFERENCES service_packages(id) ON DELETE CASCADE,
    used_quantity INT NOT NULL DEFAULT 0,
    purchased_at TIMESTAMP NOT NULL DEFAULT now(),
    valid_to DATE,
    notes TEXT
);

COMMENT ON TABLE client_packages IS 'Купленные клиентами пакеты услуг.';
COMMENT ON COLUMN client_packages.id IS 'Уникальный идентификатор покупки пакета.';
COMMENT ON COLUMN client_packages.user_id IS 'FK → users.id (клиент).';
COMMENT ON COLUMN client_packages.package_id IS 'FK → service_packages.id.';
COMMENT ON COLUMN client_packages.used_quantity IS 'Сколько услуг уже использовано из пакета.';
COMMENT ON COLUMN client_packages.purchased_at IS 'Дата покупки пакета.';
COMMENT ON COLUMN client_packages.valid_to IS 'Дата окончания действия пакета.';
COMMENT ON COLUMN client_packages.notes IS 'Примечания к пакету.';

CREATE TABLE client_discounts (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
    valid_from DATE,
    valid_to DATE,
    description TEXT
);

COMMENT ON TABLE client_discounts IS 'Персональные скидки клиентов.';
COMMENT ON COLUMN client_discounts.id IS 'Уникальный идентификатор скидки.';
COMMENT ON COLUMN client_discounts.user_id IS 'FK → users.id (клиент).';
COMMENT ON COLUMN client_discounts.discount_percent IS 'Размер скидки в процентах.';
COMMENT ON COLUMN client_discounts.valid_from IS 'Дата начала действия скидки.';
COMMENT ON COLUMN client_discounts.valid_to IS 'Дата окончания действия скидки.';
COMMENT ON COLUMN client_discounts.description IS 'Описание скидки.';

CREATE TABLE booking_discounts (
    id SERIAL PRIMARY KEY,
    booking_id INT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
    discount_reason TEXT
);

COMMENT ON TABLE booking_discounts IS 'Разовые скидки, применённые к конкретной записи.';
COMMENT ON COLUMN booking_discounts.id IS 'Уникальный идентификатор записи скидки.';
COMMENT ON COLUMN booking_discounts.booking_id IS 'FK → bookings.id.';
COMMENT ON COLUMN booking_discounts.discount_percent IS 'Разовая скидка в процентах.';
COMMENT ON COLUMN booking_discounts.discount_reason IS 'Причина применения скидки.';

CREATE TABLE client_wallets (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    balance NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'RUB',
    is_blocked BOOLEAN NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE client_wallets IS 'Кошельки клиентов. Текущий баланс.';
COMMENT ON COLUMN client_wallets.user_id IS 'FK → users.id (клиент).';
COMMENT ON COLUMN client_wallets.balance IS 'Остаток средств клиента.';
COMMENT ON COLUMN client_wallets.currency IS 'Валюта кошелька.';
COMMENT ON COLUMN client_wallets.is_blocked IS 'Флаг блокировки кошелька.';

CREATE TABLE wallet_transactions (
    id SERIAL PRIMARY KEY,
    wallet_id INT NOT NULL REFERENCES client_wallets(id) ON DELETE CASCADE,
    booking_id INT REFERENCES bookings(id) ON DELETE SET NULL,
    amount NUMERIC(12,2) NOT NULL,
    type TEXT NOT NULL DEFAULT 'payment'
        CHECK (type IN ('deposit','withdraw','payment','refund','correction')),
    description TEXT,
    created_by INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

COMMENT ON TABLE wallet_transactions IS 'Финансовые операции по клиентским кошелькам.';
COMMENT ON COLUMN wallet_transactions.id IS 'Уникальный идентификатор транзакции.';
COMMENT ON COLUMN wallet_transactions.wallet_id IS 'FK → client_wallets.id.';
COMMENT ON COLUMN wallet_transactions.booking_id IS 'FK → bookings.id.';
COMMENT ON COLUMN wallet_transactions.amount IS 'Сумма транзакции.';
COMMENT ON COLUMN wallet_transactions.type IS 'Тип транзакции.';
COMMENT ON COLUMN wallet_transactions.description IS 'Описание транзакции.';
COMMENT ON COLUMN wallet_transactions.created_by IS 'FK → users.id (создатель транзакции).';
COMMENT ON COLUMN wallet_transactions.created_at IS 'Дата создания транзакции.';

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

