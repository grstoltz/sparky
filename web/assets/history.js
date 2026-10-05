/* Chat history kept in the browser: the record shape, what gets stored, and quota-aware saving.
 * Pure functions (no DOM; storage is injected), so they can be tested with Node:
 * `node tests/history.test.js`. The page wires them up in index.html.
 *
 * chat = { id, v, mode, mock, sid, title, created, updated, items }
 * item = { role:'user', text } | a renderable bot event (see STORED_TYPES); a 'text' item may be
 *        provisional (joined stream deltas saved before the final text arrived).
 */
(function (root) {
  const VERSION = 1;
  const KEY = 'sparky.history.v1';
  const ACTIVE_KEY = 'sparky.history.active';   // written separately: a quota failure never loses it
  const NAV_KEY = 'sparky.history.nav';
  const MAX_CHATS = 50;
  const TITLE_MAX = 48;
  const STORED_TYPES = new Set(['text', 'result_table', 'sql', 'cite', 'clarify', 'error', 'replay', 'done']);

  const newId = (now) => 'c' + now.toString(36) + Math.random().toString(36).slice(2, 8);

  function newChat({ mode, mock = false, now = Date.now(), id } = {}) {
    return { id: id || newId(now), v: VERSION, mode, mock: !!mock, sid: null, title: 'New chat',
      created: now, updated: now, items: [] };
  }

  function titleFor(text, max = TITLE_MAX) {
    const t = String(text || '').replace(/\s+/g, ' ').trim();
    if (!t) return 'New chat';
    return t.length > max ? t.slice(0, max - 1).trimEnd() + '…' : t;
  }

  function appendItem(chat, item, now = Date.now()) {
    if (item.role === 'user' && !chat.items.some((i) => i.role === 'user')) chat.title = titleFor(item.text);
    chat.items.push(item);
    chat.updated = now;
    return chat;
  }

  // Keep only what the log needs to be rebuilt. Stream deltas, tool calls and usage are skipped.
  function recordEvent(chat, ev, now = Date.now()) {
    if (!ev || !STORED_TYPES.has(ev.type)) return false;
    const last = chat.items[chat.items.length - 1];
    if (ev.type === 'text' && last && last.type === 'text' && last.provisional) chat.items.pop();
    appendItem(chat, { ...ev }, now);
    return true;
  }

  function answerClarify(chat, questionId, answer, now = Date.now()) {
    const q = chat.items.find((i) => i.type === 'clarify' && i.id === questionId);
    if (!q) return false;
    q.answer = answer;
    appendItem(chat, { role: 'user', text: answer }, now);
    return true;
  }

  // Copy for saving; a non-empty provisional text (the stream so far) is added as a bot bubble.
  function snapshot(chat, provisionalText) {
    const items = chat.items.slice();
    const last = items[items.length - 1];
    if (provisionalText && !(last && last.type === 'text')) items.push({ type: 'text', text: provisionalText, provisional: true });
    return { ...chat, items };
  }

  // A turn that never reached 'done': reload mid-stream, lost connection, or a clarify left pending.
  function isInterrupted(chat) {
    const last = chat.items[chat.items.length - 1];
    return !!last && last.type !== 'done';
  }

  function listChats(payload) {
    return (payload.chats || []).slice().sort((a, b) => (b.updated - a.updated) || (b.created - a.created));
  }

  function modeShort(modes, id) {
    const m = (modes || []).find((x) => x.id === id);
    return (m && m.short) || id;
  }

  function relativeTime(then, now = Date.now()) {
    const s = Math.max(0, Math.round((now - then) / 1000));
    if (s < 60) return 'just now';
    const m = Math.round(s / 60);
    if (m < 60) return m + 'm ago';
    const h = Math.round(m / 60);
    if (h < 24) return h + 'h ago';
    const d = Math.round(h / 24);
    if (d === 1) return 'yesterday';
    if (d < 7) return d + 'd ago';
    const dt = new Date(then);
    return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  const empty = () => ({ v: VERSION, chats: [] });

  function load(storage, key = KEY) {
    try {
      const raw = storage.getItem(key);
      if (!raw) return empty();
      const data = JSON.parse(raw);
      if (!data || data.v !== VERSION || !Array.isArray(data.chats)) return empty();
      return data;
    } catch (e) {
      return empty();
    }
  }

  // Sort, cap, then write; if the browser refuses (quota), drop the oldest chat that is not the
  // active one and try again. Returns the ids that were evicted.
  function save(storage, payload, { activeId = null, key = KEY, maxChats = MAX_CHATS } = {}) {
    let chats = listChats(payload);
    const evicted = [];
    if (chats.length > maxChats) {
      const keep = chats.slice(0, maxChats);
      if (activeId && !keep.some((c) => c.id === activeId)) {
        const active = chats.find((c) => c.id === activeId);
        keep.pop(); keep.push(active);
      }
      chats.filter((c) => !keep.includes(c)).forEach((c) => evicted.push(c.id));
      chats = keep;
    }
    for (;;) {
      try {
        storage.setItem(key, JSON.stringify({ v: VERSION, chats }));
        return { ok: true, evicted };
      } catch (e) {
        let i = chats.length - 1;
        while (i >= 0 && chats[i].id === activeId) i--;
        if (i < 0) return { ok: false, evicted };
        evicted.push(chats[i].id);
        chats.splice(i, 1);
      }
    }
  }

  // Stateful convenience wrapper. If the storage is unusable (e.g. a private window that throws),
  // it keeps everything in memory for the life of the page.
  function createStore(storage, opts = {}) {
    const key = opts.key || KEY, maxChats = opts.maxChats || MAX_CHATS;
    const mem = { m: {}, getItem(k) { return k in this.m ? this.m[k] : null; }, setItem(k, v) { this.m[k] = String(v); }, removeItem(k) { delete this.m[k]; } };
    let st = storage;
    try { st.getItem(key); } catch (e) { st = mem; }
    let payload = load(st, key);
    const store = {
      list: () => listChats(payload),
      get: (id) => payload.chats.find((c) => c.id === id),
      put(chat, provisionalText) {
        const snap = snapshot(chat, provisionalText);
        const i = payload.chats.findIndex((c) => c.id === chat.id);
        if (i >= 0) payload.chats[i] = snap; else payload.chats.push(snap);
        const r = save(st, payload, { activeId: store.activeId, key, maxChats });
        if (r.evicted.length) payload.chats = payload.chats.filter((c) => !r.evicted.includes(c.id));
        return r;
      },
      remove(id) { payload.chats = payload.chats.filter((c) => c.id !== id); return save(st, payload, { activeId: store.activeId, key, maxChats }); },
      clear() { payload = empty(); try { st.removeItem(key); st.removeItem(ACTIVE_KEY); } catch (e) { /* nothing to clear */ } },
      get activeId() { try { return st.getItem(ACTIVE_KEY) || null; } catch (e) { return null; } },
      setActive(id) { try { if (id) st.setItem(ACTIVE_KEY, id); else st.removeItem(ACTIVE_KEY); } catch (e) { /* best effort */ } },
      get nav() { try { return st.getItem(NAV_KEY); } catch (e) { return null; } },
      setNav(v) { try { st.setItem(NAV_KEY, v); } catch (e) { /* best effort */ } },
    };
    return store;
  }

  const api = { VERSION, KEY, ACTIVE_KEY, NAV_KEY, MAX_CHATS, TITLE_MAX, STORED_TYPES, newChat, titleFor, appendItem,
    recordEvent, answerClarify, snapshot, isInterrupted, listChats, modeShort, relativeTime, load, save, createStore };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SparkyHistory = api;
})(typeof window !== 'undefined' ? window : globalThis);
