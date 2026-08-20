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
  document.getElementById("stat-rating").textContent = manga.rating != null ? `★ ${manga.rating}` : "–";
  document.getElementById("stat-year").textContent = manga.year;
  document.getElementById("stat-status").textContent = manga.status;

  setupRateWidget(manga);
  mountComments(manga);

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

function setupRateWidget(manga) {
  const widget = document.getElementById("rate-widget");
  const stars = Array.from(document.querySelectorAll(".rate-star"));
  const msg = document.getElementById("rate-widget-msg");
  const votedKey = `suki-voted-${manga.id}`;

  function paintStars(filled) {
    stars.forEach(s => s.classList.toggle("filled", Number(s.dataset.value) <= filled));
  }

  function lockWidget(text) {
    stars.forEach(s => { s.disabled = true; });
    msg.textContent = text;
  }

  paintStars(Math.round(manga.rating || 0));

  if (localStorage.getItem(votedKey)) {
    lockWidget("Você já avaliou este mangá.");
    return;
  }

  stars.forEach(star => {
    star.addEventListener("mouseenter", () => paintStars(Number(star.dataset.value)));
    star.addEventListener("mouseleave", () => paintStars(Math.round(manga.rating || 0)));
    star.addEventListener("click", async () => {
      const value = Number(star.dataset.value);
      try {
        const res = await fetch(`/api/mangas/${manga.id}/rate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value }),
        });
        if (res.status === 409) {
          localStorage.setItem(votedKey, "1");
          lockWidget("Você já avaliou este mangá.");
          return;
        }
        if (!res.ok) throw new Error();
        const data = await res.json();
        manga.rating = data.rating;
        document.getElementById("stat-rating").textContent = `★ ${data.rating}`;
        paintStars(value);
        localStorage.setItem(votedKey, "1");
        lockWidget("Obrigado por avaliar!");
      } catch (e) {
        msg.textContent = "Não foi possível registrar seu voto. Tente de novo.";
      }
    });
  });
}

function mountComments(manga) {
  const mount = document.getElementById("comments-mount");
  if (!mount) return;
  const appId = mount.dataset.cusdisAppId;
  if (!appId) return;

  const thread = document.createElement("div");
  thread.id = "cusdis_thread";
  thread.dataset.host = "https://cusdis.com";
  thread.dataset.appId = appId;
  thread.dataset.pageId = manga.id;
  thread.dataset.pageUrl = window.location.href;
  thread.dataset.pageTitle = manga.title;
  mount.appendChild(thread);

  const script = document.createElement("script");
  script.src = "https://cusdis.com/js/cusdis.es.js";
  script.async = true;
  script.defer = true;
  mount.appendChild(script);
}

function formatDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

renderMangaPage();
