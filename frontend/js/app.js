const currentPage = document.body.dataset.page;

document.querySelectorAll("[data-nav]").forEach((link) => {
  if (link.dataset.nav === currentPage) link.classList.add("active");
});
