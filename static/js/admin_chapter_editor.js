(function () {
  const manager = document.getElementById("page-manager");
  const initialPages = JSON.parse(document.getElementById("initial-pages").textContent);
  const addBtn = document.getElementById("add-pages-btn");
  const pickerInput = document.getElementById("new_pages_picker");
  const orderInput = document.getElementById("order-input");
  const newPagesInput = document.getElementById("new-pages-input");
  const form = document.getElementById("edit-chapter-form");
  const submitBtn = document.getElementById("edit-chapter-submit");
  const mangaId = form.dataset.mangaId;

  let items = initialPages.map(function (p) {
    return { type: "existing", id: p.id, url: p.url };
  });
  let dragIndex = null;
  const removedExistingUrls = [];

  function render() {
    manager.innerHTML = "";
    items.forEach(function (item, index) {
      const el = document.createElement("div");
      el.className = "page-item"
        + (item.uploading ? " uploading" : "")
        + (item.failed ? " upload-failed" : "");
      el.draggable = true;

      const thumb = document.createElement("div");
      thumb.className = "thumb";
      const img = document.createElement("img");
      img.src = item.url;
      img.alt = "Página " + (index + 1);
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
      badge.textContent = item.uploading ? "Enviando…" : String(index + 1);

      el.appendChild(thumb);
      el.appendChild(removeBtn);
      el.appendChild(badge);

      el.addEventListener("dragstart", function () {
        dragIndex = index;
        el.classList.add("dragging");
      });
      el.addEventListener("dragend", function () {
        el.classList.remove("dragging");
        dragIndex = null;
      });
      el.addEventListener("dragover", function (e) {
        e.preventDefault();
        el.classList.add("drag-over");
      });
      el.addEventListener("dragleave", function () {
        el.classList.remove("drag-over");
      });
      el.addEventListener("drop", function (e) {
        e.preventDefault();
        el.classList.remove("drag-over");
        if (dragIndex === null || dragIndex === index) return;
        const moved = items.splice(dragIndex, 1)[0];
        items.splice(index, 0, moved);
        render();
      });

      manager.appendChild(el);
    });
    updateSubmitState();
  }

  function removeItem(index) {
    const item = items[index];
    if (item.type === "new" && item.url) {
      URL.revokeObjectURL(item.url);
    }
    if (item.type === "existing") {
      removedExistingUrls.push(item.url);
    }
    items.splice(index, 1);
    render();
  }

  function updateSubmitState() {
    if (submitBtn) submitBtn.disabled = items.some(function (i) { return i.uploading; });
  }

  addBtn.addEventListener("click", function () {
    pickerInput.click();
  });

  pickerInput.addEventListener("change", function () {
    Array.from(pickerInput.files).forEach(function (file) {
      const item = {
        type: "new", file: file, url: URL.createObjectURL(file),
        remoteUrl: null, size: null, uploading: true, failed: false,
      };
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
    });
    pickerInput.value = "";
    render();
  });

  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    if (items.length === 0) {
      showToast("error", "Adicione ao menos uma página antes de salvar.");
      return;
    }
    if (items.some(function (i) { return i.uploading; })) {
      showToast("warning", "Aguarde o envio das páginas terminar.");
      return;
    }
    if (items.some(function (i) { return i.failed; })) {
      showToast("error", "Remova as páginas que falharam antes de continuar.");
      return;
    }

    if (submitBtn) submitBtn.disabled = true;

    const tokens = [];
    const newPagesData = [];
    items.forEach(function (item) {
      if (item.type === "existing") {
        tokens.push("e" + item.id);
      } else {
        tokens.push("n" + newPagesData.length);
        newPagesData.push({ url: item.remoteUrl, size: item.size });
      }
    });
    orderInput.value = tokens.join(",");
    newPagesInput.value = JSON.stringify(newPagesData);

    if (removedExistingUrls.length) {
      await window.AdminUploads.presignDeleteUrls(removedExistingUrls, mangaId);
    }

    form.submit();
  });

  render();
})();
