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
const KIND_OPTIONS = ['','krithi','varnam','padam','tillana','viruttam','slokam','mangalam','bhajan','rtp'];

// ---- Init ----
async function init() {
  [ragas, composers, talams] = await Promise.all([
    fetch('/review/lookup/ragas').then(r => r.json()),
    fetch('/review/lookup/composers').then(r => r.json()),
    fetch('/review/lookup/talams').then(r => r.json()),
  ]);
  await loadDrafts();
}

async function loadDrafts() {
  const res = await fetch('/review/drafts?per_page=200&page=1');
  const data = await res.json();
  drafts = data.items;
  draftsTotal = data.total;
  currentIdx = -1;
  updateDraftStats();
  renderList();
  if (drafts.length > 0) selectDraft(0);
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
  const res = await fetch('/review/drafts?per_page=200&page=1');
  const data = await res.json();
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

// ---- Tab switching ----
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach((el, i) => {
    el.classList.toggle('active', ['drafts','pieces','setlists'][i] === tab);
  });
  document.getElementById('sidebar').style.display = tab === 'drafts' ? 'flex' : 'none';
  document.getElementById('detail').style.display = tab === 'drafts' ? 'block' : 'none';
  document.getElementById('pieces-panel').style.display = tab === 'pieces' ? 'flex' : 'none';
  document.getElementById('setlists-panel').style.display = tab === 'setlists' ? 'flex' : 'none';
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
  const res = await fetch(`/review/drafts/${d.id}`);
  const detail = await res.json();
  renderDetail(detail);
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
            ${['','krithi','varnam','padam','tillana','viruttam','slokam','mangalam','bhajan','rtp'].map(k =>
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
    const res = await fetch(`/review/pieces/search?q=${encodeURIComponent(q)}&limit=8`);
    const items = await res.json();
    showSuggestions(items);
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
  const pieceName = document.getElementById('piece-search')?.value?.trim();
  const body = {
    piece_name: pieceName || d.parsed_piece,
    raga: document.getElementById('raga-input')?.value?.trim() || null,
    composer: document.getElementById('composer-input')?.value?.trim() || null,
    talam: document.getElementById('talam-input')?.value?.trim() || null,
    kind: document.getElementById('kind-input')?.value || null,
  };
  if (selectedPieceId) body.piece_id = selectedPieceId;

  const res = await fetch(`/review/drafts/${d.id}/resolve`, {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body),
  });
  if (res.ok) {
    const data = await res.json();
    toast(`✓ Resolved → ${data.piece.name}`);
    await removeCurrent();
  } else {
    const err = await res.json();
    toast(err.error || 'Error', true);
  }
}

async function statusAction(action) {
  const d = drafts[currentIdx];
  const res = await fetch(`/review/drafts/${d.id}/${action}`, { method: 'POST' });
  if (res.ok) {
    toast(action === 'skip' ? 'Skipped' : 'Rejected');
    await removeCurrent();
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
  const res = await fetch('/review/pieces/incomplete?per_page=100');
  const data = await res.json();
  renderPieceResults(data.items, `${data.total} incomplete`);
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
  const incompleteOnly = document.getElementById('piece-incomplete-only')?.checked;
  const res = await fetch(`/review/pieces/search?q=${encodeURIComponent(q)}&limit=30`);
  let items = await res.json();
  if (incompleteOnly) {
    items = items.filter(p => !p.raga || !p.composer || !p.talam);
  }
  renderPieceResults(items, `${items.length} result${items.length === 1 ? '' : 's'}`);
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

async function selectPieceForEdit(pieceId) {
  pieceEditId = pieceId;
  document.querySelectorAll('#piece-edit-results .result-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('onclick') === `selectPieceForEdit(${pieceId})`);
  });
  const res = await fetch(`/review/pieces/${pieceId}`);
  if (!res.ok) { toast('Piece not found', true); return; }
  const p = await res.json();
  renderPieceEditForm(p);
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
  const body = {
    name: document.getElementById('pe-name')?.value?.trim(),
    kind: document.getElementById('pe-kind')?.value || null,
    raga: document.getElementById('pe-raga')?.value?.trim() || null,
    composer: document.getElementById('pe-composer')?.value?.trim() || null,
    talam: document.getElementById('pe-talam')?.value?.trim() || null,
  };
  const res = await fetch(`/review/pieces/${pieceEditId}`, {
    method: 'PATCH', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body),
  });
  if (res.ok) {
    toast('✓ Piece saved');
    await selectPieceForEdit(pieceEditId);
    onPieceFilterChange();
  } else {
    const err = await res.json().catch(() => ({}));
    toast(err.error || 'Save failed', true);
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
          <input class="search-box" id="concert-search" placeholder="Search concerts by title, venue, or YouTube id…"
            oninput="onConcertSearch(this.value)" autocomplete="off">
        </div>
        <div class="edit-layout">
          <div class="edit-list">
            <div id="concert-results">
              <div style="color:#444;font-size:12px;padding:8px 0">Type at least 2 characters to search</div>
            </div>
          </div>
          <div class="edit-form" id="setlist-edit-form">
            <div class="empty"><span>🎼</span>Search for a concert to edit its setlist</div>
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
    const res = await fetch(`/review/concerts/search?q=${encodeURIComponent(q)}&limit=25`);
    const items = await res.json();
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
  }, 180);
}

async function loadConcertSetlist(concertId) {
  setlistConcertId = concertId;
  document.querySelectorAll('#concert-results .result-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('onclick') === `loadConcertSetlist(${concertId})`);
  });
  const res = await fetch(`/review/concerts/${concertId}/setlist`);
  if (!res.ok) { toast('Concert not found', true); return; }
  const data = await res.json();
  renderSetlistEditor(data);
}

function renderSetlistEditor(data) {
  const c = data.concert;
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
    <div class="section">
      <div class="label">Concert</div>
      <a class="concert-link" href="${c.url}" target="_blank">▶ ${escHtml(c.title || c.youtube_id)}</a>
      <div style="font-size:12px;color:#555;margin-top:4px">${[c.year, c.venue].filter(Boolean).join(' · ')}</div>
    </div>
    <div class="section">
      <div class="label">Setlist (${(data.items||[]).length} items)</div>
      ${rows || '<div style="color:#444;font-size:12px">No setlist items</div>'}
    </div>`;
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
    const res = await fetch(`/review/pieces/search?q=${encodeURIComponent(q)}&limit=8`);
    const items = await res.json();
    showSetlistSuggestions(itemId, items);
  }, 180);
}

function showSetlistSuggestions(itemId, items) {
  const box = document.getElementById(`si-sugg-${itemId}`);
  if (!box) return;
  if (!items.length) { box.style.display = 'none'; return; }
  setlistSuggestionIdx[itemId] = -1;
  box.style.cssText = 'position:absolute;left:0;right:0;top:100%;background:#1e1e1e;border:1px solid #2e2e2e;border-radius:0 0 6px 6px;z-index:10;max-height:180px;overflow-y:auto;';
  box.innerHTML = items.map((p, i) => {
    const sub = [p.raga, p.composer, p.talam].filter(Boolean).join(' · ');
    return `<div class="suggestion" data-id="${p.id}" data-name="${escHtml(p.name)}" data-sub="${escHtml(sub)}"
         onmousedown="pickSetlistPieceFromEl(${itemId}, this)"
         onmouseover="setlistSuggestionIdx[${itemId}]=${i}">
      <div>${escHtml(p.name)}</div>
      <div class="suggestion-sub">${escHtml(sub)}</div>
    </div>`;
  }).join('');
  box.style.display = 'block';
}

function hideSetlistSuggestions(itemId) {
  const box = document.getElementById(`si-sugg-${itemId}`);
  if (box) { box.style.display = 'none'; setlistSuggestionIdx[itemId] = -1; }
}

function onSetlistPieceKey(e, itemId) {
  const box = document.getElementById(`si-sugg-${itemId}`);
  const items = box ? box.querySelectorAll('.suggestion') : [];
  let idx = setlistSuggestionIdx[itemId] ?? -1;
  if (e.key === 'ArrowDown') {
    e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); setlistSuggestionIdx[itemId] = idx;
    items.forEach((el, i) => el.classList.toggle('active', i === idx));
  } else if (e.key === 'ArrowUp') {
    e.preventDefault(); idx = Math.max(idx - 1, -1); setlistSuggestionIdx[itemId] = idx;
    items.forEach((el, i) => el.classList.toggle('active', i === idx));
  } else if (e.key === 'Enter' && idx >= 0) {
    e.preventDefault();
    const el = items[idx];
    if (el) pickSetlistPieceFromEl(itemId, el);
  } else if (e.key === 'Escape') {
    hideSetlistSuggestions(itemId);
  }
}

function pickSetlistPieceFromEl(itemId, el) {
  pickSetlistPiece(itemId, +el.dataset.id, el.dataset.name, el.dataset.sub || '');
}

function pickSetlistPiece(itemId, pieceId, name, sub) {
  const row = document.getElementById(`si-row-${itemId}`);
  const input = document.getElementById(`si-piece-${itemId}`);
  const subEl = document.getElementById(`si-piece-sub-${itemId}`);
  if (row) row.dataset.pieceId = String(pieceId);
  if (input) input.value = name;
  if (subEl) subEl.textContent = sub || 'Selected piece';
  hideSetlistSuggestions(itemId);
  markSetlistDirty(itemId);
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

  const res = await fetch(`/review/setlist/${itemId}`, {
    method: 'PATCH', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body),
  });
  if (res.ok) {
    toast('✓ Setlist item saved');
    row?.classList.remove('dirty');
    if (setlistConcertId) await loadConcertSetlist(setlistConcertId);
  } else {
    const err = await res.json().catch(() => ({}));
    toast(err.error || 'Save failed', true);
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
