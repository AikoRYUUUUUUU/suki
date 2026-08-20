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

function renderResults(mangas, q, status, tags) {
  const filtered = mangas.filter(m => matchesSearch(m, q, status, tags));
  document.getElementById("grid-covers").innerHTML = filtered.map(mangaCardHTML).join("");
  document.getElementById("search-empty").hidden = filtered.length > 0;
  document.getElementById("search-title").textContent = describeFilters(q, status, tags);
}

async function renderSearchPage() {
  const mangas = await getAllMangas();
  const searchInput = document.getElementById("search-input");
  const searchStatus = document.getElementById("search-status");
  const tagFilter = document.getElementById("tag-filter");

  const applyFilters = () =>
    renderResults(mangas, searchInput.value.trim(), searchStatus.value, selectedTags());

  searchInput.addEventListener("input", applyFilters);
  searchStatus.addEventListener("change", applyFilters);
  tagFilter.addEventListener("change", applyFilters);
  if (selectedTags().length) tagFilter.open = true;
  applyFilters();
}

renderSearchPage();
