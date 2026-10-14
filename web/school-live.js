// A school page is built as a static file, so its numbers can be older than the console: this puts the current ones on it.
import { applyLiveRatings, fetchPublicReviews, ratingMark } from './supabase-client.js?v=11';

const list = document.getElementById('sp-criteria');
if (list) {
  try {
    const response = await fetch('/catalog.json?v=9');
    const catalog = await applyLiveRatings(await response.json());
    const school = catalog.schools.find(item => Number(item.id) === Number(list.dataset.schoolId));
    if (school) {
      const num = value => Number(value).toFixed(1).replace('.', ',');
      const scoreNode = document.getElementById('sp-score-value');
      if (scoreNode && Number.isFinite(Number(school.score))) scoreNode.textContent = num(school.score);
      const noteNode = document.getElementById('sp-score-note');
      if (noteNode) noteNode.textContent = `из 10${ratingMark(school)}`;
      list.querySelectorAll('li[data-crit]').forEach(row => {
        const key = row.dataset.crit, status = school.criteriaStatus?.[key] || 'yes', value = school.criteria?.[key];
        const label = row.dataset.label;
        const name = document.createElement('span');
        name.className = 'sp-crit-name';
        name.textContent = label;
        if (status === 'none' || value == null) {
          row.className = 'sp-empty';
          const empty = document.createElement('em');
          empty.textContent = 'Не предусмотрено';
          row.replaceChildren(name, empty);
          return;
        }
        row.className = '';
        if (status === 'tier') {
          const tier = document.createElement('small');
          tier.className = 'sp-tier';
          tier.textContent = 'зависит от тарифа';
          name.append(' ', tier);
        }
        const score = Math.max(0, Math.min(10, Number(value)));
        const meter = document.createElement('div');
        meter.className = 'sp-crit-meter';
        const valueNode = document.createElement('span');
        valueNode.className = 'meter-value';
        valueNode.textContent = num(score);
        const bar = document.createElement('span');
        bar.className = 'meter meter-segments';
        bar.setAttribute('aria-hidden', 'true');
        for (let i = 0; i < 10; i++) {
          const segment = document.createElement('i');
          segment.style.setProperty('--fill', `${Math.max(0, Math.min(1, score - i)) * 100}%`);
          bar.append(segment);
        }
        meter.append(valueNode, bar);
        row.replaceChildren(name, meter);
      });
    }
  } catch (error) {
    console.warn('Показаны оценки из файла страницы:', error);
  }
}

// How many reviews the school has: the page only links to them (the list lives on the "Отзывы" page with the school already chosen).
const reviewBox = document.getElementById('reviews');
if (reviewBox) {
  const plural = (n, one, few, many) => { const m = n % 100, d = n % 10; return m > 10 && m < 20 ? many : d === 1 ? one : d > 1 && d < 5 ? few : many; };
  const reviews = (await fetchPublicReviews()).filter(r => !r.teacher_id && Number(r.school_id) === Number(reviewBox.dataset.schoolId));
  const summary = document.getElementById('sp-reviews-summary');
  const read = document.getElementById('sp-read-reviews');
  if (reviews.length) {
    const verified = reviews.filter(r => r.verified).length;
    if (summary) summary.textContent = `${reviews.length} ${plural(reviews.length, 'отзыв', 'отзыва', 'отзывов')} учеников, из них подтверждённых: ${verified}. Каждый отзыв проверяет модератор.`;
    if (read) read.firstChild.nodeValue = `Читать отзывы о школе (${reviews.length}) `;
  } else {
    if (summary) summary.textContent = 'Отзывов о школе пока нет. Станьте первым: отзывы войдут в оценку школы, когда наберётся вес трёх подтверждённых.';
    if (read) read.hidden = true;
  }
}
