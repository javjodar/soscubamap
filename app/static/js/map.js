let map;
let markers = [];
let markerIndex = new Map();
let shapeLayers = [];
let connectivityGeoLayer;
let connectivityRefreshTimer;
let connectivityLastSnapshotId = null;
let connectivityLastRenderKey = null;
let connectivityRefreshSeconds = 300;
let connectivityWindowHours = 24;
let connectivityLastPayload = null;
let selectedConnectivityProvince = "";
let selectedConnectivityProvinceState = null;
let activeBaseMode = "map";
let mapHintElement;
let reportLegendSection;
let connectivityLegendOverlay;
let connectivityUpdatedLabel;
let connectivityTrafficPanel;
let connectivityTrafficValue;
let connectivityTrafficDelta;
let connectivityTrafficDrop;
let connectivityTrafficNote;
let connectivitySparkMain;
let connectivitySparkPrev;
let connectivityWindowButtons = [];
let connectivityProvincePanel;
let connectivityProvinceTitle;
let connectivityProvinceStatus;
let connectivityProvinceRange;
let connectivityProvinceChartMain;
let connectivityProvinceChartPrev;
let connectivityProvinceLog;
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
const MOBILE_VIEWPORT_QUERY = "(max-width: 900px)";
const HAVANA_CENTER = [23.1136, -82.3666];
const MOBILE_HAVANA_ZOOM = 9;
const MAP_PROVIDER_LEAFLET = "leaflet";
const MAP_PROVIDER_GOOGLE = "google";
const CONNECTIVITY_STATUS_COLORS = {
  normal: "#2E7D32",
  degraded: "#F9A825",
  severe: "#EF6C00",
  critical: "#C62828",
  unknown: "#667085",
};
const CONNECTIVITY_STATUS_LABELS = {
  normal: "Normal",
  degraded: "Degradacion leve",
  severe: "Problemas severos",
  critical: "Apagon o conectividad critica",
  unknown: "Sin datos",
};

function canUseGoogleMutant(provider) {
  if (provider !== MAP_PROVIDER_GOOGLE) return false;
  return (
    typeof L !== "undefined" &&
    L.gridLayer &&
    typeof L.gridLayer.googleMutant === "function" &&
    typeof window.google !== "undefined" &&
    window.google &&
    window.google.maps
  );
}

function buildMainBaseLayers(provider) {
  const useGoogle = canUseGoogleMutant(provider);

  if (useGoogle) {
    const mapLayer = L.gridLayer.googleMutant({
      type: "roadmap",
      maxZoom: 20,
    });
    const satelliteLayer = L.gridLayer.googleMutant({
      type: "hybrid",
      maxZoom: 20,
    });
    const connectivityLayer = L.gridLayer.googleMutant({
      type: "roadmap",
      maxZoom: 20,
    });
    return {
      useGoogle,
      streetsLayer: mapLayer,
      satelliteLayer,
      satelliteLabelsLayer: null,
      connectivityBaseLayer: connectivityLayer,
    };
  }

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
  const connectivityBaseLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  });
  return {
    useGoogle,
    streetsLayer,
    satelliteLayer,
    satelliteLabelsLayer,
    connectivityBaseLayer,
  };
}

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
  "sede-gobierno": "fa-building-columns",
  "sede-ujc": "fa-flag",
  "sede-seguridad-estado": "fa-user-secret",
  "unidad-militar": "fa-person-military-pointing",
  "base-espionaje": "fa-satellite-dish",
  "otros": "fa-circle-question",
};

const CATEGORY_IMAGES = {
  "sede-pcc": "/static/img/Communist_Party_of_Cuba_logo.svg.png",
  "sede-ujc": "/static/img/ujc.png",
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

function setMapHintVisible(visible) {
  if (!mapHintElement) return;
  mapHintElement.hidden = !visible;
}

function setReportLegendVisible(visible) {
  if (!reportLegendSection) return;
  reportLegendSection.hidden = !visible;
}

function setConnectivityLegendVisible(visible) {
  if (!connectivityLegendOverlay) return;
  connectivityLegendOverlay.hidden = !visible;
}

function setActiveConnectivityWindow(hours) {
  const numeric = Number(hours);
  if (![2, 6, 24].includes(numeric)) return;
  connectivityWindowHours = numeric;
  connectivityWindowButtons.forEach((button) => {
    const buttonHours = Number(button?.dataset?.connectivityWindowHours);
    const isActive = buttonHours === connectivityWindowHours;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function formatUtcLabel(timestamp) {
  if (!timestamp) return "";
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleString("es-ES", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    hour12: false,
  });
}

function formatLabelInZone(timestamp, timeZone) {
  if (!timestamp) return "";
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return "";
  const parts = new Intl.DateTimeFormat("es-ES", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone,
  }).formatToParts(parsed);
  const getPart = (type) => parts.find((item) => item.type === type)?.value || "";
  const year = getPart("year");
  const month = getPart("month");
  const day = getPart("day");
  const hour = getPart("hour");
  const minute = getPart("minute");
  return `${year}-${month}-${day} ${hour}:${minute}`;
}

function formatUtcAndCuba(timestamp) {
  const utc = formatLabelInZone(timestamp, "UTC");
  const cuba = formatLabelInZone(timestamp, "America/Havana");
  if (!utc && !cuba) return "N/D";
  if (!utc) return `${cuba} (Cuba)`;
  if (!cuba) return `${utc} UTC`;
  return `${utc} UTC (${cuba} Cuba)`;
}

function formatMetricValue(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "N/D";
  if (Math.abs(numeric) >= 1000) {
    return numeric.toLocaleString("es-ES", { maximumFractionDigits: 0 });
  }
  if (Math.abs(numeric) >= 10) {
    return numeric.toLocaleString("es-ES", { maximumFractionDigits: 2 });
  }
  return numeric.toLocaleString("es-ES", { maximumFractionDigits: 6 });
}

function formatPercentValue(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "N/D";
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toFixed(1)}%`;
}

function buildSparklinePath(values, minValue, maxValue, width = 280, height = 56, pad = 4) {
  if (!Array.isArray(values) || values.length < 2) return "";
  const valid = values.filter((value) => Number.isFinite(Number(value))).map((value) => Number(value));
  if (valid.length < 2) return "";

  const min = Number.isFinite(minValue) ? Number(minValue) : Math.min(...valid);
  const max = Number.isFinite(maxValue) ? Number(maxValue) : Math.max(...valid);
  const span = Math.max(max - min, 1e-9);
  const innerWidth = Math.max(width - pad * 2, 1);
  const innerHeight = Math.max(height - pad * 2, 1);

  let path = "";
  values.forEach((value, idx) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    const x = pad + (values.length === 1 ? 0 : (idx / (values.length - 1)) * innerWidth);
    const y = height - pad - ((numeric - min) / span) * innerHeight;
    path += `${path ? " L" : "M"} ${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  return path;
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
  if (activeBaseMode === "connectivity") {
    if (Array.isArray(allPosts) && payload.status === "approved") {
      allPosts.unshift(payload);
    }
    updateLegendCounts(allPosts);
    refreshRecent();
    refreshAlerts();
    return;
  }

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

function clearConnectivityLayer() {
  if (connectivityGeoLayer && map) {
    map.removeLayer(connectivityGeoLayer);
  }
  connectivityGeoLayer = null;
}

function normalizeProvinceName(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function getConnectivitySeries(payload) {
  if (payload?.http_requests_window) return payload.http_requests_window;
  return payload?.http_requests_24h || {};
}

function getConnectivitySeriesForProvince(payload, provinceName) {
  const byProvince = payload?.http_requests_window_by_province || {};
  const selected = normalizeProvinceName(provinceName);
  if (selected && byProvince && typeof byProvince === "object") {
    const entries = Object.entries(byProvince);
    for (let idx = 0; idx < entries.length; idx += 1) {
      const [name, summary] = entries[idx];
      if (normalizeProvinceName(name) === selected) return summary || {};
    }
  }
  return getConnectivitySeries(payload);
}

function stopConnectivityPolling() {
  if (!connectivityRefreshTimer) return;
  clearInterval(connectivityRefreshTimer);
  connectivityRefreshTimer = null;
}

function styleForConnectivityFeature(feature) {
  const status = feature?.properties?.status || "unknown";
  const color = CONNECTIVITY_STATUS_COLORS[status] || CONNECTIVITY_STATUS_COLORS.unknown;
  const province = feature?.properties?.province || "";
  const selected =
    !!selectedConnectivityProvince &&
    normalizeProvinceName(province) === normalizeProvinceName(selectedConnectivityProvince);
  return {
    color: selected ? "#f8fafc" : "#0f172a",
    weight: selected ? 2.2 : 1.2,
    opacity: 0.85,
    fillColor: color,
    fillOpacity: selected ? 0.7 : status === "unknown" ? 0.24 : 0.48,
  };
}

function onConnectivityFeature(feature, layer) {
  const province = feature?.properties?.province || "Provincia";
  const status = feature?.properties?.status || "unknown";
  const label = feature?.properties?.status_label || CONNECTIVITY_STATUS_LABELS[status] || "Sin datos";
  const score = feature?.properties?.score;
  const scoreLabel = Number.isFinite(Number(score)) ? `${Number(score).toFixed(1)}%` : "N/D";
  layer.bindTooltip(`${province}: ${label} (${scoreLabel})`, {
    sticky: true,
    direction: "top",
  });

  layer.on("click", () => {
    selectedConnectivityProvince = province;
    selectedConnectivityProvinceState = {
      province,
      status: feature?.properties?.status || "unknown",
      status_label: label,
      score: Number.isFinite(Number(score)) ? Number(score) : null,
    };
    if (connectivityGeoLayer?.setStyle) {
      connectivityGeoLayer.setStyle(styleForConnectivityFeature);
    }
    renderConnectivityProvincePanel(connectivityLastPayload);
  });
}

function renderConnectivityData(payload) {
  if (!map || !payload) return;

  clearConnectivityLayer();

  const geojson = payload.geojson || {};
  const features = Array.isArray(geojson.features) ? geojson.features : [];
  if (!features.length) return;

  connectivityGeoLayer = L.geoJSON(geojson, {
    style: styleForConnectivityFeature,
    onEachFeature: onConnectivityFeature,
  }).addTo(map);
}

async function fetchConnectivityData() {
  const params = new URLSearchParams();
  if ([2, 6, 24].includes(Number(connectivityWindowHours))) {
    params.set("window_hours", String(connectivityWindowHours));
  }
  const url = params.toString() ? `/api/connectivity/latest?${params}` : "/api/connectivity/latest";
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("No se pudo cargar conectividad");
  return await res.json();
}

function updateConnectivityUpdatedLabel(payload) {
  if (!connectivityUpdatedLabel) return;
  const snapshot = payload?.snapshot;
  const windowInfo = payload?.window || {};
  const windowHours = Number(windowInfo.hours);
  const windowPrefix = [2, 6, 24].includes(windowHours)
    ? `Ventana: ultimas ${windowHours}h`
    : "";
  if (!snapshot?.observed_at_utc) {
    connectivityUpdatedLabel.textContent = windowPrefix
      ? `${windowPrefix} | Sin datos recientes.`
      : "Sin datos recientes.";
    return;
  }
  const observed = formatUtcAndCuba(snapshot.observed_at_utc);
  const staleText = payload?.stale ? " (dato no reciente)" : "";
  let text = observed
    ? `Ultima actualizacion (UTC): ${observed}${staleText}`
    : `Ultima actualizacion (UTC): N/D${staleText}`;
  if (windowPrefix) {
    const score = Number(windowInfo.national_score);
    const statusLabel = windowInfo.national_status_label || "Sin datos";
    const scoreText = Number.isFinite(score) ? `${score.toFixed(1)}%` : "N/D";
    text = `${windowPrefix} | Estado ventana: ${statusLabel} (${scoreText}) | ${text}`;
  }
  if (!payload?.has_geojson) {
    text += " | GeoJSON provincial no configurado.";
  }
  connectivityUpdatedLabel.textContent = text;
}

function updateConnectivityTrafficPanel(payload) {
  if (
    !connectivityTrafficPanel ||
    !connectivityTrafficValue ||
    !connectivityTrafficDelta ||
    !connectivityTrafficDrop ||
    !connectivityTrafficNote
  ) {
    return;
  }
  const traffic = getConnectivitySeries(payload);
  const available = !!traffic.available;
  const seriesMain = Array.isArray(traffic.series_main) ? traffic.series_main : [];
  const seriesPrev = Array.isArray(traffic.series_previous_aligned)
    ? traffic.series_previous_aligned
    : [];

  if (!available || !seriesMain.length) {
    connectivityTrafficValue.textContent = "N/D";
    connectivityTrafficDelta.textContent = "Variacion vs control: N/D";
    connectivityTrafficDrop.textContent = "Caida maxima: N/D";
    connectivityTrafficNote.textContent = traffic.reason || "Sin serie disponible para la ventana activa.";
    if (connectivitySparkMain) connectivitySparkMain.setAttribute("d", "");
    if (connectivitySparkPrev) connectivitySparkPrev.setAttribute("d", "");
    return;
  }

  const latestMain = Number(traffic.latest_main_value);
  const latestPrev = Number(traffic.latest_previous_value);
  const deltaPct = Number(traffic.delta_pct);
  const maxDrop = Number(traffic.max_drop_from_peak_pct);
  const hours = Number(traffic.window_hours || payload?.window?.hours);
  const hoursLabel = [2, 6, 24].includes(hours) ? `${hours}h` : "ventana";

  connectivityTrafficValue.textContent = `Ultimo valor: ${formatMetricValue(latestMain)}`;
  connectivityTrafficDelta.textContent = `Variacion vs control: ${formatPercentValue(deltaPct)} (${formatMetricValue(
    latestPrev
  )})`;
  connectivityTrafficDrop.textContent = `Caida maxima ${hoursLabel}: ${formatPercentValue(maxDrop)}`;

  const latestTs = traffic.latest_timestamp_utc
    ? formatUtcAndCuba(traffic.latest_timestamp_utc)
    : "";
  const pointCount = seriesMain.length;
  connectivityTrafficNote.textContent = latestTs
    ? `Puntos: ${pointCount} · Ultimo punto (UTC): ${latestTs}`
    : `Puntos: ${pointCount}`;

  const prevMap = new Map(
    seriesPrev.map((item) => {
      const value = Number(item?.value);
      return [item?.timestamp_utc || "", Number.isFinite(value) ? value : NaN];
    })
  );
  const mainValues = seriesMain.map((item) => Number(item?.value));
  const prevValues = seriesMain.map((item) => {
    const key = item?.timestamp_utc || "";
    return prevMap.has(key) ? prevMap.get(key) : NaN;
  });

  const allValues = mainValues
    .concat(prevValues)
    .filter((value) => Number.isFinite(Number(value)))
    .map((value) => Number(value));
  const minValue = allValues.length ? Math.min(...allValues) : 0;
  const maxValue = allValues.length ? Math.max(...allValues) : 1;

  if (connectivitySparkMain) {
    connectivitySparkMain.setAttribute(
      "d",
      buildSparklinePath(mainValues, minValue, maxValue)
    );
  }
  if (connectivitySparkPrev) {
    connectivitySparkPrev.setAttribute(
      "d",
      buildSparklinePath(prevValues, minValue, maxValue)
    );
  }
}

function computeNotableDrops(seriesMain, seriesPrev, topN = 8) {
  const prevMap = new Map(
    (seriesPrev || []).map((item) => {
      const value = Number(item?.value);
      return [item?.timestamp_utc || "", Number.isFinite(value) ? value : NaN];
    })
  );
  const events = [];
  for (let idx = 1; idx < (seriesMain || []).length; idx += 1) {
    const current = seriesMain[idx] || {};
    const previous = seriesMain[idx - 1] || {};
    const currValue = Number(current.value);
    const prevValue = Number(previous.value);
    if (!Number.isFinite(currValue) || !Number.isFinite(prevValue) || currValue >= prevValue) continue;
    const dropAbs = prevValue - currValue;
    const dropPct = prevValue > 0 ? (dropAbs / prevValue) * 100 : null;
    const controlValue = prevMap.get(current.timestamp_utc || "");
    events.push({
      timestamp_utc: current.timestamp_utc,
      prev_value: prevValue,
      curr_value: currValue,
      drop_abs: dropAbs,
      drop_pct: Number.isFinite(dropPct) ? dropPct : null,
      control_value: Number.isFinite(controlValue) ? controlValue : null,
    });
  }
  events.sort((a, b) => {
    const aScore = Number.isFinite(a.drop_pct) ? a.drop_pct : a.drop_abs;
    const bScore = Number.isFinite(b.drop_pct) ? b.drop_pct : b.drop_abs;
    return bScore - aScore;
  });
  return events.slice(0, Math.max(1, topN));
}

function syncSelectedProvinceStateFromPayload(payload) {
  if (!selectedConnectivityProvince || !payload) return;
  const provinceList = Array.isArray(payload.provinces) ? payload.provinces : [];
  const selectedKey = normalizeProvinceName(selectedConnectivityProvince);
  const row = provinceList.find((item) => {
    const rowName = item?.province || "";
    return normalizeProvinceName(rowName) === selectedKey;
  });
  if (!row) return;
  selectedConnectivityProvinceState = {
    province: row.province,
    status: row.status || "unknown",
    status_label: row.status_label || CONNECTIVITY_STATUS_LABELS[row.status] || "Sin datos",
    score: Number.isFinite(Number(row.score)) ? Number(row.score) : null,
  };
}

function renderConnectivityProvincePanel(payload) {
  if (
    !connectivityProvincePanel ||
    !connectivityProvinceTitle ||
    !connectivityProvinceStatus ||
    !connectivityProvinceRange ||
    !connectivityProvinceChartMain ||
    !connectivityProvinceChartPrev ||
    !connectivityProvinceLog
  ) {
    return;
  }

  const hasSelection = !!selectedConnectivityProvince;
  if (!hasSelection || !payload) {
    connectivityProvinceTitle.textContent = "Selecciona una provincia";
    connectivityProvinceStatus.textContent = "Haz clic en una provincia para ver detalle horario.";
    connectivityProvinceRange.textContent = "";
    connectivityProvinceChartMain.setAttribute("d", "");
    connectivityProvinceChartPrev.setAttribute("d", "");
    connectivityProvinceLog.innerHTML =
      '<div class="connectivity-province-log-empty">Sin provincia seleccionada.</div>';
    return;
  }

  const traffic = getConnectivitySeriesForProvince(payload, selectedConnectivityProvince);
  const baseSeriesMain = Array.isArray(traffic.series_main) ? traffic.series_main : [];
  const baseSeriesPrev = Array.isArray(traffic.series_previous_aligned)
    ? traffic.series_previous_aligned
    : [];
  const provinceState = selectedConnectivityProvinceState || {};
  const seriesMain = baseSeriesMain;
  const seriesPrev = baseSeriesPrev;
  const score = Number(provinceState.score);
  const scoreText = Number.isFinite(score) ? `${score.toFixed(1)}%` : "N/D";
  const statusLabel = provinceState.status_label || "Sin datos";
  connectivityProvinceTitle.textContent = `Provincia: ${selectedConnectivityProvince}`;
  connectivityProvinceStatus.textContent = `Estado: ${statusLabel} (${scoreText}) · Datos Radar por geoId provincial (estimados).`;

  const windowInfo = payload?.window || {};
  const rangeStart = windowInfo.start_utc ? formatUtcAndCuba(windowInfo.start_utc) : "N/D";
  const rangeEnd = windowInfo.end_utc ? formatUtcAndCuba(windowInfo.end_utc) : "N/D";
  const hours = Number(windowInfo.hours);
  const hoursText = [2, 6, 24].includes(hours) ? `${hours}h` : "N/D";
  connectivityProvinceRange.textContent = `Ventana ${hoursText}: ${rangeStart} -> ${rangeEnd}`;

  if (!traffic.available || !seriesMain.length) {
    connectivityProvinceChartMain.setAttribute("d", "");
    connectivityProvinceChartPrev.setAttribute("d", "");
    connectivityProvinceLog.innerHTML =
      '<div class="connectivity-province-log-empty">Sin serie disponible para esta ventana.</div>';
    return;
  }

  const prevMap = new Map(
    seriesPrev.map((item) => {
      const value = Number(item?.value);
      return [item?.timestamp_utc || "", Number.isFinite(value) ? value : NaN];
    })
  );
  const mainValues = seriesMain.map((item) => Number(item?.value));
  const prevValues = seriesMain.map((item) => {
    const key = item?.timestamp_utc || "";
    return prevMap.has(key) ? prevMap.get(key) : NaN;
  });
  const allValues = mainValues
    .concat(prevValues)
    .filter((value) => Number.isFinite(Number(value)))
    .map((value) => Number(value));
  const minValue = allValues.length ? Math.min(...allValues) : 0;
  const maxValue = allValues.length ? Math.max(...allValues) : 1;
  connectivityProvinceChartMain.setAttribute(
    "d",
    buildSparklinePath(mainValues, minValue, maxValue, 280, 86)
  );
  connectivityProvinceChartPrev.setAttribute(
    "d",
    buildSparklinePath(prevValues, minValue, maxValue, 280, 86)
  );

  const drops = computeNotableDrops(seriesMain, seriesPrev, 10);
  if (!drops.length) {
    connectivityProvinceLog.innerHTML =
      '<div class="connectivity-province-log-empty">No se detectaron caídas notorias por hora.</div>';
    return;
  }

  connectivityProvinceLog.innerHTML = drops
    .map((drop, idx) => {
      const when = formatUtcAndCuba(drop.timestamp_utc);
      const dropPct = Number.isFinite(drop.drop_pct) ? `-${drop.drop_pct.toFixed(1)}%` : "N/D";
      const prevText = formatMetricValue(drop.prev_value);
      const currText = formatMetricValue(drop.curr_value);
      const controlText = Number.isFinite(drop.control_value)
        ? formatMetricValue(drop.control_value)
        : "N/D";
      return `
        <div class="connectivity-province-log-item">
          <div><strong>#${idx + 1}</strong> Hora: ${escapeHtml(when)}</div>
          <div>Caída: ${escapeHtml(dropPct)} (${escapeHtml(prevText)} -> ${escapeHtml(currText)})</div>
          <div>Control en esa hora: ${escapeHtml(controlText)}</div>
        </div>
      `;
    })
    .join("");
}

async function refreshConnectivityLayer() {
  if (activeBaseMode !== "connectivity") return;
  try {
    const payload = await fetchConnectivityData();
    connectivityLastPayload = payload;
    const snapshotId = payload?.snapshot?.id || null;
    const renderKey = [
      snapshotId,
      payload?.window?.hours || "",
      payload?.window?.snapshot_count || "",
      payload?.window?.national_score ?? "",
      payload?.window?.latest_observed_at_utc || "",
      payload?.window?.max_drop_from_peak_pct ?? "",
      payload?.has_geojson ? "1" : "0",
    ].join("|");
    if (renderKey !== connectivityLastRenderKey || !connectivityGeoLayer) {
      renderConnectivityData(payload);
      connectivityLastSnapshotId = snapshotId;
      connectivityLastRenderKey = renderKey;
    }
    syncSelectedProvinceStateFromPayload(payload);
    if (selectedConnectivityProvince && connectivityGeoLayer?.setStyle) {
      connectivityGeoLayer.setStyle(styleForConnectivityFeature);
    }
    updateConnectivityUpdatedLabel(payload);
    updateConnectivityTrafficPanel(payload);
    renderConnectivityProvincePanel(payload);
  } catch (err) {
    if (connectivityUpdatedLabel) {
      connectivityUpdatedLabel.textContent = "No fue posible actualizar conectividad.";
    }
    if (connectivityTrafficNote) {
      connectivityTrafficNote.textContent = "No fue posible cargar la serie HTTP de la ventana.";
    }
    renderConnectivityProvincePanel(null);
  }
}

function startConnectivityPolling() {
  stopConnectivityPolling();
  const intervalMs = Math.max(30, Number(connectivityRefreshSeconds) || 300) * 1000;
  connectivityRefreshTimer = setInterval(() => {
    refreshConnectivityLayer();
  }, intervalMs);
}

async function enableConnectivityMode() {
  activeBaseMode = "connectivity";
  clearMarkers();
  closeActivePopup();
  setMapHintVisible(false);
  setReportLegendVisible(false);
  setConnectivityLegendVisible(true);
  await refreshConnectivityLayer();
  startConnectivityPolling();
}

function disableConnectivityMode() {
  if (activeBaseMode !== "connectivity") return;
  activeBaseMode = "map";
  stopConnectivityPolling();
  clearConnectivityLayer();
  connectivityLastSnapshotId = null;
  connectivityLastRenderKey = null;
  connectivityLastPayload = null;
  selectedConnectivityProvince = "";
  selectedConnectivityProvinceState = null;
  setConnectivityLegendVisible(false);
  setReportLegendVisible(true);
  setMapHintVisible(true);
  renderConnectivityProvincePanel(null);
}

async function applyFilters() {
  if (activeBaseMode === "connectivity") {
    clearMarkers();
    updateLegendCounts(allPosts);
    return;
  }

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
  connectivityRefreshSeconds = Number(mapEl.dataset.connectivityRefreshSeconds || 300);
  const preferredProvider = (mapEl.dataset.mapProvider || MAP_PROVIDER_LEAFLET).toLowerCase();
  mapHintElement = document.getElementById("mapHint");
  reportLegendSection = document.getElementById("reportLegendSection");
  connectivityLegendOverlay = document.getElementById("connectivityLegendOverlay");
  connectivityUpdatedLabel = document.getElementById("connectivityUpdatedLabel");
  connectivityTrafficPanel = document.getElementById("connectivityTrafficPanel");
  connectivityTrafficValue = document.getElementById("connectivityTrafficValue");
  connectivityTrafficDelta = document.getElementById("connectivityTrafficDelta");
  connectivityTrafficDrop = document.getElementById("connectivityTrafficDrop");
  connectivityTrafficNote = document.getElementById("connectivityTrafficNote");
  connectivitySparkMain = document.getElementById("connectivitySparkMain");
  connectivitySparkPrev = document.getElementById("connectivitySparkPrev");
  connectivityProvincePanel = document.getElementById("connectivityProvincePanel");
  connectivityProvinceTitle = document.getElementById("connectivityProvinceTitle");
  connectivityProvinceStatus = document.getElementById("connectivityProvinceStatus");
  connectivityProvinceRange = document.getElementById("connectivityProvinceRange");
  connectivityProvinceChartMain = document.getElementById("connectivityProvinceChartMain");
  connectivityProvinceChartPrev = document.getElementById("connectivityProvinceChartPrev");
  connectivityProvinceLog = document.getElementById("connectivityProvinceLog");
  connectivityWindowButtons = Array.from(
    document.querySelectorAll("[data-connectivity-window-hours]")
  );
  setActiveConnectivityWindow(connectivityWindowHours);
  renderConnectivityProvincePanel(null);

  connectivityWindowButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const hours = Number(button.dataset.connectivityWindowHours);
      if (![2, 6, 24].includes(hours)) return;
      const changed = hours !== connectivityWindowHours;
      setActiveConnectivityWindow(hours);
      if (!changed) return;
      connectivityLastRenderKey = null;
      if (activeBaseMode === "connectivity") {
        await refreshConnectivityLayer();
      }
    });
  });

  map = L.map(mapEl, {
    zoomControl: true,
    minZoom: 4,
    maxZoom: 19,
  });
  enableMiddleClickPan(map);
  const layerSet = buildMainBaseLayers(preferredProvider);
  const streetsLayer = layerSet.streetsLayer;
  const satelliteLayer = layerSet.satelliteLayer;
  const satelliteLabelsLayer = layerSet.satelliteLabelsLayer;
  const connectivityBaseLayer = layerSet.connectivityBaseLayer;

  streetsLayer.addTo(map);
  L.control
    .layers(
      {
        Mapa: streetsLayer,
        Satelite: satelliteLayer,
        Conectividad: connectivityBaseLayer,
      },
      {},
      { collapsed: true }
    )
    .addTo(map);
  setMapHintVisible(true);
  setReportLegendVisible(true);
  setConnectivityLegendVisible(false);

  map.on("baselayerchange", (event) => {
    if (event.layer === connectivityBaseLayer) {
      if (satelliteLabelsLayer && map.hasLayer(satelliteLabelsLayer)) {
        map.removeLayer(satelliteLabelsLayer);
      }
      enableConnectivityMode();
      return;
    }

    if (activeBaseMode === "connectivity") {
      disableConnectivityMode();
    }

    activeBaseMode = event.layer === satelliteLayer ? "satellite" : "map";
    if (satelliteLabelsLayer && event.layer === satelliteLayer) {
      if (!map.hasLayer(satelliteLabelsLayer)) satelliteLabelsLayer.addTo(map);
    } else if (satelliteLabelsLayer && map.hasLayer(satelliteLabelsLayer)) {
      map.removeLayer(satelliteLabelsLayer);
    }

    applyFilters();
  });

  const isMobileViewport =
    typeof window.matchMedia === "function" && window.matchMedia(MOBILE_VIEWPORT_QUERY).matches;
  const cubaBounds = cubaLatLngBounds();
  map.fitBounds(cubaBounds, { padding: isMobileViewport ? [0, 0] : [16, 16] });
  if (isMobileViewport) {
    map.setView(HAVANA_CENTER, MOBILE_HAVANA_ZOOM);
  }
  map.setMaxBounds(cubaBounds.pad(isMobileViewport ? 0.2 : 0.35));

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
    if (activeBaseMode === "connectivity") {
      closeActivePopup();
      return;
    }

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
