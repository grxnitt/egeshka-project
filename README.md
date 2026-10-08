# ЕГЭ Мэтч — Telegram-бот

Бот для подбора и сравнения онлайн-школ и преподавателей подготовки к ЕГЭ.

## Быстрый запуск

1. Создайте бота в BotFather и получите токен.
2. Скопируйте `.env.example` в `.env` и заполните `BOT_TOKEN` и `ADMIN_IDS`.
3. Нужен Python 3.10+ (проверено на 3.14). Создайте окружение и поставьте зависимости: `python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
4. Запустите: `.venv/bin/python -m egeshka_bot`.

По умолчанию используется SQLite для локальной проверки. Для PostgreSQL задайте `DATABASE_URL` в `.env`.
