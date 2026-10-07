// Site motion, loaded on every page by analytics.js. Decorative only: without this script (or with
// "reduce motion" on) every element is simply visible, nothing waits for an animation.
(() => {
  if (window.__egeMotion) return;
  window.__egeMotion = true;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ease = 'cubic-bezier(.22,.7,.25,1)';
  document.documentElement.classList.add('motion-on');

  /* 1. Page headline: words rise one after another. Words inside .brand-dot only fade, so the pink dot stays put. */
  function splitWords(node) {
    for (const child of [...node.childNodes]) {
      if (child.nodeType === 3) {
        const parts = child.textContent.split(/(\s+)/);
        const frag = document.createDocumentFragment();
        for (const part of parts) {
          if (!part) continue;
          if (/^\s+$/.test(part)) { frag.append(part); continue; }
          const span = document.createElement('span');
          span.className = 'mw';
          span.textContent = part;
          frag.append(span);
        }
        child.replaceWith(frag);
      } else if (child.nodeType === 1) {
        if (child.classList.contains('brand-dot')) child.classList.add('mw', 'mw-fade');
        else splitWords(child);
      }
    }
  }
  const headline = document.querySelector('main h1');
  if (headline && !reduced) {
    splitWords(headline);
    headline.style.animation = 'none';
    headline.querySelectorAll('.mw').forEach((word, i) => {
      const fade = word.classList.contains('mw-fade');
      word.animate(fade ? [{opacity: 0}, {opacity: 1}]
                        : [{opacity: 0, transform: 'translateY(.45em)'}, {opacity: 1, transform: 'none'}],
                   {duration: 650, delay: 80 + i * 70, easing: ease, fill: 'backwards'});
    });
  }

  /* 3. Hero glow follows the pointer a little (on top of its slow CSS drift). */
  const glows = [...document.querySelectorAll('.hero-glow')];
  if (glows.length && !reduced && matchMedia('(pointer: fine)').matches) {
    let frame = 0;
    addEventListener('pointermove', event => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const x = event.clientX / innerWidth - .5, y = event.clientY / innerHeight - .5;
        glows.forEach((glow, i) => { const k = i ? -26 : 34; glow.style.translate = `${x * k}px ${y * k}px`; });
      });
    }, {passive: true});
  }

  /* 2. Blocks rise into place when they first scroll into view; cards in one row follow each other. */
  const surfaces = ['.section-heading', '.how-card', '.school-card', '.article-card', '.faq-item', '.comparison-box',
    '.compare-price-card', '.channel-section', '.reviews', '.rating-next', '.about-grid article', '.detail-card',
    '.sp-section', '.method-section', '.review-card', '.quiz-match'].join(',');
  /* 4. Score bars fill and scores count up when they become visible. */
  const scores = '.sp-score strong, .card-score strong, .detail-score strong';
  const meters = '.meter-segments';
  const seen = new WeakSet();

  function countUp(el) {
    const text = [...el.childNodes].find(n => n.nodeType === 3 && /\d/.test(n.textContent));
    const match = text && text.textContent.match(/(\d+)[.,](\d)/);
    if (!match) return;
    const target = Number(`${match[1]}.${match[2]}`), start = performance.now(), duration = 900;
    const original = text.textContent;
    const step = now => {
      const t = Math.min(1, (now - start) / duration), value = target * (1 - Math.pow(1 - t, 3));
      text.textContent = original.replace(match[0], value.toFixed(1).replace('.', ','));
      if (t < 1) requestAnimationFrame(step); else text.textContent = original;
    };
    requestAnimationFrame(step);
  }

  const observer = new IntersectionObserver(entries => {
    for (const {target, isIntersecting} of entries) {
      target.classList.toggle('motion-visible', isIntersecting);
      if (!isIntersecting || seen.has(target)) continue;
      seen.add(target);
      if (target.matches(meters)) { target.classList.add('is-in'); continue; }
      if (reduced) continue;
      if (target.matches(scores)) { countUp(target); continue; }
      const row = target.parentNode ? [...target.parentNode.children].filter(el => el.matches(surfaces)) : [];
      const index = Math.max(0, row.indexOf(target)) % 3;
      target.animate([{opacity: 0, transform: 'translateY(28px)'}, {opacity: 1, transform: 'none'}],
                     {duration: 700, delay: index * 90, easing: ease, fill: 'backwards'});
    }
  }, {threshold: .08, rootMargin: '0px 0px -40px 0px'});

  const registered = new WeakSet();
  function register(root) {
    if (root.nodeType !== 1) return;
    const nodes = [...root.querySelectorAll(`${surfaces},${scores},${meters},.hero-centered`)];
    if (root.matches(`${surfaces},${scores},${meters}`)) nodes.push(root);
    for (const node of nodes) if (!registered.has(node)) { registered.add(node); observer.observe(node); }
  }
  register(document.body);
  new MutationObserver(records => {
    for (const record of records) for (const node of record.addedNodes) register(node);
  }).observe(document.body, {childList: true, subtree: true});

  /* 6. Each new screen inside a dialog (quiz steps, results, lead form) slides in softly. */
  const content = document.getElementById('dialog-content');
  if (content && !reduced) {
    new MutationObserver(() => {
      const first = content.firstElementChild;
      if (first) first.animate([{opacity: 0, transform: 'translateX(14px)'}, {opacity: 1, transform: 'none'}],
                               {duration: 320, easing: ease});
    }).observe(content, {childList: true});
  }
})();
