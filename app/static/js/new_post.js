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

const PLACEHOLDER_BY_SLUG = {
  "accion-represiva": {
    title: "Ej: Detencion masiva en parque",
    description:
      "Indica fecha y hora del operativo. Incluye tipo de accion, fuerzas presentes, cantidad de detenidos y referencias visibles.",
  },
  "accion-represiva-del-gobierno": {
    title: "Ej: Detencion masiva en parque",
    description:
      "Indica fecha y hora del operativo. Incluye tipo de accion, fuerzas presentes, cantidad de detenidos y referencias visibles.",
  },
  "residencia-represor": {
    title: "Ej: Residencia de funcionario local",
    description:
      "Describe la ubicacion exacta, referencias cercanas, horarios frecuentes y evidencias visibles.",
  },
  "centro-penitenciario": {
    title: "Ej: Centro penitenciario provincial",
    description:
      "Anota nombre del centro, capacidad aproximada, accesos, y cualquier dato verificable.",
  },
  "estacion-policia": {
    title: "Ej: Estacion de policia",
    description:
      "Incluye la direccion, nombre del distrito, patrullas visibles y horarios de mayor actividad.",
  },
  "escuela-pcc": {
    title: "Ej: Escuela de formacion del PCC",
    description: "Detalla el nombre, ubicacion, horarios, entradas y cualquier senalizacion.",
  },
  "sede-pcc": {
    title: "Ej: Sede municipal del PCC",
    description: "Describe la sede, accesos, senales y eventos recurrentes.",
  },
  "sede-seguridad-estado": {
    title: "Ej: Sede de Seguridad del Estado",
    description:
      "Incluye la ubicacion precisa, accesos, presencia de vigilancia y referencias cercanas.",
  },
  "unidad-militar": {
    title: "Ej: Unidad militar",
    description: "Anota el tipo de unidad, accesos, perimetro y presencia visible.",
  },
  "movimiento-tropas": {
    title: "Ej: Movimiento de tropas en carretera",
    description:
      "Indica fecha y hora del movimiento. Describe tipo de tropas, armamento observado y motivo si se conoce.",
  },
  "movimiento-militar": {
    title: "Ej: Movimiento de tropas en carretera",
    description:
      "Indica fecha y hora del movimiento. Describe tipo de tropas, armamento observado y motivo si se conoce.",
  },
  "desconexion-internet": {
    title: "Ej: Desconexión total en municipio",
    description: "Indica fecha y hora de la desconexión. Añade duración aproximada y zonas afectadas.",
  },
  "base-espionaje": {
    title: "Ej: Base de espionaje",
    description:
      "Describe infraestructura, antenas, instalaciones cercanas y evidencia observable.",
  },
  otros: {
    title: "Ej: Situacion sin categoria clara",
    description:
      "Explica por que no encaja en las demas categorias, anade detalles verificables y referencias del lugar.",
  },
};

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

const getPlaceholderSample = (key) => {
  if (!key) return null;
  if (PLACEHOLDER_BY_SLUG[key]) return PLACEHOLDER_BY_SLUG[key];
  if (key.includes("accion-represiva")) return PLACEHOLDER_BY_SLUG["accion-represiva"];
  if (key.includes("movimiento")) return PLACEHOLDER_BY_SLUG["movimiento-tropas"];
  if (key.includes("desconexion")) return PLACEHOLDER_BY_SLUG["desconexion-internet"];
  return null;
};

function cubaBounds() {
  return L.latLngBounds(
    [CUBA_BOUNDS.south, CUBA_BOUNDS.west],
    [CUBA_BOUNDS.north, CUBA_BOUNDS.east]
  );
}

function isInsideCubaBounds(lat, lng) {
  return (
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    lat >= CUBA_BOUNDS.south &&
    lat <= CUBA_BOUNDS.north &&
    lng >= CUBA_BOUNDS.west &&
    lng <= CUBA_BOUNDS.east
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

function applyPlaceholders() {
  const select = document.getElementById("categorySelect");
  const title = document.getElementById("titleInput");
  const desc = document.getElementById("descriptionInput");
  if (!select || !title || !desc) return;

  const key = getCategoryKey(select);
  const sample = getPlaceholderSample(key);
  if (sample) {
    title.placeholder = sample.title;
    desc.placeholder = sample.description;
  }
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
  const status = document.getElementById("imageStatus");
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
      const latInput = document.querySelector('input[name="latitude"]');
      const lngInput = document.querySelector('input[name="longitude"]');
      const lat = parseFloat(latInput?.value || "");
      const lng = parseFloat(lngInput?.value || "");
      if (!isInsideCubaBounds(lat, lng)) {
        e.preventDefault();
        if (status) {
          status.textContent =
            "La ubicación debe estar dentro del territorio cubano.";
        } else {
          alert("La ubicación debe estar dentro del territorio cubano.");
        }
        if (latInput) latInput.focus();
        return;
      }

      const key = getCategoryKey(select);
      if (isResidenciaCategory(key)) {
        const hasFiles = imageInput && imageInput.files && imageInput.files.length > 0;
        if (!hasFiles) {
          e.preventDefault();
          if (status) {
            status.textContent = "Debes subir al menos una imagen del represor.";
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
          }
        }
      }
    });
  }

  update();
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

function loadInitialGeometry(mapEl) {
  const input = document.getElementById("polygonGeojson");
  const raw = (input?.value || "").trim();
  if (!raw) return;

  try {
    const geo = JSON.parse(raw);
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
    // ignore invalid stored geometry
  }
}

function setupDrawMap() {
  const mapEl = document.getElementById("drawMap");
  if (!mapEl || typeof L === "undefined") return;

  const lat = parseFloat(mapEl.dataset.lat);
  const lng = parseFloat(mapEl.dataset.lng);
  const zoom = parseFloat(mapEl.dataset.zoom);
  const hasPreset = Number.isFinite(lat) && Number.isFinite(lng);
  const center = hasPreset ? [lat, lng] : [21.521757, -77.781167];
  const baseZoom = Number.isFinite(zoom) ? zoom : hasPreset ? 14 : 7;

  drawMap = L.map(mapEl, {
    minZoom: 7,
    maxZoom: 19,
    zoomControl: true,
  }).setView(center, baseZoom);
  enableMiddleClickPan(drawMap);

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

  satelliteLayer.addTo(drawMap);
  satelliteLabelsLayer.addTo(drawMap);
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
    if (event.layer === satelliteLayer) {
      if (!drawMap.hasLayer(satelliteLabelsLayer)) satelliteLabelsLayer.addTo(drawMap);
    } else if (drawMap.hasLayer(satelliteLabelsLayer)) {
      drawMap.removeLayer(satelliteLabelsLayer);
    }
  });

  drawMap.setMaxBounds(cubaBounds());
  drawMap.options.maxBoundsViscosity = 1.0;

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

  loadInitialGeometry(mapEl);
}

function setupProvinceMunicipality() {
  const provSelect = document.getElementById("provinceSelect");
  const munSelect = document.getElementById("municipalitySelect");
  const municipalities = window.CUBA_MUNICIPALITIES || {};
  if (!provSelect || !munSelect) return;

  const normalize = (value) =>
    String(value || "")
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");

  const provinceLookup = new Map(Object.keys(municipalities).map((prov) => [normalize(prov), prov]));
  const municipalityLookup = new Map();
  Object.entries(municipalities).forEach(([prov, muns]) => {
    (muns || []).forEach((mun) => {
      municipalityLookup.set(normalize(mun), { name: mun, province: prov });
    });
  });

  const selectedProv = provSelect.dataset.selected || provSelect.value;
  if (selectedProv) {
    provSelect.value = selectedProv;
  }

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

  const initialSelected = munSelect.dataset.selected || munSelect.value;
  renderMunicipalities(provSelect.value, initialSelected);
  provSelect.addEventListener("change", () => {
    renderMunicipalities(provSelect.value, "");
  });

  const applySelection = (province, municipality) => {
    if (province) {
      provSelect.value = province;
    }
    renderMunicipalities(provSelect.value, municipality || "");
    if (municipality) {
      munSelect.value = municipality;
    }
  };

  const reverseLookup = async (lat, lng) => {
    const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&accept-language=es&lat=${lat}&lon=${lng}`;
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    const data = await res.json();
    const addr = data?.address || {};

    const rawProvince = addr.state || addr.province || "";
    const rawMunicipality =
      addr.county ||
      addr.city ||
      addr.town ||
      addr.municipality ||
      addr.village ||
      addr.suburb ||
      "";

    let province = provinceLookup.get(normalize(rawProvince)) || "";
    const municipalityData = municipalityLookup.get(normalize(rawMunicipality));
    let municipality = municipalityData ? municipalityData.name : "";

    if (!province && municipalityData) {
      province = municipalityData.province;
    }
    if (province && municipalityData && municipalityData.province !== province) {
      municipality = "";
    }

    return { province, municipality };
  };

  const autoFillFromLatLng = async () => {
    if (provSelect.value || provSelect.dataset.selected || munSelect.value || munSelect.dataset.selected) {
      return;
    }
    const latInput = document.querySelector('input[name="latitude"]');
    const lngInput = document.querySelector('input[name="longitude"]');
    const lat = parseFloat(latInput?.value || "");
    const lng = parseFloat(lngInput?.value || "");
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

    const result = await reverseLookup(lat, lng);
    if (!result) return;
    if (result.province || result.municipality) {
      applySelection(result.province, result.municipality);
    }
  };

  autoFillFromLatLng();
  const latInput = document.querySelector('input[name="latitude"]');
  const lngInput = document.querySelector('input[name="longitude"]');
  if (latInput) latInput.addEventListener("change", autoFillFromLatLng);
  if (lngInput) lngInput.addEventListener("change", autoFillFromLatLng);
}

function setupImageValidation() {
  const input = document.querySelector('input[name="images"]');
  const status = document.getElementById("imageStatus");
  const previewList = document.getElementById("imagePreviewList");
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

function setupSubmitLabel() {
  const form = document.querySelector(".form-grid");
  const select = document.getElementById("categorySelect");
  const submit = document.getElementById("submitReportBtn");
  if (!form || !select || !submit) return;

  const moderationEnabled = submit.dataset.moderationEnabled === "1";
  const moderationLabel = submit.dataset.moderationLabel || "Enviar a moderacion";
  const publishLabel = submit.dataset.publishLabel || "Publicar reporte";

  const updateLabel = () => {
    const key = getCategoryKey(select);
    if (moderationEnabled && !isUrgentCategory(key)) {
      submit.textContent = moderationLabel;
    } else {
      submit.textContent = publishLabel;
    }
  };

  select.addEventListener("change", updateLabel);
  updateLabel();
}

window.initDrawMap = setupDrawMap;

document.addEventListener("DOMContentLoaded", () => {
  const select = document.getElementById("categorySelect");
  if (select) {
    select.addEventListener("change", applyPlaceholders);
  }
  applyPlaceholders();
  setupCategoryRequirements();
  setupSubmitLabel();
  setupLinks();
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
