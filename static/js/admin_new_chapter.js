(function () {
  const form = document.getElementById("new-chapter-form");
  if (!form) return;

  const picker = document.getElementById("pages");
  const preview = document.getElementById("pages-upload-preview");
  const pageUrlsInput = document.getElementById("page_urls");
  const submitBtn = document.getElementById("new-chapter-submit");
  const mangaId = form.dataset.mangaId;

  let items = [];

  function render() {
    preview.innerHTML = "";
    items.forEach(function (item, index) {
      const el = document.createElement("div");
      el.className = "page-item" + (item.uploading ? " uploading" : "") + (item.failed ? " upload-failed" : "");

      const thumb = document.createElement("div");
      thumb.className = "thumb";
      const img = document.createElement("img");
      img.src = item.url;
      thumb.appendChild(img);

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "page-remove";
      removeBtn.setAttribute("aria-label", "Remover página");
      removeBtn.textContent = "×";
      removeBtn.addEventListener("click", function () {
        removeItem(index);
      });

      const badge = document.createElement("span");
      badge.className = "page-order-badge";
      badge.textContent = String(index + 1);

      el.appendChild(thumb);
      el.appendChild(removeBtn);
      el.appendChild(badge);
      preview.appendChild(el);
    });
    updateSubmitState();
  }

  function removeItem(index) {
    URL.revokeObjectURL(items[index].url);
    items.splice(index, 1);
    render();
  }

  function updateSubmitState() {
    if (submitBtn) submitBtn.disabled = items.some(function (i) { return i.uploading; });
  }

  picker.addEventListener("change", function () {
    Array.from(picker.files).forEach(function (file) {
      const item = { file: file, url: URL.createObjectURL(file), remoteUrl: null, size: null, uploading: true, failed: false };
      items.push(item);
      window.AdminUploads.sniffAndPresign(file, "page", mangaId)
        .then(function (result) {
          item.remoteUrl = result.url;
          item.size = result.size;
          item.uploading = false;
        })
        .catch(function (err) {
          item.uploading = false;
          item.failed = true;
          showToast("error", (file.name || "Arquivo") + ": " + (err.message || "falha ao enviar."));
        })
        .finally(render);
      render();
    });
    picker.value = "";
  });

  form.addEventListener("submit", function (e) {
    if (items.length === 0) {
      e.preventDefault();
      showToast("error", "Selecione ao menos uma imagem de página.");
      return;
    }
    if (items.some(function (i) { return i.uploading; })) {
      e.preventDefault();
      showToast("warning", "Aguarde o envio das páginas terminar.");
      return;
    }
    if (items.some(function (i) { return i.failed; })) {
      e.preventDefault();
      showToast("error", "Remova as páginas que falharam antes de continuar.");
      return;
    }
    pageUrlsInput.value = JSON.stringify(items.map(function (i) {
      return { url: i.remoteUrl, size: i.size };
    }));
  });
})();
