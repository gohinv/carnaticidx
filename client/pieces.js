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

// load all concerts where piece was performed
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
