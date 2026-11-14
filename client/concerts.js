// concerts tab dom refs and autocomplete
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
  fetchItems: (q) => apiAutocomplete('artists', q),
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

// year ascending, nulls last, then id
function compareConcertYear(a, b) {
  if (a.year == null && b.year == null) return a.id - b.id;
  if (a.year == null) return 1;
  if (b.year == null) return -1;
  if (a.year !== b.year) return a.year - b.year;
  return a.id - b.id;
}

// concerts where this artist is a main artist
async function loadConcerts(artist) {
  concertResultsSection.style.display = 'block';
  concertResultsTitle.textContent = artist.name;
  concertResultsSubtitle.textContent = 'Concerts as main artist';
  concertGrid.innerHTML = '';
  concertEmpty.style.display = 'none';
  concertLoading.style.display = 'block';
  concertResultsCount.textContent = '';

  try {
    const links = await apiListAll('concert-artists', {
      artist_id: artist.id,
      role: 'main artist',
    });
    const ids = dedupeIds(links.map(link => link.concert_id));
    const data = await apiGet('concerts', ids);
    data.sort(compareConcertYear);
    concertLoading.style.display = 'none';

    if (!data.length) {
      concertEmpty.textContent = 'No concerts found for this artist.';
      concertEmpty.style.display = 'block';
      return;
    }

    concertResultsCount.textContent = `${data.length} concert${data.length !== 1 ? 's' : ''}`;
    data.forEach(c => {
      cacheConcertMeta({ ...c, url: youtubeUrl(c.youtube_id) });
      concertGrid.appendChild(buildConcertTile(c));
    });
  } catch {
    concertLoading.style.display = 'none';
    concertEmpty.textContent = 'Error loading concerts. Is the server running?';
    concertEmpty.style.display = 'block';
  }
}

// link tile to concert detail hash route
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
