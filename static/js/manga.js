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
    `<span class="pill accent">${escapeHtml(manga.status)}</span>`,
    ...manga.genres.map(g => `<span class="pill">${escapeHtml(g)}</span>`)
  ].join("");

  document.getElementById("stat-chapters").textContent = manga.chapters.length;
  document.getElementById("stat-rating").textContent = manga.rating != null ? `★ ${manga.rating}` : "–";
  document.getElementById("stat-year").textContent = manga.year;
  document.getElementById("stat-status").textContent = manga.status;

  setupRateWidget(manga);
  setupFavoriteButton(manga);
  initComments(manga.id);
  renderRelated(manga);

  const sorted = [...manga.chapters].sort((a, b) => a.number - b.number);
  const startBtn = document.getElementById("start-reading");
  const history = getMangaHistory(manga.id);
  const lastRead = history && sorted.some(c => c.id === history.lastChapterId)
    ? history : null;

  if (sorted.length > 0) {
    if (lastRead) {
      startBtn.href = `reader.html?id=${manga.id}&ch=${lastRead.lastChapterId}`;
      startBtn.textContent = `Continuar — Cap. ${lastRead.lastChapterNumber}`;
    } else {
      startBtn.href = `reader.html?id=${manga.id}&ch=${sorted[0].id}`;
    }
  } else {
    startBtn.removeAttribute("href");
    startBtn.classList.add("btn-disabled");
    startBtn.textContent = "Nenhum capítulo ainda";
  }

  document.getElementById("chapter-list").innerHTML = sorted
    .slice()
    .reverse()
    .map(c => `
      <a class="chapter-row${isChapterRead(manga.id, c.id) ? " is-read" : ""}" href="reader.html?id=${manga.id}&ch=${c.id}">
        <div class="left">
          <span class="chapter-num">${String(c.number).padStart(2, "0")}</span>
          <span class="ch-title">${escapeHtml(c.title)}</span>
        </div>
        <span class="ch-date">${formatDate(c.releaseDate)}</span>
      </a>
    `).join("");
}

function setupFavoriteButton(manga) {
  const btn = document.getElementById("favorite-btn");
  const label = document.getElementById("favorite-btn-label");

  function paint(active) {
    btn.classList.toggle("is-favorite", active);
    btn.setAttribute("aria-pressed", String(active));
    label.textContent = active ? "Favoritado" : "Favoritar";
  }

  paint(isFavorite(manga.id));

  btn.addEventListener("click", () => {
    paint(toggleFavorite(manga));
  });
}

async function renderRelated(manga) {
  const allMangas = await getAllMangas();
  const related = getRelatedMangas(allMangas, manga, 6);
  if (!related.length) return;

  document.getElementById("grid-related").innerHTML = related.map(mangaCardHTML).join("");
  document.getElementById("related").style.display = "";
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

const COMMENT_VOTED_KEY = "suki-voted-comments";

function getVotedComments() {
  try {
    return new Set(JSON.parse(localStorage.getItem(COMMENT_VOTED_KEY) || "[]"));
  } catch (e) {
    return new Set();
  }
}

function markCommentVoted(id) {
  const voted = getVotedComments();
  voted.add(id);
  localStorage.setItem(COMMENT_VOTED_KEY, JSON.stringify([...voted]));
}

function initComments(mangaId) {
  const form = document.getElementById("comment-form");
  if (!form) return;

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    submitComment(form, mangaId, null);
  });

  loadComments(mangaId);
}

async function loadComments(mangaId) {
  const list = document.getElementById("comment-list");
  if (!list) return;
  try {
    const res = await fetch(`/api/mangas/${mangaId}/comments`);
    const data = await res.json();
    renderComments(data.comments || [], mangaId);
  } catch (e) {
    list.innerHTML = "<p class='empty-state'>Não foi possível carregar os comentários.</p>";
  }
}

function renderComments(comments, mangaId) {
  const list = document.getElementById("comment-list");
  const voted = getVotedComments();

  if (!comments.length) {
    list.innerHTML = "<p class='empty-state'>Nenhum comentário ainda. Seja o primeiro a comentar!</p>";
    return;
  }

  list.innerHTML = comments.map(c => commentItemHTML(c, voted)).join("");

  list.querySelectorAll(".comment-vote-btn").forEach(btn => {
    btn.addEventListener("click", () => castCommentVote(btn));
  });

  list.querySelectorAll(".comment-reply-toggle").forEach(btn => {
    btn.addEventListener("click", () => {
      const form = list.querySelector(`.comment-reply-form[data-parent-id="${btn.dataset.commentId}"]`);
      if (form) form.style.display = form.style.display === "none" ? "flex" : "none";
    });
  });

  list.querySelectorAll(".comment-reply-form").forEach(form => {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      submitComment(form, mangaId, Number(form.dataset.parentId));
    });
  });
}

function commentItemHTML(c, voted, isReply) {
  const hasVoted = voted.has(c.id);
  const repliesHTML = (c.replies || []).map(r => commentItemHTML(r, voted, true)).join("");
  const replyBlock = isReply ? "" : `
    <button type="button" class="comment-reply-toggle" data-comment-id="${c.id}">Responder</button>
    <form class="comment-reply-form" data-parent-id="${c.id}" style="display:none;">
      <textarea name="body" placeholder="Escreva uma resposta..." maxlength="2000" required></textarea>
      <input type="text" name="author_name" placeholder="Seu nome" maxlength="50" required>
      <input type="text" name="website" class="hp-field" tabindex="-1" autocomplete="off" aria-hidden="true">
      <button type="submit" class="btn btn-ghost">Responder</button>
      <p class="comment-form-msg"></p>
    </form>
  `;

  return `
    <div class="comment-item${isReply ? " is-reply" : ""}">
      <div class="comment-vote">
        <button type="button" class="comment-vote-btn" data-comment-id="${c.id}" data-value="1" ${hasVoted ? "disabled" : ""} aria-label="Votar a favor">▲</button>
        <span class="comment-score" data-score-for="${c.id}">${c.score}</span>
        <button type="button" class="comment-vote-btn" data-comment-id="${c.id}" data-value="-1" ${hasVoted ? "disabled" : ""} aria-label="Votar contra">▼</button>
      </div>
      <div class="comment-body">
        <div class="comment-meta">
          <strong class="comment-author">${escapeHtml(c.author_name)}</strong>
          <span class="comment-date">${formatDate(c.created_at.slice(0, 10))}</span>
        </div>
        <p class="comment-text">${escapeHtml(c.body)}</p>
        ${replyBlock}
        ${repliesHTML ? `<div class="comment-replies">${repliesHTML}</div>` : ""}
      </div>
    </div>
  `;
}

async function submitComment(form, mangaId, parentId) {
  const authorName = form.author_name.value.trim();
  const body = form.body.value.trim();
  const website = form.website ? form.website.value : "";
  const msgEl = form.querySelector(".comment-form-msg");

  if (!authorName || !body) return;

  const submitBtn = form.querySelector("button[type=submit]");
  if (submitBtn) submitBtn.disabled = true;

  try {
    const res = await fetch(`/api/mangas/${mangaId}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author_name: authorName, body, parent_id: parentId, website }),
    });

    if (res.status === 429) {
      if (msgEl) msgEl.textContent = "Você está comentando rápido demais. Espere um pouco.";
      return;
    }
    if (!res.ok) {
      if (msgEl) msgEl.textContent = "Não foi possível publicar o comentário.";
      return;
    }

    form.reset();
    if (parentId) form.style.display = "none";
    if (msgEl) msgEl.textContent = "";
    loadComments(mangaId);
  } catch (e) {
    if (msgEl) msgEl.textContent = "Não foi possível publicar o comentário.";
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function castCommentVote(btn) {
  const commentId = Number(btn.dataset.commentId);
  const value = Number(btn.dataset.value);
  const pair = btn.parentElement.querySelectorAll(".comment-vote-btn");

  try {
    const res = await fetch(`/api/comments/${commentId}/vote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    });

    if (res.status === 409) {
      markCommentVoted(commentId);
      pair.forEach(b => { b.disabled = true; });
      return;
    }
    if (!res.ok) return;

    const data = await res.json();
    const scoreEl = btn.parentElement.querySelector(`[data-score-for="${commentId}"]`);
    if (scoreEl) scoreEl.textContent = data.score;
    markCommentVoted(commentId);
    pair.forEach(b => { b.disabled = true; });
  } catch (e) {
    // silencioso - voto não é uma ação crítica
  }
}

renderMangaPage();
