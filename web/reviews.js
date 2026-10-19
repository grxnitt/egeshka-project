import { applyLiveRatings, fetchPublicReviews } from './supabase-client.js?v=11';
import { wireReviewExpand } from './review-expand.js?v=1';
import { schoolInitial, schoolLogos, schoolTone } from './school-content.js?v=53';

const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = n => Number(n).toFixed(1).replace('.', ',');
const grade = n => Number.isInteger(Number(n)) ? String(Number(n)) : number(n);   // review scores are whole numbers 1-10
const PERIODS = {'2026/27': 'учился(ась) в 2026/27', '2025/26': 'учился(ась) в 2025/26', '2024/25': 'учился(ась) в 2024/25', earlier: 'учился(ась) раньше 2024 года'};

const SCHOOL_CRITERIA = {teachers_score:'Преподаватели',practice_score:'Практика и ДЗ',feedback_score:'Проверка работ',curator_score:'Кураторы',platform_score:'Платформа',workload_score:'Нагрузка и темп',organization_score:'Организация обучения'};
const TEACHER_CRITERIA = {explanation:'Объяснение материала',practice:'Практика и разбор ошибок',atmosphere:'Атмосфера и вовлечённость',structure:'Структура и темп занятий',exam_value:'Польза для экзамена'};

const PAGE = 6;   // reviews shown at first and added by each "Показать ещё"
let catalog, reviews = [], mode = 'schools', limit = PAGE;
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
  return `<ul class="review-criteria">${entries.map(([key, value]) => `<li><span>${escape(labels[key])}</span><b>${grade(value)}</b></li>`).join('')}</ul>`;
}

function mark(school) {
  const logo = schoolLogos[school.name], letters = schoolInitial(school.name);
  return `<span class="school-mark review-school-mark ${logo ? 'school-mark-logo ' : ''}${schoolTone(school.name)}-mark${letters.length > 1 ? ' is-long' : ''}" aria-hidden="true"><b>${escape(letters)}</b>${logo ? `<img src="${escape(logo)}" alt="" loading="lazy">` : ''}</span>`;
}

function reviewCard(review) {
  const school = schoolById(review.school_id);
  const teacher = review.teacher_id ? teacherById(review.teacher_id) : null;
  if (!school) return '';
  const link = teacher ? `/teachers/${teacher.slug || ''}` : `/schools/${school.reviewSlug}`;
  const title = teacher ? escape(teacher.name) : escape(school.name);
  const subtitle = teacher ? `${escape((teacher.subjects || [teacher.subject]).join(', '))} · ${escape(school.name)}` : 'школа целиком';
  const date = review.created_at ? new Date(review.created_at).toLocaleDateString('ru-RU', {day: 'numeric', month: 'long', year: 'numeric'}) : '';
  const meta = [
    review.display_name ? `<span class="review-author">${escape(review.display_name)}</span>` : '<span class="review-author is-anon">Аноним</span>',
    review.verified ? '<span class="review-badge is-verified">✓ подтверждён</span>' : '<span class="review-badge">без подтверждения</span>',
    date ? `<span>${escape(date)}</span>` : '',
    PERIODS[review.study_period] ? `<span>${PERIODS[review.study_period]}</span>` : '',
  ].join('');
  const block = (title, text, cls) => `<div class="review-text ${cls}${text ? '' : ' is-blank'}"><h4>${title}</h4><p>${text ? escape(text) : 'Не указано'}</p></div>`;
  const texts = review.text_positive || review.text_negative
    ? block('Понравилось', review.text_positive, 'is-plus') + block('Не понравилось', review.text_negative, 'is-minus')
    : '<div class="review-text is-none"><p class="review-empty">Без комментария — только оценки.</p></div>';
  return `<article class="review-card">
    <header class="review-card-head">
      ${mark(school)}
      <div class="review-title"><a href="${escape(link)}">${title}</a><small>${subtitle}</small></div>
      <span class="review-score">${grade(review.score)}<small>/10</small></span>
    </header>
    <div class="review-card-meta">${meta}</div>
    ${criteriaRows(review)}
    <div class="review-body">${texts}</div>
    <button type="button" class="review-toggle" aria-expanded="false" hidden>Читать полностью</button>
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
  limit = PAGE;
  render();
}

function clearCombo() {
  if (mode === 'schools') filterSchool = ''; else filterTeacher = '';
  $('#review-filter').value = '';
  $('#review-filter-clear').hidden = true;
  closeCombo();
  limit = PAGE;
  render();
  $('#review-filter').focus();
}

function syncCombo() {
  $('#review-filter').placeholder = mode === 'schools' ? 'Все школы' : 'Все преподаватели';
  $('#review-filter').value = currentComboLabel();
  $('#review-filter-clear').hidden = !currentComboLabel();
  closeCombo();
}

// A sticker in the header appears from 10 published reviews and shows the last milestone passed: 10+, 30+, 50+, 100+...
const MILESTONES = [10, 30, 50, 100, 200, 300, 500, 1000, 2000, 5000, 10000];
function renderCounters() {
  const reached = MILESTONES.filter(step => reviews.length >= step).pop();
  const sticker = $('#reviews-sticker');
  if (sticker && reached) { sticker.textContent = `${reached}+ отзывов`; sticker.hidden = false; }
  const schools = reviews.filter(review => !review.teacher_id).length;
  $('#count-schools').textContent = schools ? ` ${schools}` : '';
  $('#count-teachers').textContent = reviews.length - schools ? ` ${reviews.length - schools}` : '';
}

const measureCards = wireReviewExpand($('#review-list'));

function topCtaHref() {
  const teacher = filterTeacher ? teacherById(filterTeacher) : null;
  if (teacher?.slug) return `/review?teacher=${encodeURIComponent(teacher.slug)}`;
  return filterSchool ? `/review?school=${encodeURIComponent(filterSchool)}` : '/review';
}

function render() {
  const rows = filteredReviews();
  $('#review-count').textContent = rows.length ? `${rows.length} ${rows.length === 1 ? 'отзыв' : rows.length < 5 ? 'отзыва' : 'отзывов'}` : 'Пока нет отзывов по этому фильтру';
  $('#review-top-cta').href = topCtaHref();
  const shown = rows.slice(0, limit);
  $('#review-list').innerHTML = shown.length ? shown.map(reviewCard).join('') : '<p class="review-empty-state">Здесь пока пусто — <a href="/review">оставь первый отзыв</a>.</p>';
  updateMore(rows, shown.length);
  measureCards();
}

function updateMore(rows, shownCount) {
  const more = $('#review-more');
  more.hidden = rows.length <= shownCount;
  more.firstChild.nodeValue = `Показать ещё ${Math.min(PAGE, rows.length - shownCount)} `;
}

// "Показать ещё": the next cards are added under the ones already on the page, so opened cards stay open.
function showMore() {
  const rows = filteredReviews();
  const from = Math.min(limit, rows.length);
  limit += PAGE;
  $('#review-list').insertAdjacentHTML('beforeend', rows.slice(from, limit).map(reviewCard).join(''));
  updateMore(rows, Math.min(limit, rows.length));
  measureCards();
}

document.querySelectorAll('[data-mode]').forEach(button => button.onclick = () => {
  mode = button.dataset.mode;
  filterSchool = ''; filterTeacher = ''; limit = PAGE;
  document.querySelectorAll('[data-mode]').forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', String(b === button)); });
  syncCombo();
  render();
});
$('#review-more').onclick = showMore;

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
    const catalogResponse = await fetch('catalog.json?v=9');
    if (!catalogResponse.ok) throw new Error('catalog');
    catalog = await catalogResponse.json();
    await applyLiveRatings(catalog);
    
    reviews = await fetchPublicReviews();
    if (filterTeacher) mode = 'teachers';
    document.querySelectorAll('[data-mode]').forEach(b => { const active = b.dataset.mode === mode; b.classList.toggle('active', active); b.setAttribute('aria-pressed', String(active)); });
    syncCombo();
    renderCounters();
    render();
  } catch (error) {
    $('#review-list').innerHTML = '<p>Не удалось загрузить отзывы. Обнови страницу, чтобы попробовать ещё раз.</p>';
    console.error(error);
  }
})();
