// contribute form options and dom refs
const KIND_OPTIONS = ['', 'krithi', 'varnam', 'padam', 'tillana', 'viruttam', 'slokam', 'mangalam', 'bhajan', 'rtp'];
const ROLE_OPTIONS = ['main artist', 'accompanist'];

const contributeForm = document.getElementById('contribute-form');
const contribArtistsEl = document.getElementById('contrib-artists');
const contribSetlistEl = document.getElementById('contrib-setlist');
const contribStatus = document.getElementById('contrib-status');
const contribSubmit = document.getElementById('contrib-submit');
const contribYoutube = document.getElementById('contrib-youtube');
const contribYoutubeHint = document.getElementById('contrib-youtube-hint');

let artistRowSeq = 0;
let setlistRowSeq = 0;

// parse youtube url or bare video id
function parseYoutubeId(raw) {
  const s = (raw || '').trim();
  if (!s) return null;
  if (/^[\w-]{11}$/.test(s)) return s;
  try {
    const url = new URL(s.includes('://') ? s : `https://${s}`);
    if (url.hostname.includes('youtu.be')) {
      const id = url.pathname.split('/').filter(Boolean)[0];
      return id && /^[\w-]{11}$/.test(id) ? id : null;
    }
    if (url.hostname.includes('youtube.com')) {
      const v = url.searchParams.get('v');
      if (v && /^[\w-]{11}$/.test(v)) return v;
      const parts = url.pathname.split('/').filter(Boolean);
      if ((parts[0] === 'embed' || parts[0] === 'shorts' || parts[0] === 'live') && parts[1] && /^[\w-]{11}$/.test(parts[1])) {
        return parts[1];
      }
    }
  } catch {
    return null;
  }
  return null;
}

// accept seconds or m:ss or h:mm:ss
function parseTimestampInput(val) {
  if (val === '' || val == null) return null;
  const s = String(val).trim();
  if (/^\d+$/.test(s)) return parseInt(s, 10);
  const parts = s.split(':').map(Number);
  if (parts.some(n => Number.isNaN(n))) return null;
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return null;
}

function setContribStatus(msg, kind = '') {
  contribStatus.textContent = msg || '';
  contribStatus.className = 'form-status' + (kind ? ` ${kind}` : '');
}

// autocomplete that remembers selected entity id
function wireEntityAutocomplete({ input, list, fetchUrl, onPick, onClear, renderItem }) {
  let selectedId = null;

  const ac = createAutocomplete({
    input,
    list,
    fetchUrl,
    renderItem,
    onSelect: (item) => {
      selectedId = item.id;
      input.value = item.name;
      onPick(item);
    },
  });

  // clear link if user edits after picking
  input.addEventListener('input', () => {
    if (selectedId != null) {
      selectedId = null;
      onClear();
    }
  });

  return {
    getSelectedId: () => selectedId,
    setSelectedId: (id) => { selectedId = id; },
    close: ac.close,
  };
}

// append one artist row to contribute form
function addArtistRow(prefill = {}) {
  const id = ++artistRowSeq;
  const row = document.createElement('div');
  row.className = 'dynamic-row';
  row.dataset.artistRow = String(id);
  row.innerHTML = `
    <div class="dynamic-row-header">
      <span class="dynamic-row-label">Artist ${contribArtistsEl.children.length + 1}</span>
      <button type="button" class="btn-remove" data-remove-artist>Remove</button>
    </div>
    <div class="dynamic-row-fields">
      <div class="ac-wrap span-2">
        <label class="search-label" for="artist-name-${id}">Name</label>
        <input id="artist-name-${id}" type="text" data-field="artist_name" required
          placeholder="Start typing to link an existing artist…" value="${prefill.artist_name || ''}" />
        <ul class="ac-list" id="artist-ac-${id}" role="listbox"></ul>
        <div class="linked-badge new" data-link-status>New artist (will be reviewed)</div>
      </div>
      <div>
        <label class="search-label" for="artist-role-${id}">Role</label>
        <select id="artist-role-${id}" data-field="role">
          ${ROLE_OPTIONS.map(r =>
            `<option value="${r}"${(prefill.role || 'main artist') === r ? ' selected' : ''}>${r}</option>`
          ).join('')}
        </select>
      </div>
      <div>
        <label class="search-label" for="artist-instrument-${id}">Instrument</label>
        <input id="artist-instrument-${id}" type="text" data-field="instrument"
          placeholder="e.g. vocal, violin" value="${prefill.instrument || ''}" />
      </div>
    </div>
  `;

  contribArtistsEl.appendChild(row);
  renumberArtistRows();

  const nameInput = row.querySelector('[data-field="artist_name"]');
  const list = row.querySelector(`#artist-ac-${id}`);
  const status = row.querySelector('[data-link-status]');

  const linker = wireEntityAutocomplete({
    input: nameInput,
    list,
    fetchUrl: (q) => `${API}/artists/autocomplete/${encodeURIComponent(q)}`,
    renderItem: (li, item) => {
      const name = document.createElement('div');
      name.className = 'ac-name';
      name.textContent = item.name;
      li.appendChild(name);
    },
    onPick: () => {
      status.textContent = 'Linked to existing artist';
      status.classList.remove('new');
    },
    onClear: () => {
      status.textContent = 'New artist (will be reviewed)';
      status.classList.add('new');
    },
  });

  if (prefill.artist_id) {
    linker.setSelectedId(prefill.artist_id);
    status.textContent = 'Linked to existing artist';
    status.classList.remove('new');
  }

  row._getArtistDraft = () => ({
    artist_id: linker.getSelectedId(),
    artist_name: nameInput.value.trim(),
    instrument: row.querySelector('[data-field="instrument"]').value.trim() || null,
    role: row.querySelector('[data-field="role"]').value,
  });

  row.querySelector('[data-remove-artist]').addEventListener('click', () => {
    if (contribArtistsEl.children.length <= 1) {
      setContribStatus('At least one artist is required.', 'err');
      return;
    }
    row.remove();
    renumberArtistRows();
  });
}

// update artist row labels after add or remove
function renumberArtistRows() {
  [...contribArtistsEl.children].forEach((row, i) => {
    const label = row.querySelector('.dynamic-row-label');
    if (label) label.textContent = `Artist ${i + 1}`;
  });
}

// append one setlist row to contribute form
function addSetlistRow(prefill = {}) {
  const id = ++setlistRowSeq;
  const seq = contribSetlistEl.children.length + 1;
  const row = document.createElement('div');
  row.className = 'dynamic-row';
  row.dataset.setlistRow = String(id);
  row.innerHTML = `
    <div class="dynamic-row-header">
      <span class="dynamic-row-label">Item ${seq}</span>
      <button type="button" class="btn-remove" data-remove-setlist>Remove</button>
    </div>
    <div class="dynamic-row-fields">
      <div>
        <label class="search-label" for="sl-seq-${id}">Sequence</label>
        <input id="sl-seq-${id}" type="number" min="1" data-field="sequence_number" value="${prefill.sequence_number || seq}" required />
      </div>
      <div>
        <label class="search-label" for="sl-ts-${id}">Timestamp</label>
        <input id="sl-ts-${id}" type="text" data-field="timestamp" required
          placeholder="m:ss or seconds" value="${prefill.timestamp || ''}" />
      </div>
      <div class="ac-wrap span-2">
        <label class="search-label" for="sl-piece-${id}">Piece</label>
        <input id="sl-piece-${id}" type="text" data-field="piece_name" required
          placeholder="Start typing to link an existing piece…" value="${prefill.piece_name || ''}" />
        <ul class="ac-list" id="sl-piece-ac-${id}" role="listbox"></ul>
        <div class="linked-badge new" data-link-status>New piece (will be reviewed)</div>
      </div>
      <div>
        <label class="search-label" for="sl-raga-${id}">Raga</label>
        <input id="sl-raga-${id}" type="text" data-field="raga_name" placeholder="Optional" value="${prefill.raga_name || ''}" />
      </div>
      <div>
        <label class="search-label" for="sl-talam-${id}">Talam</label>
        <input id="sl-talam-${id}" type="text" data-field="talam_name" placeholder="Optional" value="${prefill.talam_name || ''}" />
      </div>
      <div>
        <label class="search-label" for="sl-composer-${id}">Composer</label>
        <input id="sl-composer-${id}" type="text" data-field="composer_name" placeholder="Optional" value="${prefill.composer_name || ''}" />
      </div>
      <div>
        <label class="search-label" for="sl-kind-${id}">Kind</label>
        <select id="sl-kind-${id}" data-field="kind">
          ${KIND_OPTIONS.map(k =>
            `<option value="${k}"${(prefill.kind || '') === k ? ' selected' : ''}>${k || '—'}</option>`
          ).join('')}
        </select>
      </div>
    </div>
  `;

  contribSetlistEl.appendChild(row);
  renumberSetlistRows();

  const pieceInput = row.querySelector('[data-field="piece_name"]');
  const list = row.querySelector(`#sl-piece-ac-${id}`);
  const status = row.querySelector('[data-link-status]');
  const ragaInput = row.querySelector('[data-field="raga_name"]');
  const talamInput = row.querySelector('[data-field="talam_name"]');
  const composerInput = row.querySelector('[data-field="composer_name"]');
  const kindSelect = row.querySelector('[data-field="kind"]');

  const linker = wireEntityAutocomplete({
    input: pieceInput,
    list,
    fetchUrl: (q) => `${API}/pieces/autocomplete/${encodeURIComponent(q)}`,
    renderItem: (li, item) => {
      const name = document.createElement('div');
      name.className = 'ac-name';
      name.textContent = item.name;
      const meta = document.createElement('div');
      meta.className = 'ac-meta';
      meta.textContent = formatPieceMeta(item);
      li.appendChild(name);
      li.appendChild(meta);
    },
    onPick: (item) => {
      status.textContent = 'Linked to existing piece';
      status.classList.remove('new');
      if (item.raga) ragaInput.value = item.raga;
      if (item.talam) talamInput.value = item.talam;
      if (item.composer) composerInput.value = item.composer;
    },
    onClear: () => {
      status.textContent = 'New piece (will be reviewed)';
      status.classList.add('new');
    },
  });

  if (prefill.piece_id) {
    linker.setSelectedId(prefill.piece_id);
    status.textContent = 'Linked to existing piece';
    status.classList.remove('new');
  }

  row._getSetlistDraft = () => {
    const ts = parseTimestampInput(row.querySelector('[data-field="timestamp"]').value);
    const seq = parseInt(row.querySelector('[data-field="sequence_number"]').value, 10);
    return {
      sequence_number: Number.isFinite(seq) ? seq : null,
      timestamp_seconds: ts,
      piece_id: linker.getSelectedId(),
      piece_name: pieceInput.value.trim(),
      raga_name: ragaInput.value.trim() || null,
      talam_name: talamInput.value.trim() || null,
      composer_name: composerInput.value.trim() || null,
      kind: kindSelect.value || null,
    };
  };

  row.querySelector('[data-remove-setlist]').addEventListener('click', () => {
    if (contribSetlistEl.children.length <= 1) {
      setContribStatus('At least one setlist item is required.', 'err');
      return;
    }
    row.remove();
    renumberSetlistRows();
  });
}

// update setlist row labels and default sequences
function renumberSetlistRows() {
  [...contribSetlistEl.children].forEach((row, i) => {
    const label = row.querySelector('.dynamic-row-label');
    if (label) label.textContent = `Item ${i + 1}`;
    const seqInput = row.querySelector('[data-field="sequence_number"]');
    if (seqInput && (!seqInput.dataset.touched || seqInput.value === '')) {
      seqInput.value = String(i + 1);
    }
  });
}

contribSetlistEl.addEventListener('input', (e) => {
  if (e.target.matches('[data-field="sequence_number"]')) {
    e.target.dataset.touched = '1';
  }
});

// live feedback while parsing youtube url
contribYoutube.addEventListener('input', () => {
  const id = parseYoutubeId(contribYoutube.value);
  if (!contribYoutube.value.trim()) {
    contribYoutubeHint.textContent = '';
    contribYoutubeHint.className = 'field-hint';
  } else if (id) {
    contribYoutubeHint.textContent = `Video id: ${id}`;
    contribYoutubeHint.className = 'field-hint ok';
  } else {
    contribYoutubeHint.textContent = 'Could not parse a YouTube video id';
    contribYoutubeHint.className = 'field-hint err';
  }
});

document.getElementById('add-artist-btn').addEventListener('click', () => addArtistRow({ role: 'accompanist' }));
document.getElementById('add-setlist-btn').addEventListener('click', () => addSetlistRow());

// collect all form fields into draft payload
function buildContributePayload() {
  const youtubeId = parseYoutubeId(contribYoutube.value);
  const duration = parseTimestampInput(document.getElementById('contrib-duration').value);
  const yearRaw = document.getElementById('contrib-year').value.trim();
  const year = yearRaw === '' ? null : parseInt(yearRaw, 10);

  const artists = [...contribArtistsEl.children].map(row => row._getArtistDraft());
  const setlist = [...contribSetlistEl.children].map(row => row._getSetlistDraft());

  return {
    youtube_id: youtubeId,
    title: document.getElementById('contrib-title').value.trim(),
    year: Number.isFinite(year) ? year : null,
    venue: document.getElementById('contrib-venue').value.trim() || null,
    duration_seconds: duration,
    artists,
    setlist,
  };
}

// return list of validation error messages
function validateContributePayload(payload) {
  const errors = [];
  if (!payload.youtube_id) errors.push('A valid YouTube URL or 11-character video id is required.');
  if (!payload.title) errors.push('Concert title is required.');
  if (payload.year != null && (payload.year < 1900 || payload.year > 2100)) {
    errors.push('Year looks invalid.');
  }
  if (!payload.artists.length) errors.push('Add at least one artist.');
  payload.artists.forEach((a, i) => {
    if (!a.artist_name) errors.push(`Artist ${i + 1}: name is required.`);
  });
  if (!payload.artists.some(a => a.role === 'main artist')) {
    errors.push('Mark at least one artist as main artist.');
  }
  if (!payload.setlist.length) errors.push('Add at least one setlist item.');
  const seqs = new Set();
  payload.setlist.forEach((item, i) => {
    if (!item.piece_name) errors.push(`Setlist item ${i + 1}: piece name is required.`);
    if (item.timestamp_seconds == null || item.timestamp_seconds < 0) {
      errors.push(`Setlist item ${i + 1}: enter a valid timestamp (m:ss or seconds).`);
    }
    if (!item.sequence_number || item.sequence_number < 1) {
      errors.push(`Setlist item ${i + 1}: sequence must be a positive number.`);
    } else if (seqs.has(item.sequence_number)) {
      errors.push(`Duplicate sequence number: ${item.sequence_number}.`);
    } else {
      seqs.add(item.sequence_number);
    }
  });
  return errors;
}

// validate then post draft to create endpoint
contributeForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  setContribStatus('');

  const payload = buildContributePayload();
  const errors = validateContributePayload(payload);
  if (errors.length) {
    setContribStatus(errors[0], 'err');
    return;
  }

  contribSubmit.disabled = true;
  setContribStatus('Submitting…');

  try {
    const res = await fetch(`${API}/contributions/create_concert_draft`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setContribStatus(data.error || 'Submission failed.', 'err');
      return;
    }
    setContribStatus(`Submitted for review (draft #${data.id}).`, 'ok');
    contributeForm.reset();
    contribArtistsEl.innerHTML = '';
    contribSetlistEl.innerHTML = '';
    contribYoutubeHint.textContent = '';
    contribYoutubeHint.className = 'field-hint';
    addArtistRow({ role: 'main artist' });
    addSetlistRow({ sequence_number: 1, timestamp: '0:00' });
  } catch {
    setContribStatus('Could not reach the server. Is it running?', 'err');
  } finally {
    contribSubmit.disabled = false;
  }
});

// start form with one artist and piece
addArtistRow({ role: 'main artist' });
addSetlistRow({ sequence_number: 1, timestamp: '0:00' });
