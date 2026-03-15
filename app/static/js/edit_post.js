let drawMap;
let drawnItems;
let currentLayer;
let currentMarker;

const CUBA_BOUNDS = {
  north: 24.2,
  south: 19.0,
  west: -86.2,
  east: -73.0,
};
const MAP_PROVIDER_LEAFLET = "leaflet";
const MAP_PROVIDER_GOOGLE = "google";

const normalizeCategoryKey = (value) =>
  (value || "")
    .toString()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

const getCategoryKey = (select) => {
  if (!select) return "";
  const selected = select.options[select.selectedIndex];
  const slug = normalizeCategoryKey(selected?.dataset?.slug || "");
  if (slug) return slug;
  return normalizeCategoryKey(selected?.textContent || "");
};

const isUrgentCategory = (key) => {
  if (!key) return false;
  if (key.includes("accion-represiva")) return true;
  if (key.includes("movimiento") && (key.includes("tropa") || key.includes("militar"))) {
    return true;
  }
  if (key.includes("desconexion")) return true;
  return false;
};

const isResidenciaCategory = (key) => key.includes("residencia") && key.includes("represor");
const isOtrosCategory = (key) => key === "otros" || key.includes("otros");

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

function buildDrawBaseLayers(provider) {
  const useGoogle = canUseGoogleMutant(provider);
  if (useGoogle) {
    return {
      useGoogle,
      streetsLayer: L.gridLayer.googleMutant({
        type: "roadmap",
        maxZoom: 20,
      }),
      satelliteLayer: L.gridLayer.googleMutant({
        type: "hybrid",
        maxZoom: 20,
      }),
      satelliteLabelsLayer: null,
    };
  }

  return {
    useGoogle,
    streetsLayer: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }),
    satelliteLayer: L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        attribution:
          'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
        maxZoom: 19,
      }
    ),
    satelliteLabelsLayer: L.tileLayer(
      "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "Labels &copy; Esri",
        maxZoom: 19,
      }
    ),
  };
}

function cubaBounds() {
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

function setupLinks() {
  const addBtn = document.getElementById("addLinkBtn");
  const list = document.getElementById("linksList");
  if (!addBtn || !list) return;

  addBtn.addEventListener("click", () => {
    const input = document.createElement("input");
    input.type = "url";
    input.name = "links[]";
    input.placeholder = "https://ejemplo.com/fuente";
    list.appendChild(input);
  });
}

function setupProvinceMunicipality() {
  const provSelect = document.getElementById("provinceSelect");
  const munSelect = document.getElementById("municipalitySelect");
  const municipalities = window.CUBA_MUNICIPALITIES || {};
  if (!provSelect || !munSelect) return;

  const selectedProv = provSelect.dataset.selected || provSelect.value;
  if (selectedProv) {
    provSelect.value = selectedProv;
  }

  const selectedMun = munSelect.dataset.selected || "";

  const renderMunicipalities = (province, selected) => {
    let items = [];
    if (province && municipalities[province]) {
      items = municipalities[province];
    } else {
      Object.values(municipalities).forEach((list) => {
        items = items.concat(list);
      });
      items = Array.from(new Set(items)).sort();
    }
    munSelect.innerHTML =
      `<option value="" disabled ${selected ? "" : "selected"}>Elige municipio</option>` +
      items.map((m) => `<option value="${m}" ${m === selected ? "selected" : ""}>${m}</option>`).join("");
  };

  renderMunicipalities(provSelect.value, selectedMun);
  provSelect.addEventListener("change", () => {
    renderMunicipalities(provSelect.value, "");
  });
}

function setupCategoryRequirements() {
  const select = document.getElementById("categorySelect");
  const residenciaFields = document.getElementById("residenciaFields");
  const otrosFields = document.getElementById("otrosFields");
  const movimientoFields = document.getElementById("movimientoFields");
  const repressorInput = document.getElementById("repressorNameInput");
  const otherInput = document.getElementById("otherTypeInput");
  const movementDateInput = document.getElementById("movementDateInput");
  const movementTimeInput = document.getElementById("movementTimeInput");
  const imageInput = document.querySelector('input[name="images"]');
  const status = document.getElementById("editImageStatus");
  const form = document.querySelector(".form-grid");

  const update = () => {
    const key = getCategoryKey(select);
    const isResidencia = isResidenciaCategory(key);
    const isOtros = isOtrosCategory(key);
    const isUrgent = isUrgentCategory(key);
    if (residenciaFields) residenciaFields.classList.toggle("is-hidden", !isResidencia);
    if (otrosFields) otrosFields.classList.toggle("is-hidden", !isOtros);
    if (movimientoFields) movimientoFields.classList.toggle("is-hidden", !isUrgent);
    if (repressorInput) repressorInput.required = isResidencia;
    if (otherInput) otherInput.required = isOtros;
    if (movementDateInput) movementDateInput.required = isUrgent;
    if (movementTimeInput) movementTimeInput.required = isUrgent;
  };

  if (select) {
    select.addEventListener("change", update);
  }

  if (form) {
    form.addEventListener("submit", (e) => {
      const key = getCategoryKey(select);
      if (isResidenciaCategory(key)) {
        const existingCount = form ? parseInt(form.dataset.existingMedia || "0", 10) : 0;
        const newCount = imageInput && imageInput.files ? imageInput.files.length : 0;
        if (existingCount + newCount < 1) {
          e.preventDefault();
          if (status) {
            status.textContent = "Debes subir al menos una imagen del represor.";
          } else {
            alert("Debes subir al menos una imagen del represor.");
          }
        }
      }
      if (isOtrosCategory(key)) {
        const value = (otherInput?.value || "").toLowerCase();
        if (/(represor|represores|chivato|chivata|chivatos|chivatas|informante|informantes|delator|delatores|dse|dgi)/i.test(value)) {
          e.preventDefault();
          if (otherInput) otherInput.focus();
          if (status) {
            status.textContent =
              "El tipo en Otros no puede referirse a represores. Usa la categoria correspondiente.";
          } else {
            alert("El tipo en Otros no puede referirse a represores. Usa la categoria correspondiente.");
          }
        }
      }
      if (isUrgentCategory(key)) {
        const hasDate = movementDateInput && movementDateInput.value;
        const hasTime = movementTimeInput && movementTimeInput.value;
        if (!hasDate || !hasTime) {
          e.preventDefault();
          if (status) {
            status.textContent = "Debes indicar fecha y hora del evento.";
          } else {
            alert("Debes indicar fecha y hora del evento.");
          }
        }
      }
    });
  }

  update();
}

function replaceCurrentLayer(layer) {
  if (!drawnItems) return;
  drawnItems.clearLayers();
  currentLayer = layer || null;
  if (currentLayer) drawnItems.addLayer(currentLayer);
  syncPolygon();
}

function layerToGeoJson(layer) {
  if (!layer) return null;

  if (layer instanceof L.Circle) {
    const center = layer.getLatLng();
    return {
      type: "Point",
      coordinates: [center.lng, center.lat],
      radius_m: layer.getRadius(),
    };
  }

  if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
    const latLngs = layer.getLatLngs();
    const ring = Array.isArray(latLngs) ? latLngs[0] || [] : [];
    const path = ring.map((point) => [point.lng, point.lat]);
    if (path.length) {
      const [firstLng, firstLat] = path[0];
      const [lastLng, lastLat] = path[path.length - 1];
      if (firstLng !== lastLng || firstLat !== lastLat) {
        path.push([firstLng, firstLat]);
      }
    }
    return { type: "Polygon", coordinates: [path] };
  }

  return null;
}

function syncPolygon() {
  const input = document.getElementById("polygonGeojson");
  if (!input) return;
  const geojson = layerToGeoJson(currentLayer);
  input.value = geojson ? JSON.stringify(geojson) : "";
}

function addCenterMarker(center) {
  if (!drawMap || !center) return;
  if (currentMarker) currentMarker.remove();
  currentMarker = L.marker([center.lat, center.lng]).addTo(drawMap);
}

function loadExistingGeometry(mapEl) {
  const existing = mapEl.dataset.geojson || "";
  if (!existing) return;

  try {
    const geo = JSON.parse(existing);
    if (geo.type === "Polygon" && geo.coordinates?.length) {
      const latLngs = geo.coordinates[0].map(([lng, lat]) => [lat, lng]);
      const layer = L.polygon(latLngs, {
        color: "#6ee7b7",
        weight: 2,
        opacity: 0.8,
        fillColor: "#6ee7b7",
        fillOpacity: 0.25,
      });
      replaceCurrentLayer(layer);
      drawMap.fitBounds(layer.getBounds(), { padding: [16, 16] });
    } else if (geo.type === "Point" && geo.coordinates?.length && geo.radius_m) {
      const layer = L.circle([geo.coordinates[1], geo.coordinates[0]], {
        radius: geo.radius_m,
        color: "#6ee7b7",
        weight: 2,
        opacity: 0.8,
        fillColor: "#6ee7b7",
        fillOpacity: 0.25,
      });
      replaceCurrentLayer(layer);
      drawMap.fitBounds(layer.getBounds(), { padding: [16, 16] });
    }
  } catch (err) {
    // ignore invalid geometry
  }
}

function setupDrawMap() {
  const mapEl = document.getElementById("drawMap");
  if (!mapEl || typeof L === "undefined") return;
  const preferredProvider = (mapEl.dataset.mapProvider || MAP_PROVIDER_LEAFLET).toLowerCase();

  const lat = parseFloat(mapEl.dataset.lat);
  const lng = parseFloat(mapEl.dataset.lng);
  const hasPreset = Number.isFinite(lat) && Number.isFinite(lng);
  const center = hasPreset ? [lat, lng] : [21.521757, -77.781167];

  drawMap = L.map(mapEl, {
    minZoom: 7,
    maxZoom: 19,
    zoomControl: true,
  }).setView(center, hasPreset ? 14 : 7);
  enableMiddleClickPan(drawMap);
  const layerSet = buildDrawBaseLayers(preferredProvider);
  const streetsLayer = layerSet.streetsLayer;
  const satelliteLayer = layerSet.satelliteLayer;
  const satelliteLabelsLayer = layerSet.satelliteLabelsLayer;

  satelliteLayer.addTo(drawMap);
  if (satelliteLabelsLayer) {
    satelliteLabelsLayer.addTo(drawMap);
  }
  L.control
    .layers(
      {
        Mapa: streetsLayer,
        Satelite: satelliteLayer,
      },
      {},
      { collapsed: true }
    )
    .addTo(drawMap);

  drawMap.on("baselayerchange", (event) => {
    if (satelliteLabelsLayer && event.layer === satelliteLayer) {
      if (!drawMap.hasLayer(satelliteLabelsLayer)) satelliteLabelsLayer.addTo(drawMap);
    } else if (satelliteLabelsLayer && drawMap.hasLayer(satelliteLabelsLayer)) {
      drawMap.removeLayer(satelliteLabelsLayer);
    }
  });

  drawMap.setMaxBounds(cubaBounds().pad(0.35));

  if (hasPreset) {
    addCenterMarker({ lat, lng });
  }

  drawnItems = new L.FeatureGroup();
  drawMap.addLayer(drawnItems);

  const drawControl = new L.Control.Draw({
    position: "topleft",
    draw: {
      marker: false,
      polyline: false,
      circlemarker: false,
      polygon: {
        allowIntersection: false,
        showArea: true,
        shapeOptions: {
          color: "#6ee7b7",
          weight: 2,
          opacity: 0.8,
          fillColor: "#6ee7b7",
          fillOpacity: 0.25,
        },
      },
      rectangle: {
        shapeOptions: {
          color: "#6ee7b7",
          weight: 2,
          opacity: 0.8,
          fillColor: "#6ee7b7",
          fillOpacity: 0.25,
        },
      },
      circle: {
        shapeOptions: {
          color: "#6ee7b7",
          weight: 2,
          opacity: 0.8,
          fillColor: "#6ee7b7",
          fillOpacity: 0.25,
        },
      },
    },
    edit: {
      featureGroup: drawnItems,
      remove: true,
    },
  });

  drawMap.addControl(drawControl);

  drawMap.on(L.Draw.Event.CREATED, (event) => {
    replaceCurrentLayer(event.layer);
  });

  drawMap.on(L.Draw.Event.EDITED, () => {
    syncPolygon();
  });

  drawMap.on(L.Draw.Event.DELETED, () => {
    currentLayer = null;
    syncPolygon();
  });

  loadExistingGeometry(mapEl);
}

function setupImageValidation() {
  const input = document.querySelector('input[name="images"]');
  const status = document.getElementById("editImageStatus");
  const previewList = document.getElementById("editImagePreviewList");
  if (!input) return;

  const maxFiles = parseInt(input.dataset.maxFiles || "3", 10);
  const maxMb = parseInt(input.dataset.maxMb || "2", 10);
  const allowedExt = (input.dataset.allowedExt || "jpg,jpeg,png,webp,heic")
    .split(",")
    .map((ext) => ext.trim().toLowerCase())
    .filter(Boolean);
  const maxBytes = maxMb * 1024 * 1024;

  const showError = (message) => {
    if (!status) return;
    status.textContent = message;
  };

  const renderPreviews = () => {
    if (!previewList) return;
    if (!input.files || input.files.length === 0) {
      previewList.innerHTML = "";
      return;
    }
    previewList.innerHTML = Array.from(input.files)
      .map((file, idx) => {
        const url = URL.createObjectURL(file);
        return `
          <div class="image-preview-card">
            <img src="${url}" alt="Vista previa ${idx + 1}" />
            <label class="image-caption">
              Descripcion corta (imagen ${idx + 1})
              <input type="text" name="image_captions[]" maxlength="255" placeholder="${file.name}" />
            </label>
          </div>
        `;
      })
      .join("");
  };

  input.addEventListener("change", () => {
    if (!input.files) return;
    if (input.files.length > maxFiles) {
      showError(`Maximo ${maxFiles} imagenes por envio.`);
      input.value = "";
      renderPreviews();
      return;
    }

    for (const file of Array.from(input.files)) {
      const name = file.name || "";
      const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
      if (!allowedExt.includes(ext)) {
        showError(`Formato no permitido: ${ext || "desconocido"}.`);
        input.value = "";
        renderPreviews();
        return;
      }
      if (file.size > maxBytes) {
        showError(`Cada imagen debe ser <= ${maxMb}MB.`);
        input.value = "";
        renderPreviews();
        return;
      }
    }

    if (status) status.textContent = "";
    renderPreviews();
  });
}

window.initDrawMap = setupDrawMap;

document.addEventListener("DOMContentLoaded", () => {
  setupLinks();
  setupCategoryRequirements();
  setupProvinceMunicipality();
  setupImageValidation();
  setupDrawMap();

  const form = document.querySelector(".form-grid");
  const submit = form?.querySelector('button[type="submit"]');
  if (form && submit) {
    form.addEventListener("submit", (event) => {
      if (event.defaultPrevented) return;
      submit.disabled = true;
      submit.dataset.loading = "true";
      submit.textContent = "Enviando...";
    });
  }
});
