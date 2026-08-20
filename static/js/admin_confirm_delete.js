(function () {
  const dialog = document.getElementById("confirm-delete-dialog");
  if (!dialog) return;

  const nameEl = document.getElementById("confirm-delete-name");
  const detailEl = document.getElementById("confirm-delete-detail");
  const confirmBtn = document.getElementById("confirm-delete-btn");
  const cancelBtn = document.getElementById("confirm-delete-cancel");
  let targetForm = null;
  let r2LookupUrl = null;

  document.querySelectorAll(".js-delete-trigger").forEach(function (btn) {
    btn.addEventListener("click", function () {
      targetForm = document.getElementById(btn.dataset.targetForm);
      r2LookupUrl = btn.dataset.r2LookupUrl || null;
      nameEl.textContent = btn.dataset.name || "";
      detailEl.textContent = btn.dataset.detail || "";
      dialog.showModal();
    });
  });

  cancelBtn.addEventListener("click", function () {
    dialog.close();
  });

  confirmBtn.addEventListener("click", async function () {
    if (!targetForm) return;
    confirmBtn.disabled = true;
    // Limpa os arquivos no R2 antes de apagar o registro - best-effort, nunca
    // impede a exclusão de fato mesmo se essa parte falhar.
    if (r2LookupUrl && window.AdminUploads) {
      await window.AdminUploads.presignDeleteFromLookup(r2LookupUrl);
    }
    targetForm.submit();
  });
})();
