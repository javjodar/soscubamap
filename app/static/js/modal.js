(function () {
  const modal = document.getElementById("reportModal");
  const frame = document.getElementById("reportModalFrame");
  if (!modal || !frame) return;

  function openReportModal(url) {
    const target = url || "/nuevo";
    const joiner = target.includes("?") ? "&" : "?";
    frame.src = `${target}${joiner}modal=1`;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeReportModal() {
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    frame.src = "about:blank";
  }

  window.openReportModal = openReportModal;
  window.closeReportModal = closeReportModal;

  window.onReportSubmitted = function (payload) {
    closeReportModal();
    if (window.handleNewReport) {
      window.handleNewReport(payload);
    } else {
      window.location.reload();
    }
  };

  window.onEditSubmitted = function () {
    closeReportModal();
    window.location.reload();
  };

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
