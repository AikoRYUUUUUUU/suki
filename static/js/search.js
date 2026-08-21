function normalize(text) {
  return (text || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

function matchesSearch(manga, query, status, tags) {
  if (status && manga.status !== status) return false;
  if (tags.length) {
    const genres = manga.genres || [];
    if (!tags.every(t => genres.includes(t))) return false;
  }
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

function describeFilters(q, status, tags) {
  const parts = [];
  if (q) parts.push(`"${q}"`);
  if (status) parts.push(status);
  if (tags.length) parts.push(tags.join(", "));
  return parts.length ? `Resultados para ${parts.join(" · ")}` : "Todos os títulos";
}

function selectedTags() {
  return Array.from(
    document.querySelectorAll('#tag-filter input[type="checkbox"]:checked')
  ).map(el => el.value);
}

function sortMangas(mangas, sort) {
  const sorted = [...mangas];
  if (sort === "rating") return sorted.sort((a, b) => (b.rating || 0) - (a.rating || 0));
  if (sort === "az") return sorted.sort((a, b) => a.title.localeCompare(b.title, "pt-BR"));
  return sorted.sort((a, b) => {
    const la = getLatestChapter(a);
    const lb = getLatestChapter(b);
    if (!la && !lb) return 0;
    if (!la) return 1;
    if (!lb) return -1;
    return (lb.releaseDate || "").localeCompare(la.releaseDate || "");
  });
}

function renderResults(mangas, q, status, tags, sort) {
  const filtered = sortMangas(mangas.filter(m => matchesSearch(m, q, status, tags)), sort);
  document.getElementById("grid-covers").innerHTML = filtered.map(mangaCardHTML).join("");
  document.getElementById("search-empty").hidden = filtered.length > 0;
  document.getElementById("search-title").textContent = describeFilters(q, status, tags);
}

async function renderSearchPage() {
  const mangas = await getAllMangas();
  const searchInput = document.getElementById("search-input");
  const searchStatus = document.getElementById("search-status");
  const tagFilter = document.getElementById("tag-filter");
  const searchSort = document.getElementById("search-sort");

  const applyFilters = () =>
    renderResults(mangas, searchInput.value.trim(), searchStatus.value, selectedTags(), searchSort.value);

  searchInput.addEventListener("input", applyFilters);
  searchStatus.addEventListener("change", applyFilters);
  tagFilter.addEventListener("change", applyFilters);
  searchSort.addEventListener("change", applyFilters);
  if (selectedTags().length || location.hash === "#tag-filter") tagFilter.open = true;
  applyFilters();
}

renderSearchPage();
