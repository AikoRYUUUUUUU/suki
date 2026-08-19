let state = {
  manga: null,
  chapter: null,
  pages: [],
  current: 0,           // índice da página atual (modo paginado)
  mode: "vertical",      // "vertical" | "paginated"
};

async function initReader() {
  const mangaId = qs("id");
  const chapterId = qs("ch");
  const { manga, chapter } = await getChapter(mangaId, chapterId);

  if (!manga || !chapter) {
    document.getElementById("reader-stage").innerHTML =
      "<p style='padding:40px;'>Capítulo não encontrado. <a href='index.html'>Voltar</a>.</p>";
    return;
  }

  state.manga = manga;
  state.chapter = chapter;
  state.pages = chapter.pages;
  state.current = 0;

  document.getElementById("page-title").textContent = `${manga.title} — Cap. ${chapter.number} — Sumi`;
  document.getElementById("rt-manga").textContent = manga.title;
  document.getElementById("rt-chapter").textContent = `Cap. ${chapter.number} — ${chapter.title}`;

  renderPages();
  updateCounter();
  bindControls();
  bindKeyboard();
}

function renderPages() {
  const stage = document.getElementById("reader-stage");
  const tapzones = document.getElementById("tapzones");

  if (state.mode === "vertical") {
    tapzones.style.display = "none";
    stage.classList.remove("paginated");
    stage.innerHTML = state.pages
      .map((src, i) => `<img data-page="${i}" src="${src}" alt="Página ${i + 1}" loading="lazy">`)
      .join("");
    observeScroll();
  } else {
    tapzones.style.display = "grid";
    stage.classList.add("paginated");
    stage.innerHTML = `<img src="${state.pages[state.current]}" alt="Página ${state.current + 1}">`;
  }
}

function updateCounter() {
  document.getElementById("page-counter").textContent =
    `${state.current + 1}/${state.pages.length}`;
}

// --- modo paginado: avançar/voltar página, com transição de capítulo nas pontas ---
function goToPage(delta) {
  const next = state.current + delta;
  if (next < 0) return goAdjacentChapter(-1, true);
  if (next >= state.pages.length) return goAdjacentChapter(1, false);
  state.current = next;
  renderPages();
  updateCounter();
}

function goAdjacentChapter(direction, landOnLastPage) {
  const { prev, next } = getAdjacentChapters(state.manga, state.chapter.id);
  const target = direction < 0 ? prev : next;
  if (!target) return; // já é o primeiro/último capítulo
  const url = new URL(window.location.href);
  url.searchParams.set("ch", target.id);
  if (landOnLastPage) url.searchParams.set("p", "last");
  window.location.href = url.toString();
}

// --- scroll contínuo: observa qual página está visível para atualizar contador ---
function observeScroll() {
  const imgs = document.querySelectorAll('#reader-stage img[data-page]');
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        state.current = Number(e.target.dataset.page);
        updateCounter();
      }
    });
  }, { threshold: 0.55 });
  imgs.forEach(img => io.observe(img));
}

function bindControls() {
  document.getElementById("mode-toggle").addEventListener("click", () => {
    state.mode = state.mode === "vertical" ? "paginated" : "vertical";
    renderPages();
    updateCounter();
  });

  document.getElementById("zone-prev").addEventListener("click", () => goToPage(-1));
  document.getElementById("zone-next").addEventListener("click", () => goToPage(1));

  document.getElementById("prev-ch").addEventListener("click", () => goAdjacentChapter(-1, false));
  document.getElementById("next-ch").addEventListener("click", () => goAdjacentChapter(1, false));
}

function bindKeyboard() {
  window.addEventListener("keydown", (e) => {
    if (state.mode !== "paginated") return;
    if (e.key === "ArrowRight") goToPage(1);
    if (e.key === "ArrowLeft") goToPage(-1);
  });
}

// se chegamos vindos de "voltar capítulo", abre já na última página
window.addEventListener("DOMContentLoaded", async () => {
  await initReader();
  if (qs("p") === "last" && state.pages.length) {
    state.mode = "paginated";
    state.current = state.pages.length - 1;
    renderPages();
    updateCounter();
  }
});
