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

function continueCardHTML(entry) {
  return `
    <a class="card-manga" href="reader.html?id=${entry.id}&ch=${entry.lastChapterId}">
      <div class="cover-frame">
        <img src="${entry.cover}" alt="Capa de ${entry.title}" loading="lazy">
      </div>
      <h3>${entry.title}</h3>
      <p class="meta">Continuar — Cap. ${entry.lastChapterNumber}</p>
    </a>
  `;
}

function renderContinueReading(mangas) {
  const mangaIds = new Set(mangas.map(m => m.id));
  const entries = getRecentHistory(12).filter(e => mangaIds.has(e.id));
  if (!entries.length) return;

  document.getElementById("grid-continue").innerHTML = entries.map(e => continueCardHTML(e)).join("");
  document.getElementById("continuar").style.display = "";
  document.getElementById("lancamentos").classList.add("tight-top");
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
  renderContinueReading(mangas);
  startHeroRotation(mangas);
}

renderHome();
