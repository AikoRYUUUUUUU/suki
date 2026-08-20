(function () {
  const coverInput = document.getElementById("cover");
  const coverUrlInput = document.getElementById("cover_url");
  const preview = document.getElementById("cover-upload-preview");
  const form = coverInput ? coverInput.closest("form") : null;
  const submitBtn = form ? form.querySelector('button[type="submit"]') : null;
  if (!coverInput || !form) return;

  let uploading = false;

  function setUploading(state) {
    uploading = state;
    if (submitBtn) submitBtn.disabled = state;
  }

  coverInput.addEventListener("change", async function () {
    const file = coverInput.files[0];
    coverUrlInput.value = "";
    preview.innerHTML = "";
    if (!file) return;

    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    img.style.maxWidth = "160px";
    img.style.borderRadius = "2px";
    preview.appendChild(img);

    setUploading(true);
    try {
      const { url } = await window.AdminUploads.sniffAndPresign(file, "cover", null);
      coverUrlInput.value = url;
    } catch (e) {
      showToast("error", e.message || "Falha ao enviar a capa.");
      coverInput.value = "";
      preview.innerHTML = "";
    } finally {
      setUploading(false);
    }
  });

  form.addEventListener("submit", function (e) {
    if (uploading) {
      e.preventDefault();
      showToast("warning", "Aguarde o envio da capa terminar.");
    }
  });
})();
