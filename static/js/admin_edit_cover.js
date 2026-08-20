(function () {
  const form = document.getElementById("edit-cover-form");
  if (!form) return;

  const coverInput = document.getElementById("cover");
  const coverUrlInput = document.getElementById("cover_url");
  const submitBtn = form.querySelector('button[type="submit"]');

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const file = coverInput.files[0];
    if (!file) {
      showToast("error", "Selecione uma imagem.");
      return;
    }

    if (submitBtn) submitBtn.disabled = true;
    try {
      const { url } = await window.AdminUploads.sniffAndPresign(file, "cover", null);
      coverUrlInput.value = url;

      const oldCover = form.dataset.oldCover;
      if (oldCover) {
        await window.AdminUploads.presignDeleteUrls([oldCover]);
      }
      form.submit();
    } catch (err) {
      showToast("error", err.message || "Falha ao enviar a capa.");
      if (submitBtn) submitBtn.disabled = false;
    }
  });
})();
