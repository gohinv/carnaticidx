const API = '';

const input = document.getElementById('search-input');
const acList = document.getElementById('autocomplete-list');
const resultsSection = document.getElementById('results-section');
const resultsTitle = document.getElementById('results-title');
const resultsSubtitle = document.getElementById('results-subtitle');
const resultsCount = document.getElementById('results-count');
const renditionList = document.getElementById('rendition-list');
const loadingEl = document.getElementById('loading');
const emptyState = document.getElementById('empty-state');

let acItems = [];
let activeIdx = -1;
let debounceTimer = null;

function formatPieceMeta({ raga, talam, composer }) {
  return [raga, talam, composer].filter(Boolean).join(' · ');
}

function updateResultsHeader(piece) {
  resultsTitle.textContent = piece.name;
  resultsSubtitle.textContent = formatPieceMeta(piece);
}

input.addEventListener('input', () => {
  clearTimeout(debounceTimer);
  const q = input.value.trim();
  if (q.length < 1) { closeAc(); return; }
  debounceTimer = setTimeout(() => fetchAc(q), 160);
});

async function fetchAc(q) {
  try {
    const res = await fetch(`${API}/pieces/autocomplete/${encodeURIComponent(q)}`);
    acItems = await res.json();
    renderAc();
  } catch {
    closeAc();
  }
}

function renderAc() {
  acList.innerHTML = '';
  activeIdx = -1;
  if (!acItems.length) { closeAc(); return; }
  acItems.forEach((item) => {
    const li = document.createElement('li');
    li.className = 'ac-item';
    li.setAttribute('role', 'option');

    const name = document.createElement('div');
    name.className = 'ac-name';
    name.textContent = item.name;

    const meta = document.createElement('div');
    meta.className = 'ac-meta';
    meta.textContent = formatPieceMeta(item);

    li.appendChild(name);
    li.appendChild(meta);
    li.addEventListener('mousedown', (e) => {
      e.preventDefault();
      selectPiece(item);
    });
    acList.appendChild(li);
  });
  acList.classList.add('open');
}

function closeAc() {
  acList.classList.remove('open');
  acList.innerHTML = '';
  acItems = [];
  activeIdx = -1;
}

input.addEventListener('keydown', (e) => {
  if (!acList.classList.contains('open')) return;
  const items = acList.querySelectorAll('.ac-item');
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    activeIdx = Math.min(activeIdx + 1, items.length - 1);
    updateActive(items);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    activeIdx = Math.max(activeIdx - 1, 0);
    updateActive(items);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (activeIdx >= 0 && acItems[activeIdx]) {
      selectPiece(acItems[activeIdx]);
    }
  } else if (e.key === 'Escape') {
    closeAc();
  }
});

function updateActive(items) {
  items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
  if (activeIdx >= 0) items[activeIdx].scrollIntoView({ block: 'nearest' });
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.search-wrapper')) closeAc();
});

function selectPiece(piece) {
  input.value = piece.name;
  closeAc();
  loadSetlist(piece);
}

function formatArtists(artists) {
  return artists.map(a => a.name).join(' · ');
}

async function fetchArtistsByConcert(renditions) {
  const cache = {};
  const concertIds = [...new Set(renditions.map(r => r.concert_id))];
  await Promise.all(concertIds.map(async (id) => {
    try {
      const res = await fetch(`${API}/concerts/get-artists/${id}`);
      cache[id] = res.ok ? await res.json() : [];
    } catch {
      cache[id] = [];
    }
  }));
  return cache;
}

async function loadSetlist(piece) {
  resultsSection.style.display = 'block';
  updateResultsHeader(piece);
  renditionList.innerHTML = '';
  emptyState.style.display = 'none';
  loadingEl.style.display = 'block';
  resultsCount.textContent = '';

  try {
    const res = await fetch(`${API}/pieces/get-setlist/${encodeURIComponent(piece.name)}`);
    const data = await res.json();
    loadingEl.style.display = 'none';

    if (!data.length) {
      emptyState.textContent = 'No renditions found for this piece.';
      emptyState.style.display = 'block';
      return;
    }

    updateResultsHeader({
      name: data[0].piece_name,
      raga: data[0].raga,
      talam: data[0].talam,
      composer: data[0].composer,
    });

    resultsCount.textContent = `${data.length} rendition${data.length !== 1 ? 's' : ''}`;
    data.sort((a, b) => (a.concert_year ?? 9999) - (b.concert_year ?? 9999));
    const artistCache = await fetchArtistsByConcert(data);
    data.forEach(r => renditionList.appendChild(buildCard(r, artistCache[r.concert_id])));
  } catch {
    loadingEl.style.display = 'none';
    emptyState.textContent = 'Error loading renditions. Is the server running?';
    emptyState.style.display = 'block';
  }
}

function formatTimestamp(secs) {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function buildCard(r, artists = []) {
  const li = document.createElement('li');
  li.className = 'rendition-card';

  const meta = document.createElement('div');
  meta.className = 'rendition-meta';

  const title = document.createElement('div');
  title.className = 'rendition-concert';
  title.textContent = r.concert_title || 'Untitled Concert';
  meta.appendChild(title);

  const details = document.createElement('div');
  details.className = 'rendition-details';
  if (r.concert_year) {
    const yr = document.createElement('span');
    yr.textContent = r.concert_year;
    details.appendChild(yr);
  }
  if (artists.length) {
    const artistLine = document.createElement('span');
    artistLine.textContent = formatArtists(artists);
    details.appendChild(artistLine);
  }
  meta.appendChild(details);

  const link = document.createElement('a');
  link.className = 'rendition-link';
  link.href = r.track_url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.innerHTML = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polygon points="5 3 19 12 5 21 5 3"/>
    </svg>
    ${formatTimestamp(r.timestamp_seconds ?? 0)}
  `;

  li.appendChild(meta);
  li.appendChild(link);
  return li;
}
