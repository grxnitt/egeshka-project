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

function syncSelect() {
  const select = $('#review-filter');
  if (mode === 'schools') {
    select.innerHTML = `<option value="">Все школы</option>` + catalog.schools.slice().sort((a, b) => a.name.localeCompare(b.name, 'ru')).map(s => `<option value="${escape(s.reviewSlug)}">${escape(s.name)}</option>`).join('');
    select.value = filterSchool;
  } else {
    select.innerHTML = `<option value="">Все преподаватели</option>` + catalog.teachers.slice().sort((a, b) => a.name.localeCompare(b.name, 'ru')).map(t => `<option value="${t.id}">${escape(t.name)} · ${escape(t.school)}</option>`).join('');
    select.value = filterTeacher;
  }
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
  syncSelect();
  render();
});
$('#review-filter').onchange = event => {
  if (mode === 'schools') filterSchool = event.target.value; else filterTeacher = event.target.value;
  expanded = false;
  render();
};
$('#review-more').onclick = () => { expanded = true; render(); };

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
    syncSelect();
    render();
  } catch (error) {
    $('#review-list').innerHTML = '<p>Не удалось загрузить отзывы. Обнови страницу, чтобы попробовать ещё раз.</p>';
    console.error(error);
  }
})();
