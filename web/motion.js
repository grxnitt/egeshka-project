// Animate visible surfaces once; keep content available without JavaScript.
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const surfaces = '.comparison-box,.school-card,.compare-price-card,.about-grid article,.detail-card,.quiz-match,.reviews,.channel-section,.rating-next,.how-card';
const seen = new WeakSet();
const observer = new IntersectionObserver(entries => {
  for (const {target, isIntersecting} of entries) {
    target.classList.toggle('motion-visible', isIntersecting);
    if (isIntersecting && !seen.has(target) && target.matches(surfaces)) {
      seen.add(target);
      if (!reduced.matches) {
        const card = target.matches('.how-card');
        const delay = card ? [...target.parentNode.children].indexOf(target) * 90 : 0;
        target.animate([
          {opacity: card ? 0 : .65, transform: `translateY(${card ? 22 : 12}px)`},
          {opacity: 1, transform: 'translateY(0)'}
        ], {duration: card ? 560 : 440, delay, fill: 'backwards', easing: 'cubic-bezier(.2,.7,.2,1)'});
      }
    }
  }
}, {threshold: .05});
const registered = new WeakSet();
function register(root) {
  const nodes = [...root.querySelectorAll(`${surfaces},.hero-centered`)];
  if(root.matches?.(surfaces)) nodes.push(root);
  for(const node of nodes) if(!registered.has(node)){ registered.add(node); observer.observe(node); }
}
register(document);
const changes = new MutationObserver(records => {
  for(const record of records) for(const node of record.addedNodes) if(node.nodeType === 1) register(node);
});
changes.observe(document.querySelector('main'), {childList:true,subtree:true});
const dialog = document.querySelector('dialog');
if(dialog) changes.observe(dialog,{childList:true,subtree:true});
