// concert detail page dom refs
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

// use cache when duration is already known, otherwise fetch the concert row
async function getConcertMeta(concertId) {
  const cached = concertMetaCache[concertId];
  if (cached && Object.prototype.hasOwnProperty.call(cached, 'duration_seconds')) {
    return cached;
  }

  try {
    const rows = await apiGet('concerts', [concertId]);
    if (!rows.length) return cached || {};
    cacheConcertMeta({ ...rows[0], url: youtubeUrl(rows[0].youtube_id) });
    return concertMetaCache[concertId];
  } catch {
    return cached || {};
  }
}

// swap search view for concert detail
async function showConcert(concertId) {
  searchView.style.display = 'none';
  concertView.style.display = 'block';
  concertDetail.style.display = 'none';
  setlistEmpty.textContent = 'No setlist available.';
  setlistEmpty.style.display = 'none';
  concertDetailLoading.style.display = 'block';
  setlistEl.innerHTML = '';
  window.scrollTo(0, 0);

  try {
    const id = Number(concertId);
    const [setlist, artistCache, concertMeta] = await Promise.all([
      apiListAll('setlist-items', { concert_id: id }, { order_by: 'sequence_number' }),
      fetchArtistsByConcert([{ concert_id: id }]),
      getConcertMeta(id),
      loadLookups(),
    ]);
    const pieceRows = await apiGet('pieces', setlist.map(item => item.piece_id));
    const pieceById = new Map(pieceRows.map(piece => [piece.id, piece]));
    const artists = artistCache[id] || [];

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

    const header = document.createElement('li');
    header.className = 'setlist-header';
    header.innerHTML = `<span></span><span>Piece</span><span>Duration</span>`;
    setlistEl.appendChild(header);

    // duration is gap until next timestamp
    setlist.forEach((item, idx) => {
      const piece = item.piece_id != null ? pieceById.get(item.piece_id) : null;
      const meta = pieceMeta(piece);
      const view = {
        name: piece ? piece.name : null,
        raga: meta.raga,
        talam: meta.talam,
        composer: meta.composer,
        timestamp_seconds: item.timestamp_seconds,
      };
      const nextTs = setlist[idx + 1]?.timestamp_seconds
        ?? concertMeta.duration_seconds
        ?? null;
      setlistEl.appendChild(buildSetlistRow(view, idx + 1, concertMeta, nextTs));
    });
  } catch {
    concertDetailLoading.style.display = 'none';
    setlistEmpty.textContent = 'Error loading concert.';
    setlistEmpty.style.display = 'block';
    concertDetail.style.display = 'block';
  }
}

// one setlist row with piece link and duration
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
