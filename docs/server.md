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
