import { applyLiveRatings, fetchPublicReviews } from './supabase-client.js?v=5';

const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = n => Number(n).toFixed(1).replace('.', ',');

const SCHOOL_CRITERIA = {teachers_score:'Преподаватели',practice_score:'Практика и ДЗ',feedback_score:'Проверка работ',curator_score:'Кураторы',platform_score:'Платформа',workload_score:'Нагрузка и темп',organization_score:'Организация обучения'};
const TEACHER_CRITERIA = {explanation:'Объяснение материала',practice:'Практика и разбор ошибок',atmosphere:'Атмосфера и вовлечённость',structure:'Структура и темп занятий',exam_value:'Польза для экзамена'};

let catalog, reviews = [], mode = 'schools', expanded = false;
const params = new URLSearchParams(location.search);
let filterSchool = params.get('school') || '';
let filterTeacher = params.get('teacher') || '';

const schoolBySlug = () => Object.fromEntries((catalog?.schools || []).map(s => [s.reviewSlug, s]));
const schoolById = id => (catalog?.schools || []).find(s => Number(s.id) === Number(id));
const teacherById = id => (catalog?.teachers || []).find(t => Number(t.id) === Number(id));

function criteriaRows(review) {
  const labels = review.teacher_id ? TEACHER_CRITERIA : SCHOOL_CRITERIA;
  let entries = [];
  try {
    const parsed = JSON.parse(review.criteria_json || '{}');
    entries = Object.entries(parsed).filter(([key]) => labels[key]);
  } catch { /* ignore malformed criteria_json */ }
  if (!entries.length && review.criterion && labels[review.criterion]) entries = [[review.criterion, review.score]];
  if (!entries.length) return '';
  return `<ul class="review-criteria">${entries.map(([key, value]) => `<li><span>${escape(labels[key])}</span><b>${number(value)}</b></li>`).join('')}</ul>`;
}

function reviewCard(review) {
  const school = schoolById(review.school_id);
  const teacher = review.teacher_id ? teacherById(review.teacher_id) : null;
  if (!school) return '';
  const target = teacher ? `${escape(teacher.name)} <span>· ${escape(school.name)}</span>` : escape(school.name);
  const link = teacher ? `/teachers/${teacher.slug || ''}` : `/schools/${school.reviewSlug}`;
  const date = review.created_at ? new Date(review.created_at).toLocaleDateString('ru-RU', {day:'numeric', month:'long', year:'numeric'}) : '';
  const texts = [
    review.text_positive ? `<p><b>Плюсы:</b> ${escape(review.text_positive)}</p>` : '',
    review.text_negative ? `<p><b>Минусы:</b> ${escape(review.text_negative)}</p>` : '',
  ].join('');
  return `<article class="review-card">
    <div class="review-card-head">
      <a href="${escape(link)}">${target}</a>
      <span class="review-score">${number(review.score)}<small>/10</small></span>
    </div>
    <div class="review-card-meta">${review.verified ? '<span class="review-verified">✓ подтверждён</span>' : '<span class="review-unverified">без подтверждения</span>'}${date ? `<span>${escape(date)}</span>` : ''}</div>
    ${criteriaRows(review)}
    ${texts || '<p class="review-empty">Без комментария — только оценки.</p>'}
  </article>`;
}

function filteredReviews() {
  return reviews.filter(review => {
    if (mode === 'schools' && review.teacher_id) return false;
    if (mode === 'teachers' && !review.teacher_id) return false;
    if (filterSchool) {
      const school = schoolBySlug()[filterSchool];
      if (!school || Number(review.school_id) !== Number(school.id)) return false;
    }
    if (filterTeacher && Number(review.teacher_id) !== Number(filterTeacher)) return false;
    return true;
  });
}

function comboOptions() {
  if (mode === 'schools') {
    return catalog.schools.slice().sort((a, b) => a.name.localeCompare(b.name, 'ru')).map(s => ({value: s.reviewSlug, label: s.name, sub: ''}));
  }
  return catalog.teachers.slice().sort((a, b) => a.name.localeCompare(b.name, 'ru')).map(t => ({value: String(t.id), label: t.name, sub: t.school}));
}

function currentComboLabel() {
  if (mode === 'schools') {
    const school = filterSchool ? schoolBySlug()[filterSchool] : null;
    return school ? school.name : '';
  }
  const teacher = filterTeacher ? teacherById(filterTeacher) : null;
  return teacher ? `${teacher.name} · ${teacher.school}` : '';
}

let comboMatches = [], comboActive = -1;

function closeCombo() {
  $('#review-filter-list').hidden = true;
  $('#review-filter').setAttribute('aria-expanded', 'false');
  comboActive = -1;
}

function renderCombo(query) {
  const q = query.trim().toLowerCase();
  comboMatches = comboOptions().filter(o => !q || `${o.label} ${o.sub}`.toLowerCase().includes(q));
  comboActive = -1;
  const list = $('#review-filter-list');
  list.innerHTML = comboMatches.length
    ? comboMatches.map((o, i) => `<li role="option" data-index="${i}">${escape(o.label)}${o.sub ? `<span>${escape(o.sub)}</span>` : ''}</li>`).join('')
    : `<li class="review-combo-empty">Ничего не найдено</li>`;
  list.hidden = false;
  $('#review-filter').setAttribute('aria-expanded', 'true');
}

function highlightCombo() {
  $('#review-filter-list').querySelectorAll('li[data-index]').forEach((li, i) => li.classList.toggle('active', i === comboActive));
}

function selectCombo(option) {
  if (mode === 'schools') filterSchool = option.value; else filterTeacher = option.value;
  $('#review-filter').value = option.label + (option.sub ? ` · ${option.sub}` : '');
  $('#review-filter-clear').hidden = false;
  closeCombo();
  expanded = false;
  render();
}

function clearCombo() {
  if (mode === 'schools') filterSchool = ''; else filterTeacher = '';
  $('#review-filter').value = '';
  $('#review-filter-clear').hidden = true;
  closeCombo();
  expanded = false;
  render();
  $('#review-filter').focus();
}

function syncCombo() {
  $('#review-filter').placeholder = mode === 'schools' ? 'Все школы' : 'Все преподаватели';
  $('#review-filter').value = currentComboLabel();
  $('#review-filter-clear').hidden = !currentComboLabel();
  closeCombo();
}

function render() {
  const rows = filteredReviews();
  $('#review-count').textContent = rows.length ? `${rows.length} ${rows.length === 1 ? 'отзыв' : rows.length < 5 ? 'отзыва' : 'отзывов'}` : 'Пока нет отзывов по этому фильтру';
  const shown = rows.slice(0, expanded ? rows.length : 12);
  $('#review-list').innerHTML = shown.length ? shown.map(reviewCard).join('') : '<p class="review-empty-state">Здесь пока пусто — будь первым, кто оставит отзыв в боте.</p>';
  $('#review-more').hidden = expanded || rows.length <= shown.length;
}

document.querySelectorAll('[data-mode]').forEach(button => button.onclick = () => {
  mode = button.dataset.mode;
  filterSchool = ''; filterTeacher = ''; expanded = false;
  document.querySelectorAll('[data-mode]').forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', String(b === button)); });
  syncCombo();
  render();
});
$('#review-more').onclick = () => { expanded = true; render(); };

const comboInput = $('#review-filter');
comboInput.addEventListener('input', () => renderCombo(comboInput.value));
comboInput.addEventListener('focus', () => {
  if (comboInput.value && comboInput.value === currentComboLabel()) { comboInput.select(); renderCombo(''); }
  else renderCombo(comboInput.value);
});
comboInput.addEventListener('keydown', event => {
  const list = $('#review-filter-list');
  if (list.hidden) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { renderCombo(comboInput.value); event.preventDefault(); }
    return;
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    comboActive = Math.min(comboActive + 1, comboMatches.length - 1);
    highlightCombo();
    list.querySelector('li.active')?.scrollIntoView({block: 'nearest'});
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    comboActive = Math.max(comboActive - 1, 0);
    highlightCombo();
    list.querySelector('li.active')?.scrollIntoView({block: 'nearest'});
  } else if (event.key === 'Enter') {
    event.preventDefault();
    const chosen = comboMatches[comboActive >= 0 ? comboActive : 0];
    if (chosen) selectCombo(chosen);
  } else if (event.key === 'Escape') {
    comboInput.value = currentComboLabel();
    closeCombo();
  }
});
$('#review-filter-list').addEventListener('click', event => {
  const li = event.target.closest('li[data-index]');
  if (!li) return;
  const option = comboMatches[Number(li.dataset.index)];
  if (option) selectCombo(option);
});
$('#review-filter-clear').onclick = clearCombo;
document.addEventListener('click', event => {
  if (!$('#review-combo').contains(event.target)) closeCombo();
});

(async () => {
  try {
    const [catalogResponse, linksResponse] = await Promise.all([fetch('catalog.json?v=4'), fetch('links.json')]);
    if (!catalogResponse.ok) throw new Error('catalog');
    catalog = await catalogResponse.json();
    await applyLiveRatings(catalog);
    if (linksResponse.ok) { const links = await linksResponse.json(); $('#review-cta').href = links.bot; }
    reviews = await fetchPublicReviews();
    if (filterTeacher) mode = 'teachers';
    document.querySelectorAll('[data-mode]').forEach(b => { const active = b.dataset.mode === mode; b.classList.toggle('active', active); b.setAttribute('aria-pressed', String(active)); });
    syncCombo();
    render();
  } catch (error) {
    $('#review-list').innerHTML = '<p>Не удалось загрузить отзывы. Обнови страницу, чтобы попробовать ещё раз.</p>';
    console.error(error);
  }
})();
