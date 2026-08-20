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
  const startBtn = document.getElementById("start-reading");
  if (sorted.length > 0) {
    startBtn.href = `reader.html?id=${manga.id}&ch=${sorted[0].id}`;
  } else {
    startBtn.removeAttribute("href");
    startBtn.classList.add("btn-disabled");
    startBtn.textContent = "Nenhum capítulo ainda";
  }

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

// Cusdis renderiza o widget num iframe srcdoc (mesma origem da página, não um
// domínio externo) - por isso dá pra ler/escrever o documento de dentro dele
// sem esbarrar em bloqueio de cross-origin. Usamos isso pra (1) redimensionar
// o iframe pro tamanho real do conteúdo, já que ele nasce fixo em 150px de
// altura (o padrão do navegador pra iframe sem altura definida) e nada no
// widget deles ajusta isso sozinho, e (2) sobrescrever as classes Tailwind do
// widget pra combinar com a paleta do site, com !important porque as classes
// deles (ex. bg-transparent) têm a mesma especificidade que um seletor de
// elemento puro e venceriam sem isso.
const CUSDIS_THEME_CSS = `
  html, body {
    background: transparent !important;
    color: #EEE6D3 !important;
    font-family: 'Zen Kaku Gothic New', 'Inter', sans-serif !important;
  }
  label { color: #C9C0AA !important; }
  input, textarea {
    background: #17151F !important;
    border: 1px solid rgba(238, 230, 211, .18) !important;
    color: #EEE6D3 !important;
    border-radius: 2px !important;
  }
  input::placeholder, textarea::placeholder { color: #8A8578 !important; }
  button {
    background: #B7472A !important;
    color: #EEE6D3 !important;
    border: none !important;
    border-radius: 2px !important;
  }
  button:hover { background: #a03d24 !important; }
  a { color: #C99A3E !important; }

  /* cada comentário (nickname + data + texto + responder) numa box própria -
     .my-4 é a classe Tailwind que envolve cada item; o :has() restringe pra
     só os que têm a linha de nickname dentro, pra não pegar outros divs
     genéricos que por acaso também usem essa classe de espaçamento */
  .my-4:has(> .flex.items-center) {
    background: #221F2C !important;
    border: 1px solid rgba(238, 230, 211, .12) !important;
    border-radius: 2px !important;
    padding: 14px 16px !important;
    margin: 0 0 12px !important;
  }
  div.mr-2.font-medium { color: #C99A3E !important; }
  div.text-gray-500.text-sm { color: #8A8578 !important; }
`;

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

  function applyThemeAndResize(iframe) {
    let doc;
    try {
      doc = iframe.contentDocument;
    } catch (e) {
      return false;
    }
    if (!doc || !doc.body) return false;

    if (!doc.getElementById("suki-cusdis-theme")) {
      const style = doc.createElement("style");
      style.id = "suki-cusdis-theme";
      style.textContent = CUSDIS_THEME_CSS;
      doc.head.appendChild(style);
    }

    const resize = () => { iframe.style.height = doc.documentElement.scrollHeight + "px"; };
    resize();

    if (!iframe.dataset.sukiObserved) {
      iframe.dataset.sukiObserved = "1";
      new MutationObserver(resize).observe(doc.body, { childList: true, subtree: true, characterData: true });
      new ResizeObserver(resize).observe(doc.body);
    }
    return true;
  }

  // O iframe do Cusdis é criado de forma assíncrona pelo script deles -
  // tenta por alguns segundos até ele existir e ter conteúdo.
  let attempts = 0;
  const timer = setInterval(() => {
    attempts++;
    const iframe = thread.querySelector("iframe");
    if (iframe && applyThemeAndResize(iframe)) {
      clearInterval(timer);
    } else if (attempts > 40) {
      clearInterval(timer);
    }
  }, 250);
}

function formatDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

renderMangaPage();
