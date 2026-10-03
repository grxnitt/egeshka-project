import { incrementArticleView, fetchArticleViews, fetchArticleViewsBatch } from './supabase-client.js?v=7';

function pluralViews(n) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'просмотр';
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return 'просмотра';
  return 'просмотров';
}

// Tiny counts read as "nobody reads this", so they stay hidden until they mean something.
const MIN_VISIBLE = 50;
const label = views => `${Number(views).toLocaleString('ru-RU')} ${pluralViews(views)}`;

// The article's own hero counter — increments once per browser tab session.
const hero = document.getElementById('article-views');
const heroSlug = hero?.dataset.slug;
if (hero && heroSlug) {
  const key = `viewed:${heroSlug}`;
  const already = (() => { try { return sessionStorage.getItem(key) === '1'; } catch { return false; } })();
  (already ? fetchArticleViews(heroSlug) : incrementArticleView(heroSlug)).then(views => {
    if (views == null) return;
    try { sessionStorage.setItem(key, '1'); } catch {}
    if (views < MIN_VISIBLE) return;
    hero.textContent = label(views);
  });
}

// Read-only counts on article cards (listing page, home page, "Читайте также") —
// one batched request for every card on the page, never increments.
const cardEls = [...document.querySelectorAll('.article-card-views[data-slug]')];
if (cardEls.length) {
  const slugs = [...new Set(cardEls.map(el => el.dataset.slug))];
  fetchArticleViewsBatch(slugs).then(counts => {
    cardEls.forEach(el => {
      const views = counts[el.dataset.slug];
      if (views == null || views < MIN_VISIBLE) return;
      el.textContent = label(views);
    });
  });
}
