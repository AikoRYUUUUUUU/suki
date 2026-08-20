(function () {
  const btn = document.getElementById("migrate-btn");
  if (!btn) return;

  const log = document.getElementById("migration-log");

  function logLine(text, ok) {
    const p = document.createElement("p");
    p.className = "migration-log-line" + (ok === false ? " migration-log-error" : "");
    p.textContent = text;
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
  }

  async function migrateItem(item) {
    const fileRes = await fetch(item.local_url);
    if (!fileRes.ok) throw new Error("não consegui ler o arquivo local (" + fileRes.status + ")");
    const blob = await fileRes.blob();
    const file = new File([blob], "migrated", { type: blob.type });

    const { url, size } = await window.AdminUploads.sniffAndPresign(file, item.kind, item.manga_id);

    const commitRes = await fetch("/admin/migration/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": window.AdminUploads.csrfToken() },
      body: JSON.stringify({
        kind: item.kind, manga_id: item.manga_id, page_id: item.page_id,
        url: url, size: size,
      }),
    });
    if (!commitRes.ok) throw new Error("falha ao salvar no banco (" + commitRes.status + ")");
  }

  btn.addEventListener("click", async function () {
    btn.disabled = true;
    log.innerHTML = "";

    let items;
    try {
      const res = await fetch("/admin/migration/pending");
      items = (await res.json()).items;
    } catch (e) {
      showToast("error", "Não foi possível carregar a lista de imagens pendentes.");
      btn.disabled = false;
      return;
    }

    if (items.length === 0) {
      showToast("success", "Nada pra migrar - tudo já está no R2.");
      btn.disabled = false;
      return;
    }

    let ok = 0;
    let failed = 0;
    for (const item of items) {
      try {
        await migrateItem(item);
        ok++;
        logLine("✓ " + (item.label || item.kind), true);
      } catch (e) {
        failed++;
        logLine("✗ " + (item.label || item.kind) + " — " + e.message, false);
      }
    }

    if (failed === 0) {
      showToast("success", `${ok} imagem${ok !== 1 ? "s" : ""} migrada${ok !== 1 ? "s" : ""} pro R2 com sucesso.`);
    } else {
      showToast("warning", `${ok} migrada${ok !== 1 ? "s" : ""}, ${failed} falharam. Veja o log e tente de novo.`);
    }
    btn.disabled = false;
    setTimeout(() => location.reload(), 2500);
  });
})();
