// empty string uses same origin for api
const API = '';
const LIST_MAX = 2000;
// gunicorn rejects request lines over 4094 bytes
const IDS_PER_REQUEST = 200;

// in-memory concert metadata keyed by id
const concertMetaCache = {};
function cacheConcertMeta(meta) {
  if (!meta || meta.id == null) return;
  concertMetaCache[meta.id] = { ...concertMetaCache[meta.id], ...meta };
}

// throw on a non-ok response using the server error message
async function apiRequest(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let message = res.statusText || `request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data && data.error) message = String(data.error);
    } catch {
      // non-json error body
    }
    throw new Error(message);
  }
  return res.json();
}

// list rows. array filter values are repeated query params; null means is null
function apiList(entity, filters = {}, opts = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    const values = Array.isArray(value) ? value : [value];
    values.forEach(v => {
      params.append(key, v == null ? 'null' : String(v));
    });
  });
  if (opts.limit != null) params.append('limit', String(opts.limit));
  if (opts.offset != null) params.append('offset', String(opts.offset));
  if (opts.order_by) params.append('order_by', opts.order_by);
  const qs = params.toString();
  return apiRequest(`${API}/${entity}/${qs ? `?${qs}` : ''}`);
}

function dedupeIds(ids) {
  const seen = new Set();
  const unique = [];
  (ids || []).forEach(id => {
    if (id == null || id === '') return;
    const key = String(id);
    if (seen.has(key)) return;
    seen.add(key);
    unique.push(id);
  });
  return unique;
}

// get rows by id. empty input does not fetch. chunks keep the url short
async function apiGet(entity, ids) {
  const unique = dedupeIds(ids);
  if (!unique.length) return [];
  const rows = [];
  for (let i = 0; i < unique.length; i += IDS_PER_REQUEST) {
    const chunk = unique.slice(i, i + IDS_PER_REQUEST);
    const part = await apiList(entity, { id: chunk }, { limit: chunk.length });
    rows.push(...part);
  }
  return rows;
}

// page through a filter. long id lists are split so the query string stays small
async function apiListAll(entity, filters = {}, opts = {}) {
  if (Object.values(filters).some(value => Array.isArray(value) && value.length === 0)) {
    return [];
  }
  const longKey = Object.keys(filters).find(
    key => Array.isArray(filters[key]) && filters[key].length > IDS_PER_REQUEST
  );
  if (longKey) {
    const ids = filters[longKey];
    const rows = [];
    for (let i = 0; i < ids.length; i += IDS_PER_REQUEST) {
      const part = await apiListAll(
        entity,
        { ...filters, [longKey]: ids.slice(i, i + IDS_PER_REQUEST) },
        opts,
      );
      rows.push(...part);
    }
    return rows;
  }

  const limit = opts.limit ?? LIST_MAX;
  const rows = [];
  let offset = 0;
  for (;;) {
    const page = await apiList(entity, filters, {
      limit,
      offset,
      order_by: opts.order_by,
    });
    rows.push(...page);
    if (page.length < limit) return rows;
    offset += page.length;
    if (offset > 20000) return rows;
  }
}

function apiAutocomplete(entity, prefix, limit) {
  const url = `${API}/${entity}/autocomplete/${encodeURIComponent(prefix)}`;
  if (limit == null) return apiRequest(url);
  const params = new URLSearchParams();
  params.append('limit', String(limit));
  return apiRequest(`${url}?${params}`);
}

function apiWorkflow(name, body) {
  return apiRequest(`${API}/workflows/${name}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// id -> name for ragas, talams, and composers. one fetch per page
const ragaById = {};
const talamById = {};
const composerById = {};
let lookupsPromise = null;

function loadLookups() {
  if (!lookupsPromise) {
    lookupsPromise = Promise.all([
      apiList('ragas', {}, { limit: LIST_MAX }),
      apiList('talams', {}, { limit: LIST_MAX }),
      apiList('composers', {}, { limit: LIST_MAX }),
    ]).then(([ragas, talams, composers]) => {
      ragas.forEach(row => { ragaById[row.id] = row.name; });
      talams.forEach(row => { talamById[row.id] = row.name; });
      composers.forEach(row => { composerById[row.id] = row.name; });
    }).catch(err => {
      lookupsPromise = null;
      throw err;
    });
  }
  return lookupsPromise;
}

// names for a piece row that only has raga_id, talam_id, composer_id
function pieceMeta(piece) {
  if (!piece) return { raga: null, talam: null, composer: null };
  return {
    raga: piece.raga_id != null ? (ragaById[piece.raga_id] || null) : null,
    talam: piece.talam_id != null ? (talamById[piece.talam_id] || null) : null,
    composer: piece.composer_id != null ? (composerById[piece.composer_id] || null) : null,
  };
}

function youtubeUrl(youtubeId, timestampSeconds) {
  if (!youtubeId) return null;
  const base = `https://www.youtube.com/watch?v=${youtubeId}`;
  if (timestampSeconds == null) return base;
  return `${base}&t=${timestampSeconds}`;
}

// reusable debounced autocomplete dropdown for search inputs
// pass fetchItems(q) to post-process, or fetchUrl(q) for a raw get
function createAutocomplete({ input, list, fetchUrl, fetchItems, renderItem, onSelect }) {
  let items = [];
  let activeIdx = -1;
  let timer = null;

  const close = () => {
    list.classList.remove('open');
    list.innerHTML = '';
    items = [];
    activeIdx = -1;
  };

  // render fetched suggestions as list items
  const render = () => {
    list.innerHTML = '';
    activeIdx = -1;
    if (!items.length) { close(); return; }
    items.forEach((item) => {
      const li = document.createElement('li');
      li.className = 'ac-item';
      li.setAttribute('role', 'option');
      renderItem(li, item);
      li.addEventListener('mousedown', (e) => {
        e.preventDefault();
        onSelect(item);
        close();
      });
      list.appendChild(li);
    });
    list.classList.add('open');
  };

  const query = async (q) => {
    try {
      if (fetchItems) {
        items = await fetchItems(q);
      } else {
        const res = await fetch(fetchUrl(q));
        if (!res.ok) throw new Error('autocomplete failed');
        items = await res.json();
      }
      if (!Array.isArray(items)) { close(); return; }
      render();
    } catch {
      close();
    }
  };

  // debounce typing before hitting autocomplete endpoint
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 1) { close(); return; }
    timer = setTimeout(() => query(q), 160);
  });

  // arrow keys enter and escape for suggestions
  input.addEventListener('keydown', (e) => {
    if (!list.classList.contains('open')) return;
    const els = list.querySelectorAll('.ac-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, els.length - 1);
      updateActive(els);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
      updateActive(els);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIdx >= 0 && items[activeIdx]) {
        onSelect(items[activeIdx]);
        close();
      }
    } else if (e.key === 'Escape') {
      close();
    }
  });

  function updateActive(els) {
    els.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
    if (activeIdx >= 0) els[activeIdx].scrollIntoView({ block: 'nearest' });
  }

  // close dropdown when clicking outside input
  document.addEventListener('click', (e) => {
    if (!list.contains(e.target) && e.target !== input) close();
  });

  return { close };
}

// join piece metadata fields for display
function formatPieceMeta({ raga, talam, composer }) {
  return [raga, talam, composer].filter(Boolean).join(' · ');
}

function formatArtists(artists) {
  return artists.map(a => a.name).join(' · ');
}

// lineup for many concerts: concert-artists, then artists by id
// main artists first, then by name. returns {concert_id: [{id,name,instrument,role}]}
async function fetchArtistsByConcert(renditions) {
  const concertIds = dedupeIds((renditions || []).map(entry => (
    entry != null && typeof entry === 'object' ? entry.concert_id : entry
  )));
  const cache = {};
  concertIds.forEach(id => { cache[id] = []; });
  if (!concertIds.length) return cache;

  const links = await apiListAll('concert-artists', { concert_id: concertIds });
  const artists = await apiGet('artists', links.map(link => link.artist_id));
  const artistById = new Map(artists.map(artist => [artist.id, artist]));

  links.forEach(link => {
    const artist = artistById.get(link.artist_id);
    if (!artist) return;
    if (!cache[link.concert_id]) cache[link.concert_id] = [];
    cache[link.concert_id].push({
      id: artist.id,
      name: artist.name,
      instrument: link.instrument,
      role: link.role,
    });
  });

  Object.values(cache).forEach(group => {
    group.sort((a, b) => {
      const role = (a.role === 'main artist' ? 0 : 1) - (b.role === 'main artist' ? 0 : 1);
      if (role) return role;
      const an = a.name || '';
      const bn = b.name || '';
      if (an < bn) return -1;
      if (an > bn) return 1;
      return 0;
    });
  });
  return cache;
}

// format elapsed seconds as h:mm:ss or m:ss
function formatDuration(secs) {
  if (secs == null || secs <= 0) return '—';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

// warm the lookup cache once per page
loadLookups().catch(() => {});
