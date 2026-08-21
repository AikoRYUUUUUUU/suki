(function () {
  document.querySelectorAll(".status-select").forEach(function (sel) {
    sel.addEventListener("change", function () {
      sel.form.requestSubmit();
    });
  });

  var announceForm = document.getElementById("discord-announce-form");
  if (announceForm) {
    announceForm.addEventListener("submit", function (e) {
      if (!window.confirm("Enviar a mensagem de cargos agora? Isso posta no canal do Discord na hora - clicar de novo depois cria outra mensagem duplicada.")) {
        e.preventDefault();
      }
    });
  }
})();
