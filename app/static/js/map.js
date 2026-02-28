let map;
let markers = [];
let clickInfo;
let recentTimer;
let searchBox;
let autocomplete;
let searchMarker;
let geocoder;
let isAdmin = false;

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
}

async function loadPosts(categoryId) {
  const params = categoryId ? `?category_id=${categoryId}` : "";
  const res = await fetch(`/api/posts${params}`);
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
    const info = new google.maps.InfoWindow({
      content: `
        <div style="color:#111;max-width:260px;">
          <h3 style="margin:0 0 6px;">${post.title}</h3>
          <div style="font-size:12px;color:#555;margin-bottom:6px;">${post.category.name}</div>
          <div style="font-size:12px;color:#333;margin-bottom:6px;">${post.anon || "Anon"}</div>
          ${createdText ? `<div style="font-size:12px;color:#666;margin-bottom:6px;">${createdText}</div>` : ""}
          <p style="margin:0 0 6px;">${post.description}</p>
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
          <div style="margin-top:8px;">
            <button id="reportLocationBtn" data-report-url="/reportar-ubicacion/${post.id}" style="background:#0f151a;border:1px solid #1f2a33;color:#6ee7b7;padding:6px 8px;border-radius:6px;cursor:pointer;">Reportar ubicación</button>
            <button id="viewHistoryBtn" data-history-url="/reporte/${post.id}/historial" style="margin-left:6px;background:#0f151a;border:1px solid #1f2a33;color:#9bd1ff;padding:6px 8px;border-radius:6px;cursor:pointer;">Ver historial</button>
            <button id="verifyBtn-${post.id}" data-verify-id="${post.id}" style="margin-left:6px;background:#6ee7b7;border:none;color:#0b0f12;padding:6px 8px;border-radius:6px;cursor:pointer;">Verificar</button>
            <span id="verifyCount-${post.id}" style="margin-left:6px;font-weight:700;color:#0b0f12;background:#6ee7b7;padding:4px 6px;border-radius:6px;">${post.verify_count ?? 0}</span>
            ${
              isAdmin
                ? `<button id="editBtn-${post.id}" data-edit-url="/admin/reportes/${post.id}/editar" style="margin-left:6px;background:#0f151a;border:1px solid #1f2a33;color:#fff;padding:6px 8px;border-radius:6px;cursor:pointer;">Editar</button>`
                : ""
            }
          </div>
          ${post.address ? `<div style="font-size:12px;color:#666;">${post.address}</div>` : ""}
        </div>
      `,
    });

    google.maps.event.addListener(info, "domready", () => {
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

window.handleNewReport = function (payload) {
  if (!payload || !map) return;
  if (payload.status !== "approved") {
    refreshRecent();
    return;
  }
  const position = { lat: payload.latitude, lng: payload.longitude };
  const iconClass = CATEGORY_ICONS[payload.category?.slug] || "fa-location-dot";
  let marker;
  if (google.maps.marker && google.maps.marker.AdvancedMarkerElement) {
    marker = new google.maps.marker.AdvancedMarkerElement({
      position,
      map,
      title: payload.title,
      content: buildMarkerContent(iconClass),
    });
  } else {
    marker = new google.maps.Marker({
      position,
      map,
      title: payload.title,
    });
  }
  map.panTo(position);
  map.setZoom(Math.max(map.getZoom(), 14));
  markers.push(marker);
  refreshRecent();
};

async function applyFilters() {
  const categoryId = document.getElementById("categoryFilter").value;
  const posts = await loadPosts(categoryId);
  renderMarkers(posts);
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
    mapId: mapEl.dataset.mapId || undefined,
    mapTypeId: "hybrid",
    tilt: 0,
    heading: 0,
    rotateControl: true,
    gestureHandling: "greedy",
    // Styles should be managed via Map ID when present
  });

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

  await applyFilters();
  await refreshRecent();

  const filter = document.getElementById("categoryFilter");
  filter.addEventListener("change", applyFilters);

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
          const targetUrl = `${newUrl}?lat=${lat}&lng=${lng}`;
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
