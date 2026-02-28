(function () {
  const modal = document.getElementById("reportModal");
  const frame = document.getElementById("reportModalFrame");
  if (!modal || !frame) return;

  function openReportModal(url) {
    frame.src = url || "/nuevo";
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeReportModal() {
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    frame.src = "about:blank";
  }

  window.openReportModal = openReportModal;

  document.querySelectorAll("[data-open-report]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const url = btn.getAttribute("data-url") || "/nuevo";
      openReportModal(url);
    });
  });

  document.querySelectorAll("[data-close-report]").forEach((btn) => {
    btn.addEventListener("click", closeReportModal);
  });

  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      closeReportModal();
    }
  });
})();
