function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

async function verifyPost(postId) {
  const res = await fetch(`/api/posts/${postId}/verify`, { method: "POST" });
  return await res.json();
}

async function loadComments(postId) {
  const res = await fetch(`/api/posts/${postId}/comments`);
  return await res.json();
}

async function addComment(postId, body) {
  const res = await fetch(`/api/posts/${postId}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  });
  return await res.json();
}

async function voteComment(commentId, value) {
  const res = await fetch(`/api/comments/${commentId}/vote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  return await res.json();
}

function renderComments(postId, items) {
  const list = document.getElementById(`comment-list-${postId}`);
  if (!list) return;
  if (!items.length) {
    list.innerHTML = `<div class="muted">No hay comentarios todavía.</div>`;
    return;
  }

  list.innerHTML = items
    .map(
      (c) => `
        <div class="comment-item" data-comment-id="${c.id}">
          <div class="comment-head">
            <span class="comment-author">${escapeHtml(c.author)}</span>
            <span class="comment-time">${new Date(c.created_at).toLocaleString("es-ES")}</span>
          </div>
          <div class="comment-body">${escapeHtml(c.body)}</div>
          <div class="comment-actions">
            <button class="comment-vote" data-vote="1">▲</button>
            <span class="comment-score" id="comment-score-${c.id}">${c.score}</span>
            <button class="comment-vote" data-vote="-1">▼</button>
          </div>
        </div>
      `
    )
    .join("");

  list.querySelectorAll(".comment-vote").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const wrapper = btn.closest(".comment-item");
      const commentId = wrapper?.getAttribute("data-comment-id");
      if (!commentId) return;
      const value = parseInt(btn.getAttribute("data-vote"), 10);
      const result = await voteComment(commentId, value);
      if (result && typeof result.score !== "undefined") {
        const scoreEl = document.getElementById(`comment-score-${commentId}`);
        if (scoreEl) scoreEl.textContent = result.score;
      }
    });
  });
}

async function initReportCard(card) {
  const postId = card.getAttribute("data-post-id");
  if (!postId) return;

  const verifyBtn = card.querySelector(".verify-btn");
  const verifyCount = document.getElementById(`verify-count-${postId}`);
  if (verifyBtn) {
    verifyBtn.addEventListener("click", async () => {
      const result = await verifyPost(postId);
      if (verifyCount && result && typeof result.verify_count !== "undefined") {
        verifyCount.textContent = result.verify_count;
      }
    });
  }

  const historyBtn = card.querySelector("[data-history-url]");
  if (historyBtn) {
    historyBtn.addEventListener("click", () => {
      const url = historyBtn.getAttribute("data-history-url");
      if (!url) return;
      if (window.openReportModal) {
        window.openReportModal(url);
      } else {
        window.location.href = url;
      }
    });
  }

  const editBtn = card.querySelector(".edit-btn");
  if (editBtn) {
    editBtn.addEventListener("click", () => {
      const url = editBtn.getAttribute("data-edit-url");
      if (!url) return;
      if (window.openReportModal) {
        window.openReportModal(url);
      } else {
        window.location.href = url;
      }
    });
  }

  const form = card.querySelector(".comment-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const textarea = form.querySelector("textarea");
      const body = textarea?.value.trim();
      if (!body) return;
      await addComment(postId, body);
      textarea.value = "";
      const items = await loadComments(postId);
      renderComments(postId, items);
    });
  }

  const items = await loadComments(postId);
  renderComments(postId, items);
}

document.addEventListener("DOMContentLoaded", () => {
  const filters = document.getElementById("reportFilters");
  if (filters && window.CUBA_MUNICIPALITIES) {
    const provSelect = filters.querySelector('select[name="provincia"]');
    const munSelect = filters.querySelector('select[name="municipio"]');
    const municipalities = window.CUBA_MUNICIPALITIES;

    const renderMunicipalities = (province, selected) => {
      if (!munSelect) return;
      let items = [];
      if (province && municipalities[province]) {
        items = municipalities[province];
      } else {
        Object.values(municipalities).forEach((list) => {
          items = items.concat(list);
        });
        items = Array.from(new Set(items)).sort();
      }
      munSelect.innerHTML = `<option value="">Todos</option>` +
        items.map((m) => `<option value="${m}" ${m === selected ? "selected" : ""}>${m}</option>`).join("");
    };

    const updateUrl = () => {
      const params = new URLSearchParams(window.location.search);
      const prov = provSelect?.value || "";
      const mun = munSelect?.value || "";
      if (prov) params.set("provincia", prov); else params.delete("provincia");
      if (mun) params.set("municipio", mun); else params.delete("municipio");
      window.location.search = params.toString();
    };

    if (provSelect && munSelect) {
      renderMunicipalities(provSelect.value, munSelect.value);
      provSelect.addEventListener("change", () => {
        renderMunicipalities(provSelect.value, "");
        updateUrl();
      });
      munSelect.addEventListener("change", updateUrl);
    }
  }

  document.querySelectorAll(".report-card").forEach((card) => {
    initReportCard(card);
  });
});
