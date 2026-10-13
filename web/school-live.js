// A school page is built as a static file, so its numbers can be older than the console: this puts the current ones on it.
import { applyLiveRatings, fetchPublicReviews, ratingMark } from './supabase-client.js?v=9';
import { wireReviewExpand } from './review-expand.js?v=1';

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

// Approved reviews of this school, newest first. Text goes in as text only: nothing from a review is ever read as HTML.
const reviewBox = document.getElementById('sp-review-list');
if (reviewBox) {
  const section = reviewBox.closest('.sp-reviews');
  const PERIODS = {'2026/27': 'учился(ась) в 2026/27', '2025/26': 'учился(ась) в 2025/26', '2024/25': 'учился(ась) в 2024/25', earlier: 'учился(ась) раньше 2024 года'};
  const part = (title, text, cls) => {
    const block = document.createElement('div');
    block.className = `review-text ${cls}${text ? '' : ' is-blank'}`;
    const head = document.createElement('h4');
    head.textContent = title;
    const body = document.createElement('p');
    body.textContent = text || 'Не указано';
    block.append(head, body);
    return block;
  };
  const card = review => {
    const article = document.createElement('article');
    article.className = 'review-card sp-review';
    const head = document.createElement('header');
    head.className = 'review-card-head';
    const meta = document.createElement('div');
    meta.className = 'review-title';
    const who = document.createElement('small');
    who.textContent = [
      review.verified ? '✓ подтверждён' : 'без подтверждения',
      review.created_at ? new Date(review.created_at).toLocaleDateString('ru-RU', {day: 'numeric', month: 'long', year: 'numeric'}) : '',
      PERIODS[review.study_period] || '',
    ].filter(Boolean).join(' · ');
    meta.append(who);
    const score = document.createElement('span');
    score.className = 'review-score';
    score.textContent = String(Number(review.score));
    const of = document.createElement('small');
    of.textContent = '/10';
    score.append(of);
    head.append(meta, score);
    article.append(head);
    const body = document.createElement('div');
    body.className = 'review-body';
    if (review.text_positive || review.text_negative) {
      body.append(part('Понравилось', review.text_positive, 'is-plus'), part('Не понравилось', review.text_negative, 'is-minus'));
    } else {
      const none = document.createElement('div');
      none.className = 'review-text is-none';
      const note = document.createElement('p');
      note.className = 'review-empty';
      note.textContent = 'Без комментария — только оценки.';
      none.append(note);
      body.append(none);
    }
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'review-toggle';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.hidden = true;
    toggle.textContent = 'Читать полностью';
    article.append(body, toggle);
    return article;
  };
  const reviews = (await fetchPublicReviews()).filter(r => !r.teacher_id && Number(r.school_id) === Number(section.dataset.schoolId));
  const summary = document.getElementById('sp-reviews-summary');
  if (reviews.length) {
    const verified = reviews.filter(r => r.verified).length;
    const plural = (n, one, few, many) => { const m = n % 100, d = n % 10; return m > 10 && m < 20 ? many : d === 1 ? one : d > 1 && d < 5 ? few : many; };
    if (summary) summary.textContent = `${reviews.length} ${plural(reviews.length, 'отзыв', 'отзыва', 'отзывов')} учеников, из них подтверждённых: ${verified}. Каждый отзыв проверяет модератор.`;
    const measure = wireReviewExpand(reviewBox);
    reviewBox.replaceChildren(...reviews.slice(0, 3).map(card));
    measure();
    const all = document.getElementById('sp-reviews-all');
    if (all && reviews.length > 3) all.hidden = false;
  } else if (summary) {
    summary.textContent = 'Отзывов о школе пока нет. Станьте первым: оценка школы появится, когда наберётся три подтверждённых отзыва.';
  }
}
