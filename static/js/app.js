function normalize(text) {
  return (text || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

function matchesSearch(manga, query, status) {
  if (status && manga.status !== status) return false;
  if (!query) return true;
  const haystack = normalize([
    manga.title,
    manga.titleOriginal,
    manga.author,
    manga.group,
    ...(manga.genres || []),
  ].join(" "));
  return haystack.includes(normalize(query));
}

function renderGrid(mangas) {
  const grid = document.getElementById("grid-covers");
  const empty = document.getElementById("search-empty");
  grid.innerHTML = mangas.map(m => `
    <a class="card-manga" href="manga.html?id=${m.id}">
      <div class="cover-frame">
        <img src="${m.cover}" alt="Capa de ${m.title}" loading="lazy">
        <span class="badge-status">${m.status}</span>
      </div>
      <h3>${m.title}</h3>
      <p class="meta">${m.chapters.length} capítulos · ★ ${m.rating}</p>
    </a>
  `).join("");
  empty.hidden = mangas.length > 0;
}

async function renderHome() {
  const mangas = await getAllMangas();
  if (!mangas.length) return;

  // hero = primeiro mangá do catálogo
  const featured = mangas[0];
  document.getElementById("hero-synopsis").textContent = featured.synopsis;
  document.getElementById("hero-cover-img").src = featured.cover;
  document.getElementById("hero-cover-img").alt = `Capa de ${featured.title}`;
  document.getElementById("hero-cover-btn").href = `manga.html?id=${featured.id}`;

  const firstChapter = [...featured.chapters].sort((a, b) => a.number - b.number)[0];
  const heroReadBtn = document.getElementById("hero-read-btn");
  if (firstChapter) {
    heroReadBtn.href = `reader.html?id=${featured.id}&ch=${firstChapter.id}`;
  } else {
    heroReadBtn.style.display = "none";
  }

  renderGrid(mangas);

  const searchInput = document.getElementById("search-input");
  const searchStatus = document.getElementById("search-status");
  const applyFilters = () => {
    const filtered = mangas.filter(m =>
      matchesSearch(m, searchInput.value.trim(), searchStatus.value)
    );
    renderGrid(filtered);
  };
  searchInput.addEventListener("input", applyFilters);
  searchStatus.addEventListener("change", applyFilters);
}

renderHome();
