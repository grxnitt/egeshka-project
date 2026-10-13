// Review cards show a few lines of each text and a "Читать полностью" button, so every card in a row is the same height.
// The button appears only for cards whose text is actually cut off; an opened card spans the whole row (see composition.css).
export function wireReviewExpand(root) {
  const measure = () => {
    root.querySelectorAll('.review-card:not(.is-open)').forEach(card => {
      const toggle = card.querySelector('.review-toggle');
      if (toggle) toggle.hidden = ![...card.querySelectorAll('.review-text p')].some(p => p.scrollHeight > p.clientHeight + 1);
    });
  };
  root.addEventListener('click', event => {
    const toggle = event.target.closest('.review-toggle');
    if (!toggle) return;
    const card = toggle.closest('.review-card');
    const open = card.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', String(open));
    toggle.textContent = open ? 'Свернуть' : 'Читать полностью';
  });
  let timer;
  window.addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(measure, 150); });
  const later = () => { setTimeout(measure, 0); document.fonts?.ready.then(measure); };
  return later;
}
