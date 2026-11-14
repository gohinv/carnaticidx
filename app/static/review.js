// ---- State ----
let drafts = [];
let draftsTotal = 0;
let currentIdx = -1;
let ragas = [], composers = [], talams = [];
let selectedPieceId = null;
let suggestionIdx = -1;
let currentTab = 'drafts';
let pieceEditId = null;
let pieceSearchTimer = null;
let concertSearchTimer = null;
let setlistConcertId = null;
let setlistPieceTimers = {};
let setlistSuggestionIdx = {};
let concertDrafts = [];
let concertDraftsTotal = 0;
let expandedConcertDraftId = null;
let concertDraftDetailCache = {};
let concertArtistRowSeq = 0;
let concertArtistTimers = {};
let concertArtistSuggestionIdx = {};
const KIND_OPTIONS = ['','krithi','varnam','padam','tillana','viruttam','slokam','mangalam','bhajan','rtp','alapana'];
const ARTIST_ROLE_OPTIONS = ['main artist', 'accompanist'];
const lookup = {
  ragas: { byId: new Map(), byName: new Map() },
  composers: { byId: new Map(), byName: new Map() },
  talams: { byId: new Map(), byName: new Map() },
};

// ---- API client ----
async function apiSend(method, url, body) {
  const opts = { method };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  const text = await res.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = null; }
  }
  if (!res.ok) {
    let message = (data && data.error) || (text && text.trim()) || res.statusText || `HTTP ${res.status}`;
    if (message.length > 500) message = message.slice(0, 500);
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  return data;
}

async function apiList(entity, params = {}) {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    if (key === 'limit' || key === 'offset' || key === 'order_by') {
      if (value != null && value !== '') qs.set(key, String(value));
      continue;
    }
    const values = Array.isArray(value) ? value : [value];
    for (const item of values) {
      if (item === undefined) continue;
      qs.append(key, item == null ? 'null' : String(item));
    }
  }
  const query = qs.toString();
  const data = await apiSend('GET', `/${entity}/${query ? `?${query}` : ''}`);
  if (!Array.isArray(data)) throw new Error('Expected a list');
  return data;
}

async function apiListAll(entity, params = {}) {
  const pageSize = 2000;
  const all = [];
  const seen = new Set();
  let offset = 0;
  for (;;) {
    const page = await apiList(entity, { ...params, limit: pageSize, offset });
    if (!page.length || seen.has(page[0].id)) return all;
    for (const row of page) {
      if (seen.has(row.id)) continue;
      seen.add(row.id);
      all.push(row);
    }
    if (page.length < pageSize) return all;
    offset += page.length;
  }
}

function uniqueIds(ids) {
  const unique = [];
  const seen = new Set();
  for (const id of ids || []) {
    if (id == null || id === '') continue;
    const key = String(id);
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(id);
  }
  return unique;
}

async function apiGet(entity, ids) {
  const unique = uniqueIds(ids);
  if (!unique.length) return [];
  const out = [];
  const chunkSize = 200;
  for (let i = 0; i < unique.length; i += chunkSize) {
    const chunk = unique.slice(i, i + chunkSize);
    const rows = await apiList(entity, { id: chunk, limit: chunk.length });
    out.push(...rows);
  }
  return out;
}

async function apiListIn(entity, column, ids, extra = {}) {
  const unique = uniqueIds(ids);
  if (!unique.length) return [];
  const chunkSize = 100;
  const groups = [];
  for (let i = 0; i < unique.length; i += chunkSize) {
    groups.push(apiListAll(entity, { ...extra, [column]: unique.slice(i, i + chunkSize) }));
  }
  const pages = await Promise.all(groups);
  return pages.flat();
}

async function apiAutocomplete(entity, prefix, limit) {
  const qs = new URLSearchParams();
  if (limit != null) qs.set('limit', String(limit));
  const query = qs.toString();
  return apiSend(
    'GET',
    `/${entity}/autocomplete/${encodeURIComponent(prefix)}${query ? `?${query}` : ''}`,
  );
}

async function apiCreate(entity, body) {
  return apiSend('POST', `/${entity}/`, body);
}

async function apiUpdate(entity, id, body) {
  return apiSend('PUT', `/${entity}/${id}`, body);
}

async function apiWorkflow(name, body) {
  return apiSend('POST', `/workflows/${name}`, body === undefined ? undefined : body);
}

function indexById(rows) {
  const map = new Map();
  for (const row of rows || []) map.set(row.id, row);
  return map;
}

function countBy(rows, key) {
  const counts = new Map();
  for (const row of rows || []) counts.set(row[key], (counts.get(row[key]) || 0) + 1);
  return counts;
}

function cmpText(a, b) {
  const as = a == null ? '' : String(a);
  const bs = b == null ? '' : String(b);
  if (as < bs) return -1;
  if (as > bs) return 1;
  return 0;
}

function cmpSequence(a, b) {
  const as = a.sequence_number;
  const bs = b.sequence_number;
  if (as == null && bs == null) return (a.id || 0) - (b.id || 0);
  if (as == null) return 1;
  if (bs == null) return -1;
  if (as !== bs) return as - bs;
  return (a.id || 0) - (b.id || 0);
}

function namesFor(entity) {
  if (entity === 'ragas') return ragas;
  if (entity === 'composers') return composers;
  if (entity === 'talams') return talams;
  return null;
}

function rememberLookup(entity, row) {
  const bucket = lookup[entity];
  if (!bucket || !row) return;
  bucket.byId.set(row.id, row.name);
  bucket.byName.set(row.name, row.id);
  const names = namesFor(entity);
  if (names && !names.includes(row.name)) {
    names.push(row.name);
    names.sort(cmpText);
  }
}

function indexLookup(entity, rows) {
  const bucket = lookup[entity];
  bucket.byId.clear();
  bucket.byName.clear();
  for (const row of rows) {
    bucket.byId.set(row.id, row.name);
    bucket.byName.set(row.name, row.id);
  }
}

function lookupName(entity, id) {
  if (id == null) return null;
  const name = lookup[entity]?.byId.get(id);
  return name == null ? null : name;
}

function namedLookup(entity, id, fallback) {
  if (id == null) return fallback ?? null;
  const name = lookup[entity]?.byId.get(id);
  return name != null ? name : (fallback ?? null);
}

async function resolveNamedId(entity, name) {
  if (name == null || name === '') return null;
  const bucket = lookup[entity];
  if (bucket.byName.has(name)) return bucket.byName.get(name);
  try {
    const created = await apiCreate(entity, { name });
    rememberLookup(entity, created);
    return created.id;
  } catch (err) {
    if (err.status !== 409) throw err;
    const rows = await apiList(entity, { name, limit: 50 });
    const exact = (rows || []).find(row => row.name === name);
    if (!exact) throw err;
    rememberLookup(entity, exact);
    return exact.id;
  }
}

// ---- Summary adapters (old review JSON shapes) ----
function pieceSummary(piece) {
  if (!piece) return null;
  return {
    id: piece.id,
    name: piece.name,
    kind: piece.kind,
    raga: lookupName('ragas', piece.raga_id),
    composer: lookupName('composers', piece.composer_id),
    talam: lookupName('talams', piece.talam_id),
    raga_id: piece.raga_id,
    composer_id: piece.composer_id,
    talam_id: piece.talam_id,
  };
}

function concertSummary(concert) {
  if (!concert) return null;
  return {
    id: concert.id,
    youtube_id: concert.youtube_id,
    title: concert.title,
    year: concert.year,
    venue: concert.venue,
    duration_seconds: concert.duration_seconds,
    url: `https://www.youtube.com/watch?v=${concert.youtube_id}`,
  };
}

function draftSummary(d, concertTitle) {
  return {
    id: d.id,
    youtube_id: d.youtube_id,
    sequence_number: d.sequence_number,
    timestamp_seconds: d.timestamp_seconds,
    raw_line: d.raw_line,
    parsed_piece: d.parsed_piece,
    parsed_raga: d.parsed_raga,
    parsed_talam: d.parsed_talam,
    parsed_composer: d.parsed_composer,
    parsed_kind: d.parsed_kind,
    confidence: d.confidence == null ? 0 : d.confidence,
    status: d.status,
    concert_title: concertTitle ?? null,
  };
}

function neighbourFromDraft(d) {
  const piece = d.parsed_piece ? {
    name: d.parsed_piece,
    raga: d.parsed_raga || null,
    composer: d.parsed_composer || null,
    talam: d.parsed_talam || null,
    kind: d.parsed_kind || null,
  } : null;
  return {
    id: d.id,
    sequence_number: d.sequence_number,
    timestamp_seconds: d.timestamp_seconds,
    piece_id: null,
    piece,
  };
}

function setlistItemSummary(si, piece) {
  return {
    id: si.id,
    concert_id: si.concert_id,
    sequence_number: si.sequence_number,
    timestamp_seconds: si.timestamp_seconds,
    piece_id: si.piece_id,
    piece: piece ? pieceSummary(piece) : null,
  };
}

function concertArtistSummary(ca, artist) {
  return {
    id: ca.id,
    artist_id: artist ? artist.id : ca.artist_id,
    artist_name: artist ? artist.name : null,
    instrument: ca.instrument,
    role: ca.role,
  };
}

function concertArtistDraftSummary(row, artist) {
  return {
    id: row.id,
    artist_id: row.artist_id,
    artist_name: artist ? artist.name : row.artist_name,
    submitted_artist_name: row.artist_name,
    instrument: row.instrument,
    role: row.role,
  };
}

function setlistItemDraftSummary(item, piece) {
  const linked = piece || null;
  return {
    id: item.id,
    concert_draft_id: item.concert_draft_id,
    piece_id: item.piece_id,
    piece_name: linked ? linked.name : item.piece_name,
    submitted_piece_name: item.piece_name,
    raga_id: item.raga_id,
    raga_name: namedLookup('ragas', item.raga_id, item.raga_name),
    talam_id: item.talam_id,
    talam_name: namedLookup('talams', item.talam_id, item.talam_name),
    composer_id: item.composer_id,
    composer_name: namedLookup('composers', item.composer_id, item.composer_name),
    kind: linked ? linked.kind : item.kind,
    timestamp_seconds: item.timestamp_seconds,
    sequence_number: item.sequence_number,
  };
}

function httpError(message, status) {
  const err = new Error(message);
  err.status = status;
  return err;
}

// ---- Init ----
async function init() {
  try {
    await loadLookups();
  } catch (err) {
    toast(err.message || 'Failed to load lookups', true);
  }
  await loadDrafts();
}

async function loadLookups() {
  const [ragaRows, composerRows, talamRows] = await Promise.all([
    apiListAll('ragas', { order_by: 'name' }),
    apiListAll('composers', { order_by: 'name' }),
    apiListAll('talams', { order_by: 'name' }),
  ]);
  indexLookup('ragas', ragaRows);
  indexLookup('composers', composerRows);
  indexLookup('talams', talamRows);
  ragas = ragaRows.map(row => row.name);
  composers = composerRows.map(row => row.name);
  talams = talamRows.map(row => row.name);
}

async function fetchReviewDrafts() {
  const rows = await apiList('ingest-drafts', {
    status: 'needs_review',
    order_by: 'youtube_id',
    limit: 200,
  });
  rows.sort((a, b) => {
    const yt = cmpText(a.youtube_id, b.youtube_id);
    if (yt) return yt;
    return cmpSequence(a, b);
  });
  const ytIds = [...new Set(rows.map(d => d.youtube_id).filter(Boolean))];
    const concerts = await apiListIn('concerts', 'youtube_id', ytIds);
  const titleByYt = new Map(concerts.map(c => [c.youtube_id, c.title]));
  const items = rows.map(d => draftSummary(d, titleByYt.get(d.youtube_id) ?? null));
  return { items, total: items.length };
}

async function loadDrafts() {
  try {
    const data = await fetchReviewDrafts();
    drafts = data.items;
    draftsTotal = data.total;
    currentIdx = -1;
    updateDraftStats();
    renderList();
    if (drafts.length > 0) await selectDraft(0);
  } catch (err) {
    drafts = [];
    draftsTotal = 0;
    currentIdx = -1;
    updateDraftStats();
    const el = document.getElementById('stats');
    if (el) el.textContent = err.message || 'Failed to load drafts';
    toast(err.message || 'Failed to load drafts', true);
  }
}

function updateDraftStats() {
  const el = document.getElementById('stats');
  if (!el) return;
  if (draftsTotal === 0) {
    el.textContent = 'No drafts remaining';
  } else if (drafts.length < draftsTotal) {
    el.textContent = `${draftsTotal} drafts remaining (showing ${drafts.length})`;
  } else {
    el.textContent = `${draftsTotal} drafts remaining`;
  }
}

async function refillDraftQueue() {
  let data;
  try {
    data = await fetchReviewDrafts();
  } catch (err) {
    toast(err.message || 'Failed to load drafts', true);
    return;
  }
  draftsTotal = data.total;
  if (data.items.length === 0) {
    drafts = [];
    currentIdx = -1;
    updateDraftStats();
    renderList();
    document.getElementById('detail').innerHTML =
      '<div class="empty"><span>✅</span>All drafts resolved!</div>';
    return;
  }
  drafts = data.items;
  currentIdx = 0;
  updateDraftStats();
  renderList();
  await selectDraft(0);
}

async function loadDraftDetail(summary) {
  const youtubeId = summary.youtube_id;
  const [concertRows, neighbourRows] = await Promise.all([
    youtubeId ? apiList('concerts', { youtube_id: youtubeId, limit: 1 }) : Promise.resolve([]),
    youtubeId
      ? apiListAll('ingest-drafts', { youtube_id: youtubeId, order_by: 'sequence_number' })
      : Promise.resolve([]),
  ]);
  let draft = (neighbourRows || []).find(row => row.id === summary.id);
  if (!draft) {
    const rows = await apiGet('ingest-drafts', [summary.id]);
    draft = rows[0];
  }
  if (!draft) throw httpError('Draft not found', 404);
  const concert = concertRows[0] || null;
  const neighbours = (neighbourRows || []).map(neighbourFromDraft);
  neighbours.sort(cmpSequence);
  return {
    ...draftSummary(draft, concert ? concert.title : null),
    concert_id: concert ? concert.id : null,
    timestamp_fmt: fmtTs(draft.timestamp_seconds),
    neighbours,
  };
}

// ---- Tab switching ----
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach((el, i) => {
    el.classList.toggle('active', ['drafts','contributions','pieces','setlists'][i] === tab);
  });
  document.getElementById('sidebar').style.display = tab === 'drafts' ? 'flex' : 'none';
  document.getElementById('detail').style.display = tab === 'drafts' ? 'block' : 'none';
  document.getElementById('contributions-panel').style.display = tab === 'contributions' ? 'flex' : 'none';
  document.getElementById('pieces-panel').style.display = tab === 'pieces' ? 'flex' : 'none';
  document.getElementById('setlists-panel').style.display = tab === 'setlists' ? 'flex' : 'none';
  if (tab === 'contributions') initContributionsPanel();
  if (tab === 'pieces') initPiecesPanel();
  if (tab === 'setlists') initSetlistsPanel();
  if (tab === 'drafts') updateDraftStats();
}

// ---- Draft list ----
function renderList() {
  const container = document.getElementById('list-container');
  if (drafts.length === 0) {
    container.innerHTML = '<div class="empty" style="margin-top:40px"><span>✅</span>All done!</div>';
    return;
  }
  container.innerHTML = drafts.map((d, i) => {
    const conf = d.confidence;
    const cls = conf < 0.4 ? 'conf-low' : conf < 0.7 ? 'conf-mid' : 'conf-high';
    return `<div class="draft-item${i === currentIdx ? ' active' : ''}" onclick="selectDraft(${i})">
      <div class="draft-title">${d.parsed_piece || '<em style="color:#555">no piece name</em>'}
        <span class="draft-conf ${cls}">${(conf*100).toFixed(0)}%</span>
      </div>
      <div class="draft-meta">${d.concert_title ? truncate(d.concert_title,34) : d.youtube_id} · seq ${d.sequence_number}</div>
    </div>`;
  }).join('');
}

function truncate(s, n) { return s.length > n ? s.slice(0,n)+'…' : s; }

async function selectDraft(idx) {
  currentIdx = idx;
  selectedPieceId = null;
  renderList();
  const d = drafts[idx];
  if (!d) return;
  try {
    const detail = await loadDraftDetail(d);
    if (currentIdx !== idx) return;
    renderDetail(detail);
  } catch (err) {
    if (currentIdx !== idx) return;
    toast(err.message || 'Failed to load draft', true);
  }
}

// ---- Detail pane ----
function renderDetail(d) {
  selectedPieceId = null;
  const ytUrl = `https://youtu.be/${d.youtube_id}${d.timestamp_seconds ? '?t='+d.timestamp_seconds : ''}`;

  const neighbours = (d.neighbours || []).map(si => {
    const isCurrent = si.sequence_number === d.sequence_number;
    return `<div class="neighbour${isCurrent ? ' current' : ''}">
      <span class="neighbour-seq">${si.sequence_number}.</span>
      <span class="neighbour-ts">${fmtTs(si.timestamp_seconds)}</span>
      <span class="neighbour-piece">${si.piece ? si.piece.name : '<span style="color:#444">—</span>'}
        ${si.piece ? `<span class="neighbour-sub">· ${si.piece.raga||'?'} · ${si.piece.talam||'?'}</span>` : ''}
      </span>
    </div>`;
  }).join('');

  document.getElementById('detail').innerHTML = `
    <div class="section">
      <div class="label">Concert</div>
      <a class="concert-link" href="${ytUrl}" target="_blank">▶ ${d.concert_title || d.youtube_id}</a>
    </div>

    <div class="section">
      <div class="label">Raw line</div>
      <div class="raw-line">${escHtml(d.raw_line)}</div>
    </div>

    <div class="section">
      <div class="label">Match piece</div>
      <div id="piece-search-wrap">
        <input id="piece-search" class="field input" placeholder="Search pieces (or type new name)…"
          value="${escHtml(d.parsed_piece||'')}"
          oninput="onPieceSearch(this.value)"
          onkeydown="onPieceSearchKey(event)"
          autocomplete="off">
        <div id="piece-suggestions" style="display:none"></div>
      </div>
    </div>

    <div class="section">
      <div class="label">Metadata <span style="color:#444;font-size:10px;font-weight:400;text-transform:none">(leave blank to inherit from matched piece)</span></div>
      <div class="fields">
        <div class="field">
          <label>Raga</label>
          ${datalistInput('raga-input', 'raga-list', ragas, d.parsed_raga||'')}
        </div>
        <div class="field">
          <label>Composer</label>
          ${datalistInput('composer-input', 'composer-list', composers, d.parsed_composer||'')}
        </div>
        <div class="field">
          <label>Talam</label>
          ${datalistInput('talam-input', 'talam-list', talams, d.parsed_talam||'')}
        </div>
        <div class="field">
          <label>Kind</label>
          <select id="kind-input">
            ${['','krithi','varnam','padam','tillana','viruttam','slokam','mangalam','bhajan','rtp','alapana'].map(k =>
              `<option value="${k}"${k===(d.parsed_kind||'')?'selected':''}>${k||'—'}</option>`
            ).join('')}
          </select>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="label">Setlist context</div>
      ${neighbours || '<div style="color:#444;font-size:12px">No setlist items yet</div>'}
    </div>

    <div class="actions">
      <button class="btn btn-resolve" onclick="resolveAction()">Resolve → setlist</button>
      <button class="btn btn-skip" onclick="statusAction('skip')">Skip</button>
      <button class="btn btn-reject" onclick="statusAction('reject')">Reject</button>
      <button class="btn btn-next" onclick="nextDraft()">Next →</button>
    </div>
    <div class="kbd-hints">
      <kbd>j</kbd> next &nbsp; <kbd>k</kbd> prev &nbsp; <kbd>/</kbd> search piece &nbsp;
      <kbd>Enter</kbd> resolve &nbsp; <kbd>s</kbd> skip &nbsp; <kbd>x</kbd> reject
    </div>
  `;
  // Focus search if piece name present
  const ps = document.getElementById('piece-search');
  if (ps && d.parsed_piece) ps.select();
}

function datalistInput(id, listId, options, value) {
  return `<input id="${id}" list="${listId}" value="${escHtml(value)}" autocomplete="off">
    <datalist id="${listId}">${options.map(o=>`<option value="${escHtml(o)}">`).join('')}</datalist>`;
}

// ---- Piece search / autocomplete ----
let searchTimer = null;
async function onPieceSearch(q) {
  selectedPieceId = null;
  clearTimeout(searchTimer);
  if (!q || q.length < 2) { hideSuggestions(); return; }
  searchTimer = setTimeout(async () => {
    try {
      const items = (await apiAutocomplete('pieces', q, 8)).map(pieceSummary);
      showSuggestions(items);
    } catch (err) {
      hideSuggestions();
      toast(err.message || 'Piece search failed', true);
    }
  }, 180);
}

function showSuggestions(items) {
  const box = document.getElementById('piece-suggestions');
  if (!items.length) { box.style.display = 'none'; return; }
  suggestionIdx = -1;
  box.innerHTML = items.map((p, i) =>
    `<div class="suggestion" data-id="${p.id}" data-name="${escHtml(p.name)}"
         onmousedown="pickSuggestion(${p.id}, '${escHtml(p.name)}')"
         onmouseover="suggestionIdx=${i};highlightSuggestion()">
      <div>${escHtml(p.name)}</div>
      <div class="suggestion-sub">${[p.raga,p.composer,p.talam].filter(Boolean).join(' · ')}</div>
    </div>`
  ).join('');
  box.style.display = 'block';
}

function hideSuggestions() {
  const box = document.getElementById('piece-suggestions');
  if (box) { box.style.display = 'none'; suggestionIdx = -1; }
}

function onPieceSearchKey(e) {
  const box = document.getElementById('piece-suggestions');
  const items = box ? box.querySelectorAll('.suggestion') : [];
  if (e.key === 'ArrowDown') {
    e.preventDefault(); suggestionIdx = Math.min(suggestionIdx+1, items.length-1); highlightSuggestion();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault(); suggestionIdx = Math.max(suggestionIdx-1, -1); highlightSuggestion();
  } else if (e.key === 'Enter' && suggestionIdx >= 0) {
    e.preventDefault(); e.stopPropagation();
    const el = items[suggestionIdx];
    if (el) pickSuggestion(+el.dataset.id, el.dataset.name);
  } else if (e.key === 'Escape') {
    hideSuggestions();
  }
}

function highlightSuggestion() {
  document.querySelectorAll('#piece-suggestions .suggestion').forEach((el, i) => {
    el.classList.toggle('active', i === suggestionIdx);
  });
}

function pickSuggestion(id, name) {
  selectedPieceId = id;
  const ps = document.getElementById('piece-search');
  if (ps) { ps.value = name; }
  hideSuggestions();
}

// ---- Actions ----
async function resolveAction() {
  const d = drafts[currentIdx];
  if (!d) return;
  const pieceName = document.getElementById('piece-search')?.value?.trim();
  const body = {
    piece_name: pieceName || d.parsed_piece,
    raga: document.getElementById('raga-input')?.value?.trim() || null,
    composer: document.getElementById('composer-input')?.value?.trim() || null,
    talam: document.getElementById('talam-input')?.value?.trim() || null,
    kind: document.getElementById('kind-input')?.value || null,
  };
  if (selectedPieceId) body.piece_id = selectedPieceId;

  try {
    const data = await apiWorkflow(`resolve-ingest-draft/${d.id}`, body);
    toast(`✓ Resolved → ${data.piece.name}`);
    await removeCurrent();
  } catch (err) {
    toast(err.message || 'Error', true);
  }
}

async function statusAction(action) {
  const d = drafts[currentIdx];
  if (!d) return;
  const status = action === 'skip' ? 'skipped' : 'rejected';
  try {
    await apiUpdate('ingest-drafts', d.id, { status });
    toast(action === 'skip' ? 'Skipped' : 'Rejected');
    await removeCurrent();
  } catch (err) {
    toast(err.message || 'Error', true);
  }
}

async function removeCurrent() {
  drafts.splice(currentIdx, 1);
  draftsTotal = Math.max(0, draftsTotal - 1);
  if (drafts.length === 0) {
    await refillDraftQueue();
    return;
  }
  currentIdx = Math.min(currentIdx, drafts.length - 1);
  updateDraftStats();
  renderList();
  await selectDraft(currentIdx);
}

function nextDraft() {
  if (currentIdx < drafts.length - 1) selectDraft(currentIdx + 1);
}
function prevDraft() {
  if (currentIdx > 0) selectDraft(currentIdx - 1);
}

// ---- Contributions panel ----
function initContributionsPanel() {
  const panel = document.getElementById('contributions-panel');
  if (!panel.dataset.ready) {
    panel.innerHTML = `
      <div class="panel-shell">
        <div class="panel-search">
          <div style="flex:1;color:#888;font-size:13px" id="contrib-stats">Loading…</div>
          <button class="btn btn-sm btn-next" onclick="loadConcertDrafts()">Refresh</button>
        </div>
        <div id="contributions-list"></div>
      </div>`;
    panel.dataset.ready = '1';
  }
  loadConcertDrafts();
}

async function loadConcertDrafts() {
  const list = document.getElementById('contributions-list');
  const stats = document.getElementById('contrib-stats');
  if (list) list.innerHTML = '<div class="contrib-loading">Loading submitted concerts…</div>';
  if (stats) stats.textContent = 'Loading…';

  try {
    const rows = await apiListAll('concert-drafts', { status: 'submitted', order_by: 'id' });
    const ids = rows.map(d => d.id);
    const [artistRows, setlistRows] = await Promise.all([
      apiListIn('concert-artist-drafts', 'concert_draft_id', ids),
      apiListIn('setlist-item-drafts', 'concert_draft_id', ids),
    ]);
    const artistCounts = countBy(artistRows, 'concert_draft_id');
    const setlistCounts = countBy(setlistRows, 'concert_draft_id');
    concertDrafts = rows.map(d => ({
      ...d,
      artist_count: artistCounts.get(d.id) || 0,
      setlist_item_count: setlistCounts.get(d.id) || 0,
    }));
    concertDraftsTotal = concertDrafts.length;
    concertDraftDetailCache = {};
    if (expandedConcertDraftId && !concertDrafts.some(d => d.id === expandedConcertDraftId)) {
      expandedConcertDraftId = null;
    }
    updateContributionStats();
    renderConcertDraftCards();
  } catch (err) {
    if (list) list.innerHTML = `<div class="empty"><span>⚠️</span>${escHtml(err.message || 'Could not load contributions')}</div>`;
    if (stats) stats.textContent = 'Error loading';
  }
}

function updateContributionStats() {
  const el = document.getElementById('contrib-stats');
  if (!el) return;
  if (concertDraftsTotal === 0) {
    el.textContent = 'No pending concert contributions';
  } else {
    el.textContent = `${concertDraftsTotal} pending concert contribution${concertDraftsTotal === 1 ? '' : 's'}`;
  }
  if (currentTab === 'contributions') {
    const topStats = document.getElementById('stats');
    if (topStats) topStats.textContent = el.textContent;
  }
}

function renderConcertDraftCards() {
  const list = document.getElementById('contributions-list');
  if (!list) return;

  if (!concertDrafts.length) {
    list.innerHTML = '<div class="empty"><span>✅</span>No pending concert contributions</div>';
    return;
  }

  list.innerHTML = concertDrafts.map(d => {
    const expanded = d.id === expandedConcertDraftId;
    const detail = concertDraftDetailCache[d.id];
    return `
      <div class="contrib-card${expanded ? ' expanded' : ''}" id="contrib-card-${d.id}">
        <div class="contrib-card-header" onclick="toggleConcertDraft(${d.id})">
          <div class="contrib-chevron">▶</div>
          <div class="contrib-card-main">
            <div class="contrib-card-title">${escHtml(d.title || d.youtube_id)}</div>
            <div class="contrib-card-meta">
              ${[d.year, d.venue, d.youtube_id].filter(Boolean).map(escHtml).join(' · ')}
            </div>
          </div>
          <div class="contrib-card-counts">
            <span class="contrib-count">${d.artist_count} artist${d.artist_count === 1 ? '' : 's'}</span>
            <span class="contrib-count">${d.setlist_item_count} piece${d.setlist_item_count === 1 ? '' : 's'}</span>
            ${d.duration_seconds != null ? `<span class="contrib-count">${fmtTs(d.duration_seconds)}</span>` : ''}
          </div>
        </div>
        <div class="contrib-card-body" id="contrib-body-${d.id}">
          ${expanded ? (detail ? renderConcertDraftDetail(detail) : '<div class="contrib-loading">Loading details…</div>') : ''}
        </div>
      </div>`;
  }).join('');
}

async function loadConcertDraftDetail(draftId) {
  const draftsFound = await apiGet('concert-drafts', [draftId]);
  const draft = draftsFound[0];
  if (!draft) throw httpError('Not found', 404);
  const [artistRows, setlistRows] = await Promise.all([
    apiListAll('concert-artist-drafts', { concert_draft_id: draftId }),
    apiListAll('setlist-item-drafts', {
      concert_draft_id: draftId,
      order_by: 'sequence_number',
    }),
  ]);
  const [pieceRows, artistCatalog] = await Promise.all([
    apiGet('pieces', setlistRows.map(item => item.piece_id)),
    apiGet('artists', artistRows.map(row => row.artist_id)),
  ]);
  const pieceById = indexById(pieceRows);
  const artistById = indexById(artistCatalog);
  const artists = artistRows.map(row => concertArtistDraftSummary(
    row,
    row.artist_id ? artistById.get(row.artist_id) : null,
  ));
  const setlist = setlistRows.map(item => setlistItemDraftSummary(
    item,
    item.piece_id ? pieceById.get(item.piece_id) : null,
  ));
  return {
    id: draft.id,
    youtube_id: draft.youtube_id,
    title: draft.title,
    year: draft.year,
    venue: draft.venue,
    duration_seconds: draft.duration_seconds,
    status: draft.status,
    artist_count: artists.length,
    setlist_item_count: setlist.length,
    artists,
    setlist,
  };
}

async function toggleConcertDraft(draftId) {
  if (expandedConcertDraftId === draftId) {
    expandedConcertDraftId = null;
    renderConcertDraftCards();
    return;
  }

  expandedConcertDraftId = draftId;
  renderConcertDraftCards();

  if (!concertDraftDetailCache[draftId]) {
    try {
      concertDraftDetailCache[draftId] = await loadConcertDraftDetail(draftId);
    } catch (err) {
      const body = document.getElementById(`contrib-body-${draftId}`);
      if (body) body.innerHTML = `<div class="contrib-loading" style="color:#c06060">${escHtml(err.message || 'Failed to load draft details')}</div>`;
      return;
    }
  }

  if (expandedConcertDraftId === draftId) {
    renderConcertDraftCards();
  }
}

function linkBadge(linked) {
  return linked
    ? '<span class="link-badge linked">linked</span>'
    : '<span class="link-badge new">new</span>';
}

function renderConcertDraftDetail(d) {
  const ytUrl = `https://www.youtube.com/watch?v=${escHtml(d.youtube_id)}`;
  const metaItems = [
    ['Title', d.title || '—'],
    ['Year', d.year || '—'],
    ['Venue', d.venue || '—'],
    ['Duration', d.duration_seconds != null ? fmtTs(d.duration_seconds) : '—'],
    ['YouTube', `<a class="concert-link" href="${ytUrl}" target="_blank" rel="noopener">${escHtml(d.youtube_id)}</a>`],
    ['Status', d.status || '—'],
  ].map(([key, val]) => `
    <div class="contrib-meta-item">
      <div class="meta-key">${key}</div>
      <div class="meta-val">${val}</div>
    </div>`).join('');

  const artists = (d.artists || []).map(a => `
    <div class="contrib-artist-row">
      <div style="flex:1">
        <strong>${escHtml(a.artist_name || a.submitted_artist_name || '—')}</strong>
        ${linkBadge(!!a.artist_id)}
        <div class="contrib-setlist-sub">
          ${[a.role, a.instrument].filter(Boolean).map(escHtml).join(' · ') || '—'}
        </div>
      </div>
    </div>`).join('');

  const setlist = (d.setlist || []).map(item => {
    const pieceName = item.piece_name || item.submitted_piece_name || '';
    const pieceSub = item.piece_id
      ? [item.raga_name, item.composer_name, item.talam_name, item.kind].filter(Boolean).join(' · ') || 'Linked piece'
      : ([item.raga_name, item.composer_name, item.talam_name, item.kind].filter(Boolean).join(' · ') || 'New piece (will be created on approve)');
    return `
      <div class="setlist-edit-row" id="sid-row-${item.id}" data-piece-id="${item.piece_id || ''}" data-concert-draft-id="${d.id}" onclick="event.stopPropagation()">
        <div>
          <div class="label" style="margin-bottom:3px">Seq</div>
          <input id="sid-seq-${item.id}" type="number" min="1" value="${item.sequence_number}"
            oninput="markDraftSetlistDirty(${item.id})">
        </div>
        <div>
          <div class="label" style="margin-bottom:3px">Time</div>
          <input id="sid-ts-${item.id}" value="${fmtTs(item.timestamp_seconds)}"
            placeholder="m:ss" oninput="markDraftSetlistDirty(${item.id})">
        </div>
        <div class="setlist-piece-wrap">
          <div class="label" style="margin-bottom:3px">Piece ${linkBadge(!!item.piece_id)}</div>
          <input id="sid-piece-${item.id}" value="${escHtml(pieceName)}"
            placeholder="Search piece or type new name…" autocomplete="off"
            oninput="onDraftSetlistPieceSearch(${item.id}, this.value)"
            onkeydown="onSetlistPieceKey(event, ${item.id}, 'sid')">
          <div class="setlist-piece-sub" id="sid-piece-sub-${item.id}">${escHtml(pieceSub)}</div>
          <div id="sid-sugg-${item.id}" style="display:none"></div>
        </div>
        <div style="padding-top:18px;display:flex;flex-direction:column;gap:4px">
          <button class="btn btn-sm btn-save" onclick="saveDraftSetlistItem(${item.id})">Save</button>
          <button class="btn btn-sm btn-skip" onclick="unlinkDraftSetlistPiece(${item.id})">Unlink</button>
          ${d.youtube_id ? `<a class="btn btn-sm btn-next" style="text-align:center" href="https://youtu.be/${escHtml(d.youtube_id)}?t=${item.timestamp_seconds||0}" target="_blank" rel="noopener">▶</a>` : ''}
        </div>
      </div>`;
  }).join('');

  return `
    <div class="contrib-section-title" style="margin-top:0">Concert metadata</div>
    <div class="contrib-meta-grid">${metaItems}</div>

    <div class="contrib-section-title">Artists (${(d.artists || []).length})</div>
    ${artists || '<div class="contrib-loading">No artists</div>'}

    <div class="contrib-section-title">Setlist (${(d.setlist || []).length}) — edit before approving</div>
    ${setlist || '<div class="contrib-loading">No setlist items</div>'}

    <div class="contrib-actions">
      <button class="btn btn-resolve" onclick="event.stopPropagation(); approveConcertDraft(${d.id})">Approve → publish</button>
      <button class="btn btn-reject" onclick="event.stopPropagation(); rejectConcertDraft(${d.id})">Reject</button>
      <a class="btn btn-next" href="${ytUrl}" target="_blank" rel="noopener" onclick="event.stopPropagation()">▶ Watch</a>
    </div>`;
}

function markDraftSetlistDirty(itemId) {
  document.getElementById(`sid-row-${itemId}`)?.classList.add('dirty');
}

async function onDraftSetlistPieceSearch(itemId, q) {
  const row = document.getElementById(`sid-row-${itemId}`);
  if (row) row.dataset.pieceId = '';
  markDraftSetlistDirty(itemId);
  const subEl = document.getElementById(`sid-piece-sub-${itemId}`);
  if (subEl) subEl.textContent = q.trim() ? 'New piece (will be created on approve)' : 'No piece linked';
  clearTimeout(setlistPieceTimers[`sid-${itemId}`]);
  if (!q || q.length < 2) {
    hideSetlistSuggestions(itemId, 'sid');
    return;
  }
  setlistPieceTimers[`sid-${itemId}`] = setTimeout(async () => {
    try {
      const items = (await apiAutocomplete('pieces', q, 8)).map(pieceSummary);
      showSetlistSuggestions(itemId, items, 'sid');
    } catch (err) {
      hideSetlistSuggestions(itemId, 'sid');
      toast(err.message || 'Piece search failed', true);
    }
  }, 180);
}

async function unlinkDraftSetlistPiece(itemId) {
  const row = document.getElementById(`sid-row-${itemId}`);
  const input = document.getElementById(`sid-piece-${itemId}`);
  const subEl = document.getElementById(`sid-piece-sub-${itemId}`);
  if (row) row.dataset.pieceId = '';
  // Keep typed name if present so approve can still create the piece
  if (subEl) {
    subEl.textContent = input?.value?.trim()
      ? 'New piece (will be created on approve)'
      : 'No piece linked';
  }
  markDraftSetlistDirty(itemId);
  await saveDraftSetlistItem(itemId, true);
}

function draftStatusFor(draftId) {
  const detail = concertDraftDetailCache[draftId];
  if (detail && detail.status) return detail.status;
  const summary = concertDrafts.find(d => d.id === draftId);
  return summary ? summary.status : null;
}

async function saveDraftSetlistItem(itemId, unlinking=false) {
  const row = document.getElementById(`sid-row-${itemId}`);
  const seq = parseInt(document.getElementById(`sid-seq-${itemId}`)?.value, 10);
  const ts = parseTimestamp(document.getElementById(`sid-ts-${itemId}`)?.value);
  const pieceInput = document.getElementById(`sid-piece-${itemId}`)?.value?.trim() || '';
  if (Number.isNaN(seq) || seq < 1) { toast('Invalid sequence number', true); return; }
  if (ts === null) { toast('Invalid timestamp (use seconds or m:ss)', true); return; }
  if (!pieceInput) { toast('Piece name is required', true); return; }

  const concertDraftId = row?.dataset.concertDraftId
    ? parseInt(row.dataset.concertDraftId, 10)
    : expandedConcertDraftId;
  const status = draftStatusFor(concertDraftId);
  if (status && status !== 'submitted') {
    toast(`Only submitted drafts can be edited; status is '${status}'`, true);
    return;
  }

  const body = {
    sequence_number: seq,
    timestamp_seconds: ts,
    piece_name: pieceInput,
  };

  const linkedId = (!unlinking && row?.dataset.pieceId)
    ? parseInt(row.dataset.pieceId, 10)
    : null;

  try {
    if (linkedId) {
      const [pieceRows, existingRows] = await Promise.all([
        apiGet('pieces', [linkedId]),
        apiGet('setlist-item-drafts', [itemId]),
      ]);
      const piece = pieceRows[0];
      if (!piece) { toast('piece_id not found', true); return; }
      const existing = existingRows[0];
      const summary = pieceSummary(piece);
      body.piece_id = piece.id;
      body.piece_name = piece.name;
      body.raga_id = piece.raga_id;
      body.talam_id = piece.talam_id;
      body.composer_id = piece.composer_id;
      body.raga_name = summary.raga || existing?.raga_name || null;
      body.talam_name = summary.talam || existing?.talam_name || null;
      body.composer_name = summary.composer || existing?.composer_name || null;
      body.kind = piece.kind || existing?.kind || null;
    } else {
      body.piece_id = null;
    }

    await apiUpdate('setlist-item-drafts', itemId, body);
    toast('✓ Draft setlist item saved');
    row?.classList.remove('dirty');
    if (concertDraftId) await refreshConcertDraftDetail(concertDraftId);
  } catch (err) {
    toast(err.message || 'Save failed', true);
  }
}

async function refreshConcertDraftDetail(draftId) {
  try {
    const detail = await loadConcertDraftDetail(draftId);
    concertDraftDetailCache[draftId] = detail;
    // Keep summary counts in sync
    const summary = concertDrafts.find(d => d.id === draftId);
    if (summary && detail) {
      summary.artist_count = (detail.artists || []).length;
      summary.setlist_item_count = (detail.setlist || []).length;
      summary.title = detail.title;
      summary.year = detail.year;
      summary.venue = detail.venue;
      summary.duration_seconds = detail.duration_seconds;
      summary.status = detail.status;
    }
    if (expandedConcertDraftId === draftId) renderConcertDraftCards();
  } catch {
    toast('Saved, but failed to refresh draft view', true);
  }
}

async function approveConcertDraft(draftId) {
  const draft = concertDrafts.find(d => d.id === draftId);
  const label = draft?.title || `draft #${draftId}`;
  if (!window.confirm(`Approve and publish “${label}”?`)) return;

  try {
    const data = await apiWorkflow(`approve-concert-draft/${draftId}`);
    toast(`✓ Published concert #${data.concert?.id ?? '?'}`);
    if (expandedConcertDraftId === draftId) expandedConcertDraftId = null;
    delete concertDraftDetailCache[draftId];
    await loadConcertDrafts();
  } catch (err) {
    toast(err.message || 'Approve failed', true);
  }
}

async function rejectConcertDraft(draftId) {
  const draft = concertDrafts.find(d => d.id === draftId);
  const label = draft?.title || `draft #${draftId}`;
  if (!window.confirm(`Reject “${label}”?`)) return;

  const status = draftStatusFor(draftId);
  if (status && status !== 'submitted') {
    toast(`Only submitted drafts can be rejected; status is '${status}'`, true);
    return;
  }

  try {
    await apiUpdate('concert-drafts', draftId, { status: 'rejected' });
    toast('Rejected');
    if (expandedConcertDraftId === draftId) expandedConcertDraftId = null;
    delete concertDraftDetailCache[draftId];
    await loadConcertDrafts();
  } catch (err) {
    toast(err.message || 'Reject failed', true);
  }
}

// ---- Pieces panel ----
function initPiecesPanel() {
  const panel = document.getElementById('pieces-panel');
  if (!panel.dataset.ready) {
    panel.innerHTML = `
      <div class="panel-shell">
        <div class="panel-search">
          <input class="search-box" id="piece-edit-search" placeholder="Search pieces by name…"
            oninput="onPieceEditSearch(this.value)" autocomplete="off">
          <div class="filter-row">
            <label><input type="checkbox" id="piece-incomplete-only" onchange="onPieceFilterChange()"> Incomplete only</label>
          </div>
        </div>
        <div class="edit-layout">
          <div class="edit-list">
            <div id="piece-edit-results"></div>
          </div>
          <div class="edit-form" id="piece-edit-form">
            <div class="empty"><span>🎵</span>Search for a piece to edit</div>
          </div>
        </div>
      </div>`;
    panel.dataset.ready = '1';
  }
  onPieceFilterChange();
  requestAnimationFrame(() => document.getElementById('piece-edit-search')?.focus());
}

async function onPieceFilterChange() {
  const incompleteOnly = document.getElementById('piece-incomplete-only')?.checked;
  const q = document.getElementById('piece-edit-search')?.value?.trim() || '';
  if (q.length >= 2) {
    await runPieceSearch(q);
    return;
  }
  if (incompleteOnly) {
    await loadIncompletePieceList();
  } else {
    document.getElementById('piece-edit-results').innerHTML =
      '<div style="color:#444;font-size:12px;padding:8px 0">Type at least 2 characters to search</div>';
  }
}

async function loadIncompletePieceList() {
  try {
    const [missingRaga, missingComposer, missingTalam] = await Promise.all([
      apiListAll('pieces', { raga_id: null, order_by: 'id' }),
      apiListAll('pieces', { composer_id: null, order_by: 'id' }),
      apiListAll('pieces', { talam_id: null, order_by: 'id' }),
    ]);
    const byId = new Map();
    for (const piece of [...missingRaga, ...missingComposer, ...missingTalam]) byId.set(piece.id, piece);
    const items = [...byId.values()].map(pieceSummary).sort((a, b) => cmpText(a.name, b.name));
    renderPieceResults(items, `${items.length} incomplete`);
  } catch (err) {
    const box = document.getElementById('piece-edit-results');
    if (box) box.innerHTML = `<div style="color:#c06060;font-size:12px;padding:8px 0">${escHtml(err.message || 'Failed to load pieces')}</div>`;
  }
}

function onPieceEditSearch(q) {
  clearTimeout(pieceSearchTimer);
  const incompleteOnly = document.getElementById('piece-incomplete-only')?.checked;
  if (!q || q.length < 2) {
    if (incompleteOnly) loadIncompletePieceList();
    else {
      const box = document.getElementById('piece-edit-results');
      if (box) box.innerHTML = '<div style="color:#444;font-size:12px;padding:8px 0">Type at least 2 characters to search</div>';
    }
    return;
  }
  pieceSearchTimer = setTimeout(() => runPieceSearch(q), 180);
}

async function runPieceSearch(q) {
  try {
    const incompleteOnly = document.getElementById('piece-incomplete-only')?.checked;
    let items = (await apiAutocomplete('pieces', q, 30)).map(pieceSummary);
    if (incompleteOnly) {
      items = items.filter(p => !p.raga || !p.composer || !p.talam);
    }
    renderPieceResults(items, `${items.length} result${items.length === 1 ? '' : 's'}`);
  } catch (err) {
    const box = document.getElementById('piece-edit-results');
    if (box) box.innerHTML = `<div style="color:#c06060;font-size:12px;padding:8px 0">${escHtml(err.message || 'Search failed')}</div>`;
  }
}

function renderPieceResults(items, label) {
  const box = document.getElementById('piece-edit-results');
  if (!items.length) {
    box.innerHTML = `<div style="color:#444;font-size:12px;padding:8px 0">No pieces found</div>`;
    return;
  }
  box.innerHTML = `
    <div style="color:#555;font-size:11px;margin-bottom:8px">${label}</div>
    ${items.map(p => `
      <div class="result-item${p.id === pieceEditId ? ' active' : ''}" onclick="selectPieceForEdit(${p.id})">
        <div class="result-title">${escHtml(p.name)}</div>
        <div class="result-sub">${[p.raga||'raga?', p.composer||'composer?', p.talam||'talam?', p.kind||'kind?'].join(' · ')}</div>
      </div>`).join('')}`;
}

async function loadPieceDetail(pieceId) {
  const pieceRows = await apiGet('pieces', [pieceId]);
  const piece = pieceRows[0];
  if (!piece) throw httpError('Piece not found', 404);
  const [aliases, items] = await Promise.all([
    apiListAll('piece-aliases', { piece_id: pieceId }),
    apiListAll('setlist-items', { piece_id: pieceId }),
  ]);
  const concerts = await apiGet('concerts', items.map(item => item.concert_id));
  const concertById = indexById(concerts);
  const appearances = items.map(si => {
    const concert = concertById.get(si.concert_id);
    return {
      setlist_item_id: si.id,
      concert_id: si.concert_id,
      concert_title: concert ? concert.title : null,
      concert_year: concert ? concert.year : null,
      sequence_number: si.sequence_number,
      timestamp_seconds: si.timestamp_seconds,
      timestamp_fmt: fmtTs(si.timestamp_seconds),
      url: concert
        ? `https://www.youtube.com/watch?v=${concert.youtube_id}&t=${si.timestamp_seconds}`
        : '#',
    };
  }).sort((a, b) => {
    const ay = a.concert_year;
    const by = b.concert_year;
    if (ay == null && by != null) return 1;
    if (by == null && ay != null) return -1;
    if (ay != null && by != null && ay !== by) return by - ay;
    return cmpText(a.concert_title, b.concert_title);
  });
  return {
    ...pieceSummary(piece),
    aliases: aliases.map(alias => alias.alias),
    appearances,
  };
}

async function selectPieceForEdit(pieceId) {
  pieceEditId = pieceId;
  document.querySelectorAll('#piece-edit-results .result-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('onclick') === `selectPieceForEdit(${pieceId})`);
  });
  try {
    const p = await loadPieceDetail(pieceId);
    renderPieceEditForm(p);
  } catch (err) {
    toast(err.status === 404 ? 'Piece not found' : (err.message || 'Piece not found'), true);
  }
}

function renderPieceEditForm(p) {
  const appearances = (p.appearances || []).map(a => `
    <div class="appearance">
      <a href="${a.url}" target="_blank">${escHtml(a.concert_title || 'Concert')}</a>
      <span style="color:#555"> · ${a.concert_year || '?'} · seq ${a.sequence_number} · ${a.timestamp_fmt}</span>
      <button class="btn btn-sm btn-save" style="margin-left:8px" onclick="openSetlistFromAppearance(${a.concert_id})">Edit setlist</button>
    </div>`).join('');

  document.getElementById('piece-edit-form').innerHTML = `
    <div class="section">
      <div class="label">Edit piece #${p.id}</div>
      <div class="fields">
        <div class="field" style="flex:2;min-width:200px">
          <label>Name</label>
          <input id="pe-name" value="${escHtml(p.name||'')}">
        </div>
        <div class="field">
          <label>Kind</label>
          <select id="pe-kind">
            ${KIND_OPTIONS.map(k =>
              `<option value="${k}"${k===(p.kind||'')?'selected':''}>${k||'—'}</option>`
            ).join('')}
          </select>
        </div>
        <div class="field">
          <label>Raga</label>
          ${datalistInput('pe-raga', 'pe-raga-list', ragas, p.raga||'')}
        </div>
        <div class="field">
          <label>Composer</label>
          ${datalistInput('pe-composer', 'pe-composer-list', composers, p.composer||'')}
        </div>
        <div class="field">
          <label>Talam</label>
          ${datalistInput('pe-talam', 'pe-talam-list', talams, p.talam||'')}
        </div>
      </div>
      <div class="actions">
        <button class="btn btn-resolve" onclick="savePieceEdit()">Save piece</button>
        <button class="btn btn-skip" onclick="clearPieceField('raga')">Clear raga</button>
        <button class="btn btn-skip" onclick="clearPieceField('composer')">Clear composer</button>
        <button class="btn btn-skip" onclick="clearPieceField('talam')">Clear talam</button>
      </div>
    </div>
    <div class="section">
      <div class="label">Appearances (${(p.appearances||[]).length})</div>
      ${appearances || '<div style="color:#444;font-size:12px">Not on any setlist yet</div>'}
    </div>
    ${(p.aliases||[]).length ? `
    <div class="section">
      <div class="label">Aliases</div>
      <div style="font-size:12px;color:#888">${p.aliases.map(escHtml).join(' · ')}</div>
    </div>` : ''}`;
}

function clearPieceField(field) {
  const el = document.getElementById('pe-' + field);
  if (el) el.value = '';
}

async function savePieceEdit() {
  if (!pieceEditId) return;
  const name = document.getElementById('pe-name')?.value?.trim();
  if (!name) { toast('name cannot be empty', true); return; }
  const kind = document.getElementById('pe-kind')?.value || null;
  const ragaName = document.getElementById('pe-raga')?.value?.trim() || null;
  const composerName = document.getElementById('pe-composer')?.value?.trim() || null;
  const talamName = document.getElementById('pe-talam')?.value?.trim() || null;
  try {
    const [raga_id, composer_id, talam_id] = await Promise.all([
      resolveNamedId('ragas', ragaName),
      resolveNamedId('composers', composerName),
      resolveNamedId('talams', talamName),
    ]);
    await apiUpdate('pieces', pieceEditId, { name, kind, raga_id, composer_id, talam_id });
    toast('✓ Piece saved');
    await selectPieceForEdit(pieceEditId);
    onPieceFilterChange();
  } catch (err) {
    toast(err.message || 'Save failed', true);
  }
}

function openSetlistFromAppearance(concertId) {
  switchTab('setlists');
  loadConcertSetlist(concertId);
}

// ---- Setlists panel ----
function initSetlistsPanel() {
  const panel = document.getElementById('setlists-panel');
  if (!panel.dataset.ready) {
    panel.innerHTML = `
      <div class="panel-shell">
        <div class="panel-search">
          <input class="search-box" id="concert-search" placeholder="Search concerts by title…"
            oninput="onConcertSearch(this.value)" autocomplete="off">
        </div>
        <div class="edit-layout">
          <div class="edit-list">
            <div id="concert-results">
              <div style="color:#444;font-size:12px;padding:8px 0">Type at least 2 characters to search</div>
            </div>
          </div>
          <div class="edit-form" id="setlist-edit-form">
            <div class="empty"><span>🎼</span>Search for a concert to edit its metadata and setlist</div>
          </div>
        </div>
      </div>`;
    panel.dataset.ready = '1';
  }
  requestAnimationFrame(() => document.getElementById('concert-search')?.focus());
}

function onConcertSearch(q) {
  clearTimeout(concertSearchTimer);
  const box = document.getElementById('concert-results');
  if (!q || q.length < 2) {
    if (box) box.innerHTML = '<div style="color:#444;font-size:12px;padding:8px 0">Type at least 2 characters to search</div>';
    return;
  }
  concertSearchTimer = setTimeout(async () => {
    try {
      const items = (await apiAutocomplete('concerts', q, 25)).map(concertSummary);
      if (!box) return;
      if (!items.length) {
        box.innerHTML = '<div style="color:#444;font-size:12px;padding:8px 0">No concerts found</div>';
        return;
      }
      box.innerHTML = items.map(c => `
        <div class="result-item${c.id === setlistConcertId ? ' active' : ''}" onclick="loadConcertSetlist(${c.id})">
          <div class="result-title">${escHtml(c.title || c.youtube_id)}</div>
          <div class="result-sub">${[c.year, c.venue, c.youtube_id].filter(Boolean).join(' · ')}</div>
        </div>`).join('');
    } catch (err) {
      if (box) box.innerHTML = `<div style="color:#c06060;font-size:12px;padding:8px 0">${escHtml(err.message || 'Search failed')}</div>`;
    }
  }, 180);
}

async function loadConcertSetlist(concertId) {
  setlistConcertId = concertId;
  document.querySelectorAll('#concert-results .result-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('onclick') === `loadConcertSetlist(${concertId})`);
  });
  try {
    const concertRows = await apiGet('concerts', [concertId]);
    const concert = concertRows[0];
    if (!concert) { toast('Concert not found', true); return; }
    const [items, artistLinks] = await Promise.all([
      apiListAll('setlist-items', { concert_id: concertId, order_by: 'sequence_number' }),
      apiListAll('concert-artists', { concert_id: concertId }),
    ]);
    const [pieceRows, artistRows] = await Promise.all([
      apiGet('pieces', items.map(item => item.piece_id)),
      apiGet('artists', artistLinks.map(link => link.artist_id)),
    ]);
    const pieceById = indexById(pieceRows);
    const artistById = indexById(artistRows);
    const artists = artistLinks.map(link => concertArtistSummary(
      link,
      link.artist_id ? artistById.get(link.artist_id) : null,
    )).sort((a, b) => {
      const ar = a.role === 'main artist' ? 0 : 1;
      const br = b.role === 'main artist' ? 0 : 1;
      if (ar !== br) return ar - br;
      return cmpText(a.artist_name, b.artist_name);
    });
    const setlistItems = items.map(si => setlistItemSummary(
      si,
      si.piece_id ? pieceById.get(si.piece_id) : null,
    ));
    renderSetlistEditor({
      concert: concertSummary(concert),
      artists,
      items: setlistItems,
    });
  } catch (err) {
    toast(err.message || 'Concert not found', true);
  }
}

function renderSetlistEditor(data) {
  const c = data.concert;
  const artists = data.artists || [];
  concertArtistRowSeq = 0;

  const artistRows = artists.length
    ? artists.map(a => concertArtistRowHtml({
        artist_id: a.artist_id,
        artist_name: a.artist_name || '',
        role: a.role || 'main artist',
        instrument: a.instrument || '',
      })).join('')
    : concertArtistRowHtml({ role: 'main artist' });

  const rows = (data.items || []).map(si => {
    const pieceName = si.piece ? si.piece.name : '';
    const pieceSub = si.piece
      ? [si.piece.raga, si.piece.composer, si.piece.talam].filter(Boolean).join(' · ')
      : 'No piece linked';
    return `
      <div class="setlist-edit-row" id="si-row-${si.id}" data-piece-id="${si.piece_id || ''}">
        <div>
          <div class="label" style="margin-bottom:3px">Seq</div>
          <input id="si-seq-${si.id}" type="number" min="1" value="${si.sequence_number}"
            oninput="markSetlistDirty(${si.id})">
        </div>
        <div>
          <div class="label" style="margin-bottom:3px">Time</div>
          <input id="si-ts-${si.id}" value="${fmtTs(si.timestamp_seconds)}"
            placeholder="m:ss" oninput="markSetlistDirty(${si.id})">
        </div>
        <div class="setlist-piece-wrap">
          <div class="label" style="margin-bottom:3px">Piece</div>
          <input id="si-piece-${si.id}" value="${escHtml(pieceName)}"
            placeholder="Search piece…" autocomplete="off"
            oninput="onSetlistPieceSearch(${si.id}, this.value)"
            onkeydown="onSetlistPieceKey(event, ${si.id})">
          <div class="setlist-piece-sub" id="si-piece-sub-${si.id}">${escHtml(pieceSub)}</div>
          <div id="si-sugg-${si.id}" style="display:none"></div>
        </div>
        <div style="padding-top:18px;display:flex;flex-direction:column;gap:4px">
          <button class="btn btn-sm btn-save" onclick="saveSetlistItem(${si.id})">Save</button>
          <button class="btn btn-sm btn-skip" onclick="unlinkSetlistPiece(${si.id})">Unlink</button>
          ${c.youtube_id ? `<a class="btn btn-sm btn-next" style="text-align:center" href="https://youtu.be/${c.youtube_id}?t=${si.timestamp_seconds||0}" target="_blank">▶</a>` : ''}
        </div>
      </div>`;
  }).join('');

  document.getElementById('setlist-edit-form').innerHTML = `
    <div class="section" id="concert-meta-section">
      <div class="label">Concert metadata</div>
      <div class="fields">
        <div class="field" style="flex:2;min-width:200px">
          <label>Title</label>
          <input id="cm-title" value="${escHtml(c.title || '')}">
        </div>
        <div class="field" style="min-width:90px;flex:0.4">
          <label>Year</label>
          <input id="cm-year" type="number" value="${c.year != null ? c.year : ''}">
        </div>
        <div class="field" style="flex:1.2;min-width:140px">
          <label>Venue</label>
          <input id="cm-venue" value="${escHtml(c.venue || '')}">
        </div>
        <div class="field" style="min-width:110px;flex:0.5">
          <label>Duration (sec)</label>
          <input id="cm-duration" type="number" min="0" value="${c.duration_seconds != null ? c.duration_seconds : ''}">
        </div>
        <div class="field" style="min-width:140px">
          <label>YouTube ID</label>
          <input id="cm-youtube" value="${escHtml(c.youtube_id || '')}">
        </div>
      </div>
      <div style="margin-top:8px">
        <a class="concert-link" id="cm-watch-link" href="${c.url}" target="_blank" rel="noopener">▶ Watch on YouTube</a>
      </div>
    </div>
    <div class="section">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:5px">
        <div class="label" style="margin:0">Artists</div>
        <button type="button" class="btn btn-sm btn-save" onclick="addConcertArtistRow()">+ Add artist</button>
      </div>
      <div id="concert-artists">${artistRows}</div>
      <div class="actions" style="margin-top:12px">
        <button class="btn btn-resolve" onclick="saveConcertMetadata()">Save concert</button>
      </div>
    </div>
    <div class="section">
      <div class="label">Setlist (${(data.items||[]).length} items)</div>
      ${rows || '<div style="color:#444;font-size:12px">No setlist items</div>'}
    </div>`;

  renumberConcertArtistRows();
}

function concertArtistRowHtml(prefill = {}) {
  const id = ++concertArtistRowSeq;
  const name = prefill.artist_name || '';
  const role = prefill.role || 'main artist';
  const instrument = prefill.instrument || '';
  const artistId = prefill.artist_id || '';
  const linked = !!artistId;
  return `
    <div class="concert-artist-row" id="ca-row-${id}" data-artist-id="${artistId}">
      <div class="concert-artist-fields">
        <div class="setlist-piece-wrap" style="flex:2;min-width:160px">
          <div class="label" style="margin-bottom:3px">Name</div>
          <input id="ca-name-${id}" value="${escHtml(name)}"
            placeholder="Search existing artist or type a new name…"
            autocomplete="off"
            oninput="onConcertArtistSearch(${id}, this.value)"
            onkeydown="onConcertArtistKey(event, ${id})">
          <div class="setlist-piece-sub" id="ca-status-${id}">${
            linked ? 'Linked to existing artist' : 'New artist (will be created if no match)'
          }</div>
          <div id="ca-sugg-${id}" style="display:none"></div>
        </div>
        <div style="min-width:130px">
          <div class="label" style="margin-bottom:3px">Role</div>
          <select id="ca-role-${id}">
            ${ARTIST_ROLE_OPTIONS.map(r =>
              `<option value="${r}"${r === role ? ' selected' : ''}>${r}</option>`
            ).join('')}
          </select>
        </div>
        <div style="flex:1;min-width:120px">
          <div class="label" style="margin-bottom:3px">Instrument</div>
          <input id="ca-instrument-${id}" value="${escHtml(instrument)}" placeholder="e.g. vocal, violin">
        </div>
        <div style="padding-top:18px">
          <button type="button" class="btn btn-sm btn-skip" onclick="removeConcertArtistRow(${id})">Remove</button>
        </div>
      </div>
    </div>`;
}

function addConcertArtistRow(prefill = { role: 'accompanist' }) {
  const box = document.getElementById('concert-artists');
  if (!box) return;
  box.insertAdjacentHTML('beforeend', concertArtistRowHtml(prefill));
  renumberConcertArtistRows();
}

function removeConcertArtistRow(rowId) {
  const box = document.getElementById('concert-artists');
  if (!box) return;
  if (box.querySelectorAll('.concert-artist-row').length <= 1) {
    toast('At least one artist is required', true);
    return;
  }
  document.getElementById(`ca-row-${rowId}`)?.remove();
  renumberConcertArtistRows();
}

function renumberConcertArtistRows() {
  document.querySelectorAll('#concert-artists .concert-artist-row').forEach((row, i) => {
    row.dataset.rowIndex = String(i + 1);
  });
}

async function onConcertArtistSearch(rowId, q) {
  const row = document.getElementById(`ca-row-${rowId}`);
  if (row) row.dataset.artistId = '';
  const status = document.getElementById(`ca-status-${rowId}`);
  if (status) status.textContent = 'New artist (will be created if no match)';
  clearTimeout(concertArtistTimers[rowId]);
  if (!q || q.length < 2) {
    hideConcertArtistSuggestions(rowId);
    return;
  }
  concertArtistTimers[rowId] = setTimeout(async () => {
    try {
      const items = await apiAutocomplete('artists', q);
      showConcertArtistSuggestions(rowId, items);
    } catch (err) {
      hideConcertArtistSuggestions(rowId);
      toast(err.message || 'Artist search failed', true);
    }
  }, 180);
}

function showConcertArtistSuggestions(rowId, items) {
  const box = document.getElementById(`ca-sugg-${rowId}`);
  if (!box) return;
  if (!items.length) { box.style.display = 'none'; return; }
  concertArtistSuggestionIdx[rowId] = -1;
  box.style.cssText = 'position:absolute;left:0;right:0;top:100%;background:#1e1e1e;border:1px solid #2e2e2e;border-radius:0 0 6px 6px;z-index:10;max-height:180px;overflow-y:auto;';
  box.innerHTML = items.map((a, i) => `
    <div class="suggestion" data-id="${a.id}" data-name="${escHtml(a.name)}"
         onmousedown="pickConcertArtist(${rowId}, ${a.id}, this.dataset.name)"
         onmouseover="concertArtistSuggestionIdx[${rowId}]=${i}">
      <div>${escHtml(a.name)}</div>
    </div>`).join('');
  box.style.display = 'block';
}

function hideConcertArtistSuggestions(rowId) {
  const box = document.getElementById(`ca-sugg-${rowId}`);
  if (box) { box.style.display = 'none'; concertArtistSuggestionIdx[rowId] = -1; }
}

function onConcertArtistKey(e, rowId) {
  const box = document.getElementById(`ca-sugg-${rowId}`);
  const items = box ? box.querySelectorAll('.suggestion') : [];
  let idx = concertArtistSuggestionIdx[rowId] ?? -1;
  if (e.key === 'ArrowDown') {
    e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); concertArtistSuggestionIdx[rowId] = idx;
    items.forEach((el, i) => el.classList.toggle('active', i === idx));
  } else if (e.key === 'ArrowUp') {
    e.preventDefault(); idx = Math.max(idx - 1, -1); concertArtistSuggestionIdx[rowId] = idx;
    items.forEach((el, i) => el.classList.toggle('active', i === idx));
  } else if (e.key === 'Enter' && idx >= 0) {
    e.preventDefault();
    const el = items[idx];
    if (el) pickConcertArtist(rowId, +el.dataset.id, el.dataset.name);
  } else if (e.key === 'Escape') {
    hideConcertArtistSuggestions(rowId);
  }
}

function pickConcertArtist(rowId, artistId, name) {
  const row = document.getElementById(`ca-row-${rowId}`);
  const input = document.getElementById(`ca-name-${rowId}`);
  const status = document.getElementById(`ca-status-${rowId}`);
  if (row) row.dataset.artistId = String(artistId);
  if (input) input.value = name;
  if (status) status.textContent = 'Linked to existing artist';
  hideConcertArtistSuggestions(rowId);
}

function collectConcertArtists() {
  return [...document.querySelectorAll('#concert-artists .concert-artist-row')].map(row => {
    const id = row.id.replace('ca-row-', '');
    const artistId = row.dataset.artistId ? parseInt(row.dataset.artistId, 10) : null;
    return {
      artist_id: Number.isFinite(artistId) ? artistId : null,
      artist_name: document.getElementById(`ca-name-${id}`)?.value?.trim() || '',
      role: document.getElementById(`ca-role-${id}`)?.value || 'main artist',
      instrument: document.getElementById(`ca-instrument-${id}`)?.value?.trim() || null,
    };
  });
}

async function saveConcertMetadata() {
  if (!setlistConcertId) return;

  const title = document.getElementById('cm-title')?.value?.trim();
  const yearRaw = document.getElementById('cm-year')?.value?.trim();
  const venue = document.getElementById('cm-venue')?.value?.trim();
  const durationRaw = document.getElementById('cm-duration')?.value?.trim();
  const youtubeId = document.getElementById('cm-youtube')?.value?.trim();
  const artists = collectConcertArtists();

  if (!title) { toast('Title is required', true); return; }
  if (!youtubeId) { toast('YouTube ID is required', true); return; }
  if (!artists.length) { toast('At least one artist is required', true); return; }
  for (let i = 0; i < artists.length; i++) {
    if (!artists[i].artist_name) {
      toast(`Artist ${i + 1}: name is required`, true);
      return;
    }
  }
  if (!artists.some(a => a.role === 'main artist')) {
    toast('Mark at least one artist as main artist', true);
    return;
  }

  let year = null;
  if (yearRaw !== '') {
    year = parseInt(yearRaw, 10);
    if (Number.isNaN(year)) { toast('Year must be a number', true); return; }
  }
  let duration_seconds = null;
  if (durationRaw !== '') {
    duration_seconds = parseInt(durationRaw, 10);
    if (Number.isNaN(duration_seconds) || duration_seconds < 0) {
      toast('Duration must be a non-negative number', true);
      return;
    }
  }

  const concertId = setlistConcertId;
  try {
    await apiUpdate('concerts', concertId, {
      title,
      year,
      venue: venue || null,
      duration_seconds,
      youtube_id: youtubeId,
    });
  } catch (err) {
    toast(err.message || 'Save failed', true);
    return;
  }

  try {
    await apiWorkflow(`replace-concert-lineup/${concertId}`, { artists });
  } catch (err) {
    toast(err.message || 'Save failed', true);
    await loadConcertSetlist(concertId);
    return;
  }

  toast('✓ Concert saved');
  await loadConcertSetlist(concertId);
  const q = document.getElementById('concert-search')?.value?.trim();
  if (q && q.length >= 2) onConcertSearch(q);
}

function markSetlistDirty(id) {
  document.getElementById(`si-row-${id}`)?.classList.add('dirty');
}

function parseTimestamp(val) {
  if (val === '' || val == null) return null;
  if (/^\d+$/.test(String(val).trim())) return parseInt(val, 10);
  const parts = String(val).trim().split(':').map(Number);
  if (parts.some(n => Number.isNaN(n))) return null;
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return null;
}

async function onSetlistPieceSearch(itemId, q) {
  const row = document.getElementById(`si-row-${itemId}`);
  if (row) row.dataset.pieceId = '';
  markSetlistDirty(itemId);
  clearTimeout(setlistPieceTimers[itemId]);
  if (!q || q.length < 2) {
    hideSetlistSuggestions(itemId);
    return;
  }
  setlistPieceTimers[itemId] = setTimeout(async () => {
    try {
      const items = (await apiAutocomplete('pieces', q, 8)).map(pieceSummary);
      showSetlistSuggestions(itemId, items);
    } catch (err) {
      hideSetlistSuggestions(itemId);
      toast(err.message || 'Piece search failed', true);
    }
  }, 180);
}

function showSetlistSuggestions(itemId, items, prefix='si') {
  const box = document.getElementById(`${prefix}-sugg-${itemId}`);
  if (!box) return;
  if (!items.length) { box.style.display = 'none'; return; }
  setlistSuggestionIdx[`${prefix}-${itemId}`] = -1;
  box.style.cssText = 'position:absolute;left:0;right:0;top:100%;background:#1e1e1e;border:1px solid #2e2e2e;border-radius:0 0 6px 6px;z-index:10;max-height:180px;overflow-y:auto;';
  box.innerHTML = items.map((p, i) => {
    const sub = [p.raga, p.composer, p.talam].filter(Boolean).join(' · ');
    return `<div class="suggestion" data-id="${p.id}" data-name="${escHtml(p.name)}" data-sub="${escHtml(sub)}"
         onmousedown="pickSetlistPieceFromEl(${itemId}, this, '${prefix}')"
         onmouseover="setlistSuggestionIdx['${prefix}-${itemId}']=${i}">
      <div>${escHtml(p.name)}</div>
      <div class="suggestion-sub">${escHtml(sub)}</div>
    </div>`;
  }).join('');
  box.style.display = 'block';
}

function hideSetlistSuggestions(itemId, prefix='si') {
  const box = document.getElementById(`${prefix}-sugg-${itemId}`);
  if (box) { box.style.display = 'none'; setlistSuggestionIdx[`${prefix}-${itemId}`] = -1; }
}

function onSetlistPieceKey(e, itemId, prefix='si') {
  const box = document.getElementById(`${prefix}-sugg-${itemId}`);
  const items = box ? box.querySelectorAll('.suggestion') : [];
  const key = `${prefix}-${itemId}`;
  let idx = setlistSuggestionIdx[key] ?? -1;
  if (e.key === 'ArrowDown') {
    e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); setlistSuggestionIdx[key] = idx;
    items.forEach((el, i) => el.classList.toggle('active', i === idx));
  } else if (e.key === 'ArrowUp') {
    e.preventDefault(); idx = Math.max(idx - 1, -1); setlistSuggestionIdx[key] = idx;
    items.forEach((el, i) => el.classList.toggle('active', i === idx));
  } else if (e.key === 'Enter' && idx >= 0) {
    e.preventDefault();
    const el = items[idx];
    if (el) pickSetlistPieceFromEl(itemId, el, prefix);
  } else if (e.key === 'Escape') {
    hideSetlistSuggestions(itemId, prefix);
  }
}

function pickSetlistPieceFromEl(itemId, el, prefix='si') {
  pickSetlistPiece(itemId, +el.dataset.id, el.dataset.name, el.dataset.sub || '', prefix);
}

function pickSetlistPiece(itemId, pieceId, name, sub, prefix='si') {
  const row = document.getElementById(`${prefix}-row-${itemId}`);
  const input = document.getElementById(`${prefix}-piece-${itemId}`);
  const subEl = document.getElementById(`${prefix}-piece-sub-${itemId}`);
  if (row) row.dataset.pieceId = String(pieceId);
  if (input) input.value = name;
  if (subEl) subEl.textContent = sub || 'Selected piece';
  hideSetlistSuggestions(itemId, prefix);
  if (prefix === 'sid') markDraftSetlistDirty(itemId);
  else markSetlistDirty(itemId);
}

async function unlinkSetlistPiece(itemId) {
  const row = document.getElementById(`si-row-${itemId}`);
  const input = document.getElementById(`si-piece-${itemId}`);
  const subEl = document.getElementById(`si-piece-sub-${itemId}`);
  if (row) row.dataset.pieceId = '';
  if (input) input.value = '';
  if (subEl) subEl.textContent = 'No piece linked';
  markSetlistDirty(itemId);
  await saveSetlistItem(itemId, true);
}

async function saveSetlistItem(itemId, unlinking=false) {
  const row = document.getElementById(`si-row-${itemId}`);
  const seq = parseInt(document.getElementById(`si-seq-${itemId}`)?.value, 10);
  const ts = parseTimestamp(document.getElementById(`si-ts-${itemId}`)?.value);
  if (Number.isNaN(seq) || seq < 1) { toast('Invalid sequence number', true); return; }
  if (ts === null) { toast('Invalid timestamp (use seconds or m:ss)', true); return; }

  const body = {
    sequence_number: seq,
    timestamp_seconds: ts,
  };

  const pieceInput = document.getElementById(`si-piece-${itemId}`)?.value?.trim();
  if (unlinking || !pieceInput) {
    body.piece_id = null;
  } else if (row?.dataset.pieceId) {
    body.piece_id = parseInt(row.dataset.pieceId, 10);
  } else {
    toast('Pick a piece from suggestions (or Unlink)', true);
    return;
  }

  try {
    await apiUpdate('setlist-items', itemId, body);
    toast('✓ Setlist item saved');
    row?.classList.remove('dirty');
    if (setlistConcertId) await loadConcertSetlist(setlistConcertId);
  } catch (err) {
    toast(err.message || 'Save failed', true);
  }
}

// ---- Keyboard shortcuts ----
document.addEventListener('keydown', e => {
  if (currentTab !== 'drafts') return;
  const tag = document.activeElement?.tagName;
  const inInput = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA';
  if (e.key === '/' && !inInput) { e.preventDefault(); document.getElementById('piece-search')?.focus(); return; }
  if (inInput && e.key !== 'Escape') return;
  if (e.key === 'Escape') { document.activeElement?.blur(); hideSuggestions(); }
  if (e.key === 'j') nextDraft();
  if (e.key === 'k') prevDraft();
  if (e.key === 'Enter') resolveAction();
  if (e.key === 's') statusAction('skip');
  if (e.key === 'x') statusAction('reject');
});

// ---- Utils ----
function fmtTs(s) {
  if (!s && s !== 0) return '?';
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), sec = s%60;
  return h ? `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
           : `${m}:${String(sec).padStart(2,'0')}`;
}
function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
let toastTimer;
function toast(msg, isError=false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show' + (isError ? ' error' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = '', 2500);
}

init();
