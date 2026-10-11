# Сервер в РФ (Рег.облако, Москва)

- VPS `Amber Ruthenium` (ID 8121577), Ubuntu 24.04, 2 vCPU / 2 ГБ / 40 ГБ NVMe, IP 95.163.231.156, ежедневные бэкапы Рег.облака.
- Вход: только SSH-ключ `~/.ssh/egematch_vps` (root), пароли отключены. Файрвол ufw: 22, 80, 443. fail2ban.
- Пароли БД лежат на сервере в `/root/egematch-secrets.env` (только root), в репозиторий не попадают.

## Что работает
- PostgreSQL 16, слушает только localhost. Миграции `supabase/migrations/001–017` накатаны без правок; `pg_cron` обновляет рейтинг в 00:15 UTC.
- Роли: `anon`, `authenticated` (публичное чтение по RLS), `egeshka_bot_login` (бот), `postgrest_authenticator` (PostgREST).
- PostgREST 12.2.3 (`/etc/postgrest/postgrest.conf`, служба `postgrest`) на 127.0.0.1:3000.
- Caddy: `https://data.egematch.ru` (и путь `/rest/v1/*` для совместимости с Supabase-клиентом сайта), сертификат Let's Encrypt.
- Код бота: `/opt/egematch` (venv, `.env`), служба `egematch-bot` (сейчас выключена, см. ниже).

## Блокер
С сервера в РФ недоступен Telegram Bot API (`api.telegram.org` режется по TLS), поэтому бот там работать не может без ретранслятора за границей.

## Отзывы на сайте (reviews_service)
- Код: `reviews_service/` (не зависит от бота). Две службы с разными ролями БД:
  - `egematch-reviews-public` — API сайта на 127.0.0.1:8085, наружу через Caddy `https://data.egematch.ru/api/*`; роль `reviews_public` может только создавать отзывы «на модерации» и удалять данные по коду (ограничено RLS в БД).
  - `egematch-reviews-admin` — модерация на 127.0.0.1:8090, наружу НЕ открыта; вход только через `scripts/admin.sh` (SSH-туннель по ключу). Роль `reviews_admin`.
- Миграция `supabase/migrations/018_site_reviews.sql`. Файлы служб и Caddy — в `deploy/`.
- Настройки: `/etc/egematch/reviews-public.env` и `reviews-admin.env` (0640 root:egematch): `REVIEWS_DATABASE_URL`, `REVIEWS_HMAC_SECRET` (общий для обеих), `REVIEWS_SMTP_*`. Пароль почты — `scripts/set-mail-password.sh` (ввод скрыт).
- Скриншоты: `/var/lib/egematch/proofs`, только пересобранные WebP; удаляются при модерации, черновики — через час, непроверенные — через 30 дней.
- Почта и IP в базе только в виде HMAC-отпечатков; журнал доступа не пишется.
- Локальная проверка формы: `.venv/bin/python scripts/dev_reviews.py <папка>` + страница `review.html` на 8934.
