const API = '';

// Cache concert metadata (title, year, venue, url) keyed by concert id.
const concertMetaCache = {};
function cacheConcertMeta(meta) {
  if (!meta || meta.id == null) return;
  concertMetaCache[meta.id] = { ...concertMetaCache[meta.id], ...meta };
}

// ---------- Tab switching ----------
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.tab;
    document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.tab-panel').forEach(p => {
      p.classList.toggle('active', p.dataset.panel === target);
    });
  });
});

// ---------- Generic autocomplete helper ----------
function createAutocomplete({ input, list, fetchUrl, renderItem, onSelect }) {
  let items = [];
  let activeIdx = -1;
  let timer = null;

  const close = () => {
    list.classList.remove('open');
    list.innerHTML = '';
    items = [];
    activeIdx = -1;
  };

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

  const fetchItems = async (q) => {
    try {
      const res = await fetch(fetchUrl(q));
      items = await res.json();
      render();
    } catch {
      close();
    }
  };

  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 1) { close(); return; }
    timer = setTimeout(() => fetchItems(q), 160);
  });

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

  document.addEventListener('click', (e) => {
    if (!list.contains(e.target) && e.target !== input) close();
  });

  return { close };
}

// ---------- Helpers ----------
function formatPieceMeta({ raga, talam, composer }) {
  return [raga, talam, composer].filter(Boolean).join(' · ');
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

// ---------- PIECES TAB ----------
const pieceInput = document.getElementById('piece-input');
const pieceAcList = document.getElementById('piece-ac-list');
const pieceResultsSection = document.getElementById('piece-results-section');
const pieceResultsTitle = document.getElementById('piece-results-title');
const pieceResultsSubtitle = document.getElementById('piece-results-subtitle');
const pieceResultsCount = document.getElementById('piece-results-count');
const renditionList = document.getElementById('rendition-list');
const pieceLoading = document.getElementById('piece-loading');
const pieceEmpty = document.getElementById('piece-empty-state');

createAutocomplete({
  input: pieceInput,
  list: pieceAcList,
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
  onSelect: (piece) => {
    pieceInput.value = piece.name;
    loadSetlist(piece);
  },
});

async function loadSetlist(piece) {
  pieceResultsSection.style.display = 'block';
  pieceResultsTitle.textContent = piece.name;
  pieceResultsSubtitle.textContent = formatPieceMeta(piece);
  renditionList.innerHTML = '';
  pieceEmpty.style.display = 'none';
  pieceLoading.style.display = 'block';
  pieceResultsCount.textContent = '';

  try {
    const res = await fetch(`${API}/pieces/get-setlist/${encodeURIComponent(piece.name)}`);
    const data = await res.json();
    pieceLoading.style.display = 'none';

    if (!data.length) {
      pieceEmpty.textContent = 'No renditions found for this piece.';
      pieceEmpty.style.display = 'block';
      return;
    }

    pieceResultsTitle.textContent = data[0].piece_name;
    pieceResultsSubtitle.textContent = formatPieceMeta({
      raga: data[0].raga, talam: data[0].talam, composer: data[0].composer,
    });

    pieceResultsCount.textContent = `${data.length} rendition${data.length !== 1 ? 's' : ''}`;
    data.sort((a, b) => (a.concert_year ?? 9999) - (b.concert_year ?? 9999));
    data.forEach(r => cacheConcertMeta({
      id: r.concert_id,
      title: r.concert_title,
      year: r.concert_year,
      venue: r.concert_venue,
      url: r.track_url ? r.track_url.split('&t=')[0] : null,
    }));
    const artistCache = await fetchArtistsByConcert(data);
    data.forEach(r => renditionList.appendChild(buildRenditionCard(r, artistCache[r.concert_id])));
  } catch {
    pieceLoading.style.display = 'none';
    pieceEmpty.textContent = 'Error loading renditions. Is the server running?';
    pieceEmpty.style.display = 'block';
  }
}

function buildRenditionCard(r, artists = []) {
  const li = document.createElement('li');
  li.className = 'rendition-card';

  const meta = document.createElement('div');
  meta.className = 'rendition-meta';

  const title = document.createElement('a');
  title.className = 'rendition-concert';
  title.textContent = r.concert_title || 'Untitled Concert';
  title.href = `#/concert/${r.concert_id}`;
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
    ${formatDuration(r.duration_seconds)}
  `;

  li.appendChild(meta);
  li.appendChild(link);
  return li;
}

// ---------- CONCERTS TAB ----------
const artistInput = document.getElementById('artist-input');
const artistAcList = document.getElementById('artist-ac-list');
const concertResultsSection = document.getElementById('concert-results-section');
const concertResultsTitle = document.getElementById('concert-results-title');
const concertResultsSubtitle = document.getElementById('concert-results-subtitle');
const concertResultsCount = document.getElementById('concert-results-count');
const concertGrid = document.getElementById('concert-grid');
const concertLoading = document.getElementById('concert-loading');
const concertEmpty = document.getElementById('concert-empty-state');

createAutocomplete({
  input: artistInput,
  list: artistAcList,
  fetchUrl: (q) => `${API}/artists/autocomplete/${encodeURIComponent(q)}`,
  renderItem: (li, item) => {
    const name = document.createElement('div');
    name.className = 'ac-name';
    name.textContent = item.name;
    li.appendChild(name);
  },
  onSelect: (artist) => {
    artistInput.value = artist.name;
    loadConcerts(artist);
  },
});

async function loadConcerts(artist) {
  concertResultsSection.style.display = 'block';
  concertResultsTitle.textContent = artist.name;
  concertResultsSubtitle.textContent = 'Concerts as main artist';
  concertGrid.innerHTML = '';
  concertEmpty.style.display = 'none';
  concertLoading.style.display = 'block';
  concertResultsCount.textContent = '';

  try {
    const res = await fetch(`${API}/concerts/find/${encodeURIComponent(artist.name)}`);
    const data = await res.json();
    concertLoading.style.display = 'none';

    if (!data.length) {
      concertEmpty.textContent = 'No concerts found for this artist.';
      concertEmpty.style.display = 'block';
      return;
    }

    concertResultsCount.textContent = `${data.length} concert${data.length !== 1 ? 's' : ''}`;
    data.forEach(c => {
      cacheConcertMeta(c);
      concertGrid.appendChild(buildConcertTile(c));
    });
  } catch {
    concertLoading.style.display = 'none';
    concertEmpty.textContent = 'Error loading concerts. Is the server running?';
    concertEmpty.style.display = 'block';
  }
}

function buildConcertTile(c) {
  const li = document.createElement('li');
  const a = document.createElement('a');
  a.className = 'concert-tile';
  a.href = `#/concert/${c.id}`;

  const info = document.createElement('div');
  info.className = 'concert-tile-info';

  const title = document.createElement('div');
  title.className = 'concert-tile-title';
  title.textContent = c.title || 'Untitled Concert';

  const sub = document.createElement('div');
  sub.className = 'concert-tile-sub';
  sub.textContent = [c.year, c.venue].filter(Boolean).join(' · ');

  const arrow = document.createElement('span');
  arrow.className = 'concert-tile-arrow';
  arrow.textContent = '›';

  info.appendChild(title);
  info.appendChild(sub);
  a.appendChild(info);
  a.appendChild(arrow);
  li.appendChild(a);
  return li;
}

// ---------- CONCERT DETAIL VIEW ----------
const searchView = document.getElementById('search-view');
const concertView = document.getElementById('concert-view');
const concertDetailLoading = document.getElementById('concert-detail-loading');
const concertDetail = document.getElementById('concert-detail');
const concertDetailTitle = document.getElementById('concert-detail-title');
const concertDetailArtists = document.getElementById('concert-detail-artists');
const concertDetailSub = document.getElementById('concert-detail-sub');
const concertDetailLink = document.getElementById('concert-detail-link');
const setlistEl = document.getElementById('setlist');
const setlistEmpty = document.getElementById('setlist-empty');

async function getConcertMeta(concertId) {
  const cached = concertMetaCache[concertId];
  if (cached?.duration_seconds != null) return cached;

  try {
    const res = await fetch(`${API}/concerts/get-metadata/${concertId}`);
    if (!res.ok) return cached || {};
    const meta = await res.json();
    cacheConcertMeta(meta);
    return { ...cached, ...meta };
  } catch {
    return cached || {};
  }
}

async function showConcert(concertId) {
  searchView.style.display = 'none';
  concertView.style.display = 'block';
  concertDetail.style.display = 'none';
  setlistEmpty.style.display = 'none';
  concertDetailLoading.style.display = 'block';
  setlistEl.innerHTML = '';
  window.scrollTo(0, 0);

  try {
    const [setlistRes, artistsRes, concertMeta] = await Promise.all([
      fetch(`${API}/concerts/setlist/${concertId}`),
      fetch(`${API}/concerts/get-artists/${concertId}`),
      getConcertMeta(concertId),
    ]);
    const setlist = await setlistRes.json();
    const artists = artistsRes.ok ? await artistsRes.json() : [];

    concertDetailLoading.style.display = 'none';
    concertDetail.style.display = 'block';

    const title = concertMeta.title || 'Concert';
    concertDetailTitle.textContent = title;

    const mainArtists = artists.filter(a => a.role === 'main artist');
    const accompanists = artists.filter(a => a.role !== 'main artist');
    concertDetailArtists.textContent = mainArtists.length
      ? mainArtists.map(a => a.name).join(', ')
      : '';

    const subBits = [];
    if (concertMeta.year) subBits.push(concertMeta.year);
    if (concertMeta.venue) subBits.push(concertMeta.venue);
    if (accompanists.length) {
      subBits.push('with ' + accompanists.map(a => `${a.name}${a.instrument ? ` (${a.instrument})` : ''}`).join(', '));
    }
    concertDetailSub.textContent = subBits.join(' · ');

    if (concertMeta.url) {
      concertDetailLink.href = concertMeta.url;
      concertDetailLink.style.display = 'inline-block';
    } else {
      concertDetailLink.style.display = 'none';
    }

    if (!setlist.length) {
      setlistEmpty.style.display = 'block';
      return;
    }

    // Header row
    const header = document.createElement('li');
    header.className = 'setlist-header';
    header.innerHTML = `<span></span><span>Piece</span><span>Duration</span>`;
    setlistEl.appendChild(header);

    setlist.forEach((item, idx) => {
      const nextTs = setlist[idx + 1]?.timestamp_seconds
        ?? concertMeta.duration_seconds
        ?? null;
      setlistEl.appendChild(buildSetlistRow(item, idx + 1, concertMeta, nextTs));
    });
  } catch {
    concertDetailLoading.style.display = 'none';
    setlistEmpty.textContent = 'Error loading concert.';
    setlistEmpty.style.display = 'block';
    concertDetail.style.display = 'block';
  }
}

function formatDuration(secs) {
  if (secs == null || secs <= 0) return '—';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function buildSetlistRow(item, position, concertMeta, nextTimestamp) {
  const li = document.createElement('li');
  li.className = 'setlist-row';

  const num = document.createElement('div');
  num.className = 'setlist-num';
  num.textContent = position;

  const main = document.createElement('div');
  main.className = 'setlist-main';

  const name = document.createElement('a');
  name.className = 'setlist-name';
  name.textContent = item.name || '(unknown piece)';
  if (concertMeta && concertMeta.url) {
    name.href = `${concertMeta.url}&t=${item.timestamp_seconds}`;
    name.target = '_blank';
    name.rel = 'noopener noreferrer';
  } else {
    name.href = '#';
  }

  const meta = document.createElement('div');
  meta.className = 'setlist-meta';
  meta.textContent = formatPieceMeta({ raga: item.raga, talam: item.talam, composer: item.composer });

  main.appendChild(name);
  main.appendChild(meta);

  const durationSecs = nextTimestamp != null
    ? nextTimestamp - (item.timestamp_seconds ?? 0)
    : null;

  const time = document.createElement('span');
  time.className = 'setlist-time';
  time.textContent = formatDuration(durationSecs);

  li.appendChild(num);
  li.appendChild(main);
  li.appendChild(time);
  return li;
}

// ---------- Hash router ----------
function route() {
  const hash = window.location.hash || '#/';
  const concertMatch = hash.match(/^#\/concert\/(\d+)$/);
  if (concertMatch) {
    showConcert(concertMatch[1]);
  } else {
    concertView.style.display = 'none';
    searchView.style.display = 'block';
  }
}

window.addEventListener('hashchange', route);
route();
