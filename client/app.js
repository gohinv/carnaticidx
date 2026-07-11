// toggle visible tab panel on nav click
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.tab;
    document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.tab-panel').forEach(p => {
      p.classList.toggle('active', p.dataset.panel === target);
    });
  });
});

// show concert detail or search from hash
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
