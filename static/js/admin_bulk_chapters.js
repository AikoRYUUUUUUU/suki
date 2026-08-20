(function () {
  const card = document.getElementById("bulk-form-card");
  if (!card) return;
  const mangaId = card.dataset.mangaId;

  const zipsInput = document.getElementById("zips");
  const dateInput = document.getElementById("release_date");
  const submitBtn = document.getElementById("bulk-submit");
  const log = document.getElementById("bulk-log");

  function logLine(text, ok) {
    const p = document.createElement("p");
    p.className = "admin-log-line" + (ok === false ? " admin-log-error" : "");
    p.textContent = text;
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
  }

  function parseChapterInfo(filename) {
    const base = filename.replace(/\.zip$/i, "");
    const match = base.match(/\d+(?:\.\d+)?/);
    return { number: match ? match[0] : null, title: base };
  }

  async function processZip(file, releaseDate) {
    const info = parseChapterInfo(file.name);
    if (!info.number) {
      throw new Error("não encontrei um número no nome do arquivo (ex: \"Cap 05.zip\")");
    }

    const images = await readZipImages(file);
    if (images.length === 0) {
      throw new Error("nenhuma imagem encontrada dentro do .zip");
    }

    const pages = [];
    for (const img of images) {
      const result = await window.AdminUploads.sniffAndPresign(img.blob, "page", mangaId);
      pages.push({ url: result.url, size: result.size });
    }

    const res = await fetch(`/admin/mangas/${mangaId}/chapters/bulk-create`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": window.AdminUploads.csrfToken() },
      body: JSON.stringify({
        number: info.number, title: info.title, release_date: releaseDate, pages: pages,
      }),
    });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok) {
      throw new Error(data.error || `falha ao criar o capítulo (HTTP ${res.status})`);
    }

    return { pageCount: images.length };
  }

  submitBtn.addEventListener("click", async function () {
    const files = Array.from(zipsInput.files || []);
    if (files.length === 0) {
      showToast("error", "Selecione ao menos um arquivo .zip.");
      return;
    }
    const releaseDate = dateInput.value;
    if (!releaseDate) {
      showToast("error", "Escolha a data de publicação.");
      return;
    }

    submitBtn.disabled = true;
    log.innerHTML = "";

    let ok = 0;
    let failed = 0;
    for (const file of files) {
      try {
        const result = await processZip(file, releaseDate);
        ok++;
        logLine(`✓ ${file.name} — ${result.pageCount} página${result.pageCount !== 1 ? "s" : ""}`, true);
      } catch (e) {
        failed++;
        logLine(`✗ ${file.name} — ${e.message}`, false);
      }
    }

    submitBtn.disabled = false;
    if (failed === 0) {
      showToast("success", `${ok} capítulo${ok !== 1 ? "s" : ""} criado${ok !== 1 ? "s" : ""} com sucesso.`);
    } else {
      showToast("warning", `${ok} criado${ok !== 1 ? "s" : ""}, ${failed} falharam. Veja o log abaixo.`);
    }
  });
})();
