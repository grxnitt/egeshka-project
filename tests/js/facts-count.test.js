// Run: node tests/js/facts-count.test.js   (also called from tests/test_facts_count.py)
// Drives the real web/facts-count.js with a fake clock and fake animation frames, so what the visitor would see
// frame by frame is checked, including a stall in the middle and a number that changes while it counts.
const assert = require('node:assert/strict');
const fc = require('../../web/facts-count.js');

const fakeEl = text => ({dataset: {counting: '1'}, textContent: text});
const numberOf = el => Number(el.textContent.replace(/\D/g, ''));

// Frames of `frameMs` (60 fps by default); `stalls` = {frameIndex: extraMs} makes one frame arrive late.
function simulate(items, {frameMs = 1000 / 60, stalls = {}, onFrame} = {}) {
  let pending = null, now = 1000, index = 0, done = false;
  const trace = items.map(() => []);
  fc.run(items, {raf: cb => { pending = cb; }, done: () => { done = true; }});
  let startedAt = null;
  while (pending && index < 5000) {
    const cb = pending; pending = null;
    now += frameMs + (stalls[index] || 0);
    if (startedAt === null) startedAt = now;
    cb(now);
    items.forEach((item, i) => trace[i].push(numberOf(item.el)));
    if (onFrame) onFrame(index, now - startedAt);
    index++;
  }
  return {trace, frames: index, done, painted: now - startedAt};
}

const make = (...texts) => texts.map(text => { const el = fakeEl(text); return {el, original: text, parts: fc.parse(text)}; });
const maxJump = list => list.slice(1).reduce((max, value, i) => Math.max(max, value - list[i]), 0);

// parse / format
assert.deepEqual(fc.parse('210+'), {prefix: '', number: 210, suffix: '+'});
assert.equal(fc.parse('abc'), null);
assert.equal(fc.format(fc.parse('210+'), 57.4), '57+');

// easing: starts at 0, ends at 1, never goes backwards, same speed at the join (no kink)
assert.equal(fc.ease(0), 0); assert.equal(fc.ease(1), 1);
let previous = 0;
for (let p = 0; p <= 1.0001; p += 0.001) { const value = fc.ease(p); assert.ok(value >= previous - 1e-12); previous = value; }
assert.ok(Math.abs((fc.ease(0.8001) - fc.ease(0.8)) / 0.0001 - 1) < 0.01, 'speed is continuous where the landing starts');

// 1. a normal run: 30 and 210+ count together
{
  const items = make('30', '210+');
  const {trace, done, painted} = simulate(items);
  assert.ok(done, 'finishes');
  const [small, big] = trace;
  assert.ok(big[0] <= 3 && small[0] <= 1, 'starts from zero, no jump on the first frame');
  assert.ok(Math.abs(painted - fc.DURATION) < 40, `takes about ${fc.DURATION} ms of painted time, took ${painted}`);
  for (const list of trace) assert.ok(list.every((v, i) => !i || v >= list[i - 1]), 'never goes backwards');
  assert.ok(maxJump(big) <= 2 && maxJump(small) <= 1, 'no frame jumps ahead');
  assert.equal(new Set(big).size >= 200, true, `every number on the way is shown (saw ${new Set(big).size} different)`);
  const half = Math.round(big.length * (3500 / fc.DURATION));
  assert.ok(Math.abs(big[half] - 105) <= 4 && Math.abs(small[half] - 15) <= 1, 'evenly: halfway in time is halfway in number');
  assert.equal(items[0].el.textContent, '30'); assert.equal(items[1].el.textContent, '210+');
  assert.equal(items.every(item => !item.el.dataset.counting), true, 'ownership is given back');
  // both numbers arrive at the end together, not one long before the other
  const arrival = list => list.findIndex(v => v === list[list.length - 1]);
  assert.ok(arrival(small) >= trace[0].length * 0.9 && arrival(big) >= trace[1].length * 0.9, 'both arrive in the last tenth of the time');
}

// 2. a busy moment (1.5 s stall) pauses the count, it does not skip ahead
{
  const items = make('210+');
  const {trace, done} = simulate(items, {stalls: {60: 1500}});
  assert.ok(done && maxJump(trace[0]) <= 3, `a stalled frame advances by one small step (largest jump ${maxJump(trace[0])})`);
}

// 3. a slow device (15 fps) still counts evenly
{
  const items = make('210+');
  const {trace, done} = simulate(items, {frameMs: 1000 / 15});
  assert.ok(done && maxJump(trace[0]) <= 8, `still smooth at 15 fps (largest jump ${maxJump(trace[0])})`);
}

// 4. the catalog arrives mid-count with a different number: no jump, ends on the new number
{
  const items = make('210+');
  let jumpAt = null;
  const {trace} = simulate(items, {onFrame: (index, t) => { if (t > 3500 && jumpAt === null) { jumpAt = index; fc.setFact(items[0].el, '220+'); } }});
  assert.equal(items[0].el.textContent, '220+');
  assert.ok(maxJump(trace[0]) <= 7, `retargeting is not a jump (largest ${maxJump(trace[0])})`);
}

// 5. setFact never writes the text while a count is running, and does when it is not
{
  const el = fakeEl('0+');
  fc.setFact(el, '210+');
  assert.equal(el.textContent, '0+'); assert.equal(el.dataset.final, '210+');
  delete el.dataset.counting;
  fc.setFact(el, '220+');
  assert.equal(el.textContent, '220+');
}

console.log('facts-count: all checks passed');
