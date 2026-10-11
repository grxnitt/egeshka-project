'use strict';
// Every piece of review text goes through textContent: nothing a reviewer typed is ever parsed as HTML.
const token = document.querySelector('meta[name="admin-token"]').content;
const list = document.getElementById('list');
const LABELS = {
  teachers_score: 'Преподаватели', practice_score: 'Практика и ДЗ', feedback_score: 'Проверка работ',
  curator_score: 'Кураторы', platform_score: 'Платформа', workload_score: 'Нагрузка и темп',
  organization_score: 'Организация', explanation: 'Объяснение', practice: 'Практика', atmosphere: 'Атмосфера',
  structure: 'Структура и темп', exam_value: 'Польза для экзамена',
};
const PERIODS = {'2026/27': '2026/27 уч. год', '2025/26': '2025/26 уч. год', '2024/25': '2024/25 уч. год', earlier: 'раньше'};
let status = 'pending';

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child != null) node.append(child.nodeType ? child : document.createTextNode(String(child)));
  return node;
}

async function call(method, url, body) {
  const response = await fetch(url, {
    method, headers: method === 'GET' ? {} : {'Content-Type': 'application/json', 'X-Admin-Token': token},
    body: body ? JSON.stringify(body) : undefined, credentials: 'same-origin',
  });
  if (!response.ok) throw new Error(`${response.status}`);
  return response.json();
}

function card(review) {
  const target = review.teacher ? `${review.teacher} · ${review.school}` : `${review.school} (школа целиком)`;
  const scores = el('ul', {class: 'scores'}, ...Object.entries(review.scores).map(([key, value]) =>
    el('li', {}, el('span', {}, LABELS[key] || key), el('b', {}, value))));
  const flags = el('p', {class: 'flags'});
  if (review.samePerson) flags.append(el('span', {class: 'flag'}, `ещё отзывов от этого автора: ${review.samePerson}`));
  if (review.sameNetwork) flags.append(el('span', {class: 'flag warn'}, `с той же сети за 30 дней: ${review.sameNetwork}`));
  const proofs = el('div', {class: 'proofs'}, ...review.proofs.map(p => el('button', {
    type: 'button', class: 'proof', onclick: () => openProof(p.id), 'aria-label': 'Открыть скриншот',
  }, el('img', {src: `/proof/${p.id}`, alt: 'Скриншот подтверждения', loading: 'lazy'}))));
  const actions = el('div', {class: 'actions'});
  if (review.status === 'pending') {
    actions.append(...[
      el('button', {type: 'button', class: 'ok', onclick: () => decide(review.id, 'approve', {verified: false})}, 'Опубликовать'),
      review.proofs.length ? el('button', {type: 'button', class: 'ok strong', onclick: () => decide(review.id, 'approve', {verified: true})}, 'Опубликовать как подтверждённый') : null,
      el('button', {type: 'button', class: 'no', onclick: () => decide(review.id, 'reject')}, 'Отклонить'),
      el('button', {type: 'button', class: 'no soft', onclick: () => {
        if (confirm('Отклонить отзыв и заблокировать автора (его почту)? Он больше не сможет отправлять отзывы.')) decide(review.id, 'reject', {block: 'author', reason: 'накрутка'});
      }}, 'Отклонить и заблокировать автора'),
      el('button', {type: 'button', class: 'no soft', onclick: () => {
        if (confirm('Отклонить отзыв и заблокировать сеть, откуда он пришёл? Это может задеть других людей из той же сети (общий Wi-Fi, один оператор).')) decide(review.id, 'reject', {block: 'network', reason: 'накрутка'});
      }}, 'и сеть'),
    ].filter(Boolean));
  } else {
    actions.append(el('button', {type: 'button', class: 'no', onclick: () => {
      if (confirm('Удалить отзыв навсегда?')) decide(review.id, 'delete');
    }}, 'Удалить'));
  }
  return el('article', {class: 'review'},
    el('header', {}, el('h2', {}, target), el('span', {class: 'score'}, `${review.score}/10`)),
    el('p', {class: 'meta'}, `${review.created.replace('T', ' ')} · учился: ${PERIODS[review.period] || '—'}`,
      review.verified ? ' · подтверждён' : ''),
    flags, scores,
    review.positive ? el('div', {class: 'text'}, el('h3', {}, 'Плюсы'), el('p', {}, review.positive)) : null,
    review.negative ? el('div', {class: 'text'}, el('h3', {}, 'Минусы'), el('p', {}, review.negative)) : null,
    review.proofs.length ? proofs : (review.status === 'pending' ? el('p', {class: 'muted'}, 'Без скриншота подтверждения') : null),
    actions);
}

async function load() {
  list.replaceChildren(el('p', {class: 'muted'}, 'Загрузка…'));
  try {
    const data = await call('GET', `/api/reviews?status=${status}`);
    list.replaceChildren(...(data.reviews.length ? data.reviews.map(card) : [el('p', {class: 'muted'}, 'Пусто.')]));
    if (status === 'pending') document.getElementById('count-pending').textContent = data.reviews.length ? `(${data.reviews.length})` : '';
  } catch (error) {
    list.replaceChildren(el('p', {class: 'error'}, `Не удалось загрузить (${error.message}). Если сервис перезапускался, обнови страницу.`));
  }
}

async function decide(id, action, body = {}) {
  try {
    await call('POST', `/api/reviews/${id}/${action}`, body);
    await load();
  } catch (error) {
    alert(`Не получилось (${error.message}). Обнови страницу и попробуй ещё раз.`);
  }
}

const viewer = document.getElementById('viewer');
function openProof(id) {
  document.getElementById('viewer-img').src = `/proof/${id}`;
  viewer.showModal();
}
document.getElementById('viewer-close').addEventListener('click', () => viewer.close());
viewer.addEventListener('click', event => { if (event.target === viewer) viewer.close(); });

document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-view]').forEach(item => item.classList.toggle('active', item === button));
  document.querySelectorAll('main').forEach(view => { view.hidden = view.id !== `view-${button.dataset.view}`; });
  document.dispatchEvent(new CustomEvent('admin-view', {detail: button.dataset.view}));
}));

document.querySelectorAll('[data-status]').forEach(button => button.addEventListener('click', () => {
  status = button.dataset.status;
  document.querySelectorAll('[data-status]').forEach(item => item.classList.toggle('active', item === button));
  load();
}));
load();
