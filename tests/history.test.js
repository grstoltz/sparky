// Run with: node tests/history.test.js  (also run by tests/test_history.py)
const assert = require('assert');
const H = require('../web/assets/history.js');

const T0 = 1_700_000_000_000;

// A storage stub with a byte limit, like localStorage's quota.
function stub(limit = Infinity) {
  const m = {};
  return {
    m,
    getItem: (k) => (k in m ? m[k] : null),
    setItem(k, v) { if (String(v).length > limit) throw new Error('QuotaExceededError'); m[k] = String(v); },
    removeItem(k) { delete m[k]; },
  };
}

// --- records and titles
const c = H.newChat({ mode: 'arm3', now: T0 });
assert.strictEqual(c.v, H.VERSION);
assert.deepStrictEqual([c.mode, c.mock, c.sid, c.title, c.items], ['arm3', false, null, 'New chat', []]);
assert.strictEqual(H.titleFor('  why   is\n melt  high '), 'why is melt high');
assert.strictEqual(H.titleFor(''), 'New chat');
const long = H.titleFor('a'.repeat(100));
assert.strictEqual(long.length, H.TITLE_MAX);
assert.ok(long.endsWith('…'));

H.appendItem(c, { role: 'user', text: 'First question' }, T0 + 1);
H.appendItem(c, { role: 'user', text: 'Second question' }, T0 + 2);
assert.strictEqual(c.title, 'First question', 'title comes from the first user message only');
assert.strictEqual(c.updated, T0 + 2);

// --- which events are stored
const d = H.newChat({ mode: 'arm2', now: T0 });
assert.strictEqual(H.recordEvent(d, { type: 'session', session_id: 'x' }), false);
assert.strictEqual(H.recordEvent(d, { type: 'text_delta', text: 'hel' }), false);
assert.strictEqual(H.recordEvent(d, { type: 'tool_use', name: 'mcp__dbt__list_metrics' }), false);
assert.strictEqual(H.recordEvent(d, { type: 'tool_result', id: '1' }), false);
assert.strictEqual(H.recordEvent(d, { type: 'result', cost_usd: 1 }), false);
for (const ev of [
  { type: 'text', text: 'hello', provisional: true },
  { type: 'text', text: 'hello world' },           // replaces the provisional one
  { type: 'result_table', key: 'k', rows: [{ a: 1 }], columns: ['a'], metrics: ['a'], group_by: [] },
  { type: 'sql', key: 'k', sql: 'select 1' },
  { type: 'cite', citations: [{ path: 'p', text: 't' }] },
  { type: 'error', message: 'boom' },
  { type: 'replay' },
  { type: 'done' },
]) assert.strictEqual(H.recordEvent(d, ev, T0 + 5), true);
assert.deepStrictEqual(d.items.map((i) => i.type), ['text', 'result_table', 'sql', 'cite', 'error', 'replay', 'done']);
assert.strictEqual(d.items[0].text, 'hello world');
assert.ok(!('provisional' in d.items[0]));

// --- snapshot adds the stream so far without touching the chat
const e = H.newChat({ mode: 'arm2', now: T0 });
H.appendItem(e, { role: 'user', text: 'q' }, T0);
const snap = H.snapshot(e, 'partial answer');
assert.deepStrictEqual(snap.items[snap.items.length - 1], { type: 'text', text: 'partial answer', provisional: true });
assert.strictEqual(e.items.length, 1);
assert.strictEqual(H.snapshot(e, '').items.length, 1);

// --- clarify answers
const f = H.newChat({ mode: 'arm3', now: T0 });
H.recordEvent(f, { type: 'clarify', id: 'q1', question: 'Which term?', options: ['Fall', 'Spring'], allow_free_text: true });
assert.strictEqual(H.answerClarify(f, 'nope', 'x'), false);
assert.strictEqual(H.answerClarify(f, 'q1', 'Fall', T0 + 9), true);
assert.strictEqual(f.items[0].answer, 'Fall');
assert.deepStrictEqual(f.items[1], { role: 'user', text: 'Fall' });

// --- interrupted turns
assert.strictEqual(H.isInterrupted(H.newChat({ mode: 'arm1' })), false);
assert.strictEqual(H.isInterrupted(d), false);
assert.strictEqual(H.isInterrupted(e), true);
assert.strictEqual(H.isInterrupted(f), true);

// --- ordering, load, save
const s = stub();
assert.deepStrictEqual(H.load(s), { v: H.VERSION, chats: [] });
s.setItem(H.KEY, '{not json');
assert.deepStrictEqual(H.load(s), { v: H.VERSION, chats: [] });
s.setItem(H.KEY, JSON.stringify({ v: 99, chats: [c] }));
assert.deepStrictEqual(H.load(s), { v: H.VERSION, chats: [] }, 'unknown version is ignored');
const older = H.newChat({ mode: 'arm1', now: T0 - 10, id: 'old' });
older.updated = T0 - 10;
const r = H.save(s, { v: H.VERSION, chats: [older, c] }, { activeId: c.id });
assert.deepStrictEqual(r, { ok: true, evicted: [] });
assert.deepStrictEqual(H.listChats(H.load(s)).map((x) => x.id), [c.id, 'old']);

// quota: oldest non-active chats go first; the active chat is never evicted
const big = (id, upd) => { const x = H.newChat({ mode: 'arm2', now: upd, id }); x.updated = upd; x.items = [{ type: 'text', text: 'x'.repeat(400) }]; return x; };
const chats = [big('a', T0 + 1), big('b', T0 + 2), big('active', T0 + 3)];
const onlyActive = JSON.stringify({ v: H.VERSION, chats: [chats[2]] }).length;
const tight = stub(onlyActive + 10);   // room for the active chat alone
const r2 = H.save(tight, { v: H.VERSION, chats }, { activeId: 'active' });
assert.strictEqual(r2.ok, true);
assert.deepStrictEqual(r2.evicted, ['a', 'b']);
assert.deepStrictEqual(H.load(tight).chats.map((x) => x.id), ['active']);
const tiny = stub(100);
tiny.m[H.KEY] = 'previous';
const r3 = H.save(tiny, { v: H.VERSION, chats }, { activeId: 'active' });
assert.strictEqual(r3.ok, false);
assert.strictEqual(tiny.m[H.KEY], 'previous', 'a failed save leaves the old payload alone');

// cap on the number of chats
const many = Array.from({ length: 55 }, (_, i) => { const x = H.newChat({ mode: 'arm1', now: T0 + i, id: 'n' + i }); x.updated = T0 + i; return x; });
const r4 = H.save(stub(), { v: H.VERSION, chats: many }, { activeId: 'n0' });
assert.strictEqual(r4.evicted.length, 5);
assert.ok(!r4.evicted.includes('n0'), 'the active chat survives the cap');

// --- helpers
assert.strictEqual(H.relativeTime(T0, T0 + 5_000), 'just now');
assert.strictEqual(H.relativeTime(T0, T0 + 5 * 60_000), '5m ago');
assert.strictEqual(H.relativeTime(T0, T0 + 3 * 3_600_000), '3h ago');
assert.strictEqual(H.relativeTime(T0, T0 + 26 * 3_600_000), 'yesterday');
assert.strictEqual(H.relativeTime(T0, T0 + 4 * 86_400_000), '4d ago');
assert.ok(/[A-Z][a-z]{2} \d+/.test(H.relativeTime(T0, T0 + 30 * 86_400_000)));
assert.strictEqual(H.modeShort([{ id: 'arm2', short: 'Semantic layer' }], 'arm2'), 'Semantic layer');
assert.strictEqual(H.modeShort([], 'arm9'), 'arm9');

// --- store wrapper
const st = H.createStore(stub());
const g = H.newChat({ mode: 'arm3', now: T0 });
H.appendItem(g, { role: 'user', text: 'hi' }, T0);
st.setActive(g.id);
assert.strictEqual(st.put(g, 'streaming…').ok, true);
assert.strictEqual(st.get(g.id).items.length, 2, 'provisional text is saved');
assert.strictEqual(st.activeId, g.id);
assert.deepStrictEqual(st.list().map((x) => x.id), [g.id]);
st.setNav('closed');
assert.strictEqual(st.nav, 'closed');
st.clear();
assert.deepStrictEqual(st.list(), []);
assert.strictEqual(st.activeId, null);

// a storage that throws (private window) degrades to memory
const broken = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); }, removeItem() {} };
const memStore = H.createStore(broken);
assert.strictEqual(memStore.put(g).ok, true);
assert.strictEqual(memStore.get(g.id).title, 'hi');

console.log('history ok');
