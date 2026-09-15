// Animate visible surfaces once; keep content available without JavaScript.
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const surfaces = '.comparison-box,.school-card,.compare-price-card,.about-grid article,.detail-card,.quiz-match';
const seen = new WeakSet();
const observer = new IntersectionObserver(entries => {
  for (const {target, isIntersecting} of entries) {
    target.classList.toggle('motion-visible', isIntersecting);
    if (isIntersecting && !seen.has(target) && target.matches(surfaces)) {
      seen.add(target);
      if (!reduced.matches) target.animate([
        {opacity: .65, transform: 'translateY(12px)'},
        {opacity: 1, transform: 'translateY(0)'}
      ], {duration: 440, easing: 'cubic-bezier(.2,.7,.2,1)'});
    }
  }
}, {threshold: .05});
const registered = new WeakSet();
function register(root) {
  const nodes = [...root.querySelectorAll(`${surfaces},.hero-centered,.channel-section,.rating-next`)];
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
