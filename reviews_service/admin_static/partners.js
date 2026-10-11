'use strict';
// Schools (partnerships) and leads. Everything a school or a student typed goes through textContent / value:
// nothing is ever parsed as HTML.
const tokenMeta = document.querySelector('meta[name="admin-token"]').content;
const partnersRoot = document.getElementById('partners-root');
const leadsRoot = document.getElementById('leads-root');
const CONTACTS = {phone: 'Телефон', telegram: 'Telegram', vk: 'VK', email: 'Почта'};
const STATUS = {new: 'ждёт отправки', sent: 'доставлена', failed: 'ошибка доставки', withdrawn: 'отозвана'};
let overview = null, filterText = '', openId = null;

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, '');
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child != null && child !== false) node.append(child.nodeType ? child : document.createTextNode(String(child)));
  return node;
}

async function call(method, url, body) {
  const response = await fetch(url, {
    method, headers: method === 'GET' ? {} : {'Content-Type': 'application/json', 'X-Admin-Token': tokenMeta},
    body: body ? JSON.stringify(body) : undefined, credentials: 'same-origin',
  });
  let data = {};
  try { data = await response.json(); } catch {}
  if (!response.ok) throw new Error(data.error || `Ошибка ${response.status}`);
  return data;
}

function toast(message, bad) {
  const node = h('div', {class: `toast${bad ? ' bad' : ''}`, role: 'status'}, message);
  document.body.append(node);
  setTimeout(() => node.remove(), bad ? 6000 : 3000);
}

// ---------- the global switch ----------
function globalBanner() {
  const on = overview.global.enabled;
  const box = h('section', {class: `banner ${on ? 'is-on' : 'is-off'}`});
  box.append(h('div', {}, h('b', {}, on ? 'Заявки на сайте включены' : 'Заявки на сайте выключены'),
    h('p', {}, on ? 'У школ с включённым переключателем «Выбрать школу» открывает форму заявки.' : 'Пока выключатель стоит здесь, ни одна школа не получает заявки, даже если у неё включён свой переключатель. Кнопка «Выбрать школу» ведёт на сайт школы.')));
  const panel = h('div', {class: 'banner-panel', hidden: true});
  if (on) {
    box.append(h('button', {type: 'button', class: 'no', onclick: async () => {
      if (!confirm('Выключить заявки на всём сайте?')) return;
      try { await call('POST', '/api/partners/global', {enabled: false}); await loadPartners(); } catch (e) { toast(e.message, true); }
    }}, 'Выключить'));
  } else {
    const rkn = h('input', {type: 'checkbox', id: 'g-rkn'}), tax = h('input', {type: 'checkbox', id: 'g-tax'});
    const word = h('input', {type: 'text', id: 'g-word', placeholder: overview.word, autocomplete: 'off'});
    panel.append(
      h('label', {class: 'check'}, rkn, 'Уведомление в Роскомнадзор о начале обработки персональных данных подано'),
      h('label', {class: 'check'}, tax, 'Ответ налогового органа получен, схема оплаты заявок согласована'),
      h('label', {class: 'field'}, h('span', {}, `Введи слово «${overview.word}»`), word),
      h('button', {type: 'button', class: 'ok strong', onclick: async () => {
        try { await call('POST', '/api/partners/global', {enabled: true, rkn: rkn.checked, tax: tax.checked, word: word.value.trim()}); await loadPartners(); } catch (e) { toast(e.message, true); }
      }}, 'Включить заявки на сайте'));
    box.append(h('button', {type: 'button', class: 'ok', onclick: () => { panel.hidden = !panel.hidden; }}, 'Включить…'));
  }
  const wrap = h('div', {}, box, panel);
  return wrap;
}

// ---------- one school ----------
function pill(school) {
  if (school.enabled) return h('span', {class: 'pill is-live'}, 'Принимает заявки');
  if (school.missing.length) return h('span', {class: 'pill'}, `Не хватает: ${school.missing.length}`);
  return h('span', {class: 'pill is-ready'}, 'Готова к запуску');
}

function field(label, name, value, opts = {}) {
  const input = h(opts.area ? 'textarea' : 'input', {type: opts.type || 'text', name, rows: opts.area ? 3 : null, placeholder: opts.placeholder || '', maxlength: opts.max || null, autocomplete: 'off'});
  input.value = value ?? '';
  return h('label', {class: 'field'}, h('span', {}, label), input, opts.hint ? h('small', {}, opts.hint) : null);
}

function schoolForm(school) {
  const form = h('form', {class: 'pform', novalidate: true});
  const contacts = Object.entries(CONTACTS).map(([key, label]) => {
    const box = h('input', {type: 'checkbox', name: `contact-${key}`});
    box.checked = school.contact_types.includes(key);
    return h('label', {class: 'check'}, box, label);
  });
  const secretNote = h('small', {class: 'muted'}, school.has_secret ? 'Ключ подписи уже выдан.' : 'Ключ подписи ещё не создан.');
  form.append(
    h('fieldset', {}, h('legend', {}, '1. Школа как получатель данных'),
      h('p', {class: 'muted'}, 'Эти данные попадают в текст согласия, которое видит ученик. Они должны совпадать с договором.'),
      h('div', {class: 'grid'},
        field('Юрлицо', 'legal_name', school.legal_name, {placeholder: 'ООО «…» или ИП …'}),
        field('ИНН', 'inn', school.inn, {placeholder: '10 или 12 цифр'}),
        field('Политика школы (ссылка)', 'policy_url', school.policy_url, {placeholder: 'https://…'}),
        field('Кому школа получает уведомления об отзыве согласия', 'pd_contact', school.pd_contact, {hint: 'почта или имя ответственного'}),
        field('Кто в школе обрабатывает заявки', 'sales_contact', school.sales_contact),
        field('Дата договора', 'agreement_date', school.agreement_date, {type: 'date'}))),
    h('fieldset', {}, h('legend', {}, '2. Как ученик может оставить контакт'),
      h('p', {class: 'muted'}, 'Выключи способ, который школа не принимает: он пропадёт из формы.'),
      h('div', {class: 'checks'}, contacts)),
    h('fieldset', {}, h('legend', {}, '3. Куда доставлять заявки'),
      h('p', {class: 'muted'}, 'Пустое поле значит, что канал выключен. Хватит одного. Если включено несколько, заявка считается доставленной, когда сработали все.'),
      h('div', {class: 'grid'},
        field('Почта школы', 'delivery_email', school.delivery_email, {placeholder: 'zayavki@school.ru'}),
        field('Чат Telegram школы', 'tg_chat_id', school.tg_chat_id, {placeholder: '-1001234567890', hint: overview.telegram_relay ? 'работает через ретранслятор' : 'С российского сервера Telegram сейчас недоступен: пока не настроен ретранслятор, этот канал не сработает.'}),
        field('CRM (адрес вебхука)', 'webhook_url', school.webhook_url, {placeholder: 'https://crm.school.ru/hook'})),
      h('div', {class: 'row'}, h('button', {type: 'button', onclick: async () => {
        if (school.has_secret && !confirm('Старый ключ перестанет работать. Создать новый?')) return;
        try {
          const result = await call('POST', `/api/partners/${school.id}/secret`);
          prompt('Ключ подписи вебхука (показывается один раз, передай его школе):', result.secret);
          school.has_secret = true; secretNote.textContent = 'Ключ подписи создан.';
        } catch (e) { toast(e.message, true); }
      }}, 'Создать ключ подписи вебхука'), secretNote)),
    h('fieldset', {}, h('legend', {}, '4. Условия (видишь только ты, на сайте не показывается)'),
      h('div', {class: 'grid'},
        field('Ставка за заявку, ₽', 'rate', school.rate, {type: 'number', hint: '0 — без оплаты за заявки'}),
        field('Бонус за оплатившего, ₽', 'bonus_fixed', school.bonus_fixed, {type: 'number'}),
        field('или процент от первого платежа', 'bonus_percent', school.bonus_percent, {type: 'number'}),
        field('минимум при проценте, ₽', 'bonus_min', school.bonus_min, {type: 'number'})),
      field('Заметки', 'notes', school.notes, {area: true, max: 4000})));
  return form;
}

function readForm(form) {
  const data = {contact_types: Object.keys(CONTACTS).filter(key => form.elements[`contact-${key}`].checked)};
  for (const name of ['legal_name', 'inn', 'policy_url', 'pd_contact', 'sales_contact', 'agreement_date', 'delivery_email', 'tg_chat_id', 'webhook_url', 'notes'])
    data[name] = form.elements[name].value;
  for (const name of ['rate', 'bonus_fixed', 'bonus_percent', 'bonus_min']) data[name] = form.elements[name].value === '' ? 0 : form.elements[name].value;
  return data;
}

function schoolCard(school) {
  const open = openId === school.id;
  const card = h('article', {class: `pcard${open ? ' is-open' : ''}`});
  const stats = school.counts.total ? `заявок: ${school.counts.total}, доставлено: ${school.counts.sent}${school.counts.waiting ? `, ждут: ${school.counts.waiting}` : ''}` : 'заявок пока нет';
  card.append(h('header', {onclick: () => { openId = open ? null : school.id; renderPartners(); }},
    h('h3', {}, school.name), pill(school), h('span', {class: 'muted'}, stats), h('span', {class: 'chev', 'aria-hidden': 'true'}, open ? '–' : '+')));
  if (!open) return card;
  const form = schoolForm(school);
  const toggle = h('input', {type: 'checkbox', role: 'switch', id: `sw-${school.id}`, disabled: !school.enabled && school.missing.length > 0});
  toggle.checked = school.enabled;
  toggle.addEventListener('change', async () => {
    try {
      const saved = await call('POST', `/api/partners/${school.id}/save`, readForm(form));
      Object.assign(school, saved.school);
      const result = await call('POST', `/api/partners/${school.id}/switch`, {enabled: toggle.checked});
      Object.assign(school, result.school);
      toast(school.enabled ? `«${school.name}» принимает заявки` : `«${school.name}» поставлена на паузу`);
      renderPartners();
    } catch (e) { toggle.checked = !toggle.checked; toast(e.message, true); }
  });
  const missing = school.missing.length ? h('p', {class: 'missing'}, 'Чтобы включить, заполни: ', school.missing.join(', '), '.') : null;
  const month = h('input', {type: 'month', value: new Date().toISOString().slice(0, 7)});
  card.append(
    h('div', {class: 'switchbar'}, h('label', {class: 'switch', for: `sw-${school.id}`}, toggle, h('span', {class: 'track'}), h('b', {}, 'Принимает заявки')),
      !overview.global.enabled ? h('small', {class: 'muted'}, 'Главный выключатель сейчас выключен: заявки не принимаются, пока его не включишь.') : null),
    missing, form,
    h('div', {class: 'actions'},
      h('button', {type: 'button', class: 'ok strong', onclick: async () => {
        try {
          const saved = await call('POST', `/api/partners/${school.id}/save`, readForm(form));
          Object.assign(school, saved.school); toast('Сохранено'); renderPartners();
        } catch (e) { toast(e.message, true); }
      }}, 'Сохранить'),
      h('button', {type: 'button', class: 'ok', onclick: async () => {
        try {
          const saved = await call('POST', `/api/partners/${school.id}/save`, readForm(form));
          Object.assign(school, saved.school);
          const result = await call('POST', `/api/partners/${school.id}/test`);
          toast(result.ok ? `Тестовая заявка №${result.id} доставлена (${result.channels || '—'})` : `Тест не прошёл: ${result.error}`, !result.ok);
        } catch (e) { toast(e.message, true); }
      }}, 'Отправить тестовую заявку'),
      h('span', {class: 'report'}, month, h('a', {class: 'button-link', href: '#', onclick: event => {
        event.preventDefault();
        location.href = `/api/lead-report?school=${school.id}&month=${encodeURIComponent(month.value)}`;
      }}, 'Скачать отчёт за месяц'))));
  return card;
}

function renderPartners() {
  if (!overview) return;
  const search = h('input', {type: 'search', class: 'search', placeholder: 'Найти школу…', 'aria-label': 'Найти школу'});
  search.value = filterText;
  search.addEventListener('input', () => { filterText = search.value; renderList(); });
  const list = h('div', {id: 'pcards'});
  partnersRoot.replaceChildren(globalBanner(), h('div', {class: 'toolbar'}, search,
    h('span', {class: 'muted'}, `Принимают заявки: ${overview.schools.filter(s => s.enabled).length} из ${overview.schools.length}`)), list);
  renderList();
  function renderList() {
    const query = filterText.trim().toLowerCase();
    list.replaceChildren(...overview.schools.filter(s => !query || s.name.toLowerCase().includes(query)).map(schoolCard));
  }
}

async function loadPartners() {
  partnersRoot.replaceChildren(h('p', {class: 'muted'}, 'Загрузка…'));
  try { overview = await call('GET', '/api/partners'); renderPartners(); }
  catch (e) { partnersRoot.replaceChildren(h('p', {class: 'error'}, `Не удалось загрузить (${e.message}). Обнови страницу.`)); }
}

// ---------- leads ----------
async function loadLeads() {
  leadsRoot.replaceChildren(h('p', {class: 'muted'}, 'Загрузка…'));
  try {
    const data = await call('GET', '/api/leads');
    if (!data.leads.length) { leadsRoot.replaceChildren(h('p', {class: 'muted'}, 'Заявок пока нет.')); return; }
    const rows = data.leads.map(lead => h('tr', {class: lead.test ? 'is-test' : ''},
      h('td', {}, `№${lead.id}${lead.test ? ' (тест)' : ''}`), h('td', {}, lead.created), h('td', {}, lead.school),
      h('td', {}, lead.subject), h('td', {}, CONTACTS[lead.contact_type] || lead.contact_type),
      h('td', {}, h('span', {class: `pill${lead.status === 'sent' ? ' is-live' : ''}`}, STATUS[lead.status] || lead.status), lead.error ? h('small', {class: 'muted'}, ` ${lead.error}`) : null),
      h('td', {}, lead.excluded ? `исключена: ${lead.excluded}` : (lead.paid ? `оплатил ${lead.paid}${lead.first_payment ? `, ${lead.first_payment} ₽` : ''}` : '—')),
      h('td', {class: 'rowactions'},
        lead.status !== 'withdrawn' ? h('button', {type: 'button', onclick: async () => { try { const r = await call('POST', `/api/leads/${lead.id}/retry`); toast(r.ok ? 'Доставлена' : `Не доставлена: ${r.error}`, !r.ok); loadLeads(); } catch (e) { toast(e.message, true); } }}, 'Отправить снова') : null,
        !lead.test && lead.status === 'sent' && !lead.paid ? h('button', {type: 'button', onclick: async () => { const sum = prompt('Первый платёж, ₽ (можно 0):', '0'); if (sum === null) return; try { await call('POST', `/api/leads/${lead.id}/paid`, {first_payment: Number(sum) || 0}); loadLeads(); } catch (e) { toast(e.message, true); } }}, 'Оплатил') : null,
        !lead.test && !lead.excluded ? h('button', {type: 'button', onclick: async () => { const reason = prompt('Причина исключения (спор школы):'); if (!reason) return; try { await call('POST', `/api/leads/${lead.id}/exclude`, {reason}); loadLeads(); } catch (e) { toast(e.message, true); } }}, 'Исключить') : null,
        lead.excluded ? h('button', {type: 'button', onclick: async () => { try { await call('POST', `/api/leads/${lead.id}/include`); loadLeads(); } catch (e) { toast(e.message, true); } }}, 'Вернуть') : null)));
    leadsRoot.replaceChildren(
      h('p', {class: 'hint'}, 'Имён и контактов учеников здесь нет: они хранятся в базе только для доставки школе и удаляются через 365 дней или по отзыву согласия.'),
      h('div', {class: 'tablewrap'}, h('table', {class: 'ltable'}, h('thead', {}, h('tr', {}, ['Заявка', 'Когда (МСК)', 'Школа', 'Предмет', 'Контакт', 'Статус', 'Оплата', ''].map(t => h('th', {}, t)))), h('tbody', {}, rows))));
  } catch (e) { leadsRoot.replaceChildren(h('p', {class: 'error'}, `Не удалось загрузить (${e.message}).`)); }
}

document.addEventListener('admin-view', event => {
  if (event.detail === 'partners') loadPartners();
  if (event.detail === 'leads') loadLeads();
});
