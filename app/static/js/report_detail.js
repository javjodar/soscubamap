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

function setupCopyLink() {
  const copyBtn = document.getElementById("copyLinkBtn");
  if (!copyBtn) return;
  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      copyBtn.textContent = "Enlace copiado";
      setTimeout(() => (copyBtn.textContent = "Copiar enlace"), 1500);
    } catch (e) {
      copyBtn.textContent = "Copia manual";
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  const card = document.querySelector("[data-post-id]");
  const postId = card?.getAttribute("data-post-id");
  if (!postId) return;

  const verifyBtn = document.getElementById("verifyBtn");
  const verifyCount = document.getElementById("verifyCount");
  if (verifyBtn) {
    verifyBtn.addEventListener("click", async () => {
      const result = await verifyPost(postId);
      if (verifyCount && result && typeof result.verify_count !== "undefined") {
        verifyCount.textContent = result.verify_count;
      }
    });
  }

  const form = document.querySelector(".comment-form");
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
  setupCopyLink();

  const mediaForm = document.getElementById("mediaUploadForm");
  const mediaInput = document.getElementById("mediaInput");
  const mediaStatus = document.getElementById("mediaStatus");
  const mediaGrid = document.getElementById("mediaGrid");
  const modal = document.getElementById("imageModal");
  const modalImg = document.getElementById("imageModalImg");

  const bindThumbnails = () => {
    document.querySelectorAll(".media-thumb").forEach((btn) => {
      btn.addEventListener("click", () => {
        const src = btn.getAttribute("data-image");
        if (!src || !modal || !modalImg) return;
        modalImg.src = src;
        modal.setAttribute("aria-hidden", "false");
        modal.classList.add("open");
      });
    });
  };

  const closeModal = () => {
    if (!modal || !modalImg) return;
    modal.setAttribute("aria-hidden", "true");
    modal.classList.remove("open");
    modalImg.src = "";
  };

  document.querySelectorAll("[data-close-image]").forEach((btn) => {
    btn.addEventListener("click", closeModal);
  });

  if (mediaForm && mediaInput) {
    mediaForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const files = mediaInput.files;
      if (!files || files.length === 0) return;

      const maxFiles = parseInt(mediaInput.dataset.maxFiles || "3", 10);
      const maxMb = parseInt(mediaInput.dataset.maxMb || "2", 10);
      const allowedExt = (mediaInput.dataset.allowedExt || "jpg,jpeg,png,webp,heic")
        .split(",")
        .map((ext) => ext.trim().toLowerCase())
        .filter(Boolean);
      const maxBytes = maxMb * 1024 * 1024;

      if (files.length > maxFiles) {
        if (mediaStatus) mediaStatus.textContent = `Máximo ${maxFiles} imágenes por envío.`;
        mediaInput.value = "";
        return;
      }

      for (const file of Array.from(files)) {
        const name = file.name || "";
        const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
        if (!allowedExt.includes(ext)) {
          if (mediaStatus) mediaStatus.textContent = `Formato no permitido: ${ext || "desconocido"}.`;
          mediaInput.value = "";
          return;
        }
        if (file.size > maxBytes) {
          if (mediaStatus) mediaStatus.textContent = `Cada imagen debe ser <= ${maxMb}MB.`;
          mediaInput.value = "";
          return;
        }
      }

      const formData = new FormData();
      Array.from(files).forEach((file) => formData.append("images", file));

      if (mediaStatus) mediaStatus.textContent = "Subiendo imágenes...";
      const res = await fetch(`/api/posts/${postId}/media`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok || data?.ok === false) {
        if (mediaStatus) mediaStatus.textContent = data?.error || "Error al subir.";
        return;
      }

      if (data.status === "pending") {
        if (mediaStatus) mediaStatus.textContent = "Enviado a moderación.";
      } else {
        if (mediaStatus) mediaStatus.textContent = "Imágenes agregadas.";
      }

      if (Array.isArray(data.media) && mediaGrid) {
        mediaGrid.innerHTML = data.media
          .map(
            (url) => `
              <button class="media-thumb" type="button" data-image="${url}">
                <img src="${url}" alt="Imagen del reporte" />
              </button>
            `
          )
          .join("");
        bindThumbnails();
      }

      mediaInput.value = "";
      setTimeout(() => {
        if (mediaStatus) mediaStatus.textContent = "";
      }, 2000);
    });
  }

  bindThumbnails();
});

window.initDetailMap = function () {
  const mapEl = document.getElementById("detailMap");
  if (!mapEl || !window.google?.maps) return;

  const lat = parseFloat(mapEl.dataset.lat);
  const lng = parseFloat(mapEl.dataset.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

  const map = new google.maps.Map(mapEl, {
    center: { lat, lng },
    zoom: 14,
    minZoom: 6,
    mapId: mapEl.dataset.mapId || undefined,
    mapTypeId: "hybrid",
    tilt: 0,
    heading: 0,
  });

  new google.maps.Marker({ position: { lat, lng }, map });

  const raw = mapEl.dataset.geojson || "";
  if (!raw) return;
  try {
    const geo = JSON.parse(raw);
    if (geo && geo.type === "Polygon" && geo.coordinates?.length) {
      const path = geo.coordinates[0].map(([lngVal, latVal]) => ({ lat: latVal, lng: lngVal }));
      new google.maps.Polygon({
        paths: path,
        strokeColor: "#6ee7b7",
        strokeOpacity: 0.7,
        strokeWeight: 2,
        fillColor: "#6ee7b7",
        fillOpacity: 0.18,
        map,
      });
    } else if (geo && geo.type === "Point" && geo.coordinates?.length && geo.radius_m) {
      new google.maps.Circle({
        center: { lat: geo.coordinates[1], lng: geo.coordinates[0] },
        radius: geo.radius_m,
        strokeColor: "#6ee7b7",
        strokeOpacity: 0.7,
        strokeWeight: 2,
        fillColor: "#6ee7b7",
        fillOpacity: 0.18,
        map,
      });
    }
  } catch (e) {
    // ignore invalid geojson
  }
};
