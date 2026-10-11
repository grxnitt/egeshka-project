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

## Школы-партнёры и заявки (вкладки «Школы» и «Заявки» в панели)
- Панель открывается так же, как модерация: `scripts/admin.sh` (SSH-туннель), после перезапуска службы страницу нужно обновить.
- Служба заявок `egematch-reviews-leads` (127.0.0.1:8081, роль БД `reviews_leads_login`), Caddy отдаёт ей `/api/leads*`, `/api/lead-schools`, `/api/lead-consent`.
- Миграция `019_lead_admin.sql`: поля `agreement_date`, `notes`, таблица `site_flags`, строки `lead_schools` для всех школ, права ролей.
- Главный выключатель `leads_enabled` лежит в БД (`site_flags`), стоит ВЫКЛ; включается только в панели (два подтверждения: уведомление РКН и ответ налоговой, плюс слово «ВКЛЮЧИТЬ»). Пока он выключен, сайт заявки не показывает, даже если у школы переключатель включён.
- Чтобы форма заявки вообще загружалась на сайте, в `web/analytics-config.js` должно быть `window.EGE_LEADS_API = 'https://data.egematch.ru'` (сейчас пусто, это последний шаг запуска).
- Доставка: почта (info@egematch.ru), вебхук CRM, чат Telegram. С российского сервера Telegram недоступен, поэтому для Telegram-канала нужен ретранслятор (`REVIEWS_TELEGRAM_API_BASE`).
- Бэкап БД перед запуском: `/var/backups/egematch/after-019.dump`.
- Команды `/lead_*` в боте отключены: заявки живут в базе на сервере, а не в базе бота на Mac.
