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
