(function () {
  const dialog = document.getElementById("confirm-delete-dialog");
  if (!dialog) return;

  const nameEl = document.getElementById("confirm-delete-name");
  const detailEl = document.getElementById("confirm-delete-detail");
  const confirmBtn = document.getElementById("confirm-delete-btn");
  const cancelBtn = document.getElementById("confirm-delete-cancel");
  let targetForm = null;

  document.querySelectorAll(".js-delete-trigger").forEach(function (btn) {
    btn.addEventListener("click", function () {
      targetForm = document.getElementById(btn.dataset.targetForm);
      nameEl.textContent = btn.dataset.name || "";
      detailEl.textContent = btn.dataset.detail || "";
      dialog.showModal();
    });
  });

  cancelBtn.addEventListener("click", function () {
    dialog.close();
  });

  confirmBtn.addEventListener("click", function () {
    if (targetForm) {
      targetForm.submit();
    }
  });
})();
