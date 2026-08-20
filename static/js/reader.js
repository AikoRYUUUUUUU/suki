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

  if (isAdultManga(manga) && sessionStorage.getItem("age_confirmed") !== "1") {
    showAgeGate(manga, () => startReader(manga, chapter));
    return;
  }

  startReader(manga, chapter);
}

function showAgeGate(manga, onConfirm) {
  const overlay = document.createElement("div");
  overlay.className = "age-gate-overlay";
  overlay.innerHTML = `
    <div class="age-gate-box">
      <p class="age-gate-warning">⚠ Conteúdo +18</p>
      <p class="age-gate-text">"${manga.title}" contém material para maiores de 18 anos. Confirme que você tem 18 anos ou mais para continuar.</p>
      <div class="age-gate-actions">
        <button type="button" class="btn btn-primary" id="age-gate-confirm">Sim, tenho 18 anos ou mais</button>
        <button type="button" class="btn btn-ghost" id="age-gate-leave">Sair</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  document.getElementById("age-gate-confirm").addEventListener("click", () => {
    sessionStorage.setItem("age_confirmed", "1");
    overlay.remove();
    onConfirm();
  });
  document.getElementById("age-gate-leave").addEventListener("click", () => {
    window.location.href = `manga.html?id=${manga.id}`;
  });
}

function startReader(manga, chapter) {
  state.manga = manga;
  state.chapter = chapter;
  state.pages = chapter.pages;
  state.current = 0;

  document.getElementById("page-title").textContent = `${manga.title} — Cap. ${chapter.number} — Suki`;
  document.getElementById("rt-manga").textContent = manga.title;
  document.getElementById("rt-chapter").textContent = `Cap. ${chapter.number} — ${chapter.title}`;

  renderPages();
  updateCounter();
  populateChapterSelects();
  updateChapterNavState();
  bindControls();
  bindKeyboard();

  // se chegamos vindos de "voltar capítulo", abre já na última página
  if (qs("p") === "last" && state.pages.length) {
    state.mode = "paginated";
    state.current = state.pages.length - 1;
    renderPages();
    updateCounter();
  }
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
  goToChapterId(target.id, landOnLastPage);
}

function goToChapterId(chapterId, landOnLastPage) {
  if (!chapterId || chapterId === state.chapter.id) return;
  const url = new URL(window.location.href);
  url.searchParams.set("ch", chapterId);
  if (landOnLastPage) url.searchParams.set("p", "last");
  else url.searchParams.delete("p");
  window.location.href = url.toString();
}

// --- seletor de capítulos (topo + rodapé) ---
function populateChapterSelects() {
  const sorted = [...state.manga.chapters].sort((a, b) => a.number - b.number);
  const optionsHTML = sorted
    .map(c => `<option value="${c.id}"${c.id === state.chapter.id ? " selected" : ""}>Cap. ${c.number} — ${c.title}</option>`)
    .join("");
  document.querySelectorAll(".chapter-select").forEach(sel => {
    sel.innerHTML = optionsHTML;
  });
}

function updateChapterNavState() {
  const { prev, next } = getAdjacentChapters(state.manga, state.chapter.id);
  document.querySelectorAll(".chapter-prev-btn").forEach(btn => { btn.disabled = !prev; });
  document.querySelectorAll(".chapter-next-btn").forEach(btn => { btn.disabled = !next; });
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

  document.querySelectorAll(".chapter-prev-btn").forEach(btn =>
    btn.addEventListener("click", () => goAdjacentChapter(-1, false)));
  document.querySelectorAll(".chapter-next-btn").forEach(btn =>
    btn.addEventListener("click", () => goAdjacentChapter(1, false)));
  document.querySelectorAll(".chapter-select").forEach(sel =>
    sel.addEventListener("change", (e) => goToChapterId(e.target.value, false)));
}

function bindKeyboard() {
  window.addEventListener("keydown", (e) => {
    if (state.mode !== "paginated") return;
    if (e.key === "ArrowRight") goToPage(1);
    if (e.key === "ArrowLeft") goToPage(-1);
  });
}

window.addEventListener("DOMContentLoaded", () => {
  initReader();
});
