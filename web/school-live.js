// A school page is built as a static file, so its numbers can be older than the console: this puts the current ones on it.
import { applyLiveRatings, ratingMark } from './supabase-client.js?v=9';

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
