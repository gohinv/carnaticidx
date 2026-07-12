// contribute form options and dom refs
const KIND_OPTIONS = ['', 'krithi', 'varnam', 'javali', 'padam', 'tillana', 'viruttam', 'slokam', 'mangalam', 'bhajan', 'tiruppavai', 'tiruppugazh', 'rtp'];
const ROLE_OPTIONS = ['main artist', 'accompanist'];

const contributeForm = document.getElementById('contribute-form');
const contribArtistsEl = document.getElementById('contrib-artists');
const contribSetlistEl = document.getElementById('contrib-setlist');
const contribStatus = document.getElementById('contrib-status');
const contribSubmit = document.getElementById('contrib-submit');
const contribYoutube = document.getElementById('contrib-youtube');
const contribYoutubeHint = document.getElementById('contrib-youtube-hint');
const contribDescription = document.getElementById('contrib-description');
const contribDescriptionHint = document.getElementById('contrib-description-hint');
const prefillSetlistBtn = document.getElementById('prefill-setlist-btn');

let artistRowSeq = 0;
let setlistRowSeq = 0;

function escapeHtmlAttribute(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

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

function formatTimestamp(seconds) {
  const total = Number(seconds);
  if (!Number.isInteger(total) || total < 0) return '';
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }
  return `${minutes}:${String(secs).padStart(2, '0')}`;
}

function setContribStatus(msg, kind = '') {
  contribStatus.textContent = msg || '';
  contribStatus.className = 'form-status' + (kind ? ` ${kind}` : '');
}

function setPrefillStatus(msg, kind = '') {
  contribDescriptionHint.textContent = msg || '';
  contribDescriptionHint.className = 'field-hint' + (kind ? ` ${kind}` : '');
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
          placeholder="Start typing to link an existing artist…" value="${escapeHtmlAttribute(prefill.artist_name)}" />
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
          placeholder="e.g. vocal, violin" value="${escapeHtmlAttribute(prefill.instrument)}" />
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
        <input id="sl-seq-${id}" type="number" min="1" data-field="sequence_number"
          value="${escapeHtmlAttribute(prefill.sequence_number || seq)}" required />
      </div>
      <div>
        <label class="search-label" for="sl-ts-${id}">Timestamp</label>
        <input id="sl-ts-${id}" type="text" data-field="timestamp" required
          placeholder="m:ss or seconds" value="${escapeHtmlAttribute(prefill.timestamp)}" />
      </div>
      <div class="ac-wrap span-2">
        <label class="search-label" for="sl-piece-${id}">Piece</label>
        <input id="sl-piece-${id}" type="text" data-field="piece_name" required
          placeholder="Start typing to link an existing piece…" value="${escapeHtmlAttribute(prefill.piece_name)}" />
        <ul class="ac-list" id="sl-piece-ac-${id}" role="listbox"></ul>
        <div class="linked-badge new" data-link-status>New piece (will be reviewed)</div>
      </div>
      <div class="ac-wrap">
        <label class="search-label" for="sl-raga-${id}">Raga</label>
        <input id="sl-raga-${id}" type="text" data-field="raga_name"
          placeholder="Type to link or enter a new raga" value="${escapeHtmlAttribute(prefill.raga_name)}" />
        <ul class="ac-list" id="sl-raga-ac-${id}" role="listbox"></ul>
        <div class="linked-badge new" data-raga-link-status>New raga (will be reviewed)</div>
      </div>
      <div class="ac-wrap">
        <label class="search-label" for="sl-talam-${id}">Talam</label>
        <input id="sl-talam-${id}" type="text" data-field="talam_name"
          placeholder="Type to link or enter a new talam" value="${escapeHtmlAttribute(prefill.talam_name)}" />
        <ul class="ac-list" id="sl-talam-ac-${id}" role="listbox"></ul>
        <div class="linked-badge new" data-talam-link-status>New talam (will be reviewed)</div>
      </div>
      <div class="ac-wrap">
        <label class="search-label" for="sl-composer-${id}">Composer</label>
        <input id="sl-composer-${id}" type="text" data-field="composer_name"
          placeholder="Type to link or enter a new composer" value="${escapeHtmlAttribute(prefill.composer_name)}" />
        <ul class="ac-list" id="sl-composer-ac-${id}" role="listbox"></ul>
        <div class="linked-badge new" data-composer-link-status>New composer (will be reviewed)</div>
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

  const wireMetadataAutocomplete = ({ entity, input, listId, endpoint, statusSelector }) => {
    const entityStatus = row.querySelector(statusSelector);
    const metadataLinker = wireEntityAutocomplete({
      input,
      list: row.querySelector(listId),
      fetchUrl: (q) => `${API}/${endpoint}/autocomplete/${encodeURIComponent(q)}`,
      renderItem: (li, item) => {
        const name = document.createElement('div');
        name.className = 'ac-name';
        name.textContent = item.name;
        li.appendChild(name);
      },
      onPick: () => {
        entityStatus.textContent = `Linked to existing ${entity}`;
        entityStatus.classList.remove('new');
      },
      onClear: () => {
        entityStatus.textContent = `New ${entity} (will be reviewed)`;
        entityStatus.classList.add('new');
      },
    });

    return { linker: metadataLinker, status: entityStatus };
  };

  const raga = wireMetadataAutocomplete({
    entity: 'raga',
    input: ragaInput,
    listId: `#sl-raga-ac-${id}`,
    endpoint: 'ragas',
    statusSelector: '[data-raga-link-status]',
  });
  const talam = wireMetadataAutocomplete({
    entity: 'talam',
    input: talamInput,
    listId: `#sl-talam-ac-${id}`,
    endpoint: 'talams',
    statusSelector: '[data-talam-link-status]',
  });
  const composer = wireMetadataAutocomplete({
    entity: 'composer',
    input: composerInput,
    listId: `#sl-composer-ac-${id}`,
    endpoint: 'composers',
    statusSelector: '[data-composer-link-status]',
  });

  const linkMetadataFromPiece = (metadata, item, nameKey, idKey, input, entity) => {
    if (!item[nameKey]) return;
    input.value = item[nameKey];
    metadata.linker.setSelectedId(item[idKey]);
    metadata.status.textContent = `Linked to existing ${entity}`;
    metadata.status.classList.remove('new');
  };

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
      linkMetadataFromPiece(raga, item, 'raga', 'raga_id', ragaInput, 'raga');
      linkMetadataFromPiece(talam, item, 'talam', 'talam_id', talamInput, 'talam');
      linkMetadataFromPiece(composer, item, 'composer', 'composer_id', composerInput, 'composer');
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

  [
    [raga, prefill.raga_id, 'raga'],
    [talam, prefill.talam_id, 'talam'],
    [composer, prefill.composer_id, 'composer'],
  ].forEach(([metadata, selectedId, entity]) => {
    if (!selectedId) return;
    metadata.linker.setSelectedId(selectedId);
    metadata.status.textContent = `Linked to existing ${entity}`;
    metadata.status.classList.remove('new');
  });

  row._getSetlistDraft = () => {
    const ts = parseTimestampInput(row.querySelector('[data-field="timestamp"]').value);
    const seq = parseInt(row.querySelector('[data-field="sequence_number"]').value, 10);
    return {
      sequence_number: Number.isFinite(seq) ? seq : null,
      timestamp_seconds: ts,
      piece_id: linker.getSelectedId(),
      piece_name: pieceInput.value.trim(),
      raga_id: raga.linker.getSelectedId(),
      raga_name: ragaInput.value.trim() || null,
      talam_id: talam.linker.getSelectedId(),
      talam_name: talamInput.value.trim() || null,
      composer_id: composer.linker.getSelectedId(),
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

function setlistHasUserEdits() {
  const rows = [...contribSetlistEl.children];
  if (rows.length !== 1) return rows.length > 0;

  const row = rows[0];
  const sequence = row.querySelector('[data-field="sequence_number"]').value.trim();
  const timestamp = row.querySelector('[data-field="timestamp"]').value.trim();
  const contentFields = [
    'piece_name',
    'raga_name',
    'talam_name',
    'composer_name',
    'kind',
  ];
  return (
    sequence !== '1'
    || timestamp !== '0:00'
    || contentFields.some(field => row.querySelector(`[data-field="${field}"]`).value.trim())
  );
}

contribDescription.addEventListener('input', () => setPrefillStatus(''));

prefillSetlistBtn.addEventListener('click', async () => {
  const description = contribDescription.value.trim();
  if (!description) {
    setPrefillStatus('Paste a timestamped description or comment first.', 'err');
    return;
  }
  if (
    setlistHasUserEdits()
    && !window.confirm('Replace the current setlist with entries parsed from this text?')
  ) {
    return;
  }

  prefillSetlistBtn.disabled = true;
  setPrefillStatus('Parsing setlist…');

  try {
    const res = await fetch(`${API}/contributions/parse_setlist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setPrefillStatus(data.error || 'Could not parse a setlist from this text.', 'err');
      return;
    }

    contribSetlistEl.innerHTML = '';
    data.setlist.forEach(item => addSetlistRow({
      ...item,
      timestamp: formatTimestamp(item.timestamp_seconds),
    }));
    setPrefillStatus(
      `Prefilled ${data.setlist.length} setlist ${data.setlist.length === 1 ? 'item' : 'items'}. Review and edit them below.`,
      'ok',
    );
  } catch {
    setPrefillStatus('Could not reach the server. Is it running?', 'err');
  } finally {
    prefillSetlistBtn.disabled = false;
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
    setPrefillStatus('');
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
