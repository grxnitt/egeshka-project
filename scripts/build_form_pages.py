"""Builds /review, /delete-data and /consent from one template, with the header and footer of web/reviews.html.

Run after changing the texts below:  .venv/bin/python scripts/build_form_pages.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
CSS = {"styles.css": "37", "refinements.css": "46", "typography.css": "31", "composition.css": "267", "review-form.css": "5"}
JS_VERSION = "10"
CONSENT_VERSION = "reviews-2026-10-14"   # keep equal to reviews_service.validation.CONSENT_VERSION


def chrome():
    source = (WEB / "reviews.html").read_text(encoding="utf-8")
    header = re.search(r'<header class="header wrap">.*?</header>', source, re.S).group(0).replace(' class="active"', "")
    mobile = re.search(r'<nav class="mobile-product-nav".*?</nav>', source, re.S).group(0).replace(' class="active"', "")
    footer = re.search(r'<footer class="wrap footer site-footer">.*?</footer>', source, re.S).group(0)
    fonts = re.search(r'<link rel="preload" href="/assets/fonts/.*?\n', source).group(0)
    return header, mobile, footer, fonts


def page(slug, title, description, body_class, main, script=None, index=True):
    header, mobile, footer, fonts = chrome()
    styles = "".join(f'  <link rel="stylesheet" href="{name}?v={version}">\n' for name, version in CSS.items())
    scripts = '<script src="analytics-config.js?v=2"></script>\n<script src="analytics.js?v=30"></script>\n'
    if script:
        scripts += f'<script type="module" src="{script}?v={JS_VERSION}"></script>\n'
    robots = "" if index else '  <meta name="robots" content="noindex">\n'
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#FAF8F5">
  <meta name="description" content="{description}">
{robots}  <link rel="canonical" href="https://egematch.ru/{slug}">
  <title>{title}</title>
  <link rel="icon" href="assets/egeshka-logo-icon.svg" type="image/svg+xml">
  <link rel="icon" href="assets/favicon-32.png" sizes="32x32" type="image/png">
  <link rel="apple-touch-icon" href="assets/apple-touch-icon.png">
  <link rel="icon" href="favicon.ico" sizes="48x48">
  <link rel="manifest" href="site.webmanifest">
  {fonts}{styles}</head>
<body class="{body_class}">
{header}
{main}
{mobile}
{footer}
{scripts}
</body></html>
"""


REVIEW_MAIN = """<main class="rf-page">
  <section class="hero hero-centered rating-centered wrap privacy-hero rf-hero">
    <div class="hero-glow hero-glow-blue" aria-hidden="true"></div><div class="hero-glow hero-glow-pink" aria-hidden="true"></div>
    <div class="hero-copy"><h1><span class="hero-title-line">Оставить</span> <span class="hero-title-line brand-dot">отзыв</span></h1><p class="lead">Отзыв выходит после модерации, анонимно или с вашим именем. Займёт пару минут: оценки, пара предложений и почта для кода.</p></div>
  </section>
  <div class="wrap rf-layout">
    <div id="rf-root" class="rf-card" aria-busy="true">
      <p id="rf-alert" class="rf-alert" role="alert" hidden></p>
      <form id="rf-form" novalidate>
        <section class="rf-step" aria-labelledby="rf-h0">
          <h2 id="rf-h0"><span class="rf-num">1</span>Как подписать отзыв</h2>
          <div class="tabs rf-tabs" role="group" aria-label="Как подписать отзыв"><button type="button" data-author="anon" class="active" aria-pressed="true">Анонимно</button><button type="button" data-author="named" aria-pressed="false">С именем или ником</button></div>
          <p class="rf-hint" id="rf-author-hint">Имя автора не покажем. Отзывы с именем вызывают больше доверия, но это ваш выбор.</p>
          <label class="rf-field" id="rf-name-wrap" hidden><span>Имя или ник</span><input type="text" id="rf-name" maxlength="30" autocomplete="nickname" placeholder="Например: Маша или ege_ivan"></label>
          <p class="rf-error" id="rf-name-error" aria-live="polite"></p>
        </section>
        <section class="rf-step" aria-labelledby="rf-h1">
          <h2 id="rf-h1"><span class="rf-num">2</span>О ком отзыв</h2>
          <div class="tabs rf-tabs" role="group" aria-label="О ком отзыв"><button type="button" data-kind="school" class="active" aria-pressed="true">О школе</button><button type="button" data-kind="teacher" aria-pressed="false">О преподавателе</button></div>
          <p class="rf-hint rf-kind-hint" id="rf-kind-hint"></p>
          <label class="rf-field"><span>Школа</span><select id="rf-school"></select></label>
          <label class="rf-field" id="rf-teacher-wrap" hidden><span>Преподаватель</span><select id="rf-teacher"></select></label>
          <p class="rf-error" id="rf-target-error" aria-live="polite"></p>
        </section>
        <section class="rf-step" aria-labelledby="rf-h2">
          <h2 id="rf-h2"><span class="rf-num">3</span>Оценки</h2>
          <div id="rf-scores"></div>
          <p class="rf-error" id="rf-scores-error" aria-live="polite"></p>
        </section>
        <section class="rf-step" aria-labelledby="rf-h3">
          <h2 id="rf-h3"><span class="rf-num">4</span>Когда ты учился(ась)</h2>
          <div class="rf-chips" id="rf-periods" role="radiogroup" aria-labelledby="rf-h3"></div>
          <p class="rf-error" id="rf-period-error" aria-live="polite"></p>
        </section>
        <section class="rf-step" aria-labelledby="rf-h4">
          <h2 id="rf-h4"><span class="rf-num">5</span>Расскажи подробнее</h2>
          <label class="rf-field"><span>Что понравилось</span><textarea id="rf-positive" rows="4" maxlength="2200" placeholder="Например: понятно объясняют вторую часть, быстро проверяют домашки"></textarea><small class="rf-count" id="rf-positive-count"></small></label>
          <label class="rf-field"><span>Что не понравилось</span><textarea id="rf-negative" rows="4" maxlength="2200" placeholder="Например: много записей вместо живых занятий, куратор отвечал через день"></textarea><small class="rf-count" id="rf-negative-count"></small></label>
          <p class="rf-hint">Пиши о школе и занятиях. Отзывы с именами других учеников, телефонами, ссылками или оскорблениями не публикуем.</p>
          <p class="rf-error" id="rf-text-error" aria-live="polite"></p>
        </section>
        <section class="rf-step" aria-labelledby="rf-h5">
          <h2 id="rf-h5"><span class="rf-num">6</span>Подтверди, что учился(ась) <em>необязательно</em></h2>
          <p class="rf-hint">Скриншот договора, чека или личного кабинета школы. Подтверждённый отзыв входит в оценку школы и преподавателя полностью. Без подтверждения он тоже публикуется и учитывается, но с весом в пять раз меньше.</p>
          <div class="rf-files" id="rf-files"></div>
          <label class="rf-drop" id="rf-drop"><input type="file" id="rf-file-input" accept="image/jpeg,image/png,image/webp" multiple><b>Добавить скриншот</b><small>JPG, PNG или WebP · до 10 МБ · не больше трёх</small></label>
          <p class="rf-note"><b>Закрой на скриншоте</b> ФИО, телефон, номер договора и паспортные данные. Скриншоты видит только модератор: мы пересохраняем их без метаданных и удаляем сразу после проверки.</p>
          <p class="rf-error" id="rf-files-error" aria-live="polite"></p>
        </section>
        <section class="rf-step" aria-labelledby="rf-h6">
          <h2 id="rf-h6"><span class="rf-num">7</span>Почта для кода</h2>
          <label class="rf-field"><span>Электронная почта</span><input type="email" id="rf-email" autocomplete="email" inputmode="email" maxlength="254" placeholder="you@example.ru"></label>
          <p class="rf-hint">Пришлём шестизначный код. Почту не публикуем и не храним: в базе остаётся только её необратимый отпечаток, чтобы один человек оставлял один отзыв о школе или преподавателе.</p>
          <p class="rf-error" id="rf-email-error" aria-live="polite"></p>
          <label class="rf-check"><input type="checkbox" id="rf-consent"><span>Я даю <a href="/consent" target="_blank">согласие на обработку персональных данных</a> и подтверждаю, что мне исполнилось 14 лет. Как мы обрабатываем данные — в <a href="/privacy" target="_blank">политике конфиденциальности</a>.</span></label>
          <p class="rf-error" id="rf-consent-error" aria-live="polite"></p>
          <div class="rf-hp" aria-hidden="true"><label>Это поле заполнять не нужно<input type="text" id="rf-website" tabindex="-1" autocomplete="off"></label></div>
        </section>
        <button type="submit" class="button blue rf-submit" id="rf-submit"><span class="rf-label">Получить код на почту</span><span aria-hidden="true">→</span></button>
        <p class="rf-fine">Отзыв публикуется после модерации — анонимно или с выбранным вами именем. Удалить его можно в любой момент на странице <a href="/delete-data">«Удалить данные»</a>.</p>
      </form>
      <section id="rf-code-step" class="rf-code" hidden>
        <h2>Проверь почту</h2>
        <p>Мы отправили код на <b id="rf-code-email"></b>. Письмо приходит в течение минуты — загляни и в «Спам». Не пришло? Нажми «Отправить код ещё раз» или укажи другую почту: некоторые почтовые сервисы (например, Mail.ru) иногда задерживают такие письма.</p>
        <form id="rf-code-form" novalidate>
          <label class="rf-field"><span>Код из письма</span><input id="rf-code" class="rf-code-input" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000"></label>
          <p class="rf-error" id="rf-code-error" aria-live="polite"></p>
          <button type="submit" class="button blue rf-submit" id="rf-confirm"><span class="rf-label">Подтвердить</span><span aria-hidden="true">→</span></button>
        </form>
        <div class="rf-code-actions"><button type="button" class="rf-link" id="rf-resend" disabled>Отправить код ещё раз</button><button type="button" class="rf-link" id="rf-back">← Исправить отзыв или почту</button></div>
      </section>
      <section id="rf-done" class="rf-done" hidden>
        <div class="rf-done-mark" aria-hidden="true">✓</div>
        <h2>Спасибо! Отзыв на модерации</h2>
        <p>Обычно проверяем за 1–2 дня. После проверки отзыв появится на странице школы и в разделе «Отзывы». Скриншоты удалим сразу после проверки.</p>
        <p id="rf-done-replaced" hidden>Твой прошлый отзыв об этой школе (преподавателе) заменён новым.</p>
        <section class="rf-next" id="rf-next" hidden aria-labelledby="rf-next-title">
          <h3 id="rf-next-title"></h3>
          <p id="rf-next-text"></p>
          <div class="rf-next-row" id="rf-next-row"></div>
        </section>
        <div class="rf-done-actions"><a class="button outline" href="/reviews">Читать отзывы <span>→</span></a><button type="button" class="button pink" id="rf-again">Ещё один отзыв <span>+</span></button></div>
      </section>
    </div>
    <aside class="rf-aside" aria-label="Как мы защищаем отзывы">
      <h2>Честные отзывы</h2>
      <ul>
        <li><b>Без накруток.</b> Каждый отзыв подтверждается кодом из письма, один человек — один отзыв о школе или преподавателе.</li>
        <li><b>Модерация.</b> Каждый отзыв читает человек. Школы не могут удалить или купить отзыв.</li>
        <li><b>Имя — на ваш выбор.</b> Можно подписаться именем или ником, можно остаться анонимным. Почту автора мы никогда не показываем.</li>
        <li><b>Данные в России.</b> Отзывы хранятся на нашем сервере в Москве.</li>
      </ul>
    </aside>
  </div>
</main>"""

DELETE_MAIN = """<main class="rf-page">
  <section class="hero hero-centered rating-centered wrap privacy-hero rf-hero">
    <div class="hero-glow hero-glow-blue" aria-hidden="true"></div><div class="hero-glow hero-glow-pink" aria-hidden="true"></div>
    <div class="hero-copy"><h1><span class="hero-title-line">Удалить</span> <span class="hero-title-line brand-dot">мои данные</span></h1><p class="lead">Удалим все отзывы, оставленные с твоей почты, и всё, что с ними связано. Восстановить их будет нельзя.</p></div>
  </section>
  <div class="wrap rf-layout rf-layout-narrow">
    <div class="rf-card" id="dd-root">
      <p id="rf-alert" class="rf-alert" role="alert" hidden></p>
      <form id="dd-form" novalidate>
        <h2>Отзывы на сайте</h2>
        <label class="rf-field"><span>Почта, с которой ты оставлял отзывы</span><input type="email" id="dd-email" autocomplete="email" inputmode="email" maxlength="254" placeholder="you@example.ru"></label>
        <p class="rf-hint">Пришлём код подтверждения. Мы не подскажем, есть ли у этой почты отзывы: ответ одинаковый для любого адреса.</p>
        <p class="rf-error" id="dd-email-error" aria-live="polite"></p>
        <div class="rf-hp" aria-hidden="true"><label>Это поле заполнять не нужно<input type="text" id="dd-website" tabindex="-1" autocomplete="off"></label></div>
        <button type="submit" class="button blue rf-submit" id="dd-send"><span class="rf-label">Получить код</span><span aria-hidden="true">→</span></button>
      </form>
      <form id="dd-code-form" hidden novalidate>
        <h2>Проверь почту</h2>
        <p>Код отправлен на <b id="dd-code-email"></b>. После ввода кода данные удалятся сразу и навсегда.</p>
        <label class="rf-field"><span>Код из письма</span><input id="dd-code" class="rf-code-input" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000"></label>
        <p class="rf-error" id="dd-code-error" aria-live="polite"></p>
        <button type="submit" class="button pink rf-submit" id="dd-confirm"><span class="rf-label">Удалить навсегда</span><span aria-hidden="true">×</span></button>
      </form>
      <section id="dd-done" class="rf-done" hidden>
        <div class="rf-done-mark" aria-hidden="true">✓</div>
        <h2>Готово</h2>
        <p id="dd-done-text"></p>
      </section>
      <div class="rf-divider"></div>
      <h2>Данные в Telegram-боте</h2>
      <p class="rf-hint">Бот @egematch_bot ничего о пользователях не сохраняет. Если ты пользовался им до 11 октября 2026 года, удалить сохранённые тогда данные можно командой <code>/delete_data</code>.</p>
      <a class="button outline" href="https://t.me/egematch_bot?start=delete_data" target="_blank" rel="noopener">Открыть бота <span>↗</span></a>
      <p class="rf-fine">Если что-то не получается, напиши на <a href="mailto:info@egematch.ru">info@egematch.ru</a> — ответим в течение 30 дней, как требует закон.</p>
    </div>
  </div>
</main>"""

CONSENT_MAIN = f"""<main class="article-page wrap">
  <section class="hero hero-centered rating-centered wrap privacy-hero rf-hero">
    <div class="hero-glow hero-glow-blue" aria-hidden="true"></div><div class="hero-glow hero-glow-pink" aria-hidden="true"></div>
    <div class="hero-copy"><h1><span class="hero-title-line">Согласие</span> <span class="hero-title-line brand-dot">на обработку данных</span></h1><p class="lead">Для отзывов на сайте egematch.ru.</p></div>
  </section>
  <div class="article-body">
  <p><strong>Версия {CONSENT_VERSION}. Действует с 14 октября 2026 г.</strong></p>
  <p>Отмечая поле «Я даю согласие на обработку персональных данных» в форме отзыва на сайте egematch.ru, я свободно, своей волей и в своём интересе даю согласие Стародубцеву Александру Дмитриевичу, ИНН 482623207383, физическому лицу, применяющему специальный налоговый режим «Налог на профессиональный доход» (далее — Оператор), на обработку моих персональных данных на следующих условиях.</p>
  <h2>1. Какие данные</h2>
  <ul>
    <li>адрес электронной почты — используется только для отправки кода подтверждения; в базе данных хранится не адрес, а его необратимый контрольный отпечаток (хеш с секретным ключом);</li>
    <li>текст и оценки отзыва, учебный год, к которому относится отзыв;</li>
    <li>имя или ник — только если я сам указал его в форме; без него отзыв публикуется анонимно;</li>
    <li>скриншоты, подтверждающие обучение, если я их прикладываю, — в пересохранённом виде без метаданных;</li>
    <li>контрольный отпечаток IP-адреса — до решения модерации, для защиты от массовых и поддельных отзывов;</li>
    <li>дата и время отзыва и версия этого согласия.</li>
  </ul>
  <h2>2. Зачем</h2>
  <p>Чтобы проверить, что отзыв оставил реальный человек и один раз; провести модерацию и проверить подтверждение обучения; опубликовать отзыв на сайте анонимно или с указанным мной именем или ником — без почты и иных сведений, позволяющих установить мою личность; учесть оценки в рейтинге школ и преподавателей; выполнить мой запрос на удаление данных.</p>
  <h2>3. Что с ними делают</h2>
  <p>Сбор, запись, систематизация, накопление, хранение, уточнение, извлечение, использование, обезличивание, блокирование, удаление и уничтожение — с использованием средств автоматизации и без них. Публикуются только текст и оценки отзыва и, если я указал, имя или ник; почта и иные идентификаторы не публикуются. Данные не передаются третьим лицам, кроме случаев, прямо предусмотренных законом. Письмо с кодом отправляется через почтовый сервис ООО «Регистратор доменных имён РЕГ.РУ».</p>
  <h2>4. Где и сколько</h2>
  <p>Данные хранятся в базе данных на сервере, расположенном в Российской Федерации (Москва). Неподтверждённый черновик отзыва удаляется через час. Скриншоты удаляются сразу после решения модерации и в любом случае не позднее 30 дней. Отпечаток IP-адреса удаляется при модерации. Отзыв и отпечаток почты хранятся до отзыва согласия или удаления отзыва.</p>
  <h2>5. Срок и отзыв согласия</h2>
  <p>Согласие действует до его отзыва. Отозвать его можно в любой момент на странице <a href="/delete-data">«Удалить данные»</a> (подтверждение кодом из письма) или письмом на <a href="mailto:info@egematch.ru">info@egematch.ru</a>. После отзыва Оператор прекращает обработку и уничтожает данные в течение 10 рабочих дней, а через страницу «Удалить данные» — сразу.</p>
  <h2>6. Возраст</h2>
  <p>Отмечая поле, я подтверждаю, что мне исполнилось 14 лет. Если мне меньше 14 лет, отзыв за меня может оставить родитель или законный представитель.</p>
  <p>Подробнее о том, как Оператор обрабатывает данные, — в <a href="/privacy">Политике конфиденциальности</a>.</p>
  </div>
</main>"""


def _counts():
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    schools, teachers = len(catalog["schools"]), len(catalog["teachers"])
    return schools, f"{teachers // 10 * 10}+"


def about_main():
    schools, teachers = _counts()
    return f"""<main class="article-page wrap">
  <section class="hero hero-centered rating-centered wrap privacy-hero rf-hero">
    <div class="hero-glow hero-glow-blue" aria-hidden="true"></div><div class="hero-glow hero-glow-pink" aria-hidden="true"></div>
    <div class="hero-copy"><h1><span class="hero-title-line">О</span> <span class="hero-title-line brand-dot">проекте</span></h1><p class="lead">ЕГЭ Мэтч помогает выбрать онлайн-школу для подготовки к ЕГЭ осознанно: по понятным критериям и с отзывами учеников.</p></div>
  </section>
  <div class="article-body">
  <h2>Что это</h2>
  <p>ЕГЭ Мэтч — бесплатный каталог и рейтинг онлайн-школ подготовки к ЕГЭ и их преподавателей. Сейчас в нём {schools} школ и {teachers} преподавателей. Мы не школа, не продаём курсы и не участвуем в ваших договорах со школой: мы помогаем сравнить варианты и принять решение самому.</p>
  <h2>Зачем он нужен</h2>
  <p>Школ много, у каждой свои тарифы, формат, кураторы и обещания, и каждая рассказывает о себе только хорошее. Найти честное сравнение сложно. Мы собираем открытую информацию о школах в одном месте, оцениваем их по одним и тем же критериям и показываем, что о них говорят ученики.</p>
  <h2>Что можно сделать на сайте</h2>
  <ul>
    <li><a href="/?start=quiz">Подобрать школу</a> — короткий тест: предмет, бюджет, формат, уровень. В ответе несколько подходящих вариантов и почему.</li>
    <li><a href="/ratings">Смотреть рейтинг</a> — школы и преподаватели по предметам, с ценами, форматом и оценкой по критериям.</li>
    <li><a href="/compare">Сравнить две школы</a> — рядом, по каждому критерию.</li>
    <li><a href="/reviews">Читать отзывы</a> и <a href="/review">оставить свой</a> — можно анонимно или с именем или ником.</li>
    <li><a href="/articles">Читать статьи</a> — как проверять школу до оплаты и на что смотреть.</li>
    <li>Пользоваться <a href="https://t.me/egematch_bot" target="_blank" rel="noopener">Telegram-ботом</a>: рейтинг, курсы и подбор школ в мессенджере.</li>
  </ul>
  <h2>Как считается оценка</h2>
  <p>Оценка школы складывается из двух частей. Редакционная часть — по семи критериям (преподаватели, практика и домашние задания, проверка работ, кураторы, организация, платформа, нагрузка) на основе открытых материалов школы; мы пересматриваем её каждый месяц. Ученическая часть — отзывы: подтверждённые скриншотом обучения весят больше, чем без подтверждения. Чем больше отзывов, тем сильнее они влияют на итог. Подробности и формулы — на странице <a href="/methodology">«Методология»</a>.</p>
  <h2>Кому подойдёт</h2>
  <ul>
    <li>Школьникам 10–11 классов и родителям, которые выбирают первую школу для подготовки к ЕГЭ.</li>
    <li>Тем, кто уже учится и сомневается: можно сравнить свою школу с другими и прочитать, что о ней пишут.</li>
    <li>Тем, кому нужен конкретный предмет или формат (с куратором, без куратора, живые занятия или записи).</li>
  </ul>
  <p>Рейтинг не гарантирует баллов на экзамене: он помогает выбрать, но результат зависит от ученика, его нагрузки и целей.</p>
  <h2>Как мы остаёмся честными</h2>
  <ul>
    <li>Места в рейтинге не продаются. Сотрудничество со школами, в том числе возможное вознаграждение за заявки, не влияет ни на оценку, ни на порядок школ (см. <a href="/terms">Условия использования</a>, раздел 7).</li>
    <li>Каждый отзыв читает модератор; школы не могут удалить или купить отзыв. Накрученные и заказные отзывы мы отклоняем.</li>
    <li>Данные о школах — из открытых источников; сведения, которые опубликовала сама школа, мы помечаем как данные школы. Перед покупкой проверяйте цены и условия на сайте школы.</li>
    <li>Отзывы хранятся на сервере в России, а подробности о данных — в <a href="/privacy">Политике конфиденциальности</a>.</li>
  </ul>
  <h2>Кто за проектом</h2>
  <p>Сервис ведёт независимый автор. Реквизиты оператора указаны в <a href="/privacy">Политике конфиденциальности</a>.</p>
  <h2>Связь</h2>
  <p>Нашли неточность в данных о школе, хотите предложить идею или у вас вопрос? Напишите на <a href="mailto:info@egematch.ru">info@egematch.ru</a> или в <a href="https://t.me/EgeMatch_blog" target="_blank" rel="noopener">Telegram-канал</a>.</p>
  <p class="about-actions"><a class="button blue" href="/?start=quiz">Подобрать школу <span>→</span></a> <a class="button outline" href="/ratings">Смотреть рейтинг <span>→</span></a></p>
  </div>
</main>"""


def main():
    pages = {
        "review.html": page("review", "Оставить отзыв — ЕГЭ Мэтч",
                            "Оставь отзыв об онлайн-школе или преподавателе ЕГЭ: оценки по критериям, плюсы и минусы. Отзывы проходят модерацию.",
                            "review-form-page", REVIEW_MAIN, "review.js"),
        "delete-data.html": page("delete-data", "Удалить мои данные — ЕГЭ Мэтч",
                                 "Удаление отзывов и данных, оставленных на сайте ЕГЭ Мэтч, по коду из письма.",
                                 "review-form-page", DELETE_MAIN, "delete-data.js", index=False),
        "about.html": page("about", "О проекте — ЕГЭ Мэтч",
                           "ЕГЭ Мэтч — бесплатный каталог и рейтинг онлайн-школ подготовки к ЕГЭ: что это за проект, как считается оценка, кому он подойдёт и как мы остаёмся честными.",
                           "article-page-body", about_main()),
        "consent.html": page("consent", "Согласие на обработку персональных данных — ЕГЭ Мэтч",
                             "Текст согласия на обработку персональных данных при отправке отзыва на сайте ЕГЭ Мэтч.",
                             "article-page-body", CONSENT_MAIN, index=False),
    }
    for name, html in pages.items():
        (WEB / name).write_text(html, encoding="utf-8")
    print("built", ", ".join(pages))


if __name__ == "__main__":
    main()
