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

function describeFilters(q, status) {
  const parts = [];
  if (q) parts.push(`"${q}"`);
  if (status) parts.push(status);
  return parts.length ? `Resultados para ${parts.join(" · ")}` : "Todos os títulos";
}

function renderResults(mangas, q, status) {
  const filtered = mangas.filter(m => matchesSearch(m, q, status));
  document.getElementById("grid-covers").innerHTML = filtered.map(mangaCardHTML).join("");
  document.getElementById("search-empty").hidden = filtered.length > 0;
  document.getElementById("search-title").textContent = describeFilters(q, status);
}

async function renderSearchPage() {
  const mangas = await getAllMangas();
  const searchInput = document.getElementById("search-input");
  const searchStatus = document.getElementById("search-status");

  const applyFilters = () => renderResults(mangas, searchInput.value.trim(), searchStatus.value);

  searchInput.addEventListener("input", applyFilters);
  searchStatus.addEventListener("change", applyFilters);
  applyFilters();
}

renderSearchPage();
