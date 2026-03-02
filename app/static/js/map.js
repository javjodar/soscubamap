let map;
let markers = [];
let clickInfo;
let recentTimer;
let searchBox;
let autocomplete;
let searchMarker;
let geocoder;
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

document.addEventListener("DOMContentLoaded", () => {
  const filters = document.querySelector(".filters");
  const toggle = document.getElementById("filtersToggle");
  if (!filters || !toggle) return;

  toggle.addEventListener("click", () => {
    const isCollapsed = filters.classList.toggle("collapsed");
    toggle.textContent = isCollapsed ? "Mostrar filtros" : "Ocultar filtros";
    toggle.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
  });
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
  "residencia-represor": "fa-house-chimney-user",
  "centro-penitenciario": "fa-landmark-dome",
  "estacion-policia": "fa-building-shield",
  "escuela-pcc": "fa-graduation-cap",
  "sede-pcc": "fa-people-group",
  "sede-seguridad-estado": "fa-user-secret",
  "unidad-militar": "fa-person-military-pointing",
  "base-espionaje": "fa-satellite-dish",
};

const CATEGORY_IMAGES = {
  "sede-pcc": "/static/img/Communist_Party_of_Cuba_logo.svg.png",
};

function buildMarkerContent(iconClass, imageUrl) {
  const wrapper = document.createElement("div");
  wrapper.className = "pin-icon";
  if (imageUrl) {
    const img = document.createElement("img");
    img.src = imageUrl;
    img.alt = "";
    img.className = "pin-image";
    wrapper.appendChild(img);
  } else {
    wrapper.innerHTML = `<i class="fa-solid ${iconClass}"></i>`;
  }
  return wrapper;
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
  markers.forEach((marker) => marker.setMap(null));
  markers = [];
  pendingMarkers.forEach((marker) => marker.setMap(null));
  pendingMarkers = [];
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

function renderMarkers(posts) {
  clearMarkers();
  posts.forEach((post) => {
    const position = { lat: post.latitude, lng: post.longitude };
    const iconClass = CATEGORY_ICONS[post.category.slug] || "fa-location-dot";
    const imageUrl = CATEGORY_IMAGES[post.category.slug];
    let marker;

    if (google.maps.marker && google.maps.marker.AdvancedMarkerElement) {
      marker = new google.maps.marker.AdvancedMarkerElement({
        position,
        map,
        title: post.title,
        content: buildMarkerContent(iconClass, imageUrl),
      });
    } else {
      marker = new google.maps.Marker({
        position,
        map,
        title: post.title,
        icon: imageUrl
          ? {
              url: imageUrl,
              scaledSize: new google.maps.Size(28, 28),
            }
          : undefined,
      });
    }

    const created = post.created_at ? new Date(post.created_at) : null;
    const createdText = created ? created.toLocaleString("es-ES") : "";
    const mediaItems = Array.isArray(post.media) ? post.media : [];
    const mediaHtml = mediaItems.length
      ? `<div class="info-media">
          ${mediaItems
            .slice(0, 4)
            .map((item) => {
              const url = typeof item === "string" ? item : item?.url;
              if (!url) return "";
              const caption = typeof item === "string" ? "" : item?.caption || "";
              const safeCaption = caption
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll("\"", "&quot;")
                .replaceAll("'", "&#39;");
              return `
                <button class="info-media-thumb" type="button" data-image="${url}" data-caption="${safeCaption}">
                  <img src="${url}" alt="Imagen del reporte" />
                </button>
              `;
            })
            .join("")}
        </div>`
      : "";
    const info = new google.maps.InfoWindow({
      content: `
        <div style="color:#111;max-width:260px;">
          <h3 style="margin:0 0 6px;">${post.title}</h3>
          <div style="font-size:12px;color:#555;margin-bottom:6px;">${post.category.name}</div>
          <div style="font-size:12px;color:#333;margin-bottom:6px;">${post.anon || "Anon"}</div>
          ${createdText ? `<div style="font-size:12px;color:#666;margin-bottom:6px;">${createdText}</div>` : ""}
          <p style="margin:0 0 6px;">${post.description}</p>
          ${mediaHtml}
          ${
            post.links && post.links.length
              ? `<div style="font-size:12px;margin-top:6px;">
                   ${post.links
                     .map(
                       (link) =>
                         `<div><a href="${link}" target="_blank" rel="noopener noreferrer">${link}</a></div>`
                     )
                     .join("")}
                </div>`
              : ""
          }
          <div class="info-actions">
            <button id="detailBtn-${post.id}" data-detail-url="/reporte/${post.id}" class="info-btn info-btn-outline">Ver detalle</button>
            <button id="copyLinkBtn-${post.id}" data-copy-url="/reporte/${post.id}" class="info-btn info-btn-outline">Copiar enlace</button>
            <button id="reportLocationBtn" data-report-url="/reportar-ubicacion/${post.id}" class="info-btn info-btn-outline">Reportar ubicación</button>
            <button id="viewHistoryBtn" data-history-url="/reporte/${post.id}/historial" class="info-btn info-btn-outline info-btn-blue">Ver historial</button>
            <button id="verifyBtn-${post.id}" data-verify-id="${post.id}" class="info-btn info-btn-solid">Verificar</button>
            <span id="verifyCount-${post.id}" class="info-badge">${post.verify_count ?? 0}</span>
            <button id="editBtn-${post.id}" data-edit-url="/reporte/${post.id}/editar" class="info-btn info-btn-outline">Editar</button>
            ${
              isAdmin
                ? `
                  <button id="hideBtn-${post.id}" data-status="hidden" class="info-btn info-btn-outline">Ocultar</button>
                  <button id="deleteBtn-${post.id}" data-status="deleted" class="info-btn info-btn-outline">Eliminar</button>
                `
                : ""
            }
          </div>
          ${post.address ? `<div style="font-size:12px;color:#666;">${post.address}</div>` : ""}
        </div>
      `,
    });

    google.maps.event.addListener(info, "domready", () => {
      const thumbs = document.querySelectorAll(".info-media-thumb");
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
      const detailBtn = document.getElementById(`detailBtn-${post.id}`);
      if (detailBtn) {
        detailBtn.addEventListener("click", () => {
          const url = detailBtn.getAttribute("data-detail-url");
          if (!url) return;
          window.location.href = url;
        });
      }
      const copyBtn = document.getElementById(`copyLinkBtn-${post.id}`);
      if (copyBtn) {
        copyBtn.addEventListener("click", async () => {
          const url = copyBtn.getAttribute("data-copy-url");
          if (!url) return;
          const full = `${window.location.origin}${url}`;
          try {
            await navigator.clipboard.writeText(full);
            copyBtn.textContent = "Enlace copiado";
            setTimeout(() => (copyBtn.textContent = "Copiar enlace"), 1500);
          } catch (e) {
            copyBtn.textContent = "Copia manual";
          }
        });
      }
      const reportBtn = document.getElementById("reportLocationBtn");
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
      const historyBtn = document.getElementById("viewHistoryBtn");
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
      const verifyBtn = document.getElementById(`verifyBtn-${post.id}`);
      if (verifyBtn) {
        verifyBtn.addEventListener("click", async () => {
          const res = await fetch(`/api/posts/${post.id}/verify`, { method: "POST" });
          const data = await res.json();
          const countEl = document.getElementById(`verifyCount-${post.id}`);
          if (countEl && typeof data.verify_count !== "undefined") {
            countEl.textContent = data.verify_count;
          }
        });
      }
      const editBtn = document.getElementById(`editBtn-${post.id}`);
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

      if (isAdmin) {
        const hideBtn = document.getElementById(`hideBtn-${post.id}`);
        const deleteBtn = document.getElementById(`deleteBtn-${post.id}`);
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
            if (!confirm("¿Ocultar este reporte?")) return;
            const result = await updateStatus("hidden");
            if (result && result.ok) {
              allPosts = allPosts.filter((p) => p.id !== post.id);
              applyFilters();
              info.close();
            }
          });
        }
        if (deleteBtn) {
          deleteBtn.addEventListener("click", async () => {
            if (!confirm("¿Eliminar este reporte?")) return;
            const result = await updateStatus("deleted");
            if (result && result.ok) {
              allPosts = allPosts.filter((p) => p.id !== post.id);
              applyFilters();
              info.close();
            }
          });
        }
      }
    });

    marker.addListener("click", () => info.open({ anchor: marker, map }));
    markers.push(marker);

    if (post.polygon_geojson) {
      try {
        const geo = JSON.parse(post.polygon_geojson);
        if (geo && geo.type === "Polygon" && geo.coordinates?.length) {
          const path = geo.coordinates[0].map(([lng, lat]) => ({ lat, lng }));
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
    }
  });
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
  const position = { lat: payload.latitude, lng: payload.longitude };
  const iconClass = CATEGORY_ICONS[payload.category?.slug] || "fa-location-dot";
  const imageUrl = CATEGORY_IMAGES[payload.category?.slug];

  if (payload.status !== "approved") {
    let marker;
    if (google.maps.marker && google.maps.marker.AdvancedMarkerElement) {
      marker = new google.maps.marker.AdvancedMarkerElement({
        position,
        map,
        title: payload.title || "Reporte pendiente",
        content: buildMarkerContent("fa-hourglass-half", imageUrl),
      });
    } else {
      marker = new google.maps.Marker({
        position,
        map,
        title: payload.title || "Reporte pendiente",
        icon: imageUrl
          ? {
              url: imageUrl,
              scaledSize: new google.maps.Size(28, 28),
            }
          : undefined,
      });
    }
    pendingMarkers.push(marker);
    map.panTo(position);
    const info = new google.maps.InfoWindow({
      content: `
        <div style="color:#111;max-width:240px;">
          <strong>Reporte enviado a moderación.</strong>
          <div style="font-size:12px;margin-top:6px;">Se mostrará cuando sea aprobado.</div>
        </div>
      `,
    });
    info.open({ anchor: marker, map });
    refreshRecent();
    return;
  }

  if (Array.isArray(allPosts)) {
    allPosts.unshift(payload);
  }
  updateLegendCounts(allPosts);
  const selected = getSelectedCategoryIds();
  if (selected.size && payload.category?.id && !selected.has(payload.category.id)) {
    refreshRecent();
    map.panTo(position);
    return;
  }
  let marker;
  if (google.maps.marker && google.maps.marker.AdvancedMarkerElement) {
    marker = new google.maps.marker.AdvancedMarkerElement({
      position,
      map,
      title: payload.title,
      content: buildMarkerContent(iconClass, imageUrl),
    });
  } else {
    marker = new google.maps.Marker({
      position,
      map,
      title: payload.title,
      icon: imageUrl
        ? {
            url: imageUrl,
            scaledSize: new google.maps.Size(28, 28),
          }
        : undefined,
    });
  }
  map.panTo(position);
  markers.push(marker);
  refreshRecent();
};

async function applyFilters() {
  const selected = getSelectedCategoryIds();
  const { province, municipality } = getSelectedLocationFilters();
  let filtered = selected.size
    ? allPosts.filter((post) => selected.has(post.category?.id))
    : [];

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
  const res = await fetch("/api/posts?limit=8");
  return await res.json();
}

function renderRecent(posts) {
  const container = document.getElementById("recentFeed");
  if (!container) return;

  if (!posts.length) {
    container.innerHTML = `<div class="console-empty">Sin aportaciones visibles aún.</div>`;
    return;
  }

  container.innerHTML = posts
    .map(
      (post) => `
        <div class="console-item">
          <div>
            <div class="console-title-row">${post.title}</div>
            <div class="console-meta">${post.category.name}</div>
            <div class="console-meta">${post.anon || "Anon"}</div>
          </div>
          <div class="console-side">
            <div class="console-coords">${post.latitude.toFixed(4)}, ${post.longitude.toFixed(4)}</div>
            <div class="console-time">${post.created_at ? new Date(post.created_at).toLocaleString("es-ES") : ""}</div>
            <button class="btn-secondary console-btn" data-pan-lat="${post.latitude}" data-pan-lng="${post.longitude}">Ver en mapa</button>
          </div>
        </div>
      `
    )
    .join("");

  container.querySelectorAll("[data-pan-lat]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const lat = parseFloat(btn.getAttribute("data-pan-lat"));
      const lng = parseFloat(btn.getAttribute("data-pan-lng"));
      if (!Number.isFinite(lat) || !Number.isFinite(lng) || !map) return;
      map.panTo({ lat, lng });
      map.setZoom(Math.max(map.getZoom(), 14));
    });
  });
}

async function refreshRecent() {
  try {
    const posts = await loadRecent();
    renderRecent(posts);
  } catch (err) {
    // no-op for now
  }
}

window.initMap = async function () {
  setupMapImageModal();
  syncLegend();
  const mapEl = document.getElementById("map");
  const apiKey = mapEl.dataset.apiKey;
  isAdmin = mapEl.dataset.isAdmin === "1";
  if (!apiKey) {
    refreshRecent();
    return;
  }

  const isMobile = window.matchMedia("(max-width: 900px)").matches;
  const baseZoom = isMobile ? 6 : 7;

  map = new google.maps.Map(mapEl, {
    center: { lat: 21.521757, lng: -77.781167 },
    zoom: baseZoom,
    minZoom: baseZoom,
    maxZoom: undefined,
    restriction: { latLngBounds: CUBA_BOUNDS, strictBounds: true },
    mapId: mapEl.dataset.mapId || undefined,
    mapTypeId: "hybrid",
    tilt: 0,
    heading: 0,
    rotateControl: true,
    gestureHandling: "greedy",
    zoomControl: true,
    scrollwheel: true,
    disableDoubleClickZoom: false,
    keyboardShortcuts: true,
    // Styles should be managed via Map ID when present
  });

  const params = new URLSearchParams(window.location.search);
  const latParam = parseFloat(params.get("lat"));
  const lngParam = parseFloat(params.get("lng"));
  if (Number.isFinite(latParam) && Number.isFinite(lngParam)) {
    const target = { lat: latParam, lng: lngParam };
    map.setCenter(target);
    map.setZoom(Math.max(map.getZoom(), 14));
    new google.maps.Marker({ position: target, map, title: "Ubicación" });
  }

  const searchInput = document.getElementById("mapSearch");
  if (searchInput && google.maps.places) {
    const cubaBounds = new google.maps.LatLngBounds(
      { lat: 19.8, lng: -85.2 },
      { lat: 23.7, lng: -73.9 }
    );
    geocoder = new google.maps.Geocoder();
    autocomplete = new google.maps.places.Autocomplete(searchInput, {
      bounds: cubaBounds,
      componentRestrictions: { country: "cu" },
      fields: ["geometry", "name"],
      types: ["geocode"],
    });
    autocomplete.addListener("place_changed", () => {
      const place = autocomplete.getPlace();
      if (!place.geometry || !place.geometry.location) return;
      focusSearchResult(place.geometry, place.name);
    });

    searchInput.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const query = searchInput.value.trim();
      if (!query || !geocoder) return;
      geocoder.geocode(
        {
          address: query,
          bounds: cubaBounds,
          componentRestrictions: { country: "cu" },
        },
        (results, status) => {
          if (status !== "OK" || !results?.length) return;
          const result = results[0];
          focusSearchResult(result.geometry, result.formatted_address);
        }
      );
    });
  }

  allPosts = await loadPosts();
  await applyFilters();
  await refreshRecent();

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

  clickInfo = new google.maps.InfoWindow();
  map.addListener("click", (event) => {
    const lat = event.latLng.lat().toFixed(6);
    const lng = event.latLng.lng().toFixed(6);
    const newUrl = mapEl.dataset.newUrl;

    clickInfo.setContent(`
      <div style="color:#111;max-width:240px;">
        <div style="font-weight:600;margin-bottom:8px;">Crear reporte aquí</div>
        <button id="createReportBtn" style="background:#6ee7b7;border:none;padding:8px 10px;border-radius:6px;cursor:pointer;">Abrir formulario</button>
      </div>
    `);
    clickInfo.setPosition(event.latLng);
    clickInfo.open(map);

    google.maps.event.addListenerOnce(clickInfo, "domready", () => {
      const btn = document.getElementById("createReportBtn");
      if (btn) {
        btn.addEventListener("click", () => {
          const zoom = map ? map.getZoom() : "";
          const zoomParam = Number.isFinite(zoom) ? `&zoom=${zoom}` : "";
          const targetUrl = `${newUrl}?lat=${lat}&lng=${lng}${zoomParam}`;
          if (window.openReportModal) {
            window.openReportModal(targetUrl);
          } else {
            window.location.href = targetUrl;
          }
        });
      }
    });
  });

  if (recentTimer) {
    clearInterval(recentTimer);
  }
  recentTimer = setInterval(refreshRecent, 8000);
};

function focusSearchResult(geometry, label) {
  if (geometry.viewport) {
    map.fitBounds(geometry.viewport);
  } else if (geometry.location) {
    map.panTo(geometry.location);
    map.setZoom(Math.max(map.getZoom(), 16));
  }

  if (searchMarker) {
    searchMarker.setMap(null);
  }
  const position = geometry.location || geometry.viewport?.getCenter();
  if (position) {
    searchMarker = new google.maps.Marker({
      position,
      map,
      title: label || "Búsqueda",
    });
  }
}
