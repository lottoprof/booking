# Ключевой принцип

У клиента один кошелёк → он должен видеть все свои операции.
Но транзакции не CRUD, они создаются ТОЛЬКО через бизнес-операции.

## МОДЕЛЬ доступа
> Wallet API (domain-level) описан отдельно и работает поверх foundation CRUD.


Таблица:

- client_wallets — объект кошелька
- wallet_transactions — операции (read-only для клиента)

Логика:
клиент может:
- смотреть баланс
- смотреть историю операций
- сервер может:
списывать
- пополнять
- проводить оплату записи
- делать возврат
- корректировать баланс

## СВЯЗЫВАЕМ транзакции с client_wallets 

Структура:

`client_wallets`
   ↓ (1 ко многим)
`wallet_transactions`


API должен работать через кошелёк, а НЕ напрямую через транзакции.

## Итоговое дерево API (универсальное, строго по домену кошелька)
1. Получить кошелёк клиента
GET /wallets/{user_id}

2. Получить историю операций клиента
GET /wallets/{user_id}/transactions

Возвращает список WalletTransactionRead.

3. Пополнить кошелёк
POST /wallets/{user_id}/deposit

Тело: WalletDeposit

4. Списать с кошелька
POST /wallets/{user_id}/withdraw

Тело: WalletWithdraw

5. Оплатить запись
POST /wallets/{user_id}/payment

Тело: WalletPayment

6. Вернуть деньги
POST /wallets/{user_id}/refund

Тело: WalletRefund

7. Корректировка (только админ/система)
POST /wallets/{user_id}/correction

Тело: WalletCorrection

## Та же самая таблица wallet_transactions, но API через client_wallets
API	Pydantic	Заполняет таблицу?
/wallets/{id}/deposit	WalletDeposit	✔
/wallets/{id}/withdraw	WalletWithdraw	✔
/wallets/{id}/payment	WalletPayment	✔
/wallets/{id}/refund	WalletRefund	✔
/wallets/{id}/correction	WalletCorrection	✔
/wallets/{id}/transactions	WalletTransactionRead	✖ (только просмотр)

 Клиент видит ВСЕ поступления и списания

Потому что:

GET /wallets/{user_id}/transactions
возвращает:
deposit
withdraw
payment
refund
correction

в одном списке, отсортированном по времени.

1. API становится безопасным и прозрачным

клиент ничего не может испортить.

2. Финансовая логика централизована

в одном месте на backend.

3. UI и Telegram-бот получают единый интерфейс:
Баланс: 1500 ₽
История:
+500 пополнение
-300 запись №15
-200 запись №18
+300 возврат

4. Расхождение данных становится невозможным
все операции проходят через один маршрут.
