# TODO: Реферальная система + бонусный баланс с TTL

**Статус:** Ожидает
**Приоритет:** Средний

---

## 1. Реферальная система

### Сценарий

1. Клиент A открывает inline-режим бота, выбирает процедуру
2. Бот формирует inline-сообщение с описанием процедуры + deep-link на бота
3. Клиент A отправляет это сообщение знакомому (клиент B)
4. Клиент B переходит по ссылке → `/start ref_{user_id}_{package_id}`
5. Клиент B записывается и получает услугу (админ подтверждает `status=done`)
6. Клиенту A начисляется бонус (% от стоимости) на кошелёк

### Ограничения

- **Один уровень** — только прямые рефералы. A пригласил B — получает бонус. Если B пригласит C — бонус только B, не A
- **Только новые клиенты** — бонус начисляется только если B не был в системе до перехода по ссылке
- **Однократно** — бонус за приглашение B выплачивается один раз (за первый `done`-букинг)
- **Обратный трафик не принимается** — если B пригласит A обратно, бонус не начисляется

### Схема БД

```sql
-- ── Referrals ─────────────────────────────────
CREATE TABLE referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL,           -- кто пригласил (клиент A)
    referred_id INTEGER NOT NULL,           -- кого пригласил (клиент B)
    service_package_id INTEGER,             -- какой пакет/процедуру рекомендовал
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'rewarded', 'expired')),
    booking_id INTEGER,                     -- букинг, за который начислен бонус
    reward_amount REAL,                     -- сумма начисленного бонуса
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    rewarded_at TEXT,
    FOREIGN KEY (referrer_id) REFERENCES users(id),
    FOREIGN KEY (referred_id) REFERENCES users(id),
    FOREIGN KEY (booking_id) REFERENCES bookings(id),
    UNIQUE(referred_id)                     -- у клиента один реферер
);
```

`UNIQUE(referred_id)` гарантирует: один клиент — один реферер. Обратный трафик блокируется проверкой `referrer_id != referred_id` + `referred_id` не может быть чьим-то реферером, если уже является реферером сам.

### Настройки реферальной программы

Хранить в таблице `company` (уже есть, одна строка):

```sql
ALTER TABLE company ADD COLUMN referral_bonus_percent REAL DEFAULT 10;
ALTER TABLE company ADD COLUMN referral_bonus_max REAL;               -- NULL = без лимита
ALTER TABLE company ADD COLUMN referral_enabled INTEGER DEFAULT 0;
```

### Inline-режим бота

**Файл:** `bot/app/handlers/inline_query.py` (NEW)

```python
@router.inline_query()
async def on_inline_query(query: InlineQuery):
    # 1. Получить список пакетов (show_on_booking=True)
    # 2. Фильтр по query.query (поиск по названию)
    # 3. Сформировать InlineQueryResultArticle для каждого:
    #    - title: название процедуры
    #    - description: краткое описание + цена
    #    - input_message_content: текст с описанием + кнопка
    #    - reply_markup: InlineKeyboardButton(
    #        text="Записаться",
    #        url=f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}_{package_id}"
    #      )
```

### Обработка deep-link

**Файл:** `bot/app/handlers/start.py` (модификация)

```python
# Парсинг /start ref_123_5
if payload.startswith("ref_"):
    parts = payload.split("_")
    referrer_id = int(parts[1])
    package_id = int(parts[2]) if len(parts) > 2 else None

    # Проверки:
    # - B не существует в системе (новый клиент)
    # - A != B
    # - A не является referred от B (анти-кольцо)
    # Если ок → INSERT INTO referrals (referrer_id, referred_id, service_package_id)
```

### Начисление бонуса

**Файл:** `backend/app/services/booking_payment.py` (модификация)

Добавить в конец `process_booking_payment()`:

```python
# После обработки платежа → проверить реферальный бонус
_process_referral_reward(db, booking, created_by)
```

```python
def _process_referral_reward(db, booking, created_by):
    """Начислить реферальный бонус если это первый done-букинг приглашённого."""
    referral = db.query(DBReferral).filter(
        DBReferral.referred_id == booking.client_id,
        DBReferral.status == "pending",
    ).first()

    if not referral:
        return

    # Проверить что это первый done-букинг клиента B
    done_count = db.query(DBBooking).filter(
        DBBooking.client_id == booking.client_id,
        DBBooking.status == "done",
    ).count()

    if done_count > 1:  # уже не первый
        return

    # Рассчитать бонус
    company = db.query(DBCompany).first()
    if not company or not company.referral_enabled:
        return

    bonus = booking.final_price * (company.referral_bonus_percent / 100)
    if company.referral_bonus_max:
        bonus = min(bonus, company.referral_bonus_max)

    # Начислить бонусный баланс (см. раздел 2)
    _credit_bonus(db, referral.referrer_id, bonus,
                  description=f"Реферальный бонус: {booking.service_name}",
                  created_by=created_by)

    # Обновить реферал
    referral.status = "rewarded"
    referral.booking_id = booking.id
    referral.reward_amount = bonus
    referral.rewarded_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
```

---

## 2. Бонусный баланс с TTL

### Проблема

Текущий `client_wallets.balance` — единый баланс. Нужны два вида средств:
- **Основной баланс** — без срока (пакеты, корректировки)
- **Бонусный баланс** — с TTL (рефералы, акции, подарки)

### Варианты реализации

#### Вариант A: Отдельное поле `bonus_balance` (рекомендуется)

```sql
ALTER TABLE client_wallets ADD COLUMN bonus_balance REAL NOT NULL DEFAULT 0;

-- Бонусные начисления с TTL
CREATE TABLE bonus_credits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id INTEGER NOT NULL,
    amount REAL NOT NULL,               -- начальная сумма
    remaining REAL NOT NULL,            -- остаток
    source TEXT NOT NULL                -- 'referral', 'promo', 'gift'
        CHECK (source IN ('referral', 'promo', 'gift')),
    description TEXT,
    expires_at TEXT NOT NULL,           -- дата истечения
    is_expired INTEGER DEFAULT 0,      -- помечается при списании/истечении
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wallet_id) REFERENCES client_wallets(id)
);
```

**Логика списания (FIFO по expires_at):**

```python
def spend_bonus(db, wallet_id, amount):
    """Списать бонусы начиная с ближайших к истечению."""
    credits = db.query(DBBonusCredit).filter(
        DBBonusCredit.wallet_id == wallet_id,
        DBBonusCredit.remaining > 0,
        DBBonusCredit.is_expired == 0,
        DBBonusCredit.expires_at >= today,
    ).order_by(DBBonusCredit.expires_at.asc()).all()

    to_spend = amount
    for credit in credits:
        if to_spend <= 0:
            break
        use = min(credit.remaining, to_spend)
        credit.remaining -= use
        to_spend -= use
        if credit.remaining == 0:
            credit.is_expired = 1

    wallet.bonus_balance -= (amount - to_spend)
    return amount - to_spend  # фактически списано
```

**Протухание (крон):**

```python
def expire_bonuses():
    """Ежедневный крон: обнулить истёкшие бонусы."""
    expired = db.query(DBBonusCredit).filter(
        DBBonusCredit.expires_at < today,
        DBBonusCredit.is_expired == 0,
        DBBonusCredit.remaining > 0,
    ).all()

    for credit in expired:
        wallet = db.get(DBWallet, credit.wallet_id)
        wallet.bonus_balance -= credit.remaining
        credit.remaining = 0
        credit.is_expired = 1
        # Транзакция для аудита
        _create_transaction(db, wallet.id, -credit.remaining,
                           "correction", description="Бонус истёк")
```

#### Вариант B: Только `bonus_credits` без поля в wallet

Плюс: нет дублирования. Минус: каждый раз считать `SUM(remaining)` вместо чтения поля.

**Рекомендация:** Вариант A — поле `bonus_balance` как кэш для быстрого отображения.

### Порядок списания при оплате

```
1. Бонусный баланс (FIFO по expires_at) — сначала сгорающие
2. Основной баланс (пакеты)
3. Если не хватает — оплата наличными (баланс = 0, не уходит в минус)
```

### Типы бонусных начислений

| source | Описание | TTL | Пример |
|--------|----------|-----|--------|
| `referral` | Реферальный бонус | 90 дней | Приглашение друга |
| `promo` | Акционные бонусы | 30–60 дней | Промо к 8 марта, Новый год |
| `gift` | Подарочные бонусы | 30–180 дней | День рождения, лояльность |

### API

```
POST /wallets/{user_id}/bonus-credit
{
    "amount": 500,
    "source": "promo",
    "description": "Бонус к 8 Марта",
    "expires_at": "2026-04-30"
}

GET /wallets/{user_id}
→ { "balance": 10000, "bonus_balance": 500, ... }

GET /wallets/{user_id}/bonuses
→ [{ "amount": 500, "remaining": 500, "source": "promo", "expires_at": "2026-04-30" }]
```

### Отображение в боте

```
💰 Ваш баланс: 10 000 ₽
🎁 Бонусы: 500 ₽ (до 30 апреля)
```

---

## 3. Связь реферальная система + бонусный баланс

```
Клиент A → inline-сообщение → Клиент B
                                  ↓
                            /start ref_A_pkg
                                  ↓
                        INSERT referrals (pending)
                                  ↓
                     B записывается → B получает услугу
                                  ↓
                       status=done → process_booking_payment()
                                  ↓
                       _process_referral_reward()
                                  ↓
                INSERT bonus_credits (source=referral, TTL=90d)
                   wallet.bonus_balance += reward
                   referrals.status = rewarded
                                  ↓
                  A получает уведомление в боте:
                  "Вам начислен бонус 300 ₽ за приглашение!"
```

---

## 4. План реализации

### Фаза 1: Бонусный баланс с TTL
1. Миграция: `bonus_balance` + таблица `bonus_credits`
2. API: `POST /wallets/{user_id}/bonus-credit`, `GET .../bonuses`
3. Крон: `expire_bonuses()` (ежедневно в 04:00)
4. `booking_payment.py`: приоритет бонусов при оплате
5. Бот: отображение бонусного баланса
6. Ручное начисление (админ) — для акций

### Фаза 2: Реферальная система
1. Миграция: таблица `referrals`, поля в `company`
2. Inline-mode handler
3. Обработка `/start ref_...` deep-link
4. `_process_referral_reward()` в `booking_payment.py`
5. Уведомление реферера (бот → Redis event → notification)
6. Админ: просмотр рефералов (`GET /referrals/`)

### Фаза 3: Акционные бонусы
1. Массовая раздача бонусов (админ выбирает сегмент → POST batch)
2. Автоматические бонусы по триггерам (день рождения, N-я запись)
3. Промо-код → бонус на баланс

---

## 5. Что уже готово

- Кошелёк (`client_wallets` + `wallet_transactions`) — работает
- `process_booking_payment()` — точка интеграции для реферального бонуса
- `discount_resolver.py` — не пересекается (скидки = % от цены, бонусы = абсолютная сумма)
- Deep-link в боте — частично (есть `/start`, нет парсинга `ref_`)
- Уведомления через Redis events — инфраструктура есть

## 6. Риски

| Риск | Митигация |
|------|-----------|
| Злоупотребление (фейковые аккаунты) | Бонус только после `done` (подтверждение админом) |
| Кольцевые рефералы (A→B→A) | `UNIQUE(referred_id)` + проверка при регистрации |
| Рассинхрон `bonus_balance` | Крон-сверка `SUM(remaining)` vs поле |
| Начисление бонуса без визита | Только по факту `status=done` |
