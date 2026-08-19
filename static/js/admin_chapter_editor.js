(function () {
  const manager = document.getElementById("page-manager");
  const initialPages = JSON.parse(document.getElementById("initial-pages").textContent);
  const addBtn = document.getElementById("add-pages-btn");
  const pickerInput = document.getElementById("new_pages_picker");
  const submitInput = document.getElementById("new_pages_submit");
  const orderInput = document.getElementById("order-input");
  const form = document.getElementById("edit-chapter-form");

  let items = initialPages.map(function (p) {
    return { type: "existing", id: p.id, url: p.url };
  });
  let dragIndex = null;

  function render() {
    manager.innerHTML = "";
    items.forEach(function (item, index) {
      const el = document.createElement("div");
      el.className = "page-item";
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
      badge.textContent = String(index + 1);

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
  }

  function removeItem(index) {
    const item = items[index];
    if (item.type === "new" && item.url) {
      URL.revokeObjectURL(item.url);
    }
    items.splice(index, 1);
    render();
  }

  addBtn.addEventListener("click", function () {
    pickerInput.click();
  });

  pickerInput.addEventListener("change", function () {
    Array.from(pickerInput.files).forEach(function (file) {
      items.push({ type: "new", file: file, url: URL.createObjectURL(file) });
    });
    pickerInput.value = "";
    render();
  });

  form.addEventListener("submit", function (e) {
    if (items.length === 0) {
      e.preventDefault();
      alert("Adicione ao menos uma página antes de salvar.");
      return;
    }

    const dt = new DataTransfer();
    const tokens = [];
    let newIndex = 0;
    items.forEach(function (item) {
      if (item.type === "existing") {
        tokens.push("e" + item.id);
      } else {
        dt.items.add(item.file);
        tokens.push("n" + newIndex);
        newIndex++;
      }
    });
    submitInput.files = dt.files;
    orderInput.value = tokens.join(",");
  });

  render();
})();
