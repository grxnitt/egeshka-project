# ЕГЭ Мэтч — Telegram-бот

Бот для подбора и сравнения онлайн-школ и преподавателей подготовки к ЕГЭ.

## Быстрый запуск

1. Создайте бота в BotFather и получите токен.
2. Скопируйте `.env.example` в `.env` и заполните `BOT_TOKEN` и `ADMIN_IDS`.
3. Установите зависимости: `python3 -m pip install -r requirements.txt`.
4. Запустите: `python3 -m egeshka_bot`.

По умолчанию используется SQLite для локальной проверки. Для PostgreSQL задайте `DATABASE_URL` в `.env`.
