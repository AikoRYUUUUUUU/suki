/**
 * Camada de dados. Lê o catálogo via API do backend Flask (banco SQLite).
 */
const DB_URL = "/api/mangas";

async function loadDB() {
  const res = await fetch(DB_URL);
  if (!res.ok) throw new Error("Não foi possível carregar o banco de dados.");
  return res.json();
}

async function getAllMangas() {
  const db = await loadDB();
  return db.mangas;
}

async function getManga(id) {
  const db = await loadDB();
  return db.mangas.find(m => m.id === id) || null;
}

async function getChapter(mangaId, chapterId) {
  const manga = await getManga(mangaId);
  if (!manga) return { manga: null, chapter: null };
  const chapter = manga.chapters.find(c => c.id === chapterId) || null;
  return { manga, chapter };
}

function getAdjacentChapters(manga, chapterId) {
  const sorted = [...manga.chapters].sort((a, b) => a.number - b.number);
  const idx = sorted.findIndex(c => c.id === chapterId);
  return {
    prev: idx > 0 ? sorted[idx - 1] : null,
    next: idx < sorted.length - 1 ? sorted[idx + 1] : null,
  };
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

// dados vêm do banco (admin ou autofill do AniList) e acabam indo pra innerHTML
// em vários lugares - escapa antes de interpolar pra evitar XSS armazenado.
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

const ADULT_TAGS = new Set(["Adulto (18+)", "Smut", "Mature"]);

function isAdultManga(m) {
  return (m.genres || []).some(g => ADULT_TAGS.has(g));
}

function getLatestChapter(manga) {
  if (!manga.chapters.length) return null;
  return [...manga.chapters].sort((a, b) => b.number - a.number)[0];
}

function daysSinceRelease(iso) {
  const released = new Date(iso + "T00:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.floor((today - released) / 86400000);
}

function formatDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

function getRecentUpdates(mangas, limit) {
  // um card por obra - o capítulo mais recente dela, não um card por capítulo
  const updates = mangas
    .map(m => ({ manga: m, chapter: getLatestChapter(m) }))
    .filter(u => u.chapter);

  updates.sort((a, b) => {
    const byDate = (b.chapter.releaseDate || "").localeCompare(a.chapter.releaseDate || "");
    return byDate !== 0 ? byDate : b.chapter.number - a.chapter.number;
  });
  return updates.slice(0, limit || 12);
}

function getRelatedMangas(mangas, manga, limit) {
  const genres = new Set(manga.genres || []);
  return mangas
    .map(m => ({ m, overlap: (m.genres || []).filter(g => genres.has(g)).length }))
    .filter(x => x.m.id !== manga.id && x.overlap > 0)
    .sort((a, b) => b.overlap - a.overlap || (b.m.rating || 0) - (a.m.rating || 0))
    .slice(0, limit || 6)
    .map(x => x.m);
}

function mangaCardHTML(m) {
  const latest = getLatestChapter(m);
  const isNew = latest && daysSinceRelease(latest.releaseDate) <= 3;
  return `
    <a class="card-manga" href="manga.html?id=${m.id}">
      <div class="cover-frame">
        <img src="${m.cover}" alt="Capa de ${escapeHtml(m.title)}" loading="lazy">
        <div class="cover-badges">
          <span class="badge-status">${escapeHtml(m.status)}</span>
          ${isAdultManga(m) ? '<span class="badge-adult">+18</span>' : ""}
        </div>
      </div>
      <h3>${escapeHtml(m.title)}</h3>
      ${latest ? `
        <p class="latest-chapter">Cap. ${latest.number}${isNew ? ' <span class="badge-new">NOVO</span>' : ""}</p>
      ` : ""}
      <p class="meta">${m.chapters.length} capítulos · ★ ${m.rating}</p>
    </a>
  `;
}
