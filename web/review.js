// "Оставить отзыв": the form posts to our own server in Russia (data.egematch.ru), never to a third party.
// The email is used only to send a one-time code; the server keeps a one-way hash of it, not the address.
const LOCAL = ['localhost', '127.0.0.1'].includes(location.hostname);
const API = LOCAL ? 'http://127.0.0.1:8085' : 'https://data.egematch.ru';
const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const track = (name, params) => { try { window.egeTrack && window.egeTrack(name, params || {}); } catch {} };

const SCHOOL_CRITERIA = [
  ['teachers_score', 'Преподаватели', 'Как объясняют, насколько сильные'],
  ['practice_score', 'Практика и ДЗ', 'Объём и польза домашек, пробники'],
  ['feedback_score', 'Проверка работ', 'Как проверяли работы и разбирали ошибки'],
  ['curator_score', 'Кураторы', 'Поддержка, ответы на вопросы, контроль'],
  ['platform_score', 'Платформа', 'Удобство сайта, приложения, записей'],
  ['workload_score', 'Нагрузка и темп', 'Получалось ли всё успевать'],
  ['organization_score', 'Организация обучения', 'Расписание, понятные условия, поддержка'],
];
const TEACHER_CRITERIA = [
  ['explanation', 'Объяснение материала', 'Понятно ли объясняет'],
  ['practice', 'Практика и разбор ошибок', 'Сколько практики и как разбирает ошибки'],
  ['atmosphere', 'Атмосфера и вовлечённость', 'Хочется ли заниматься'],
  ['structure', 'Структура и темп занятий', 'Логично ли выстроен курс'],
  ['exam_value', 'Польза для экзамена', 'Помогло ли в подготовке к ЕГЭ'],
];
const PERIODS = [['2026/27', '2026/27'], ['2025/26', '2025/26'], ['2024/25', '2024/25'], ['earlier', 'Раньше']];
const MAX_TEXT = 2000, MIN_TEXT_TOTAL = 40, MAX_FILES = 3, MAX_FILE = 10 * 1024 * 1024;
const TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const LINK = /(https?:\/\/|www\.|\b[a-z0-9-]+\.(?:ru|com|net|org|рф|io|me|online|site|pro)\b\/?)/i;

let catalog, form = null;
const state = {kind: 'school', schoolId: null, teacherId: null, scores: {}, period: null, files: [], draftToken: null, email: ''};

function school() { return catalog.schools.find(item => item.id === state.schoolId) || null; }
function teachersOf(id) { return catalog.teachers.filter(t => t.school === catalog.schools.find(s => s.id === id)?.name).sort((a, b) => a.name.localeCompare(b.name, 'ru')); }
function criteriaList() {
  if (state.kind === 'teacher') return TEACHER_CRITERIA.map(([key, label, hint]) => ({key, label, hint, optional: false}));
  const status = school()?.criteriaStatus || {};
  return SCHOOL_CRITERIA.filter(([key]) => status[key] !== 'none')
    .map(([key, label, hint]) => ({key, label, hint, optional: status[key] === 'tier'}));
}

function fieldError(id, message) {
  const node = document.getElementById(`${id}-error`);
  if (node) node.textContent = message || '';
}
function clearErrors() { document.querySelectorAll('.rf-error').forEach(node => { node.textContent = ''; }); $('#rf-alert').hidden = true; }
function alertBox(message) { const box = $('#rf-alert'); box.textContent = message; box.hidden = false; box.scrollIntoView({block: 'center', behavior: 'smooth'}); }

const KIND_HINTS = {
  school: 'Отзыв о школе в целом: организация, кураторы, платформа, проверка работ. Про конкретного преподавателя — отдельный отзыв, вкладка «О преподавателе».',
  teacher: 'Отзыв о конкретном преподавателе: как объясняет, как ведёт занятия. Он попадает в карточку преподавателя, а не в оценку школы целиком.',
};

function renderTarget() {
  $('#rf-kind-hint').textContent = KIND_HINTS[state.kind];
  const schools = [...catalog.schools].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
  $('#rf-school').innerHTML = '<option value="">Выбери школу</option>' + schools.map(s => `<option value="${s.id}"${s.id === state.schoolId ? ' selected' : ''}>${escape(s.name)}</option>`).join('');
  document.querySelectorAll('[data-kind]').forEach(button => {
    const active = button.dataset.kind === state.kind;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  const teacherWrap = $('#rf-teacher-wrap');
  teacherWrap.hidden = state.kind !== 'teacher';
  if (state.kind === 'teacher') {
    const list = state.schoolId ? teachersOf(state.schoolId) : [];
    $('#rf-teacher').disabled = !list.length;
    $('#rf-teacher').innerHTML = `<option value="">${state.schoolId ? (list.length ? 'Выбери преподавателя' : 'У школы пока нет преподавателей в каталоге') : 'Сначала выбери школу'}</option>`
      + list.map(t => `<option value="${t.id}"${t.id === state.teacherId ? ' selected' : ''}>${escape(t.name)} — ${escape((t.subjects || [t.subject]).join(', '))}</option>`).join('');
  }
}

function renderScores() {
  const list = criteriaList();
  const box = $('#rf-scores');
  if (!state.schoolId || (state.kind === 'teacher' && !state.teacherId)) {
    box.innerHTML = `<p class="rf-muted">${state.kind === 'teacher' ? 'Выбери школу и преподавателя — здесь появятся оценки.' : 'Выбери школу — здесь появятся оценки.'}</p>`;
    return;
  }
  const keep = Object.fromEntries(Object.entries(state.scores).filter(([key]) => list.some(item => item.key === key)));
  state.scores = keep;
  box.innerHTML = list.map(({key, label, hint, optional}) => {
    const name = `score-${key}`;
    const pills = Array.from({length: 10}, (_, i) => i + 1).map(n => `<label class="rf-pill"><input type="radio" name="${name}" value="${n}"${state.scores[key] === n ? ' checked' : ''}><span>${n}</span></label>`).join('');
    const skip = optional ? `<label class="rf-pill rf-pill-skip"><input type="radio" name="${name}" value="skip"${state.scores[key] === null ? ' checked' : ''}><span>Не было в моём тарифе</span></label>` : '';
    return `<fieldset class="rf-score" data-key="${key}"><legend><b>${escape(label)}</b><small>${escape(hint)}</small></legend><div class="rf-pills">${pills}${skip}</div></fieldset>`;
  }).join('') + '<p class="rf-muted rf-scale">1 — очень плохо, 10 — отлично.</p>';
  box.querySelectorAll('input[type=radio]').forEach(input => input.addEventListener('change', () => {
    const key = input.closest('.rf-score').dataset.key;
    state.scores[key] = input.value === 'skip' ? null : Number(input.value);
    input.closest('.rf-score').classList.remove('rf-invalid');
    fieldError('rf-scores', '');
  }));
}

function renderPeriods() {
  $('#rf-periods').innerHTML = PERIODS.map(([value, label]) => `<label class="rf-chip"><input type="radio" name="period" value="${value}"${state.period === value ? ' checked' : ''}><span>${label}</span></label>`).join('');
  $('#rf-periods').querySelectorAll('input').forEach(input => input.addEventListener('change', () => { state.period = input.value; fieldError('rf-period', ''); }));
}

function renderFiles() {
  const grid = $('#rf-files');
  grid.querySelectorAll('img').forEach(img => URL.revokeObjectURL(img.src));
  grid.innerHTML = state.files.map((file, i) => `<figure class="rf-file"><img alt="Скриншот ${i + 1}"><button type="button" class="rf-file-remove" data-remove="${i}" aria-label="Убрать скриншот ${i + 1}">×</button></figure>`).join('');
  grid.querySelectorAll('img').forEach((img, i) => { img.src = URL.createObjectURL(state.files[i]); });
  grid.querySelectorAll('[data-remove]').forEach(button => button.addEventListener('click', () => {
    state.files.splice(Number(button.dataset.remove), 1);
    renderFiles();
  }));
  $('#rf-drop').hidden = state.files.length >= MAX_FILES;
}

function addFiles(list) {
  fieldError('rf-files', '');
  for (const file of list) {
    if (state.files.length >= MAX_FILES) { fieldError('rf-files', 'Не больше трёх скриншотов.'); break; }
    if (!TYPES.includes(file.type)) { fieldError('rf-files', 'Подходят только картинки JPG, PNG или WebP.'); continue; }
    if (file.size > MAX_FILE) { fieldError('rf-files', 'Файл больше 10 МБ. Сделай скриншот поменьше.'); continue; }
    state.files.push(file);
  }
  renderFiles();
}

function counter(id) {
  const field = document.getElementById(id);
  const out = document.getElementById(`${id}-count`);
  const update = () => { out.textContent = `${field.value.length} / ${MAX_TEXT}`; out.classList.toggle('rf-over', field.value.length > MAX_TEXT); };
  field.addEventListener('input', update);
  update();
}

function validate() {
  clearErrors();
  let first = null;
  const mark = (id, message, node) => { fieldError(id, message); if (!first) first = node || document.getElementById(id); };
  if (!state.schoolId) mark('rf-target', 'Выбери школу.', $('#rf-school'));
  else if (state.kind === 'teacher' && !state.teacherId) mark('rf-target', 'Выбери преподавателя.', $('#rf-teacher'));
  else {
    const missing = criteriaList().filter(item => !(item.key in state.scores) || (state.scores[item.key] === null && !item.optional));
    missing.forEach(item => document.querySelector(`.rf-score[data-key="${item.key}"]`)?.classList.add('rf-invalid'));
    if (missing.length) mark('rf-scores', `Поставь оценку: ${missing.map(item => item.label[0].toLowerCase() + item.label.slice(1)).join(', ')}.`, document.querySelector('.rf-invalid'));
  }
  if (!state.period) mark('rf-period', 'Укажи, когда ты учился(ась).');
  const positive = $('#rf-positive').value.trim(), negative = $('#rf-negative').value.trim();
  if (positive.length > MAX_TEXT || negative.length > MAX_TEXT) mark('rf-text', `Каждое поле — не длиннее ${MAX_TEXT} символов.`, $('#rf-positive'));
  else if (positive.length + negative.length < MIN_TEXT_TOTAL) mark('rf-text', 'Расскажи чуть подробнее: хотя бы пару предложений о плюсах или минусах.', $('#rf-positive'));
  else if (LINK.test(positive) || LINK.test(negative)) mark('rf-text', 'Ссылки в отзывах не публикуются. Убери их, пожалуйста.', $('#rf-positive'));
  const email = $('#rf-email').value.trim();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) mark('rf-email', 'Проверь адрес почты.', $('#rf-email'));
  if (!$('#rf-consent').checked) mark('rf-consent', 'Нужно согласие на обработку персональных данных.', $('#rf-consent'));
  if (first) { first.scrollIntoView({block: 'center', behavior: 'smooth'}); first.focus?.({preventScroll: true}); }
  return !first;
}

const CONNECTION_HINT = 'Не получилось связаться с сервером. Если включён VPN, блокировщик рекламы или «безопасный DNS», выключи его на этой странице и попробуй снова.';
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

// A failed connection is retried (reading the form token is safe to repeat; a POST is retried only if it never reached us).
async function api(path, options) {
  let response, lastError;
  const attempts = options?.method === 'GET' ? 3 : 2;
  for (let attempt = 0; attempt < attempts && !response; attempt++) {
    try {
      response = await fetch(`${API}${path}`, {...options, credentials: 'omit', mode: 'cors'});
    } catch (error) {
      lastError = error;
      if (attempt < attempts - 1) await pause(700 * (attempt + 1));
    }
  }
  if (!response) throw Object.assign(new Error(CONNECTION_HINT), {network: true});
  let data = {};
  try { data = await response.json(); } catch {}
  if (!response.ok) throw Object.assign(new Error(data.error || 'Что-то пошло не так. Попробуй ещё раз чуть позже.'), {status: response.status});
  return data;
}

async function loadFormToken() {
  form = {...await api('/api/reviews/form', {method: 'GET'}), loadedAt: Date.now()};
}

// The server refuses a form sent within seconds of opening it (that is how scripts behave). Someone who submits
// right after the token was (re)loaded just waits out the remainder instead of seeing an error.
async function tokenAged() {
  const wait = 9000 - (Date.now() - form.loadedAt);
  if (wait > 0) await new Promise(resolve => setTimeout(resolve, wait));
}

function busy(button, on, label) {
  button.disabled = on;
  button.classList.toggle('rf-busy', on);
  if (label) button.querySelector('.rf-label').textContent = label;
}

async function submit(event) {
  event.preventDefault();
  if (!validate()) return;
  const button = $('#rf-submit');
  busy(button, true, state.files.length ? 'Загружаем скриншоты…' : 'Отправляем…');
  try {
    if (!form) await loadFormToken();
    await tokenAged();
    state.email = $('#rf-email').value.trim();
    const payload = {
      school_id: state.schoolId, teacher_id: state.kind === 'teacher' ? state.teacherId : null,
      scores: Object.fromEntries(Object.entries(state.scores).filter(([, value]) => value !== null)),
      positive: $('#rf-positive').value, negative: $('#rf-negative').value, period: state.period,
      email: state.email, consent: $('#rf-consent').checked, consent_version: form.consentVersion,
      formToken: form.formToken, website: $('#rf-website').value,
    };
    const body = new FormData();
    body.append('payload', JSON.stringify(payload));
    state.files.forEach(file => body.append('proof', file, 'proof'));
    const result = await api('/api/reviews/draft', {method: 'POST', body});
    state.draftToken = result.draftToken;
    track('review_draft_sent', {kind: state.kind, proofs: state.files.length});
    showCode(result.email, result.resendIn);
  } catch (error) {
    if (error.status === 400 && /устарела|быстро/.test(error.message)) form = null;   // a fresh token next time
    alertBox(error.message);
  } finally {
    busy(button, false, 'Получить код на почту');
  }
}

let resendTimer = null;
function startResendTimer(seconds) {
  const button = $('#rf-resend');
  clearInterval(resendTimer);
  let left = seconds;
  const tick = () => {
    button.disabled = left > 0;
    button.textContent = left > 0 ? `Отправить код ещё раз через ${left} с` : 'Отправить код ещё раз';
    if (left-- <= 0) clearInterval(resendTimer);
  };
  tick();
  resendTimer = setInterval(tick, 1000);
}

function showCode(maskedEmail, resendIn) {
  $('#rf-form').hidden = true;
  $('#rf-code-step').hidden = false;
  $('#rf-code-email').textContent = maskedEmail;
  $('#rf-code').value = '';
  fieldError('rf-code', '');
  startResendTimer(resendIn || 60);
  $('#rf-code-step').scrollIntoView({block: 'start', behavior: 'smooth'});
  setTimeout(() => $('#rf-code').focus(), 300);
}

async function confirmCode(event) {
  event.preventDefault();
  const code = $('#rf-code').value.replace(/\D/g, '');
  if (code.length !== 6) { fieldError('rf-code', 'Код — шесть цифр из письма.'); return; }
  const button = $('#rf-confirm');
  busy(button, true, 'Проверяем…');
  try {
    const result = await api('/api/reviews/confirm', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({draftToken: state.draftToken, code})});
    track('review_confirmed', {kind: state.kind});
    state.files = [];
    try { sessionStorage.setItem('rf-email', state.email); } catch {}   // only this tab: the next review is quicker
    $('#rf-code-step').hidden = true;
    $('#rf-done').hidden = false;
    $('#rf-done-replaced').hidden = !result.replaced;
    $('#rf-done-replaced').textContent = `Твой прошлый отзыв ${state.kind === 'school' ? 'об этой школе' : 'об этом преподавателе'} заменён новым.`;
    renderNext();
    $('#rf-done').scrollIntoView({block: 'start', behavior: 'smooth'});
  } catch (error) {
    fieldError('rf-code', error.message);
  } finally {
    busy(button, false, 'Подтвердить');
  }
}

async function resend() {
  fieldError('rf-code', '');
  try {
    const result = await api('/api/reviews/resend', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({draftToken: state.draftToken, email: state.email})});
    startResendTimer(result.resendIn || 60);
  } catch (error) {
    fieldError('rf-code', error.message);
  }
}

// The hook after a review: from a school to one of its teachers, from a teacher to the school as a whole.
function renderNext() {
  const owner = school();
  if (!owner) return;
  const others = teachersOf(owner.id).filter(t => t.id !== state.teacherId);
  const picker = (label, lead) => `<div class="rf-next-option">${lead ? `<p class="rf-next-lead">${lead}</p>` : ''}<div class="rf-next-pick"><select id="rf-next-teacher" aria-label="Преподаватель">${others.map(t => `<option value="${escape(t.slug || '')}">${escape(t.name)} — ${escape((t.subjects || [t.subject]).join(', '))}</option>`).join('')}</select><a class="button outline" id="rf-next-go" href="#">${label} <span>→</span></a></div></div>`;
  if (state.kind === 'school') {
    if (!others.length) return;
    $('#rf-next-title').textContent = 'Учился у конкретного преподавателя?';
    $('#rf-next-text').textContent = `Оцени его отдельно: о школе ты рассказал про организацию и сервис, а о преподавателе расскажешь, как он объясняет. Отзыв появится в карточке преподавателя ${owner.name}.`;
    $('#rf-next-row').innerHTML = picker('Оценить');
  } else {
    $('#rf-next-title').textContent = `А как тебе ${owner.name} в целом?`;
    $('#rf-next-text').textContent = 'Отзыв о школе отдельный: про организацию, кураторов, платформу и проверку работ. Он влияет на оценку школы.';
    $('#rf-next-row').innerHTML = `<div class="rf-next-option"><a class="button blue rf-next-school" href="/review?school=${encodeURIComponent(owner.reviewSlug)}">Оценить школу <span>→</span></a></div>`
      + (others.length ? `<div class="rf-next-or" aria-hidden="true"><span>или</span></div>${picker('Оценить', 'Другого преподавателя этой школы')}` : '');
  }
  const go = $('#rf-next-go');
  if (go) go.addEventListener('click', event => {
    event.preventDefault();
    const slug = $('#rf-next-teacher')?.value;
    if (slug) location.assign(`/review?teacher=${encodeURIComponent(slug)}`);
  });
  $('#rf-next').hidden = false;
}

function backToForm() {
  $('#rf-code-step').hidden = true;
  $('#rf-form').hidden = false;
  $('#rf-form').scrollIntoView({block: 'start', behavior: 'smooth'});
}

function bind() {
  document.querySelectorAll('[data-kind]').forEach(button => button.addEventListener('click', () => {
    state.kind = button.dataset.kind;
    state.teacherId = null;
    state.scores = {};
    fieldError('rf-target', '');
    renderTarget();
    renderScores();
  }));
  $('#rf-school').addEventListener('change', event => {
    state.schoolId = Number(event.target.value) || null;
    state.teacherId = null;
    fieldError('rf-target', '');
    renderTarget();
    renderScores();
  });
  $('#rf-teacher').addEventListener('change', event => {
    state.teacherId = Number(event.target.value) || null;
    fieldError('rf-target', '');
    renderScores();
  });
  const input = $('#rf-file-input');
  input.addEventListener('change', () => { addFiles([...input.files]); input.value = ''; });
  const drop = $('#rf-drop');
  ['dragenter', 'dragover'].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.add('rf-drag'); }));
  ['dragleave', 'drop'].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.remove('rf-drag'); }));
  drop.addEventListener('drop', event => addFiles([...(event.dataTransfer?.files || [])]));
  counter('rf-positive');
  counter('rf-negative');
  $('#rf-form').addEventListener('submit', submit);
  $('#rf-code-form').addEventListener('submit', confirmCode);
  $('#rf-code').addEventListener('input', event => { event.target.value = event.target.value.replace(/\D/g, '').slice(0, 6); });
  $('#rf-resend').addEventListener('click', resend);
  $('#rf-back').addEventListener('click', backToForm);
  $('#rf-again').addEventListener('click', () => location.assign('/review'));
}

function prefill() {
  const params = new URLSearchParams(location.search);
  const target = catalog.schools.find(s => s.reviewSlug === params.get('school'));
  if (target) state.schoolId = target.id;
  const teacher = catalog.teachers.find(t => t.slug && t.slug === params.get('teacher'));
  if (teacher) {
    const owner = catalog.schools.find(s => s.name === teacher.school);
    if (owner) { state.kind = 'teacher'; state.schoolId = owner.id; state.teacherId = teacher.id; }
  }
}

async function start() {
  try {
    const response = await fetch('catalog.json?v=9');
    if (!response.ok) throw new Error('catalog');
    catalog = await response.json();
  } catch {
    $('#rf-root').innerHTML = '<p class="rf-alert">Не удалось загрузить каталог школ. Обнови страницу.</p>';
    return;
  }
  prefill();
  try { const saved = sessionStorage.getItem('rf-email'); if (saved) $('#rf-email').value = saved; } catch {}
  bind();
  renderTarget();
  renderScores();
  renderPeriods();
  renderFiles();
  $('#rf-root').removeAttribute('aria-busy');
  // Coming from a school page's "Вы учились здесь?" card: the school is already chosen, so start at the scores.
  if (new URLSearchParams(location.search).get('ref') === 'school_card' && state.schoolId) {
    setTimeout(() => $('#rf-h2')?.scrollIntoView({block: 'start', behavior: 'smooth'}), 150);
  }
  loadFormToken().catch(() => {
    alertBox(CONNECTION_HINT);
    const retry = document.createElement('button');
    retry.type = 'button'; retry.className = 'rf-link'; retry.textContent = 'Повторить';
    retry.addEventListener('click', () => { clearErrors(); loadFormToken().catch(() => { alertBox(CONNECTION_HINT); }); });
    $('#rf-alert').append(' ', retry);
  });
}

start();
