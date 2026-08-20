/**
 * Preenche o formulário de novo mangá com dados públicos do AniList.
 * A busca roda direto no navegador do admin (fetch client-side) - o
 * AniList libera CORS pra chamadas de browser, então isso nunca passa
 * pelo servidor Flask (evita o bloqueio de outbound do PythonAnywhere).
 */
(function () {
  const ANILIST_ENDPOINT = "https://graphql.anilist.co";

  const QUERY = `query ($s: String) {
    Media(search: $s, type: MANGA) {
      title { romaji native }
      description(asHtml: false)
      genres
      tags { name }
      startDate { year }
      status
      isAdult
      averageScore
      staff(perPage: 8) { edges { role node { name { full } } } }
    }
  }`;

  const GENRE_TAG_MAP = {
    "action": "Ação",
    "adventure": "Aventura",
    "comedy": "Comédia",
    "drama": "Drama",
    "fantasy": "Fantasia",
    "horror": "Terror",
    "mystery": "Mistério",
    "psychological": "Psicológico",
    "romance": "Romance",
    "slice of life": "Slice of Life",
    "sports": "Esporte",
    "supernatural": "Sobrenatural",
    "thriller": "Suspense",
    "mecha": "Mecha",
    "ecchi": "Ecchi",
    "hentai": "Hentai",
    "sci-fi": "Ficção Científica",
    "isekai": "Isekai",
    "school": "Escolar",
    "historical": "Histórico",
    "harem": "Harém",
    "reverse harem": "Harém",
    "boys' love": "Yaoi",
    "girls' love": "Yuri",
    "shounen": "Shounen",
    "shoujo": "Shoujo",
    "seinen": "Seinen",
    "josei": "Josei",
  };

  const STATUS_MAP = {
    RELEASING: "Em andamento",
    FINISHED: "Finalizado",
    CANCELLED: "Finalizado",
    HIATUS: "Em Hiatus",
  };

  function stripHtml(html) {
    const div = document.createElement("div");
    div.innerHTML = (html || "").replace(/<br\s*\/?>/gi, "\n");
    return (div.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
  }

  function pickStaff(edges) {
    let author = null;
    let artist = null;
    (edges || []).forEach((e) => {
      const role = (e.role || "").toLowerCase();
      const name = e.node && e.node.name && e.node.name.full;
      if (!name) return;
      if (role.includes("story") && role.includes("art")) {
        author = author || name;
        artist = artist || name;
      } else if (role.includes("story") || role === "original creator") {
        author = author || name;
      } else if (role.includes("art") && !role.includes("assistant") && !role.includes("lettering")) {
        artist = artist || name;
      }
    });
    return { author, artist };
  }

  function matchedTags(media) {
    const names = new Set();
    (media.genres || []).forEach((g) => {
      const t = GENRE_TAG_MAP[g.toLowerCase()];
      if (t) names.add(t);
    });
    (media.tags || []).forEach((tag) => {
      const t = GENRE_TAG_MAP[(tag.name || "").toLowerCase()];
      if (t) names.add(t);
    });
    if (media.isAdult) names.add("Adulto (18+)");
    return names;
  }

  async function searchAniList(title) {
    const res = await fetch(ANILIST_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: QUERY, variables: { s: title } }),
    });
    // O AniList responde 404 (em vez de 200 com Media: null) quando não
    // encontra nenhum resultado pra busca - não é uma falha de rede.
    if (res.status === 404) return null;
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    return data && data.data && data.data.Media;
  }

  function setField(id, value) {
    const el = document.getElementById(id);
    if (!el || value === null || value === undefined || value === "") return false;
    el.value = value;
    return true;
  }

  // showToast() vem de admin_uploads.js (carregado antes deste script).

  async function runAutofill() {
    const titleInput = document.getElementById("title");
    const btn = document.getElementById("autofill-btn");
    const title = (titleInput.value || "").trim();

    if (!title) {
      titleInput.focus();
      showToast("error", "Digite um título antes de buscar.");
      return;
    }

    const originalLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Buscando…";

    try {
      const media = await searchAniList(title);
      if (!media) {
        showToast("error", `Não encontramos "${title}" no AniList. Preencha os dados manualmente.`);
        return;
      }

      const filled = [];
      const missing = [];

      const nativeTitle = media.title && (media.title.native || media.title.romaji);
      if (setField("title_original", nativeTitle)) filled.push("título original"); else missing.push("título original");

      if (setField("synopsis", stripHtml(media.description))) filled.push("sinopse"); else missing.push("sinopse");

      const year = media.startDate && media.startDate.year;
      if (year && setField("year", String(year))) filled.push("ano"); else missing.push("ano");

      if (typeof media.averageScore === "number") {
        setField("rating", (media.averageScore / 20).toFixed(1));
        filled.push("avaliação");
      } else {
        missing.push("avaliação");
      }

      const statusSelect = document.getElementById("status");
      const mappedStatus = STATUS_MAP[media.status];
      if (mappedStatus && statusSelect) {
        statusSelect.value = mappedStatus;
        filled.push("status");
      } else {
        missing.push("status");
      }

      const { author, artist } = pickStaff(media.staff && media.staff.edges);
      if (setField("author", author)) filled.push("autor"); else missing.push("autor");
      if (setField("artist", artist)) filled.push("artista"); else missing.push("artista");

      let anyTagChecked = false;
      const tagNames = matchedTags(media);
      document.querySelectorAll('input[name="tags"]').forEach((cb) => {
        if (tagNames.has(cb.value)) {
          cb.checked = true;
          anyTagChecked = true;
        }
      });
      if (anyTagChecked) filled.push("tags"); else missing.push("tags");

      if (missing.length === 0) {
        showToast("success", "Dados preenchidos a partir do AniList. Revise antes de salvar.");
      } else if (filled.length === 0) {
        showToast("error", `Encontramos "${title}" no AniList, mas sem dados suficientes. Preencha manualmente.`);
      } else {
        showToast("warning", `Preenchido parcialmente pelo AniList — não encontramos: ${missing.join(", ")}. Complete manualmente.`);
      }
    } catch (e) {
      showToast("error", `Falha ao buscar dados no AniList para "${title}". Preencha manualmente.`);
    } finally {
      btn.disabled = false;
      btn.textContent = originalLabel;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("autofill-btn");
    if (btn) btn.addEventListener("click", runAutofill);
  });
})();
