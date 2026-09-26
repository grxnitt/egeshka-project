import { priceContext } from './school-content.js?v=30';
import { priceDetails, relativeStrengths } from './comparison.js?v=25';
import { applyLiveRatings, teacherRatingLabel } from './supabase-client.js?v=4';
import { teacherSubjects } from './subjects.js?v=1';
const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = n => Number(n).toFixed(1).replace('.', ',');
const criteria = {teachers_score:'Преподаватели',practice_score:'Практика и ДЗ',feedback_score:'Проверка работ',curator_score:'Кураторы',platform_score:'Платформа',workload_score:'Нагрузка и темп',organization_score:'Организация обучения'};
const teacherCriteria = {explanation:'Объяснение материала',practice:'Практика и разбор ошибок',atmosphere:'Атмосфера и вовлечённость',structure:'Структура и темп занятий',exam_value:'Польза для экзамена'};
let catalog, mode = 'schools';
const alphabetically = (a, b) => a.name.localeCompare(b.name, 'ru', {numeric: true, sensitivity: 'base'});
const candidates = () => (mode === 'schools' ? [...catalog.schools] : catalog.teachers.filter(t => teacherSubjects(t).includes($('#teacher-subject').value))).sort(alphabetically);
const defaultPair = () => [...catalog.schools].sort((a, b) => b.score - a.score).slice(0, 2).map(s => s.name);
const track = () => { try { window.egeTrack && window.egeTrack('compare_used', {mode}); } catch {} };

function populate(usePreset = false) {
  const rows = candidates();
  const params = new URLSearchParams(location.search);
  let preset = usePreset && mode === 'schools' ? [params.get('compareLeft'), params.get('compareRight')] : [];
  if (mode === 'schools' && !preset[0] && !preset[1]) preset = defaultPair();
  ['left', 'right'].forEach((side, i) => {
    $(`#${side}-select`).innerHTML = rows.map((r, j) => `<option value="${j}">${escape(r.name)}${mode === 'teachers' ? `, ${escape(r.school)}` : ''}</option>`).join('');
    const found = rows.findIndex(row => row.name === preset[i]);
    $(`#${side}-select`).value = String(found >= 0 ? found : Math.min(i, rows.length - 1));
  });
  render();
}

// The pair lives in the address, so a comparison can be shared as a link.
function syncAddress(left, right) {
  try {
    const query = mode === 'schools' ? `?${new URLSearchParams({compareLeft: left.name, compareRight: right.name})}` : '';
    history.replaceState(null, '', location.pathname + query);
  } catch {}
}

function render(changed) {
  const rows = candidates(), l = $('#left-select'), r = $('#right-select');
  if (l.value === r.value && rows.length > 1) {
    const other = changed === 'right' ? l : r;
    other.value = String((Number(other.value) + 1) % rows.length);
  }
  const left = rows[Number(l.value)], right = rows[Number(r.value)];
  if (!left || !right) { $('#comparison-result').textContent = 'Для сравнения нужны два преподавателя по этому предмету.'; return; }
  document.querySelectorAll('#left-select option').forEach(o => o.disabled = o.value === r.value);
  document.querySelectorAll('#right-select option').forEach(o => o.disabled = o.value === l.value);
  const row = (title, a, b, cls = '') => `<div class="comparison-row ${cls}"><span>${title}</span><p>${a}</p><p>${b}</p></div>`;
  const segments = score => Array.from({length: 10}, (_, i) => `<i style="--fill:${Math.max(0, Math.min(1, score - i)) * 100}%"></i>`).join('');
  const meter = value => { const score = Math.max(0, Math.min(10, Number(value))); return `<span class="meter-value">${number(score)}</span><span class="meter meter-segments" aria-hidden="true">${segments(score)}</span>`; };
  const teacherMeter = value => {
    if (value == null || !Number.isFinite(Number(value))) return '<span class="no-score">Пока нет оценки</span>';
    const score = Math.max(0, Math.min(10, Number(value)));
    return `<span class="meter-value">${number(score)}</span><span class="meter meter-segments teacher-meter" aria-hidden="true">${segments(score)}</span>`;
  };
  let table = row('', escape(left.name), escape(right.name), 'column-heads'), after = '';
  if (mode === 'schools') {
    table += row('Общая оценка', `<strong>${number(left.score)}/10</strong>`, `<strong>${number(right.score)}/10</strong>`);
    table += Object.entries(criteria).map(([key, label]) => row(label, meter(left.criteria[key]), meter(right.criteria[key]))).join('');
    if (catalog.schools.some(school => school.isPreliminary)) table += '<p class="fine">* Предварительно: подтверждённых отзывов пока недостаточно.</p>';
    const priceCard = school => {
      const price = priceDetails[school.name];
      if (!price) return `<article class="compare-price-card"><h4>${escape(school.name)}</h4><p>${escape(school.price)}</p>${priceContext(school)}</article>`;
      return `<article class="compare-price-card"><h4>${escape(school.name)}</h4><strong>${escape(price.period)}</strong><dl><div><dt>За весь курс</dt><dd>${escape(price.total)}</dd></div><div><dt>Рассрочка / оплата частями</dt><dd>${escape(price.installment)}</dd></div></dl><p>${escape(price.note)}</p>${priceContext(school)}<a href="${escape(school.url)}" target="_blank" rel="noopener">Проверить тариф на сайте ↗</a></article>`;
    };
    const summaryCard = (school, other) => {
      const strengths = relativeStrengths(school, other);
      const text = strengths.length ? `Выше оценки по критериям: ${strengths.map(key => criteria[key].toLowerCase()).join(' и ')}.` : 'В этой паре нет критериев с более высокой оценкой. Сравни конкретного преподавателя, тариф и формат занятий.';
      return `<article><h4>${escape(school.name)}</h4><p>${escape(text)}</p></article>`;
    };
    after = `<section class="compare-prices" aria-label="Стоимость подготовки"><h3>Сколько стоит подготовка</h3><p class="compare-price-context">Ориентиры из каталога: пакеты и сроки обучения отличаются.</p><div class="compare-price-grid">${priceCard(left)}${priceCard(right)}</div></section><section class="compare-verdict" aria-label="Краткий вывод"><h3>Что это значит для выбора</h3><div class="compare-verdict-grid">${summaryCard(left, right)}${summaryCard(right, left)}</div></section>`;
  } else {
    table += row('Оценка учеников', `<strong>${escape(teacherRatingLabel(left))}</strong>`, `<strong>${escape(teacherRatingLabel(right))}</strong>`);
    table += row('Школа', escape(left.school), escape(right.school));
    table += '<div class="criteria-title"><strong>По оценкам учеников</strong><span>Отдельные критерии, шкала 1–10</span></div>';
    table += Object.entries(teacherCriteria).map(([key, label]) => row(label, teacherMeter(left.criteria?.[key]), teacherMeter(right.criteria?.[key]), 'teacher-metric')).join('');
    table += '<p class="fine">Оценка появляется, когда набирается вес трёх подтверждённых отзывов (без подтверждения отзыв весит меньше), и считается как среднее пяти критериев.</p>';
    const teacherCard = t => `<article class="teacher-compare-card"><div><span>${escape(t.school)}</span><strong>${escape(teacherRatingLabel(t))}</strong></div><h3>${escape(t.name)}</h3><p>${escape(t.description)}</p><a href="${escape(t.url)}" target="_blank" rel="noopener">Открыть профиль <b>↗</b></a></article>`;
    after = `<details class="teacher-details"><summary class="comparison-summary">Подробнее о преподавателях</summary><div class="teacher-compare-cards">${teacherCard(left)}${teacherCard(right)}</div></details>`;
  }
  $('#comparison-result').innerHTML = `<div class="comparison-table">${table}</div>${after}`;
  syncAddress(left, right);
}

$('#left-select').onchange = () => { render('left'); track(); };
$('#right-select').onchange = () => { render('right'); track(); };
$('#teacher-subject').onchange = () => populate();
document.querySelectorAll('[data-mode]').forEach(button => button.onclick = () => {
  mode = button.dataset.mode;
  document.querySelectorAll('[data-mode]').forEach(x => { x.classList.toggle('active', x === button); x.setAttribute('aria-pressed', String(x === button)); });
  $('#teacher-subject-wrap').hidden = mode !== 'teachers';
  $('#left-label').textContent = mode === 'teachers' ? '2. Первый преподаватель' : 'Первая школа';
  $('#right-label').textContent = mode === 'teachers' ? '3. Второй преподаватель' : 'Вторая школа';
  populate();
});
try {
  const response = await fetch('catalog.json');
  if (!response.ok) throw new Error('catalog');
  catalog = await response.json();
  await applyLiveRatings(catalog);
  $('#teacher-subject').innerHTML = [...new Set(catalog.teachers.flatMap(teacherSubjects))].sort().map(s => `<option>${escape(s)}</option>`).join('');
  populate(true);
} catch (error) {
  console.error(error);
  $('#comparison-result').innerHTML = '<p class="compare-error">Не удалось загрузить каталог школ. Обнови страницу, чтобы попробовать снова.</p>';
}
