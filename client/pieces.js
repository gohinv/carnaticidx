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

createAutocomplete({
  input: pieceInput,
  list: pieceAcList,
  fetchItems: async (q) => {
    await loadLookups();
    return apiAutocomplete('pieces', q);
  },
  renderItem: (li, item) => {
    const name = document.createElement('div');
    name.className = 'ac-name';
    name.textContent = item.name;
    const meta = document.createElement('div');
    meta.className = 'ac-meta';
    meta.textContent = formatPieceMeta(pieceMeta(item));
    li.appendChild(name);
    li.appendChild(meta);
  },
  onSelect: (piece) => {
    pieceInput.value = piece.name;
    loadSetlist(piece);
  },
});

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

// load all concerts where piece was performed
async function loadSetlist(piece) {
  pieceResultsSection.style.display = 'block';
  pieceResultsTitle.textContent = piece.name;
  pieceResultsSubtitle.textContent = formatPieceMeta(pieceMeta(piece));
  renditionList.innerHTML = '';
  pieceEmpty.style.display = 'none';
  pieceLoading.style.display = 'block';
  pieceResultsCount.textContent = '';

  try {
    await loadLookups();
    pieceResultsSubtitle.textContent = formatPieceMeta(pieceMeta(piece));

    const renditions = await apiListAll('setlist-items', { piece_id: piece.id });
    if (!renditions.length) {
      pieceLoading.style.display = 'none';
      pieceEmpty.textContent = 'No renditions found for this piece.';
      pieceEmpty.style.display = 'block';
      return;
    }

    const concertIds = dedupeIds(renditions.map(item => item.concert_id));
    const [concerts, concertItems, artistCache] = await Promise.all([
      apiGet('concerts', concertIds),
      apiListAll('setlist-items', { concert_id: concertIds }),
      fetchArtistsByConcert(renditions),
    ]);
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

    const cards = renditions.map(item => {
      const concert = concertById.get(item.concert_id);
      return {
        concert_id: item.concert_id,
        concert_title: concert?.title,
        concert_year: concert?.year,
        concert_venue: concert?.venue,
        track_url: concert ? youtubeUrl(concert.youtube_id, item.timestamp_seconds) : null,
        duration_seconds: renditionDuration(item, itemsByConcert.get(item.concert_id), concert),
      };
    });

    cards.sort((a, b) => (a.concert_year ?? 9999) - (b.concert_year ?? 9999));
    pieceResultsCount.textContent = `${cards.length} rendition${cards.length !== 1 ? 's' : ''}`;
    cards.forEach(r => renditionList.appendChild(buildRenditionCard(r, artistCache[r.concert_id] || [])));
  } catch {
    pieceLoading.style.display = 'none';
    pieceEmpty.textContent = 'Error loading renditions. Is the server running?';
    pieceEmpty.style.display = 'block';
  }
}

// single rendition card with youtube link
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
