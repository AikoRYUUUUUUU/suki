/**
 * Roda toda vez que o painel admin carrega: busca comentários do Cusdis que
 * chegaram via webhook (fila em /admin/comments/pending-approvals) e dispara
 * o approve_link de cada um sozinho, direto do navegador do admin - o Flask
 * não pode fazer essa chamada (bloqueio de saída do PythonAnywhere free-tier),
 * mas o navegador de quem estiver logado pode. Não é instantâneo pra qualquer
 * comentário (só roda quando o painel é aberto), mas tira a aprovação manual.
 */
(function () {
  async function run() {
    let items;
    try {
      const res = await fetch("/admin/comments/pending-approvals");
      if (!res.ok) return;
      items = (await res.json()).items;
    } catch (e) {
      return;
    }
    if (!items || items.length === 0) return;

    let approved = 0;
    for (const item of items) {
      try {
        await fetch(item.approve_link, { mode: "no-cors" });
        await fetch(`/admin/comments/pending-approvals/${item.id}/done`, {
          method: "POST",
          headers: { "X-CSRFToken": window.AdminUploads.csrfToken() },
        });
        approved++;
      } catch (e) {
        // deixa pendente - tenta de novo na próxima vez que o painel carregar
      }
    }

    if (approved > 0) {
      showToast("success", `${approved} comentário${approved !== 1 ? "s" : ""} aprovado${approved !== 1 ? "s" : ""} automaticamente.`);
    }
  }

  run();
})();
