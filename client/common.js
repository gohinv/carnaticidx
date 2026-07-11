// empty string uses same origin for api
const API = '';

// in-memory concert metadata keyed by id
const concertMetaCache = {};
function cacheConcertMeta(meta) {
  if (!meta || meta.id == null) return;
  concertMetaCache[meta.id] = { ...concertMetaCache[meta.id], ...meta };
}

// reusable debounced autocomplete dropdown for search inputs
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

  const fetchItems = async (q) => {
    try {
      const res = await fetch(fetchUrl(q));
      items = await res.json();
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
    timer = setTimeout(() => fetchItems(q), 160);
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

// fetch lineup for each concert in parallel
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

// format elapsed seconds as h:mm:ss or m:ss
function formatDuration(secs) {
  if (secs == null || secs <= 0) return '—';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}
