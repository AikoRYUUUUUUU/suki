const HERO_ROTATE_MS = 7000;
const HERO_FADE_MS = 350;

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function renderGrid(mangas) {
  document.getElementById("grid-covers").innerHTML = mangas.map(mangaCardHTML).join("");
}

function renderHeroManga(manga) {
  document.getElementById("hero-manga-title").textContent = manga.title;
  document.getElementById("hero-synopsis").textContent = manga.synopsis;
  document.getElementById("hero-tags").innerHTML = (manga.genres || [])
    .map(g => `<span class="pill">${g}</span>`).join("");
  document.getElementById("hero-cover-img").src = manga.cover;
  document.getElementById("hero-cover-img").alt = `Capa de ${manga.title}`;
  document.getElementById("hero-cover-btn").href = `manga.html?id=${manga.id}`;

  const firstChapter = [...manga.chapters].sort((a, b) => a.number - b.number)[0];
  const heroReadBtn = document.getElementById("hero-read-btn");
  if (firstChapter) {
    heroReadBtn.href = `reader.html?id=${manga.id}&ch=${firstChapter.id}`;
    heroReadBtn.style.display = "";
  } else {
    heroReadBtn.style.display = "none";
  }
}

function startHeroRotation(mangas) {
  const order = shuffle(mangas);
  let i = 0;
  renderHeroManga(order[i]);
  if (order.length <= 1) return;

  const heroManga = document.getElementById("hero-manga");
  const heroCover = document.getElementById("hero-cover");

  setInterval(() => {
    heroManga.classList.add("is-fading");
    heroCover.classList.add("is-fading");
    setTimeout(() => {
      i = (i + 1) % order.length;
      renderHeroManga(order[i]);
      heroManga.classList.remove("is-fading");
      heroCover.classList.remove("is-fading");
    }, HERO_FADE_MS);
  }, HERO_ROTATE_MS);
}

async function renderHome() {
  const mangas = await getAllMangas();
  if (!mangas.length) return;

  renderGrid(mangas);
  startHeroRotation(mangas);
}

renderHome();
