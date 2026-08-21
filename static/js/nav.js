(function () {
  const toggle = document.getElementById("nav-toggle");
  const nav = document.getElementById("nav-links");
  if (!toggle || !nav) return;

  function close() {
    nav.classList.remove("open");
    toggle.setAttribute("aria-expanded", "false");
  }

  toggle.addEventListener("click", function () {
    const isOpen = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(isOpen));
  });

  nav.querySelectorAll("a").forEach(function (a) {
    a.addEventListener("click", close);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") close();
  });
})();

(function () {
  const searchToggle = document.getElementById("search-toggle");
  const searchForm = document.getElementById("topbar-search");
  if (!searchToggle || !searchForm) return;

  const input = searchForm.querySelector('input[type="text"]');

  function setActive(active) {
    searchForm.classList.toggle("is-active", active);
    searchToggle.setAttribute("aria-expanded", String(active));
    if (active && input) input.focus();
  }

  // se a busca já chegou preenchida (ex: veio de /busca.html?q=...), começa aberta
  if (input && input.value.trim()) setActive(true);

  searchToggle.addEventListener("click", function () {
    setActive(!searchForm.classList.contains("is-active"));
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setActive(false);
  });
})();
