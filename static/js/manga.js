async function renderMangaPage() {
  const id = qs("id");
  const manga = await getManga(id);

  if (!manga) {
    document.querySelector(".manga-hero .wrap").innerHTML =
      "<p>Mangá não encontrado. <a href='index.html'>Voltar à biblioteca</a>.</p>";
    return;
  }

  document.getElementById("page-title").textContent = `${manga.title} — Suki`;
  document.getElementById("cover-img").src = manga.cover;
  document.getElementById("cover-img").alt = `Capa de ${manga.title}`;
  document.getElementById("title-jp").textContent = manga.titleOriginal;
  document.getElementById("title-pt").textContent = manga.title;
  document.getElementById("synopsis").textContent = manga.synopsis;

  document.getElementById("genres-row").innerHTML = [
    `<span class="pill accent">${manga.status}</span>`,
    ...manga.genres.map(g => `<span class="pill">${g}</span>`)
  ].join("");

  document.getElementById("stat-chapters").textContent = manga.chapters.length;
  document.getElementById("stat-rating").textContent = `★ ${manga.rating}`;
  document.getElementById("stat-year").textContent = manga.year;
  document.getElementById("stat-status").textContent = manga.status;

  const sorted = [...manga.chapters].sort((a, b) => a.number - b.number);
  const firstChapter = sorted[0];
  const startBtn = document.getElementById("start-reading");
  startBtn.href = `reader.html?id=${manga.id}&ch=${firstChapter.id}`;

  document.getElementById("chapter-list").innerHTML = sorted
    .slice()
    .reverse()
    .map(c => `
      <a class="chapter-row" href="reader.html?id=${manga.id}&ch=${c.id}">
        <div class="left">
          <span class="chapter-num">${String(c.number).padStart(2, "0")}</span>
          <span class="ch-title">${c.title}</span>
        </div>
        <span class="ch-date">${formatDate(c.releaseDate)}</span>
      </a>
    `).join("");
}

function formatDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

renderMangaPage();
