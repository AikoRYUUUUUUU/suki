/**
 * Histórico de leitura - 100% local (localStorage), sem conta de usuário.
 * Guarda, por mangá: capítulos já abertos e o último capítulo lido.
 */
const HISTORY_KEY = "suki-history";

function getHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "{}");
  } catch (e) {
    return {};
  }
}

function saveHistory(history) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
}

function recordChapterRead(manga, chapter) {
  const history = getHistory();
  const entry = history[manga.id] || { readChapterIds: [] };
  entry.title = manga.title;
  entry.cover = manga.cover;
  entry.lastChapterId = chapter.id;
  entry.lastChapterNumber = chapter.number;
  entry.updatedAt = Date.now();
  if (!entry.readChapterIds.includes(chapter.id)) entry.readChapterIds.push(chapter.id);
  history[manga.id] = entry;
  saveHistory(history);
}

function getMangaHistory(mangaId) {
  return getHistory()[mangaId] || null;
}

function isChapterRead(mangaId, chapterId) {
  const entry = getHistory()[mangaId];
  return !!(entry && entry.readChapterIds.includes(chapterId));
}

function getRecentHistory(limit) {
  const history = getHistory();
  return Object.entries(history)
    .map(([id, entry]) => ({ id, ...entry }))
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, limit || 12);
}
