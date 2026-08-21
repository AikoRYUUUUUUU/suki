/**
 * Favoritos - 100% local (localStorage), sem conta de usuário.
 */
const FAVORITES_KEY = "suki-favorites";

function getFavorites() {
  try {
    return JSON.parse(localStorage.getItem(FAVORITES_KEY) || "{}");
  } catch (e) {
    return {};
  }
}

function isFavorite(mangaId) {
  return !!getFavorites()[mangaId];
}

function toggleFavorite(manga) {
  const favorites = getFavorites();
  if (favorites[manga.id]) {
    delete favorites[manga.id];
  } else {
    favorites[manga.id] = { title: manga.title, cover: manga.cover, addedAt: Date.now() };
  }
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(favorites));
  return !!favorites[manga.id];
}

function getFavoritesList() {
  const favorites = getFavorites();
  return Object.entries(favorites)
    .map(([id, entry]) => ({ id, ...entry }))
    .sort((a, b) => b.addedAt - a.addedAt);
}
