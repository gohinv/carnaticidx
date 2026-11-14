// pieces tab dom refs and autocomplete
const pieceInput = document.getElementById('piece-input');
const pieceAcList = document.getElementById('piece-ac-list');
const pieceResultsSection = document.getElementById('piece-results-section');
const pieceResultsTitle = document.getElementById('piece-results-title');
const pieceResultsSubtitle = document.getElementById('piece-results-subtitle');
const pieceResultsCount = document.getElementById('piece-results-count');
const renditionList = document.getElementById('rendition-list');
const pieceLoading = document.getElementById('piece-loading');
const pieceEmpty = document.getElementById('piece-empty-state');

const filterRadios = document.querySelectorAll('input[name="piece-filter-type"]');
const pieceInputLabel = document.getElementById('piece-input-label');
const artistFilter = document.getElementById('artist-filter');
const artistInput = document.getElementById('artist-input');
const artistAcList = document.getElementById('artist-ac-list');

// per-filter config: which entity the primary autocomplete searches
const FILTER_CONFIG = {
  name: { entity: 'pieces', label: 'Piece', placeholder: 'Begin typing a piece name…' },
  raga: { entity: 'ragas', label: 'Raga', placeholder: 'Begin typing a raga name…' },
  composer: { entity: 'composers', label: 'Composer', placeholder: 'Begin typing a composer name…' },
};

// current search: selected primary item (piece/raga/composer) and optional artist
const searchState = { selected: null, artist: null };
let searchSeq = 0; // guards against stale responses from overlapping searches

function currentFilterType() {
  return document.querySelector('input[name="piece-filter-type"]:checked').value;
}

function currentFilter() {
  return FILTER_CONFIG[currentFilterType()];
}

const pieceAutocomplete = createAutocomplete({
  input: pieceInput,
  list: pieceAcList,
  fetchItems: async (q) => {
    await loadLookups();
    return apiAutocomplete(currentFilter().entity, q);
  },
  renderItem: (li, item) => {
    const name = document.createElement('div');
    name.className = 'ac-name';
    name.textContent = item.name;
    li.appendChild(name);
    if (currentFilterType() === 'name') {
      const meta = document.createElement('div');
      meta.className = 'ac-meta';
      meta.textContent = formatPieceMeta(pieceMeta(item));
      li.appendChild(meta);
    }
  },
  onSelect: (item) => {
    pieceInput.value = item.name;
    searchState.selected = item;
    artistFilter.style.display = 'block';
    runSearch();
  },
});

const artistAutocomplete = createAutocomplete({
  input: artistInput,
  list: artistAcList,
  fetchItems: (q) => apiAutocomplete('artists', q),
  renderItem: (li, item) => {
    const name = document.createElement('div');
    name.className = 'ac-name';
    name.textContent = item.name;
    li.appendChild(name);
  },
  onSelect: (artist) => {
    artistInput.value = artist.name;
    searchState.artist = artist;
    runSearch();
  },
});

// clearing the artist field removes the artist filter
artistInput.addEventListener('input', () => {
  if (artistInput.value.trim() === '' && searchState.artist) {
    searchState.artist = null;
    runSearch();
  }
});

// switching filter type resets the whole search
filterRadios.forEach(radio => radio.addEventListener('change', () => {
  const cfg = currentFilter();
  pieceInputLabel.textContent = cfg.label;
  pieceInput.placeholder = cfg.placeholder;
  pieceInput.value = '';
  artistInput.value = '';
  searchState.selected = null;
  searchState.artist = null;
  artistFilter.style.display = 'none';
  pieceResultsSection.style.display = 'none';
  searchSeq++;
  pieceAutocomplete.close();
  artistAutocomplete.close();
}));

// gap until the next timestamp in the same concert, else until concert end
function renditionDuration(item, concertItems, concert) {
  let nextTs = concert ? concert.duration_seconds : null;
  if (concertItems) {
    for (let i = 0; i < concertItems.length; i++) {
      if (concertItems[i].id === item.id && i + 1 < concertItems.length) {
        nextTs = concertItems[i + 1].timestamp_seconds;
        break;
      }
    }
  }
  if (nextTs == null || item.timestamp_seconds == null) return null;
  const delta = nextTs - item.timestamp_seconds;
  return delta > 0 ? delta : null;
}

function setResultsHeading(selected, artist) {
  const type = currentFilterType();
  const byArtist = artist ? ` by ${artist.name}` : '';
  if (type === 'name') {
    pieceResultsTitle.textContent = selected.name;
    pieceResultsSubtitle.textContent =
      formatPieceMeta(pieceMeta(selected)) + (artist ? (formatPieceMeta(pieceMeta(selected)) ? ' · ' : '') + `by ${artist.name}` : '');
  } else if (type === 'raga') {
    pieceResultsTitle.textContent = `Renditions of Raga ${selected.name}`;
    pieceResultsSubtitle.textContent = byArtist.trim();
  } else {
    pieceResultsTitle.textContent = `Composed by ${selected.name}`;
    pieceResultsSubtitle.textContent = byArtist.trim();
  }
}

// load renditions for the selected piece/raga/composer, optionally limited to one artist
async function runSearch() {
  const selected = searchState.selected;
  const artist = searchState.artist;
  if (!selected) return;
  const seq = ++searchSeq;
  const type = currentFilterType();

  pieceResultsSection.style.display = 'block';
  setResultsHeading(selected, artist);
  renditionList.innerHTML = '';
  pieceEmpty.style.display = 'none';
  pieceLoading.style.display = 'block';
  pieceResultsCount.textContent = '';

  const showEmpty = (msg) => {
    pieceLoading.style.display = 'none';
    pieceEmpty.textContent = msg;
    pieceEmpty.style.display = 'block';
  };

  try {
    await loadLookups();

    // resolve the pieces covered by the selected filter value
    let pieces;
    if (type === 'name') pieces = [selected];
    else if (type === 'raga') pieces = await apiListAll('pieces', { raga_id: selected.id });
    else pieces = await apiListAll('pieces', { composer_id: selected.id });
    if (seq !== searchSeq) return;
    if (!pieces.length) return showEmpty('No renditions found.');
    const pieceById = new Map(pieces.map(p => [p.id, p]));

    // optional artist filter: restrict to concerts the artist performed in
    const filters = { piece_id: pieces.map(p => p.id) };
    if (artist) {
      const lineup = await apiListAll('concert-artists', { artist_id: artist.id });
      if (seq !== searchSeq) return;
      const artistConcertIds = dedupeIds(lineup.map(ca => ca.concert_id));
      if (!artistConcertIds.length) return showEmpty('No renditions found.');
      filters.concert_id = artistConcertIds;
    }

    const renditions = await apiListAll('setlist-items', filters);
    if (seq !== searchSeq) return;
    if (!renditions.length) return showEmpty('No renditions found.');

    const concertIds = dedupeIds(renditions.map(item => item.concert_id));
    const [concerts, concertItems, artistCache] = await Promise.all([
      apiGet('concerts', concertIds),
      apiListAll('setlist-items', { concert_id: concertIds }),
      fetchArtistsByConcert(renditions),
    ]);
    if (seq !== searchSeq) return;
    pieceLoading.style.display = 'none';

    const concertById = new Map(concerts.map(c => [c.id, c]));
    concerts.forEach(c => cacheConcertMeta({ ...c, url: youtubeUrl(c.youtube_id) }));

    const itemsByConcert = new Map();
    concertItems.forEach(item => {
      if (!itemsByConcert.has(item.concert_id)) itemsByConcert.set(item.concert_id, []);
      itemsByConcert.get(item.concert_id).push(item);
    });
    itemsByConcert.forEach(list => {
      list.sort((a, b) => a.sequence_number - b.sequence_number || a.id - b.id);
    });

    // raga/composer searches span many pieces, so each card names its piece
    const multiPiece = type !== 'name';
    const cards = renditions.map(item => {
      const concert = concertById.get(item.concert_id);
      const piece = pieceById.get(item.piece_id);
      return {
        concert_id: item.concert_id,
        concert_title: concert?.title,
        concert_year: concert?.year,
        concert_venue: concert?.venue,
        track_url: concert ? youtubeUrl(concert.youtube_id, item.timestamp_seconds) : null,
        duration_seconds: renditionDuration(item, itemsByConcert.get(item.concert_id), concert),
        piece_name: multiPiece && piece ? piece.name : null,
        piece_meta: multiPiece && piece ? formatPieceMeta(pieceMeta(piece)) : null,
      };
    });

    cards.sort((a, b) => (a.concert_year ?? 9999) - (b.concert_year ?? 9999));
    pieceResultsCount.textContent = `${cards.length} rendition${cards.length !== 1 ? 's' : ''}`;
    cards.forEach(r => renditionList.appendChild(buildRenditionCard(r, artistCache[r.concert_id] || [])));
  } catch {
    if (seq !== searchSeq) return;
    showEmpty('Error loading renditions. Is the server running?');
  }
}

// single rendition card with youtube link
function buildRenditionCard(r, artists = []) {
  const li = document.createElement('li');
  li.className = 'rendition-card';

  const meta = document.createElement('div');
  meta.className = 'rendition-meta';

  if (r.piece_name) {
    const pieceLine = document.createElement('div');
    pieceLine.className = 'rendition-piece';
    pieceLine.textContent = r.piece_meta ? `${r.piece_name} · ${r.piece_meta}` : r.piece_name;
    meta.appendChild(pieceLine);
  }

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
  link.href = r.track_url || '#';
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
