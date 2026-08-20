(function () {
  document.querySelectorAll(".status-select").forEach(function (sel) {
    sel.addEventListener("change", function () {
      sel.form.requestSubmit();
    });
  });
})();
