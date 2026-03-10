let map;
let markers = [];
let markerIndex = new Map();
let shapeLayers = [];
let activePopup;
let recentTimer;
let searchMarker;
let isAdmin = false;
let allPosts = [];
let mapImageModal;
let mapImageModalImg;
let mapImageModalCaption;
let pendingMarkers = [];

const CUBA_BOUNDS = {
  north: 24.2,
  south: 19.0,
  west: -86.2,
  east: -73.0,
};

function cubaLatLngBounds() {
  return L.latLngBounds(
    [CUBA_BOUNDS.south, CUBA_BOUNDS.west],
    [CUBA_BOUNDS.north, CUBA_BOUNDS.east]
  );
}

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

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function safeUrl(value) {
  const url = String(value || "").trim();
  if (!/^https?:\/\//i.test(url)) return "";
  return url.replaceAll('"', "%22").replaceAll("'", "%27");
}

function isWithinCubaBounds(location) {
  if (!location) return false;
  const lat = Number(location.lat);
  const lng = Number(location.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
  return lat <= CUBA_BOUNDS.north && lat >= CUBA_BOUNDS.south && lng >= CUBA_BOUNDS.west && lng <= CUBA_BOUNDS.east;
}

document.addEventListener("DOMContentLoaded", () => {
  const filters = document.querySelector(".filters");
  const toggle = document.getElementById("filtersToggle");
  if (filters && toggle) {
    toggle.addEventListener("click", () => {
      const isCollapsed = filters.classList.toggle("collapsed");
      toggle.textContent = isCollapsed ? "Mostrar filtros" : "Ocultar filtros";
      toggle.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
    });
  }

  const searchInput = document.getElementById("mapSearch");
  if (searchInput) {
    const placeholders = [
      "Ej: Sector PNR",
      "Ej: Prision",
      "Ej: Unidad Militar",
      "Ej: Tropas",
      "Ej: Estacion de policia",
      "Ej: Centro de detencion",
      "Ej: Brigada Especial",
    ];
    const pick = placeholders[Math.floor(Math.random() * placeholders.length)];
    searchInput.setAttribute("placeholder", pick);
  }

  initMap();
});

function setupMapImageModal() {
  mapImageModal = document.getElementById("mapImageModal");
  mapImageModalImg = document.getElementById("mapImageModalImg");
  mapImageModalCaption = document.getElementById("mapImageModalCaption");
  if (!mapImageModal || !mapImageModalImg) return;

  const close = () => {
    mapImageModal.setAttribute("aria-hidden", "true");
    mapImageModal.classList.remove("open");
    mapImageModalImg.src = "";
    if (mapImageModalCaption) mapImageModalCaption.textContent = "";
  };

  document.querySelectorAll("[data-close-map-image]").forEach((btn) => {
    btn.addEventListener("click", close);
  });
}

const CATEGORY_ICONS = {
  "accion-represiva": "fa-hand-fist",
  "movimiento-tropas": "fa-bolt",
  "desconexion-internet": "fa-wifi",
  "residencia-represor": "fa-house-chimney-user",
  "centro-penitenciario": "fa-landmark-dome",
  "estacion-policia": "fa-building-shield",
  "escuela-pcc": "fa-graduation-cap",
  "sede-pcc": "fa-people-group",
  "sede-seguridad-estado": "fa-user-secret",
  "unidad-militar": "fa-person-military-pointing",
  "base-espionaje": "fa-satellite-dish",
  "otros": "fa-circle-question",
};

const CATEGORY_IMAGES = {
  "sede-pcc": "/static/img/Communist_Party_of_Cuba_logo.svg.png",
};

const ALERT_SLUGS = new Set(["accion-represiva", "movimiento-tropas", "desconexion-internet"]);

function isAlertCategory(slug) {
  return ALERT_SLUGS.has(slug);
}

function createMarkerIcon(iconClass, imageUrl, slug, pending) {
  const classes = ["pin-icon"];
  if (isAlertCategory(slug)) classes.push("alert");
  if (pending) classes.push("pending");
  const iconHtml = imageUrl
    ? `<img src="${imageUrl}" alt="" class="pin-image" />`
    : `<i class="fa-solid ${iconClass}"></i>`;

  return L.divIcon({
    className: "pin-icon-wrap",
    html: `<div class="${classes.join(" ")}">${iconHtml}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -24],
  });
}

function syncLegend() {
  const items = document.querySelectorAll(".legend-item");
  items.forEach((item) => {
    const slug = item.dataset.slug;
    const iconClass = CATEGORY_ICONS[slug] || "fa-location-dot";
    const icon = item.querySelector("i");
    if (icon) {
      icon.className = `fa-solid ${iconClass}`;
    }
  });
}

function clearMarkers() {
  markers.forEach((marker) => marker.remove());
  markers = [];
  pendingMarkers.forEach((marker) => marker.remove());
  pendingMarkers = [];
  shapeLayers.forEach((layer) => layer.remove());
  shapeLayers = [];
  markerIndex = new Map();
}

function closeActivePopup() {
  if (!map || !activePopup) return;
  map.closePopup(activePopup);
  activePopup = null;
}

function getSelectedCategoryIds() {
  const checkboxes = document.querySelectorAll(".category-checkbox");
  const selected = new Set();
  checkboxes.forEach((cb) => {
    if (cb.checked) {
      const id = parseInt(cb.value, 10);
      if (!Number.isNaN(id)) selected.add(id);
    }
  });
  return selected;
}

function getSelectedLocationFilters() {
  const province = document.getElementById("provinceFilter")?.value || "";
  const municipality = document.getElementById("municipalityFilter")?.value || "";
  return { province, municipality };
}

async function loadPosts() {
  const res = await fetch(`/api/posts`);
  return await res.json();
}

function attachMediaThumbHandlers(container) {
  if (!container) return;
  const thumbs = container.querySelectorAll(".info-media-thumb");
  thumbs.forEach((thumb) => {
    thumb.addEventListener("click", () => {
      const url = thumb.getAttribute("data-image");
      const caption = thumb.getAttribute("data-caption") || "";
      if (!url || !mapImageModal || !mapImageModalImg) return;
      mapImageModalImg.src = url;
      if (mapImageModalCaption) mapImageModalCaption.textContent = caption;
      mapImageModal.setAttribute("aria-hidden", "false");
      mapImageModal.classList.add("open");
    });
  });
}

function renderGeometry(post) {
  if (!post?.polygon_geojson || !map) return;
  try {
    const geo = JSON.parse(post.polygon_geojson);
    if (geo && geo.type === "Polygon" && geo.coordinates?.length) {
      const latLngs = geo.coordinates[0].map(([lng, lat]) => [lat, lng]);
      const polygon = L.polygon(latLngs, {
        color: "#6ee7b7",
        weight: 2,
        opacity: 0.7,
        fillColor: "#6ee7b7",
        fillOpacity: 0.18,
      }).addTo(map);
      shapeLayers.push(polygon);
    } else if (geo && geo.type === "Point" && geo.coordinates?.length && geo.radius_m) {
      const circle = L.circle([geo.coordinates[1], geo.coordinates[0]], {
        radius: geo.radius_m,
        color: "#6ee7b7",
        weight: 2,
        opacity: 0.7,
        fillColor: "#6ee7b7",
        fillOpacity: 0.18,
      }).addTo(map);
      shapeLayers.push(circle);
    }
  } catch (err) {
    // ignore invalid geometry
  }
}

function attachPopupActions(post, popupElement, popupRef) {
  if (!popupElement) return;

  attachMediaThumbHandlers(popupElement);

  const detailBtn = popupElement.querySelector(`#detailBtn-${post.id}`);
  if (detailBtn) {
    detailBtn.addEventListener("click", () => {
      const url = detailBtn.getAttribute("data-detail-url");
      if (!url) return;
      window.location.href = url;
    });
  }

  const copyBtn = popupElement.querySelector(`#copyLinkBtn-${post.id}`);
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      const url = copyBtn.getAttribute("data-copy-url");
      if (!url) return;
      const full = `${window.location.origin}${url}`;
      try {
        await navigator.clipboard.writeText(full);
        copyBtn.textContent = "Enlace copiado";
        setTimeout(() => (copyBtn.textContent = "Copiar enlace"), 1500);
      } catch (err) {
        copyBtn.textContent = "Copia manual";
      }
    });
  }

  const reportBtn = popupElement.querySelector("#reportLocationBtn");
  if (reportBtn) {
    reportBtn.addEventListener("click", () => {
      const url = reportBtn.getAttribute("data-report-url");
      if (!url) return;
      if (window.openReportModal) {
        window.openReportModal(url);
      } else {
        window.location.href = url;
      }
    });
  }

  const historyBtn = popupElement.querySelector("#viewHistoryBtn");
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

  const verifyBtn = popupElement.querySelector(`#verifyBtn-${post.id}`);
  if (verifyBtn) {
    verifyBtn.addEventListener("click", async () => {
      if (verifyBtn.disabled) return;
      const res = await fetch(`/api/posts/${post.id}/verify`, { method: "POST" });
      const data = await res.json();
      const countEl = popupElement.querySelector(`#verifyCount-${post.id}`);
      if (countEl && typeof data.verify_count !== "undefined") {
        countEl.textContent = data.verify_count;
      }
      if (data && data.ok) {
        verifyBtn.disabled = true;
        verifyBtn.textContent = "Verificado";
        verifyBtn.classList.add("is-verified");
        verifyBtn.setAttribute("data-verified", "1");
      }
    });
  }

  const editBtn = popupElement.querySelector(`#editBtn-${post.id}`);
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

  if (!isAdmin) return;

  const hideBtn = popupElement.querySelector(`#hideBtn-${post.id}`);
  const deleteBtn = popupElement.querySelector(`#deleteBtn-${post.id}`);

  const updateStatus = async (status) => {
    const res = await fetch(`/api/posts/${post.id}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    return await res.json();
  };

  if (hideBtn) {
    hideBtn.addEventListener("click", async () => {
      if (!confirm("Ocultar este reporte?")) return;
      const result = await updateStatus("hidden");
      if (result && result.ok) {
        allPosts = allPosts.filter((p) => p.id !== post.id);
        applyFilters();
        if (map && popupRef) map.closePopup(popupRef);
      }
    });
  }

  if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("Eliminar este reporte?")) return;
      const result = await updateStatus("deleted");
      if (result && result.ok) {
        allPosts = allPosts.filter((p) => p.id !== post.id);
        applyFilters();
        if (map && popupRef) map.closePopup(popupRef);
      }
    });
  }
}

function popupHtmlForPost(post) {
  const created = post.created_at ? new Date(post.created_at) : null;
  const createdText = created ? created.toLocaleString("es-ES") : "";
  const safeTitle = escapeHtml(post.title);
  const safeCategory = escapeHtml(post.category?.name || "");
  const safeAnon = escapeHtml(post.anon || "Anon");
  const safeDescription = escapeHtml(post.description || "");
  const safeAddress = escapeHtml(post.address || "");
  const mediaItems = Array.isArray(post.media) ? post.media : [];
  const mediaHtml = mediaItems.length
    ? `<div class="info-media">
        ${mediaItems
          .slice(0, 4)
          .map((item) => {
            const url = typeof item === "string" ? item : item?.url;
            if (!url) return "";
            const caption = typeof item === "string" ? "" : item?.caption || "";
            const safeCaption = escapeHtml(caption);
            return `
              <button class="info-media-thumb" type="button" data-image="${url}" data-caption="${safeCaption}">
                <img src="${url}" alt="Imagen del reporte" />
              </button>
            `;
          })
          .join("")}
      </div>`
    : "";
  const editLocked = !isAdmin && (post.verify_count ?? 0) >= 10;
  const verifiedByMe = !!post.verified_by_me;
  const verifyLabel = verifiedByMe ? "Verificado" : "Verificar";
  const verifyDisabled = verifiedByMe ? "disabled data-verified=\"1\"" : "";

  return `
    <div style="color:#111;max-width:260px;">
      <h3 style="margin:0 0 6px;">${safeTitle}</h3>
      <div style="font-size:12px;color:#555;margin-bottom:6px;">${safeCategory}</div>
      <div style="font-size:12px;color:#333;margin-bottom:6px;">${safeAnon}</div>
      ${createdText ? `<div style="font-size:12px;color:#666;margin-bottom:6px;">${createdText}</div>` : ""}
      <p style="margin:0 0 6px;">${safeDescription}</p>
      ${mediaHtml}
      ${
        post.links && post.links.length
          ? `<div style="font-size:12px;margin-top:6px;">
               ${post.links
                 .map((link) => {
                   const href = safeUrl(link);
                   if (!href) return "";
                   const label = escapeHtml(link);
                   return `<div><a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a></div>`;
                 })
                 .join("")}
            </div>`
          : ""
      }
      <div class="info-actions">
        <button id="detailBtn-${post.id}" data-detail-url="/reporte/${post.id}" class="info-btn info-btn-outline">Ver detalle</button>
        <button id="copyLinkBtn-${post.id}" data-copy-url="/reporte/${post.id}" class="info-btn info-btn-outline">Copiar enlace</button>
        <button id="reportLocationBtn" data-report-url="/reportar-ubicacion/${post.id}" class="info-btn info-btn-outline">Reportar ubicacion</button>
        <button id="viewHistoryBtn" data-history-url="/reporte/${post.id}/historial" class="info-btn info-btn-outline info-btn-blue">Ver historial</button>
        <button id="verifyBtn-${post.id}" data-verify-id="${post.id}" class="info-btn info-btn-solid ${verifiedByMe ? "is-verified" : ""}" ${verifyDisabled}>${verifyLabel}</button>
        <span id="verifyCount-${post.id}" class="info-badge">${post.verify_count ?? 0}</span>
        ${
          editLocked
            ? `<span style="font-size:11px;color:#777;">Edicion bloqueada: 10+ verificaciones. Puedes comentar y reportar ubicacion si hay datos erroneos.</span>`
            : `<button id="editBtn-${post.id}" data-edit-url="/reporte/${post.id}/editar" class="info-btn info-btn-outline">Editar</button>`
        }
        ${
          isAdmin
            ? `
              <button id="hideBtn-${post.id}" data-status="hidden" class="info-btn info-btn-outline">Ocultar</button>
              <button id="deleteBtn-${post.id}" data-status="deleted" class="info-btn info-btn-outline">Eliminar</button>
            `
            : ""
        }
      </div>
      ${post.address ? `<div style="font-size:12px;color:#666;">${safeAddress}</div>` : ""}
    </div>
  `;
}

function renderMarkers(posts) {
  clearMarkers();

  posts.forEach((post) => {
    const lat = Number(post.latitude);
    const lng = Number(post.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

    const slug = post.category?.slug;
    const iconClass = CATEGORY_ICONS[slug] || "fa-location-dot";
    const imageUrl = CATEGORY_IMAGES[slug];

    const marker = L.marker([lat, lng], {
      title: post.title,
      icon: createMarkerIcon(iconClass, imageUrl, slug, false),
    }).addTo(map);

    const popupHtml = popupHtmlForPost(post);
    marker.bindPopup(popupHtml, { maxWidth: 300 });

    marker.on("popupopen", (evt) => {
      activePopup = evt.popup;
      const popupElement = evt.popup.getElement();
      attachPopupActions(post, popupElement, evt.popup);
    });

    marker.on("click", () => {
      closeActivePopup();
      marker.openPopup();
    });

    markers.push(marker);
    markerIndex.set(post.id, { marker, post });
    renderGeometry(post);
  });
}

function openPostOnMap(post) {
  if (!post || !map) return;
  const lat = Number(post.latitude);
  const lng = Number(post.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

  map.setView([lat, lng], Math.max(map.getZoom(), 14));
  const entry = markerIndex.get(post.id);
  if (entry?.marker) {
    closeActivePopup();
    entry.marker.openPopup();
  }
}

function updateLegendCounts(posts) {
  const counts = {};
  (posts || []).forEach((post) => {
    const id = post.category?.id;
    if (!id) return;
    counts[id] = (counts[id] || 0) + 1;
  });

  document.querySelectorAll(".legend-count").forEach((el) => {
    const id = parseInt(el.id.replace("legend-count-", ""), 10);
    const value = counts[id] || 0;
    el.textContent = value;
  });
}

window.handleNewReport = function (payload) {
  if (!payload || !map) return;
  const lat = Number(payload.latitude);
  const lng = Number(payload.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

  const slug = payload.category?.slug;
  const iconClass = CATEGORY_ICONS[slug] || "fa-location-dot";
  const imageUrl = CATEGORY_IMAGES[slug];

  if (payload.status !== "approved") {
    const marker = L.marker([lat, lng], {
      title: payload.title || "Reporte pendiente",
      icon: createMarkerIcon("fa-hourglass-half", imageUrl, slug, true),
    }).addTo(map);

    marker.bindPopup(
      `
      <div style="color:#111;max-width:240px;">
        <strong>Reporte enviado a moderacion.</strong>
        <div style="font-size:12px;margin-top:6px;">Se mostrara cuando sea aprobado.</div>
      </div>
      `,
      { maxWidth: 260 }
    );

    pendingMarkers.push(marker);
    map.setView([lat, lng], Math.max(map.getZoom(), 12));
    marker.openPopup();
    refreshRecent();
    refreshAlerts();
    return;
  }

  if (Array.isArray(allPosts)) {
    allPosts.unshift(payload);
  }
  updateLegendCounts(allPosts);
  applyFilters();
  map.setView([lat, lng], Math.max(map.getZoom(), 12));
  refreshRecent();
  refreshAlerts();
};

async function applyFilters() {
  const selected = getSelectedCategoryIds();
  const { province, municipality } = getSelectedLocationFilters();
  let filtered = selected.size ? allPosts.filter((post) => selected.has(post.category?.id)) : [];

  if (province) {
    filtered = filtered.filter((post) => post.province === province);
  }
  if (municipality) {
    filtered = filtered.filter((post) => post.municipality === municipality);
  }

  updateLegendCounts(allPosts);
  renderMarkers(filtered);
}

async function loadRecent() {
  const res = await fetch("/api/posts?limit=8", { cache: "no-store" });
  return await res.json();
}

async function loadAlerts() {
  const res = await fetch("/api/posts?limit=40", { cache: "no-store" });
  return await res.json();
}

function renderRecent(posts) {
  const container = document.getElementById("recentFeed");
  if (!container) return;

  if (!posts.length) {
    container.innerHTML = `<div class="console-empty">Sin aportaciones visibles aun.</div>`;
    return;
  }

  container.innerHTML = posts
    .map((post) => {
      const safeTitle = escapeHtml(post.title || "");
      const safeCategory = escapeHtml(post.category?.name || "");
      const safeAnon = escapeHtml(post.anon || "Anon");
      return `
        <div class="console-item">
          <div>
            <button class="console-title-row console-link" type="button" data-detail-url="/reporte/${post.id}">${safeTitle}</button>
            <div class="console-meta">${safeCategory}</div>
            <div class="console-meta">${safeAnon}</div>
          </div>
          <div class="console-side">
            <div class="console-coords">${post.latitude.toFixed(4)}, ${post.longitude.toFixed(4)}</div>
            <div class="console-time">${post.created_at ? new Date(post.created_at).toLocaleString("es-ES") : ""}</div>
            <button class="btn-secondary console-btn" data-pan-lat="${post.latitude}" data-pan-lng="${post.longitude}" data-post-id="${post.id}">Ver en mapa</button>
          </div>
        </div>
      `;
    })
    .join("");

  container.querySelectorAll("[data-pan-lat]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const lat = parseFloat(btn.getAttribute("data-pan-lat"));
      const lng = parseFloat(btn.getAttribute("data-pan-lng"));
      if (!Number.isFinite(lat) || !Number.isFinite(lng) || !map) return;
      const postId = parseInt(btn.getAttribute("data-post-id"), 10);
      const post = allPosts.find((p) => p.id === postId) || { id: postId, latitude: lat, longitude: lng };
      openPostOnMap(post);
      const mapEl = document.getElementById("map");
      if (mapEl) {
        mapEl.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });

  container.querySelectorAll(".console-link").forEach((btn) => {
    btn.addEventListener("click", () => {
      const url = btn.getAttribute("data-detail-url");
      if (!url) return;
      if (window.openReportModal) {
        window.openReportModal(url);
      } else {
        window.location.href = url;
      }
    });
  });
}

function renderAlerts(posts) {
  const container = document.getElementById("alertFeed");
  if (!container) return;

  const alerts = (posts || []).filter((post) => isAlertCategory(post.category?.slug));
  if (!alerts.length) {
    container.innerHTML = `<div class="console-empty">Sin movimientos, desconexiones o acciones recientes.</div>`;
    return;
  }

  container.innerHTML = alerts
    .slice(0, 8)
    .map((post) => {
      const safeTitle = escapeHtml(post.title || "");
      const safeCategory = escapeHtml(post.category?.name || "");
      const safeProvince = escapeHtml(post.province || "N/D");
      const safeMunicipality = escapeHtml(post.municipality || "N/D");
      const locationText = `${safeProvince} · ${safeMunicipality}`;
      const eventTime = post.movement_at || post.created_at;
      const timeText = eventTime ? new Date(eventTime).toLocaleString("es-ES") : "";
      return `
        <div class="console-item">
          <div>
            <button class="console-title-row console-link" type="button" data-detail-url="/reporte/${post.id}">${safeTitle}</button>
            <div class="console-meta">${safeCategory}</div>
            <div class="console-meta">${locationText}</div>
          </div>
          <div class="console-side">
            <div class="console-time">${timeText}</div>
          </div>
        </div>
      `;
    })
    .join("");

  container.querySelectorAll(".console-link").forEach((btn) => {
    btn.addEventListener("click", () => {
      const url = btn.getAttribute("data-detail-url");
      if (!url) return;
      if (window.openReportModal) {
        window.openReportModal(url);
      } else {
        window.location.href = url;
      }
    });
  });
}

async function refreshRecent() {
  try {
    const posts = await loadRecent();
    renderRecent(posts);
  } catch (err) {
    // no-op
  }
}

async function refreshAlerts() {
  try {
    const posts = await loadAlerts();
    renderAlerts(posts);
  } catch (err) {
    // no-op
  }
}

function parseNominatimResult(item, fallbackLabel) {
  if (!item) return null;
  const lat = Number(item.lat);
  const lng = Number(item.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  if (!isWithinCubaBounds({ lat, lng })) return null;

  return {
    lat,
    lng,
    label: item.display_name || fallbackLabel || `${lat.toFixed(5)}, ${lng.toFixed(5)}`,
  };
}

async function searchSuggestionsInCuba(query, limit = 5) {
  const q = String(query || "").trim();
  if (!q) return [];

  const size = Math.min(Math.max(parseInt(limit, 10) || 5, 1), 8);
  const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&accept-language=es&limit=${size}&countrycodes=cu&q=${encodeURIComponent(
    q
  )}`;
  const res = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  });
  if (!res.ok) return [];
  const data = await res.json();
  if (!Array.isArray(data) || !data.length) return [];

  const seen = new Set();
  const results = [];
  data.forEach((item) => {
    const parsed = parseNominatimResult(item, q);
    if (!parsed) return;
    const key = `${parsed.lat.toFixed(6)},${parsed.lng.toFixed(6)}`;
    if (seen.has(key)) return;
    seen.add(key);
    results.push(parsed);
  });

  return results;
}

async function searchInCuba(query) {
  const matches = await searchSuggestionsInCuba(query, 5);
  return matches[0] || null;
}

function focusSearchResult(result) {
  if (!map || !result) return;
  map.setView([result.lat, result.lng], Math.max(map.getZoom(), 16));

  if (searchMarker) {
    searchMarker.remove();
  }

  searchMarker = L.marker([result.lat, result.lng], {
    title: result.label || "Busqueda",
  }).addTo(map);
}

function setupMapSearchAutocomplete(searchInput) {
  if (!searchInput) return;
  const searchBar = searchInput.closest(".map-search-bar");
  if (!searchBar) return;

  let suggestions = [];
  let activeIndex = -1;
  let debounceTimer = null;
  let requestToken = 0;

  let dropdown = searchBar.querySelector(".map-search-suggestions");
  if (!dropdown) {
    dropdown = document.createElement("div");
    dropdown.className = "map-search-suggestions";
    dropdown.id = "mapSearchSuggestions";
    dropdown.setAttribute("role", "listbox");
    dropdown.hidden = true;
    searchBar.appendChild(dropdown);
  }

  searchInput.setAttribute("autocomplete", "off");
  searchInput.setAttribute("role", "combobox");
  searchInput.setAttribute("aria-autocomplete", "list");
  searchInput.setAttribute("aria-controls", dropdown.id);
  searchInput.setAttribute("aria-expanded", "false");

  const closeDropdown = () => {
    dropdown.hidden = true;
    dropdown.innerHTML = "";
    activeIndex = -1;
    searchInput.setAttribute("aria-expanded", "false");
  };

  const refreshActiveItem = () => {
    const items = dropdown.querySelectorAll(".map-search-suggestion");
    items.forEach((item, idx) => {
      const isActive = idx === activeIndex;
      item.classList.toggle("is-active", isActive);
      item.setAttribute("aria-selected", isActive ? "true" : "false");
      if (isActive) {
        item.scrollIntoView({ block: "nearest" });
      }
    });
  };

  const selectSuggestion = (entry) => {
    if (!entry) return;
    searchInput.value = entry.label || searchInput.value;
    closeDropdown();
    focusSearchResult(entry);
  };

  const renderDropdown = () => {
    if (!suggestions.length) {
      closeDropdown();
      return;
    }
    dropdown.innerHTML = suggestions
      .map((entry, idx) => {
        const label = escapeHtml(entry.label || "");
        const activeClass = idx === activeIndex ? " is-active" : "";
        const selected = idx === activeIndex ? "true" : "false";
        return `<button type="button" class="map-search-suggestion${activeClass}" data-idx="${idx}" role="option" aria-selected="${selected}">${label}</button>`;
      })
      .join("");
    dropdown.hidden = false;
    searchInput.setAttribute("aria-expanded", "true");

    dropdown.querySelectorAll(".map-search-suggestion").forEach((item) => {
      item.addEventListener("mousedown", (event) => {
        event.preventDefault();
      });
      item.addEventListener("click", () => {
        const idx = parseInt(item.getAttribute("data-idx"), 10);
        if (Number.isNaN(idx)) return;
        selectSuggestion(suggestions[idx]);
      });
    });
  };

  const runSearch = async () => {
    const query = searchInput.value.trim();
    if (query.length < 3) {
      suggestions = [];
      closeDropdown();
      return;
    }

    const token = ++requestToken;
    try {
      const found = await searchSuggestionsInCuba(query, 6);
      if (token !== requestToken) return;
      suggestions = found;
      activeIndex = suggestions.length ? 0 : -1;
      renderDropdown();
    } catch (err) {
      if (token !== requestToken) return;
      suggestions = [];
      closeDropdown();
    }
  };

  searchInput.addEventListener("input", () => {
    if (debounceTimer) window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(runSearch, 240);
  });

  searchInput.addEventListener("focus", () => {
    if (suggestions.length) {
      dropdown.hidden = false;
      searchInput.setAttribute("aria-expanded", "true");
      refreshActiveItem();
    }
  });

  searchInput.addEventListener("keydown", async (event) => {
    if (event.key === "ArrowDown") {
      if (!suggestions.length) return;
      event.preventDefault();
      activeIndex = (activeIndex + 1) % suggestions.length;
      refreshActiveItem();
      return;
    }
    if (event.key === "ArrowUp") {
      if (!suggestions.length) return;
      event.preventDefault();
      activeIndex = activeIndex <= 0 ? suggestions.length - 1 : activeIndex - 1;
      refreshActiveItem();
      return;
    }
    if (event.key === "Escape") {
      if (dropdown.hidden) return;
      event.preventDefault();
      suggestions = [];
      closeDropdown();
      return;
    }
    if (event.key !== "Enter") return;

    event.preventDefault();
    if (suggestions.length && activeIndex >= 0) {
      selectSuggestion(suggestions[activeIndex]);
      return;
    }

    const query = searchInput.value.trim();
    if (!query) return;
    const found = await searchInCuba(query);
    if (!found) return;
    selectSuggestion(found);
  });

  document.addEventListener("click", (event) => {
    if (searchBar.contains(event.target)) return;
    suggestions = [];
    closeDropdown();
  });
}

async function initMap() {
  setupMapImageModal();
  syncLegend();

  const mapEl = document.getElementById("map");
  if (!mapEl || typeof L === "undefined") {
    refreshRecent();
    refreshAlerts();
    return;
  }

  isAdmin = mapEl.dataset.isAdmin === "1";

  map = L.map(mapEl, {
    zoomControl: true,
    minZoom: 4,
    maxZoom: 19,
  });
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

  const cubaBounds = cubaLatLngBounds();
  map.fitBounds(cubaBounds);
  map.setMaxBounds(cubaBounds.pad(0.35));

  const params = new URLSearchParams(window.location.search);
  const latParam = parseFloat(params.get("lat"));
  const lngParam = parseFloat(params.get("lng"));
  if (Number.isFinite(latParam) && Number.isFinite(lngParam)) {
    map.setView([latParam, lngParam], Math.max(map.getZoom(), 14));
    L.marker([latParam, lngParam], { title: "Ubicacion" }).addTo(map);
  }

  const searchInput = document.getElementById("mapSearch");
  if (searchInput) {
    setupMapSearchAutocomplete(searchInput);
  }

  allPosts = await loadPosts();
  await applyFilters();
  await refreshRecent();
  await refreshAlerts();

  const filters = document.querySelectorAll(".category-checkbox");
  filters.forEach((checkbox) => {
    checkbox.addEventListener("change", applyFilters);
  });

  const provinceSelect = document.getElementById("provinceFilter");
  const municipalitySelect = document.getElementById("municipalityFilter");
  const municipalities = window.CUBA_MUNICIPALITIES || {};

  const renderMunicipalities = (province, selected) => {
    if (!municipalitySelect) return;
    let items = [];
    if (province && municipalities[province]) {
      items = municipalities[province];
    } else {
      Object.values(municipalities).forEach((list) => {
        items = items.concat(list);
      });
      items = Array.from(new Set(items)).sort();
    }
    municipalitySelect.innerHTML =
      `<option value="">Todos</option>` +
      items.map((m) => `<option value="${m}" ${m === selected ? "selected" : ""}>${m}</option>`).join("");
  };

  if (provinceSelect && municipalitySelect) {
    renderMunicipalities(provinceSelect.value, municipalitySelect.value);
    provinceSelect.addEventListener("change", () => {
      renderMunicipalities(provinceSelect.value, "");
      applyFilters();
    });
    municipalitySelect.addEventListener("change", applyFilters);
  }

  map.on("click", (event) => {
    closeActivePopup();
    const lat = event.latlng.lat.toFixed(6);
    const lng = event.latlng.lng.toFixed(6);
    const newUrl = mapEl.dataset.newUrl;

    const popup = L.popup({ maxWidth: 260 })
      .setLatLng(event.latlng)
      .setContent(`
        <div style="color:#111;max-width:240px;">
          <div style="font-weight:600;margin-bottom:8px;">Crear reporte aqui</div>
          <button type="button" data-create-report-btn style="background:#6ee7b7;border:none;padding:8px 10px;border-radius:6px;cursor:pointer;">Abrir formulario</button>
        </div>
      `)
      .openOn(map);

    activePopup = popup;

    const bindCreateReportButton = () => {
      const popupEl = popup.getElement();
      if (!popupEl) return false;
      L.DomEvent.disableClickPropagation(popupEl);
      const btn = popupEl.querySelector("[data-create-report-btn]");
      if (!btn) return false;
      if (btn.dataset.bound === "1") return true;
      btn.dataset.bound = "1";
      btn.addEventListener("click", (clickEvent) => {
        clickEvent.preventDefault();
        clickEvent.stopPropagation();
        const zoom = map ? map.getZoom() : "";
        const zoomParam = Number.isFinite(zoom) ? `&zoom=${zoom}` : "";
        const targetUrl = `${newUrl}?lat=${lat}&lng=${lng}${zoomParam}`;
        if (window.openReportModal) {
          window.openReportModal(targetUrl);
        } else {
          window.location.href = targetUrl;
        }
      });
      return true;
    };

    if (!bindCreateReportButton()) {
      requestAnimationFrame(bindCreateReportButton);
    }
  });

  if (recentTimer) {
    clearInterval(recentTimer);
  }
  recentTimer = setInterval(() => {
    refreshRecent();
    refreshAlerts();
  }, 8000);
}
