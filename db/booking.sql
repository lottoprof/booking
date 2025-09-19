-- Таблица: locations
CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    capacity INT NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE locations IS 'Локации (филиалы, салоны, клиники).';
COMMENT ON COLUMN locations.id IS 'Уникальный идентификатор локации.';
COMMENT ON COLUMN locations.name IS 'Название локации (например, "Салон №1").';
COMMENT ON COLUMN locations.address IS 'Адрес локации.';
COMMENT ON COLUMN locations.capacity IS 'Максимальное количество клиентов, которое может обслуживаться одновременно (по местам).';
COMMENT ON COLUMN locations.is_active IS 'Флаг активности локации.';


-- Таблица: services
CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    duration_min INT NOT NULL,
    break_min INT NOT NULL DEFAULT 0,
    price NUMERIC(10,2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE services IS 'Глобальный справочник услуг (базовые параметры).';
COMMENT ON COLUMN services.id IS 'Уникальный идентификатор услуги.';
COMMENT ON COLUMN services.name IS 'Название услуги (например, "Массаж общий").';
COMMENT ON COLUMN services.description IS 'Описание услуги.';
COMMENT ON COLUMN services.duration_min IS 'Базовая длительность услуги в минутах.';
COMMENT ON COLUMN services.break_min IS 'Базовое время перерыва после услуги (минуты).';
COMMENT ON COLUMN services.price IS 'Базовая стоимость услуги.';
COMMENT ON COLUMN services.is_active IS 'Флаг активности услуги.';


-- Таблица: specialists
CREATE TABLE specialists (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    specialization TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE specialists IS 'Справочник специалистов.';
COMMENT ON COLUMN specialists.id IS 'Уникальный идентификатор специалиста.';
COMMENT ON COLUMN specialists.name IS 'ФИО или отображаемое имя специалиста.';
COMMENT ON COLUMN specialists.specialization IS 'Специализация (например, стоматолог, массажист).';
COMMENT ON COLUMN specialists.is_active IS 'Флаг активности специалиста.';


-- Таблица: clients
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    tg_id BIGINT,
    phone TEXT,
    first_name TEXT NOT NULL,
    last_name TEXT,
    email TEXT,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE clients IS 'Клиенты системы (пациенты, посетители).';
COMMENT ON COLUMN clients.id IS 'Уникальный идентификатор клиента.';
COMMENT ON COLUMN clients.tg_id IS 'Telegram user_id для интеграции с ботом.';
COMMENT ON COLUMN clients.phone IS 'Телефон клиента.';
COMMENT ON COLUMN clients.first_name IS 'Имя клиента.';
COMMENT ON COLUMN clients.last_name IS 'Фамилия клиента.';
COMMENT ON COLUMN clients.email IS 'Email клиента.';
COMMENT ON COLUMN clients.notes IS 'Примечания (VIP, аллергии и т.п.).';
COMMENT ON COLUMN clients.is_active IS 'Флаг активности клиента.';


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
COMMENT ON COLUMN location_schedules.day_of_week IS 'День недели (0=Пн … 6=Вс).';
COMMENT ON COLUMN location_schedules.start_time IS 'Время начала работы.';
COMMENT ON COLUMN location_schedules.end_time IS 'Время окончания работы.';
COMMENT ON COLUMN location_schedules.is_day_off IS 'Признак выходного дня.';


-- Таблица: workplaces
CREATE TABLE workplaces (
    id SERIAL PRIMARY KEY,
    location_id INT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE workplaces IS 'Рабочие места в локации (кресла, кушетки, кабинеты).';
COMMENT ON COLUMN workplaces.id IS 'Уникальный идентификатор рабочего места.';
COMMENT ON COLUMN workplaces.location_id IS 'FK → locations.id. Локация, к которой относится рабочее место.';
COMMENT ON COLUMN workplaces.name IS 'Название рабочего места (например, "Кушетка №1").';
COMMENT ON COLUMN workplaces.type IS 'Тип рабочего места (например, кресло, кушетка).';
COMMENT ON COLUMN workplaces.is_active IS 'Флаг активности рабочего места.';


-- Таблица: workplace_services
CREATE TABLE workplace_services (
    id SERIAL PRIMARY KEY,
    workplace_id INT NOT NULL REFERENCES workplaces(id) ON DELETE CASCADE,
    service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    price NUMERIC(10,2),
    duration_min INT,
    break_min INT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(workplace_id, service_id)
);

COMMENT ON TABLE workplace_services IS 'Связка рабочих мест с услугами, с возможностью индивидуальных параметров (цена, длительность, перерыв).';
COMMENT ON COLUMN workplace_services.id IS 'Уникальный идентификатор записи связки.';
COMMENT ON COLUMN workplace_services.workplace_id IS 'FK → workplaces.id. Рабочее место.';
COMMENT ON COLUMN workplace_services.service_id IS 'FK → services.id. Услуга.';
COMMENT ON COLUMN workplace_services.price IS 'Индивидуальная цена услуги для данного рабочего места. NULL = используется базовая цена.';
COMMENT ON COLUMN workplace_services.duration_min IS 'Индивидуальная длительность услуги для рабочего места. NULL = используется базовое значение.';
COMMENT ON COLUMN workplace_services.break_min IS 'Индивидуальный перерыв после услуги на рабочем месте. NULL = используется базовое значение.';
COMMENT ON COLUMN workplace_services.is_active IS 'Флаг активности связки.';


-- Таблица: service_specialists
CREATE TABLE service_specialists (
    id SERIAL PRIMARY KEY,
    service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    specialist_id INT NOT NULL REFERENCES specialists(id) ON DELETE CASCADE,
    custom_price NUMERIC(10,2),
    custom_duration INT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(service_id, specialist_id)
);

COMMENT ON TABLE service_specialists IS 'Компетенции специалистов (какие услуги они могут оказывать).';
COMMENT ON COLUMN service_specialists.service_id IS 'FK → services.id. Услуга.';
COMMENT ON COLUMN service_specialists.specialist_id IS 'FK → specialists.id. Специалист.';
COMMENT ON COLUMN service_specialists.custom_price IS 'Индивидуальная цена услуги у данного специалиста.';
COMMENT ON COLUMN service_specialists.custom_duration IS 'Индивидуальная длительность услуги у данного специалиста.';
COMMENT ON COLUMN service_specialists.is_active IS 'Флаг активности компетенции.';


-- Таблица: specialist_schedules
CREATE TABLE specialist_schedules (
    id SERIAL PRIMARY KEY,
    specialist_id INT NOT NULL REFERENCES specialists(id) ON DELETE CASCADE,
    location_id INT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    workplace_id INT REFERENCES workplaces(id) ON DELETE CASCADE,
    day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TIME,
    end_time TIME,
    is_day_off BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(specialist_id, location_id, workplace_id, day_of_week)
);

COMMENT ON TABLE specialist_schedules IS 'Расписание специалистов по дням недели (с привязкой к локациям и рабочим местам).';
COMMENT ON COLUMN specialist_schedules.specialist_id IS 'FK → specialists.id. Специалист.';
COMMENT ON COLUMN specialist_schedules.location_id IS 'FK → locations.id. Локация, где работает специалист.';
COMMENT ON COLUMN specialist_schedules.workplace_id IS 'FK → workplaces.id. Рабочее место (опционально).';
COMMENT ON COLUMN specialist_schedules.day_of_week IS 'День недели (0=Пн … 6=Вс).';
COMMENT ON COLUMN specialist_schedules.start_time IS 'Время начала работы специалиста.';
COMMENT ON COLUMN specialist_schedules.end_time IS 'Время окончания работы специалиста.';
COMMENT ON COLUMN specialist_schedules.is_day_off IS 'Признак выходного дня специалиста.';


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


-- Таблица: appointments
CREATE TABLE appointments (
    id SERIAL PRIMARY KEY,
    location_id INT NOT NULL REFERENCES locations(id),
    service_id INT NOT NULL REFERENCES services(id),
    workplace_id INT REFERENCES workplaces(id),
    specialist_id INT NOT NULL REFERENCES specialists(id),
    client_id INT NOT NULL REFERENCES clients(id),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

COMMENT ON TABLE appointments IS 'Записи клиентов на услуги.';
COMMENT ON COLUMN appointments.location_id IS 'FK → locations.id. Локация записи.';
COMMENT ON COLUMN appointments.service_id IS 'FK → services.id. Услуга.';
COMMENT ON COLUMN appointments.workplace_id IS 'FK → workplaces.id. Рабочее место.';
COMMENT ON COLUMN appointments.specialist_id IS 'FK → specialists.id. Специалист.';
COMMENT ON COLUMN appointments.client_id IS 'FK → clients.id. Клиент.';
COMMENT ON COLUMN appointments.start_time IS 'Дата и время начала приёма.';
COMMENT ON COLUMN appointments.end_time IS 'Дата и время окончания приёма.';
COMMENT ON COLUMN appointments.status IS 'Статус записи (pending / confirmed / cancelled / done / no-show).';
COMMENT ON COLUMN appointments.created_at IS 'Дата создания записи.';
COMMENT ON COLUMN appointments.updated_at IS 'Дата обновления записи.';


-- Таблица: client_wallets
CREATE TABLE client_wallets (
    client_id INT PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,
    balance NUMERIC(12,2) NOT NULL DEFAULT 0
);

COMMENT ON TABLE client_wallets IS 'Текущий баланс клиента.';
COMMENT ON COLUMN client_wallets.client_id IS 'FK → clients.id. Клиент.';
COMMENT ON COLUMN client_wallets.balance IS 'Остаток средств на счету клиента.';


-- Таблица: wallet_transactions
CREATE TABLE wallet_transactions (
    id SERIAL PRIMARY KEY,
    client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    appointment_id INT REFERENCES appointments(id) ON DELETE SET NULL,
    amount NUMERIC(12,2) NOT NULL,
    discount NUMERIC(5,2),
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

COMMENT ON TABLE wallet_transactions IS 'Транзакции кошелька клиента (пополнения и списания).';
COMMENT ON COLUMN wallet_transactions.client_id IS 'FK → clients.id. Клиент.';
COMMENT ON COLUMN wallet_transactions.appointment_id IS 'FK → appointments.id. Связь с записью, если списание за услугу.';
COMMENT ON COLUMN wallet_transactions.amount IS 'Сумма транзакции (>0 пополнение, <0 списание).';
COMMENT ON COLUMN wallet_transactions.discount IS 'Скидка (%) применённая при списании (NULL если нет).';
COMMENT ON COLUMN wallet_transactions.description IS 'Комментарий к транзакции (пополнение, оплата за услугу).';
COMMENT ON COLUMN wallet_transactions.created_at IS 'Дата и время проведения транзакции.';

