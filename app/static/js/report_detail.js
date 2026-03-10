function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function unescapeHtml(value) {
  const textarea = document.createElement("textarea");
  textarea.innerHTML = value || "";
  return textarea.value;
}

let isAdmin = false;

async function verifyPost(postId) {
  const res = await fetch(`/api/posts/${postId}/verify`, { method: "POST" });
  return await res.json();
}

async function loadComments(postId) {
  const res = await fetch(`/api/posts/${postId}/comments`);
  return await res.json();
}

async function addComment(postId, body, recaptcha) {
  const res = await fetch(`/api/posts/${postId}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body, recaptcha }),
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
            <span class="comment-score ${c.score < 0 ? "score-negative" : ""}" id="comment-score-${c.id}">${c.score}</span>
            <button class="comment-vote" data-vote="-1">▼</button>
            ${isAdmin ? `<button class="comment-delete" data-delete="${c.id}">Eliminar</button>` : ""}
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
        if (scoreEl) {
          scoreEl.textContent = result.score;
          scoreEl.classList.toggle("score-negative", result.score < 0);
        }
      }
    });
  });

  if (isAdmin) {
    list.querySelectorAll(".comment-delete").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const commentId = btn.getAttribute("data-delete");
        if (!commentId) return;
        if (!confirm("¿Eliminar comentario?")) return;
        await fetch(`/api/comments/${commentId}`, { method: "DELETE" });
        const updated = await loadComments(postId);
        renderComments(postId, updated);
      });
    });
  }
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
  isAdmin = card?.getAttribute("data-is-admin") === "1";
  if (!postId) return;

  const verifyBtn = document.getElementById("verifyBtn");
  const verifyCount = document.getElementById("verifyCount");
  const hideBtn = document.getElementById("hideReportBtn");
  const deleteBtn = document.getElementById("deleteReportBtn");
  if (verifyBtn) {
    if (verifyBtn.getAttribute("data-verified") === "1") {
      verifyBtn.disabled = true;
      verifyBtn.textContent = "Verificado";
      verifyBtn.classList.add("is-verified");
    }
    verifyBtn.addEventListener("click", async () => {
      if (verifyBtn.disabled) return;
      const result = await verifyPost(postId);
      if (verifyCount && result && typeof result.verify_count !== "undefined") {
        verifyCount.textContent = result.verify_count;
      }
      if (result && result.ok) {
        verifyBtn.disabled = true;
        verifyBtn.textContent = "Verificado";
        verifyBtn.setAttribute("data-verified", "1");
        verifyBtn.classList.add("is-verified");
      }
    });
  }

  const updateStatus = async (status) => {
    const res = await fetch(`/api/posts/${postId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    return await res.json();
  };

  if (hideBtn) {
    hideBtn.addEventListener("click", async () => {
      if (!confirm("¿Ocultar este reporte?")) return;
      const result = await updateStatus("hidden");
      if (result && result.ok) {
        window.location.href = "/admin/reportes?status=hidden";
      }
    });
  }

  if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("¿Eliminar este reporte?")) return;
      const result = await updateStatus("deleted");
      if (result && result.ok) {
        window.location.href = "/admin/reportes?status=deleted";
      }
    });
  }

  const form = document.querySelector(".comment-form");
  const commentStatus = document.getElementById("commentStatus");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (commentStatus) commentStatus.textContent = "";
      const textarea = form.querySelector("textarea");
      const body = textarea?.value.trim();
      if (!body) return;
      let token = "";
      const recaptchaEl = document.getElementById("reportCommentRecaptcha");
      if (recaptchaEl && !window.grecaptcha) {
        if (commentStatus) {
          commentStatus.textContent = "reCAPTCHA aún está cargando. Intenta de nuevo.";
        }
        return;
      }
      if (window.grecaptcha) {
        token = grecaptcha.getResponse();
      }
      if (window.grecaptcha && !token) {
        if (commentStatus) {
          commentStatus.textContent = "Completa el reCAPTCHA antes de enviar.";
        }
        return;
      }
      const result = await addComment(postId, body, token);
      if (result && result.ok === false) {
        if (commentStatus) {
          commentStatus.textContent = result.error || "No se pudo enviar el comentario.";
        }
        return;
      }
      textarea.value = "";
      if (window.grecaptcha) {
        grecaptcha.reset();
      }
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
  const previewList = document.getElementById("detailImagePreviewList");
  const modal = document.getElementById("imageModal");
  const modalImg = document.getElementById("imageModalImg");
  const modalCaption = document.getElementById("imageModalCaption");

  const bindThumbnails = () => {
    document.querySelectorAll(".media-thumb").forEach((btn) => {
      btn.addEventListener("click", () => {
        const src = btn.getAttribute("data-image");
        const caption = unescapeHtml(btn.getAttribute("data-caption") || "");
        if (!src || !modal || !modalImg) return;
        modalImg.src = src;
        if (modalCaption) {
          modalCaption.textContent = caption;
        }
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
    if (modalCaption) modalCaption.textContent = "";
  };

  document.querySelectorAll("[data-close-image]").forEach((btn) => {
    btn.addEventListener("click", closeModal);
  });

  const renderPreviews = () => {
    if (!previewList || !mediaInput) return;
    if (!mediaInput.files || mediaInput.files.length === 0) {
      previewList.innerHTML = "";
      return;
    }
    previewList.innerHTML = Array.from(mediaInput.files)
      .map((file, idx) => {
        const url = URL.createObjectURL(file);
        return `
          <div class="image-preview-card">
            <img src="${url}" alt="Vista previa ${idx + 1}" />
            <label class="image-caption">
              Descripción corta (imagen ${idx + 1})
              <input type="text" name="image_captions[]" maxlength="255" placeholder="${file.name}" />
            </label>
          </div>
        `;
      })
      .join("");
  };

  if (mediaInput) {
    mediaInput.addEventListener("change", renderPreviews);
  }

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
      if (previewList) {
        previewList.querySelectorAll('input[name="image_captions[]"]').forEach((input) => {
          formData.append("image_captions[]", input.value || "");
        });
      }

      if (mediaStatus) mediaStatus.textContent = "Subiendo imágenes...";
      const submitBtn = mediaForm.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.dataset.loading = "true";
        submitBtn.textContent = "Subiendo...";
      }
      const res = await fetch(`/api/posts/${postId}/media`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok || data?.ok === false) {
        if (mediaStatus) mediaStatus.textContent = data?.error || "Error al subir.";
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.dataset.loading = "false";
          submitBtn.textContent = "Subir imágenes";
        }
        return;
      }

      if (data.status === "pending") {
        if (mediaStatus) mediaStatus.textContent = "Enviado a moderación.";
      } else {
        if (mediaStatus) mediaStatus.textContent = "Imágenes agregadas.";
      }

      if (Array.isArray(data.media) && mediaGrid) {
        mediaGrid.innerHTML = data.media
          .map((item) => {
            if (typeof item === "string") {
              return `
                <button class="media-thumb" type="button" data-image="${item}" data-caption="">
                  <img src="${item}" alt="Imagen del reporte" />
                </button>
              `;
            }
            const url = item?.url || "";
            const caption = item?.caption || "";
            return `
              <button class="media-thumb" type="button" data-image="${url}" data-caption="${escapeHtml(caption)}">
                <img src="${url}" alt="Imagen del reporte" />
              </button>
            `;
          })
          .join("");
        bindThumbnails();
      }

      mediaInput.value = "";
      renderPreviews();
      setTimeout(() => {
        if (mediaStatus) mediaStatus.textContent = "";
      }, 2000);
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.dataset.loading = "false";
        submitBtn.textContent = "Subir imágenes";
      }
    });
  }

  bindThumbnails();
});

function enableMiddleClickPan(leafletMap) {
  const container = leafletMap?.getContainer?.();
  if (!container) return;

  let middleDown = false;
  let lastX = 0;
  let lastY = 0;

  const onMouseMove = (event) => {
    if (!middleDown) return;
    event.preventDefault();
    const dx = event.clientX - lastX;
    const dy = event.clientY - lastY;
    if (!dx && !dy) return;
    leafletMap.panBy([-dx, -dy], { animate: false, noMoveStart: true });
    lastX = event.clientX;
    lastY = event.clientY;
  };

  const stopMiddlePan = () => {
    if (!middleDown) return;
    middleDown = false;
    container.style.cursor = "";
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
  };

  const onMouseUp = (event) => {
    if (event.button !== 1 && !middleDown) return;
    stopMiddlePan();
  };

  container.addEventListener(
    "mousedown",
    (event) => {
      if (event.button !== 1) return;
      event.preventDefault();
      middleDown = true;
      lastX = event.clientX;
      lastY = event.clientY;
      container.style.cursor = "grabbing";
      window.addEventListener("mousemove", onMouseMove, { passive: false });
      window.addEventListener("mouseup", onMouseUp);
    },
    { passive: false }
  );

  container.addEventListener("auxclick", (event) => {
    if (event.button === 1) event.preventDefault();
  });
}

function initDetailMap() {
  const mapEl = document.getElementById("detailMap");
  if (!mapEl || typeof L === "undefined") return;

  const lat = parseFloat(mapEl.dataset.lat);
  const lng = parseFloat(mapEl.dataset.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

  const bounds = L.latLngBounds(
    [19.0, -86.2],
    [24.2, -73.0]
  );

  const map = L.map(mapEl, {
    minZoom: 6,
    maxZoom: 19,
    zoomControl: true,
  }).setView([lat, lng], 14);
  enableMiddleClickPan(map);

  const streetsLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  });

  const satelliteLayer = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      attribution:
        'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
      maxZoom: 19,
    }
  );
  const satelliteLabelsLayer = L.tileLayer(
    "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    {
      attribution: "Labels &copy; Esri",
      maxZoom: 19,
    }
  );

  streetsLayer.addTo(map);
  L.control
    .layers(
      {
        Mapa: streetsLayer,
        Satelite: satelliteLayer,
      },
      {},
      { collapsed: true }
    )
    .addTo(map);

  map.on("baselayerchange", (event) => {
    if (event.layer === satelliteLayer) {
      if (!map.hasLayer(satelliteLabelsLayer)) satelliteLabelsLayer.addTo(map);
    } else if (map.hasLayer(satelliteLabelsLayer)) {
      map.removeLayer(satelliteLabelsLayer);
    }
  });

  map.setMaxBounds(bounds.pad(0.35));
  L.marker([lat, lng]).addTo(map);

  const raw = mapEl.dataset.geojson || "";
  if (!raw) return;
  try {
    const geo = JSON.parse(raw);
    if (geo && geo.type === "Polygon" && geo.coordinates?.length) {
      const latLngs = geo.coordinates[0].map(([lngVal, latVal]) => [latVal, lngVal]);
      L.polygon(latLngs, {
        color: "#6ee7b7",
        opacity: 0.7,
        weight: 2,
        fillColor: "#6ee7b7",
        fillOpacity: 0.18,
      }).addTo(map);
    } else if (geo && geo.type === "Point" && geo.coordinates?.length && geo.radius_m) {
      L.circle([geo.coordinates[1], geo.coordinates[0]], {
        radius: geo.radius_m,
        color: "#6ee7b7",
        opacity: 0.7,
        weight: 2,
        fillColor: "#6ee7b7",
        fillOpacity: 0.18,
      }).addTo(map);
    }
  } catch (e) {
    // ignore invalid geojson
  }
}

window.initDetailMap = initDetailMap;

document.addEventListener("DOMContentLoaded", () => {
  initDetailMap();
});
