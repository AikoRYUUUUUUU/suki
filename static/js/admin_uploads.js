/**
 * Helpers compartilhados pelas telas do admin que fazem upload direto pro R2:
 * o navegador manda só os primeiros 16 bytes do arquivo pro Flask (confere a
 * assinatura mágica real da imagem), recebe de volta uma URL PUT pré-assinada
 * e envia o arquivo inteiro direto pro bucket - o arquivo nunca passa pelo
 * servidor Flask/PythonAnywhere. Exclusão de arquivos usa o mesmo princípio:
 * o servidor só assina uma URL DELETE, o navegador é quem chama.
 */
(function () {
  function csrfToken() {
    const input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value : "";
  }

  function showToast(type, message) {
    let stack = document.getElementById("toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.id = "toast-stack";
      stack.className = "toast-stack";
      document.body.appendChild(stack);
    }
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${message}</span>`;
    const close = document.createElement("button");
    close.type = "button";
    close.className = "toast-close";
    close.setAttribute("aria-label", "Fechar aviso");
    close.textContent = "×";
    close.addEventListener("click", () => toast.remove());
    toast.appendChild(close);
    stack.appendChild(toast);
    setTimeout(() => toast.remove(), 8000);
  }

  async function sniffAndPresign(file, kind, mangaId) {
    const headBuf = await file.slice(0, 16).arrayBuffer();
    const head = Array.from(new Uint8Array(headBuf));

    const presignRes = await fetch("/admin/uploads/presign", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ kind: kind, manga_id: mangaId || null, head: head }),
    });
    if (!presignRes.ok) {
      const body = await presignRes.json().catch(() => ({}));
      throw new Error(body.error || "Falha ao preparar o envio da imagem.");
    }
    const { upload_url, public_url, content_type } = await presignRes.json();

    const putRes = await fetch(upload_url, {
      method: "PUT",
      headers: { "Content-Type": content_type },
      body: file,
    });
    if (!putRes.ok) {
      throw new Error("Falha ao enviar o arquivo pro armazenamento.");
    }

    return { url: public_url, size: file.size };
  }

  async function presignDeleteUrls(urls) {
    const list = (urls || []).filter(Boolean);
    if (!list.length) return;
    try {
      const res = await fetch("/admin/r2/presign-delete", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ urls: list }),
      });
      if (!res.ok) return;
      const { urls: deleteUrls } = await res.json();
      await Promise.allSettled(
        Object.values(deleteUrls).map((delUrl) => fetch(delUrl, { method: "DELETE" }))
      );
    } catch (e) {
      // best-effort - nunca deve impedir a exclusão real do registro no banco
    }
  }

  async function presignDeleteFromLookup(lookupUrl) {
    try {
      const res = await fetch(lookupUrl, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken() },
      });
      if (!res.ok) return;
      const { urls: deleteUrls } = await res.json();
      await Promise.allSettled(
        Object.values(deleteUrls).map((delUrl) => fetch(delUrl, { method: "DELETE" }))
      );
    } catch (e) {
      // best-effort - nunca deve impedir a exclusão real do registro no banco
    }
  }

  window.showToast = showToast;
  window.AdminUploads = {
    csrfToken: csrfToken,
    sniffAndPresign: sniffAndPresign,
    presignDeleteUrls: presignDeleteUrls,
    presignDeleteFromLookup: presignDeleteFromLookup,
  };
})();
