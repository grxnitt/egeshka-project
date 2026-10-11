'use strict';
// Dashboard, editorial scores, audit log and block list. Uses h / call / toast from partners.js.
const dashboardRoot = document.getElementById('dashboard-root');
const scoresRoot = document.getElementById('scores-root');
const journalRoot = document.getElementById('journal-root');
const STATUS_LABEL = {yes: 'есть', tier: 'зависит от тарифа', none: 'нет у школы'};
const ACTION_LABEL = {
  review_approve: 'Опубликован отзыв', review_reject: 'Отклонён отзыв', review_delete: 'Удалён отзыв',
  partner_save: 'Данные школы', partner_on: 'Школа включена', partner_off: 'Школа выключена', partner_secret: 'Ключ вебхука',
  partner_test: 'Тестовая заявка', leads_global_on: 'Заявки на сайте ВКЛЮЧЕНЫ', leads_global_off: 'Заявки на сайте выключены',
  lead_retry: 'Повторная отправка заявки', lead_paid: 'Заявка: оплатил', lead_unpaid: 'Заявка: оплата снята',
  lead_exclude: 'Заявка исключена', lead_include: 'Заявка возвращена', scores: 'Оценки школы', unblock: 'Снята блокировка',
};
let dashTimer = null, scoreData = null, scoreFilter = '', scoreOpen = null;

const num = value => (value == null ? '—' : String(value).replace('.', ','));

// ---------- dashboard ----------
function stat(label, value, note, tone, view) {
  const card = h('button', {type: 'button', class: `stat${tone ? ` ${tone}` : ''}`, onclick: () => view && document.querySelector(`[data-view="${view}"]`).click()},
    h('small', {}, label), h('strong', {}, value), note ? h('span', {}, note) : null);
  return card;
}

async function loadDashboard() {
  try {
    const [data, health] = await Promise.all([call('GET', '/api/dashboard'), call('GET', '/api/health')]);
    const r = data.reviews, s = data.scores, l = data.leads;
    const monthName = new Date(`${s.month}-01`).toLocaleDateString('ru-RU', {month: 'long'});
    const cards = h('div', {class: 'stats'},
      stat('Отзывы ждут модерации', r.pending, r.pending ? `старейший с ${r.oldest_pending}` : 'очередь пуста', r.pending ? 'warn' : '', 'reviews'),
      stat('Опубликовано отзывов', r.approved, `подтверждённых: ${r.verified}, новых в этом месяце: ${r.new_month}`, '', 'reviews'),
      l ? stat('Заявки школам', l.global ? 'включены' : 'выключены', `школ принимают: ${l.schools_on}, за месяц: ${l.month}${l.waiting ? `, ждут отправки: ${l.waiting}` : ''}`, l.waiting ? 'warn' : (l.global ? 'good' : ''), 'partners') : null,
      stat(`Пересмотр оценок (${monthName})`, `${s.reviewed_this_month} из ${s.total}`, s.reviewed_this_month === s.total ? 'всё проверено' : 'остальные ещё не проверены в этом месяце', s.reviewed_this_month === s.total ? 'good' : '', 'scores'),
      stat('Заблокировано отправителей', data.blocked, 'почты и сети, с которых шла накрутка', '', 'journal'));
    const list = h('ul', {class: 'health'}, health.checks.map(item => h('li', {class: item.ok ? 'is-ok' : 'is-bad'}, h('i', {'aria-hidden': 'true'}), h('b', {}, item.name), h('span', {}, item.detail))));
    dashboardRoot.replaceChildren(
      h('section', {class: `banner ${health.ok ? 'is-on' : 'is-off'}`}, h('div', {}, h('b', {}, health.ok ? 'Всё работает' : 'Есть проблемы'), h('p', {}, `Проверено ${health.at} (МСК). Страница обновляется сама.`)),
        h('button', {type: 'button', class: 'ok', onclick: loadDashboard}, 'Проверить сейчас')),
      cards, h('h2', {class: 'sectitle'}, 'Состояние системы'), list);
  } catch (e) { dashboardRoot.replaceChildren(h('p', {class: 'error'}, `Не удалось загрузить сводку (${e.message}). Обнови страницу.`)); }
}

function startDashboardTimer() {
  clearInterval(dashTimer);
  dashTimer = setInterval(() => { if (!document.getElementById('view-dashboard').hidden) loadDashboard(); }, 60000);
}

// ---------- editorial scores ----------
function editorialPreview(weights, scores, statuses) {
  let total = 0, weight = 0;
  for (const key of Object.keys(weights)) {
    if (statuses[key] === 'none') continue;
    total += scores[key] * weights[key]; weight += weights[key];
  }
  return weight ? Math.round((total / weight) * 10) / 10 : null;
}

function reviewedThisMonth(school) { return school.reviewed_iso && school.reviewed_iso.slice(0, 7) === scoreData.month; }

function scoreCard(school) {
  const open = scoreOpen === school.id;
  const card = h('article', {class: `pcard${open ? ' is-open' : ''}`});
  card.append(h('header', {onclick: () => { scoreOpen = open ? null : school.id; renderScores(); }},
    h('h3', {}, school.name),
    h('span', {class: `pill${reviewedThisMonth(school) ? ' is-live' : ''}`}, reviewedThisMonth(school) ? `проверена ${school.reviewed_at.slice(0, 10)}` : 'не проверена в этом месяце'),
    h('span', {class: 'muted'}, `редакция ${num(school.editorial)} · итог ${num(school.final)} · подтверждённых отзывов: ${school.verified}`),
    h('span', {class: 'chev', 'aria-hidden': 'true'}, open ? '–' : '+')));
  if (!open) return card;
  const inputs = {}, selects = {};
  const preview = h('b', {}, num(school.editorial));
  const reason = h('textarea', {rows: 2, maxlength: 500, placeholder: 'Основание: что проверили и где (сайт школы, оферта, дата). Обязательно, если меняешь оценки.', autocomplete: 'off'});
  const update = () => {
    const scores = {}, statuses = {};
    for (const key of Object.keys(scoreData.labels)) { scores[key] = Number(inputs[key].value); statuses[key] = selects[key].value; inputs[key].disabled = statuses[key] === 'none'; }
    preview.textContent = num(editorialPreview(scoreData.weights, scores, statuses));
  };
  const grid = h('div', {class: 'grid scoregrid'}, Object.entries(scoreData.labels).map(([key, label]) => {
    const input = h('input', {type: 'number', min: 0, max: 10, step: 0.1, 'aria-label': label}); input.value = school.scores[key]; input.addEventListener('input', update); inputs[key] = input;
    const select = h('select', {'aria-label': `Статус: ${label}`}, Object.entries(STATUS_LABEL).map(([value, text]) => h('option', {value}, text))); select.value = school.statuses[key]; select.addEventListener('change', update); selects[key] = select;
    return h('div', {class: 'scorerow'}, h('span', {}, label, h('small', {}, ` вес ${Math.round(scoreData.weights[key] * 100)}%`)), input, select);
  }));
  const collect = () => ({scores: Object.fromEntries(Object.keys(inputs).map(k => [k, Number(inputs[k].value)])), statuses: Object.fromEntries(Object.keys(selects).map(k => [k, selects[k].value])), reason: reason.value});
  const history = h('div', {class: 'history'});
  const save = async (unchanged) => {
    const body = collect();
    const jumps = Object.keys(body.scores).filter(k => Math.abs(body.scores[k] - school.scores[k]) >= scoreData.big_change);
    if (!unchanged && jumps.length && !confirm(`Большое изменение (${jumps.map(k => scoreData.labels[k]).join(', ')}). Точно сохранить?`)) return;
    if (unchanged) { body.scores = {...school.scores}; body.statuses = {...school.statuses}; }
    try {
      const result = await call('POST', `/api/scores/${school.id}/save`, body);
      Object.assign(school, result.school);
      toast(result.changes ? `Сохранено, рейтинг пересчитан (изменений: ${result.changes})` : 'Отмечено как проверенное');
      renderScores();
    } catch (e) { toast(e.message, true); }
  };
  card.append(h('div', {class: 'pform'}, h('p', {class: 'muted'}, 'Эти оценки видят посетители сайта: после сохранения рейтинг пересчитывается сразу. Каждое изменение записывается в историю с основанием.'),
    grid, h('p', {class: 'preview'}, 'Редакционный балл по этим цифрам: ', preview),
    h('label', {class: 'field'}, h('span', {}, 'Основание'), reason)),
    h('div', {class: 'actions'},
      h('button', {type: 'button', class: 'ok strong', onclick: () => save(false)}, 'Сохранить изменения'),
      h('button', {type: 'button', class: 'ok', onclick: () => save(true)}, 'Проверено, без изменений'),
      h('button', {type: 'button', onclick: async () => {
        try {
          const data = await call('GET', `/api/scores/${school.id}/history`);
          const describe = changes => Object.entries(changes).map(([key, [from, to]]) => {
            const base = key.replace(':status', '');
            return `${data.labels[base] || base}${key.endsWith(':status') ? ' (статус)' : ''}: ${from} → ${to}`;
          }).join('; ');
          const entries = data.history.map(item => h('div', {class: 'hentry'}, h('b', {}, item.at), ' — ', item.reason,
            Object.keys(item.changes).length ? h('small', {}, describe(item.changes)) : null));
          history.replaceChildren(...(entries.length ? entries : [h('p', {class: 'muted'}, 'Изменений пока не было.')]));
        } catch (e) { toast(e.message, true); }
      }}, 'Показать историю')),
    history);
  update();
  return card;
}

function renderScores() {
  if (!scoreData) return;
  const done = scoreData.schools.filter(reviewedThisMonth).length;
  const search = h('input', {type: 'search', class: 'search', placeholder: 'Найти школу…', 'aria-label': 'Найти школу'});
  search.value = scoreFilter;
  const list = h('div', {});
  const draw = () => {
    const q = scoreFilter.trim().toLowerCase();
    list.replaceChildren(...scoreData.schools.filter(s => !q || s.name.toLowerCase().includes(q)).map(scoreCard));
  };
  search.addEventListener('input', () => { scoreFilter = search.value; draw(); });
  const bar = h('div', {class: 'progress', role: 'img', 'aria-label': `Проверено ${done} из ${scoreData.schools.length}`}, h('i', {style: `width:${Math.round(done / scoreData.schools.length * 100)}%`}));
  scoresRoot.replaceChildren(
    h('section', {class: 'banner'}, h('div', {}, h('b', {}, `Пересмотр оценок за ${scoreData.month}: ${done} из ${scoreData.schools.length}`),
      h('p', {}, 'Мы обещаем пересматривать редакционную часть 1-го числа каждого месяца. Открой школу, сверь источники (чек-лист в docs/monthly-review.md), поправь оценки или нажми «Проверено, без изменений».')), bar),
    h('div', {class: 'toolbar'}, search), list);
  draw();
}

async function loadScores() {
  scoresRoot.replaceChildren(h('p', {class: 'muted'}, 'Загрузка…'));
  try { scoreData = await call('GET', '/api/scores'); renderScores(); }
  catch (e) { scoresRoot.replaceChildren(h('p', {class: 'error'}, `Не удалось загрузить (${e.message}).`)); }
}

// ---------- journal + block list ----------
async function loadJournal() {
  journalRoot.replaceChildren(h('p', {class: 'muted'}, 'Загрузка…'));
  try {
    const [log, blocked] = await Promise.all([call('GET', '/api/audit'), call('GET', '/api/blocked')]);
    const blockedBox = h('section', {}, h('h2', {class: 'sectitle'}, 'Блокировки'),
      h('p', {class: 'muted'}, 'Почты и сети, с которых отправка отзывов закрыта. Здесь только отпечатки, не сами адреса. Заблокировать можно из карточки отзыва.'),
      blocked.blocked.length ? h('div', {class: 'tablewrap'}, h('table', {class: 'ltable'}, h('thead', {}, h('tr', {}, ['Что', 'Отпечаток', 'Причина', 'Когда', ''].map(t => h('th', {}, t)))),
        h('tbody', {}, blocked.blocked.map(item => h('tr', {}, h('td', {}, item.kind === 'email' ? 'почта автора' : 'сеть'), h('td', {}, `${item.short}…`), h('td', {}, item.reason), h('td', {}, item.at),
          h('td', {}, h('button', {type: 'button', onclick: async () => { if (!confirm('Снять блокировку?')) return; try { await call('POST', `/api/blocked/${item.id}/remove`); loadJournal(); } catch (e) { toast(e.message, true); } }}, 'Снять')))))))
        : h('p', {class: 'muted'}, 'Никто не заблокирован.'));
    const logBox = h('section', {}, h('h2', {class: 'sectitle'}, 'Журнал действий'),
      log.entries.length ? h('div', {class: 'tablewrap'}, h('table', {class: 'ltable'}, h('thead', {}, h('tr', {}, ['Когда (МСК)', 'Что', 'Объект', 'Подробности'].map(t => h('th', {}, t)))),
        h('tbody', {}, log.entries.map(item => h('tr', {}, h('td', {}, item.at), h('td', {}, ACTION_LABEL[item.action] || item.action), h('td', {}, item.target), h('td', {}, item.detail))))))
        : h('p', {class: 'muted'}, 'Записей пока нет.'));
    journalRoot.replaceChildren(blockedBox, logBox);
  } catch (e) { journalRoot.replaceChildren(h('p', {class: 'error'}, `Не удалось загрузить (${e.message}).`)); }
}

document.addEventListener('admin-view', event => {
  if (event.detail === 'dashboard') loadDashboard();
  if (event.detail === 'scores') loadScores();
  if (event.detail === 'journal') loadJournal();
});
loadDashboard();
startDashboardTimer();
