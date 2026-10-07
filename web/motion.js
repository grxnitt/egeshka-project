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

  /* 2. Small cards rise into place when they first scroll into view; cards in one row follow each other.
     Big panels (articles, CTA blocks, page sections) stay still: a whole panel sliding in is too loud. */
  const surfaces = ['.how-card', '.school-card', '.home-top-card', '.faq-item', '.review-card'].join(',');
  // Fast scrolling: skip the entrance so nothing lags behind or flickers.
  let lastY = scrollY, lastT = performance.now(), speed = 0;
  addEventListener('scroll', () => {
    const now = performance.now();
    speed = Math.abs(scrollY - lastY) / Math.max(1, now - lastT);
    lastY = scrollY; lastT = now;
  }, {passive: true});
  /* 4. Score bars fill and scores count up when they become visible. */
  const scores = '.sp-score strong, .card-score strong, .detail-score strong, .home-top-score';
  const meters = '.meter-segments';
  // Panels whose background ornament runs only while they are on screen (CSS .motion-visible).
  const decor = '.hero-centered,.channel-section,.reviews,.rating-next';
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
      if (!target.matches(surfaces)) continue;  // decorative panels only get the motion-visible class
      if (speed > 1.5 || target.getBoundingClientRect().top < innerHeight * .55) continue;  // fast scroll or already on screen
      const row = target.parentNode ? [...target.parentNode.children].filter(el => el.matches(surfaces)) : [];
      const index = Math.max(0, row.indexOf(target)) % 3;
      target.animate([{opacity: 0, transform: 'translateY(14px)'}, {opacity: 1, transform: 'none'}],
                     {duration: 520, delay: index * 70, easing: ease, fill: 'backwards'});
    }
  }, {threshold: .08, rootMargin: '0px 0px -40px 0px'});

  const registered = new WeakSet();
  function register(root) {
    if (root.nodeType !== 1) return;
    const nodes = [...root.querySelectorAll(`${surfaces},${scores},${meters},${decor}`)];
    if (root.matches(`${surfaces},${scores},${meters},${decor}`)) nodes.push(root);
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
