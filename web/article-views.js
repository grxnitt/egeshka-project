import { incrementArticleView, fetchArticleViews } from './supabase-client.js?v=6';

const el = document.getElementById('article-views');
const slug = el?.dataset.slug;
if (el && slug) {
  const key = `viewed:${slug}`;
  const already = (() => { try { return sessionStorage.getItem(key) === '1'; } catch { return false; } })();
  (already ? fetchArticleViews(slug) : incrementArticleView(slug)).then(views => {
    if (views == null) return;
    el.textContent = `${Number(views).toLocaleString('ru-RU')} ${pluralViews(views)}`;
    try { sessionStorage.setItem(key, '1'); } catch {}
  });
}

function pluralViews(n) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'просмотр';
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return 'просмотра';
  return 'просмотров';
}
