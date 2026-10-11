/* The numbers on the home page ("30 школ", "210+ преподавателей") count up from zero, together, at an even pace,
   and arrive at the same moment, about 7 seconds after the visitor can see them.

   Why this is its own file, and not part of motion.js:
   - One owner. While the count runs, only this file writes the number. Another script writing the final value
     (app.js does it when the catalog arrives) used to cut the count short: the number jumped straight to 210.
     Everyone else goes through setFact(), which remembers the value and leaves the text alone during the count.
   - Painted time only. The clock starts at the first painted frame and a single frame can advance it by at most
     MAX_STEP ms, so a busy moment (the page is still loading, a slow device) pauses the count instead of skipping it.
   - It waits: for the page to finish loading, then for the numbers to be on screen (60% visible).
   The text in the HTML is the real final number (search engines, no-JS visitors); the script shows 0 first, so the
   final number never flashes before the count. With "reduce motion" the number is simply shown. */
(function (root) {
  'use strict';

  var DURATION = 7000;     // ms of painted time from 0 to the final number
  var MAX_STEP = 50;       // ms: the most one frame may add to the clock
  var START_DELAY = 700;   // ms after the page has loaded (the headline intro and the catalog are done by then)
  var CRUISE = 0.8;        // constant speed up to this share of the time, then a soft landing

  function ease(p) {
    if (p <= 0) return 0;
    if (p >= 1) return 1;
    if (p <= CRUISE) return p;                           // evenly: every number is visible on the way
    var q = (p - CRUISE) / (1 - CRUISE);
    return CRUISE + (1 - CRUISE) * (q + q * q - q * q * q);   // same speed as before, easing to a stop
  }

  function parse(text) {
    var match = /^(\D*)(\d+)(\D*)$/.exec(String(text).trim());
    return match ? {prefix: match[1], number: Number(match[2]), suffix: match[3]} : null;
  }

  function format(parts, value) {
    return parts.prefix + Math.round(value) + parts.suffix;
  }

  // The number the count is heading for: a later value from setFact() wins over the one written in the HTML.
  function targetOf(item) {
    return parse(item.el.dataset.final || item.original) || item.parts;
  }

  function setFact(el, value) {
    el.dataset.final = value;
    if (!el.dataset.counting && el.textContent !== value) el.textContent = value;
  }

  function run(items, env) {
    var elapsed = 0, last = null;
    function frame(now) {
      if (last === null) last = now;                                      // the first painted frame starts the clock
      elapsed += Math.min(Math.max(now - last, 0), MAX_STEP);
      last = now;
      var progress = Math.min(1, elapsed / DURATION);
      items.forEach(function (item) {
        var parts = targetOf(item);
        item.el.textContent = format(parts, parts.number * ease(progress));
      });
      if (progress < 1) env.raf(frame);
      else {
        items.forEach(function (item) { delete item.el.dataset.counting; });
        items.forEach(function (item) { var parts = targetOf(item); item.el.textContent = format(parts, parts.number); });
        if (env.done) env.done();
      }
    }
    env.raf(frame);
  }

  function init() {
    var els = [].slice.call(document.querySelectorAll('[data-fact]'));
    if (!els.length) return;
    var reduced = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var items = [];
    els.forEach(function (el) {
      var original = (el.dataset.final || el.textContent).trim();
      var parts = parse(original);
      if (parts && !reduced) items.push({el: el, original: original, parts: parts});
      el.classList.add('is-ready');                                       // CSS keeps them hidden until this
    });
    if (!items.length || !('IntersectionObserver' in root)) return;

    items.forEach(function (item) {                                       // take ownership and show zero right away
      item.el.dataset.counting = '1';
      item.el.textContent = format(item.parts, 0);
    });

    var loaded = false, seen = false, started = false;
    function maybeStart() {
      if (started || !loaded || !seen) return;
      started = true;
      run(items, {raf: function (callback) { return root.requestAnimationFrame(callback); }});
    }
    function afterLoad() { setTimeout(function () { loaded = true; maybeStart(); }, START_DELAY); }
    if (document.readyState === 'complete') afterLoad(); else root.addEventListener('load', afterLoad);

    var watch = items[0].el.closest('.hs-facts') || items[0].el;
    var observer = new root.IntersectionObserver(function (entries) {
      if (!entries.some(function (entry) { return entry.isIntersecting; })) return;
      seen = true;
      observer.disconnect();
      maybeStart();
    }, {threshold: 0.6});
    observer.observe(watch);
  }

  var api = {ease: ease, parse: parse, format: format, setFact: setFact, run: run, DURATION: DURATION, MAX_STEP: MAX_STEP};
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.egeSetFact = setFact;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  }
})(typeof window !== 'undefined' ? window : globalThis);
