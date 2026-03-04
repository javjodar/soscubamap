let drawMap;
let drawingManager;
let currentPolygon;
const CUBA_BOUNDS = {
  north: 24.2,
  south: 19.0,
  west: -86.2,
  east: -73.0,
};

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
      items
        .map(
          (m) => `<option value="${m}" ${m === selected ? "selected" : ""}>${m}</option>`
        )
        .join("");
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
    const selected = select?.options[select.selectedIndex];
    const slug = selected?.dataset?.slug || "";
    const isResidencia = slug === "residencia-represor";
    const isOtros = slug === "otros";
    const isMovimiento = slug === "movimiento-tropas";
    if (residenciaFields) residenciaFields.classList.toggle("is-hidden", !isResidencia);
    if (otrosFields) otrosFields.classList.toggle("is-hidden", !isOtros);
    if (movimientoFields) movimientoFields.classList.toggle("is-hidden", !isMovimiento);
    if (repressorInput) repressorInput.required = isResidencia;
    if (otherInput) otherInput.required = isOtros;
    if (movementDateInput) movementDateInput.required = isMovimiento;
    if (movementTimeInput) movementTimeInput.required = isMovimiento;
  };

  if (select) {
    select.addEventListener("change", update);
  }

  if (form) {
    form.addEventListener("submit", (e) => {
      const selected = select?.options[select.selectedIndex];
      const slug = selected?.dataset?.slug || "";
      if (slug === "residencia-represor") {
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
      if (slug === "otros") {
        const value = (otherInput?.value || "").toLowerCase();
        if (/(represor|represores|chivato|chivata|chivatos|chivatas|informante|informantes|delator|delatores|dse|dgi)/i.test(value)) {
          e.preventDefault();
          if (otherInput) otherInput.focus();
          if (status) {
            status.textContent = "El tipo en “Otros” no puede referirse a represores. Usa la categoría correspondiente.";
          } else {
            alert("El tipo en “Otros” no puede referirse a represores. Usa la categoría correspondiente.");
          }
        }
      }
      if (slug === "movimiento-tropas") {
        const hasDate = movementDateInput && movementDateInput.value;
        const hasTime = movementTimeInput && movementTimeInput.value;
        if (!hasDate || !hasTime) {
          e.preventDefault();
          if (status) {
            status.textContent = "Debes indicar fecha y hora del movimiento.";
          } else {
            alert("Debes indicar fecha y hora del movimiento.");
          }
        }
      }
    });
  }

  update();
}

window.initDrawMap = function () {
  const mapEl = document.getElementById("drawMap");
  if (!mapEl) return;

  const lat = parseFloat(mapEl.dataset.lat);
  const lng = parseFloat(mapEl.dataset.lng);
  const center = Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : { lat: 21.521757, lng: -77.781167 };

  drawMap = new google.maps.Map(mapEl, {
    center,
    zoom: 14,
    minZoom: 7,
    restriction: { latLngBounds: CUBA_BOUNDS, strictBounds: true },
    mapId: mapEl.dataset.mapId || undefined,
    mapTypeId: "hybrid",
    disableDefaultUI: true,
  });

  new google.maps.Marker({ position: center, map: drawMap });

  drawingManager = new google.maps.drawing.DrawingManager({
    drawingMode: google.maps.drawing.OverlayType.POLYGON,
    drawingControl: true,
    drawingControlOptions: {
      position: google.maps.ControlPosition.TOP_LEFT,
      drawingModes: [
        google.maps.drawing.OverlayType.POLYGON,
        google.maps.drawing.OverlayType.RECTANGLE,
        google.maps.drawing.OverlayType.CIRCLE,
      ],
    },
    polygonOptions: {
      fillColor: "#6ee7b7",
      fillOpacity: 0.25,
      strokeColor: "#6ee7b7",
      strokeOpacity: 0.8,
      strokeWeight: 2,
      editable: true,
      draggable: false,
    },
    rectangleOptions: {
      fillColor: "#6ee7b7",
      fillOpacity: 0.25,
      strokeColor: "#6ee7b7",
      strokeOpacity: 0.8,
      strokeWeight: 2,
      editable: true,
      draggable: false,
    },
    circleOptions: {
      fillColor: "#6ee7b7",
      fillOpacity: 0.25,
      strokeColor: "#6ee7b7",
      strokeOpacity: 0.8,
      strokeWeight: 2,
      editable: true,
      draggable: false,
    },
  });

  drawingManager.setMap(drawMap);

  google.maps.event.addListener(drawingManager, "overlaycomplete", (event) => {
    if (currentPolygon) {
      currentPolygon.setMap(null);
    }
    currentPolygon = event.overlay;
    drawingManager.setDrawingMode(null);
    syncPolygon(event);

    if (event.type === google.maps.drawing.OverlayType.POLYGON) {
      google.maps.event.addListener(currentPolygon.getPath(), "set_at", () => syncPolygon(event));
      google.maps.event.addListener(currentPolygon.getPath(), "insert_at", () => syncPolygon(event));
    }
    if (event.type === google.maps.drawing.OverlayType.RECTANGLE) {
      google.maps.event.addListener(currentPolygon, "bounds_changed", () => syncPolygon(event));
    }
    if (event.type === google.maps.drawing.OverlayType.CIRCLE) {
      google.maps.event.addListener(currentPolygon, "center_changed", () => syncPolygon(event));
      google.maps.event.addListener(currentPolygon, "radius_changed", () => syncPolygon(event));
    }
  });

  const existing = mapEl.dataset.geojson;
  if (existing) {
    try {
      const geo = JSON.parse(existing);
      if (geo.type === "Polygon" && geo.coordinates?.length) {
        const path = geo.coordinates[0].map(([lng, lat]) => ({ lat, lng }));
        currentPolygon = new google.maps.Polygon({
          paths: path,
          strokeColor: "#6ee7b7",
          strokeOpacity: 0.8,
          strokeWeight: 2,
          fillColor: "#6ee7b7",
          fillOpacity: 0.25,
          editable: true,
          map: drawMap,
        });
        syncPolygon({ type: google.maps.drawing.OverlayType.POLYGON });
      } else if (geo.type === "Point" && geo.coordinates?.length && geo.radius_m) {
        currentPolygon = new google.maps.Circle({
          center: { lat: geo.coordinates[1], lng: geo.coordinates[0] },
          radius: geo.radius_m,
          strokeColor: "#6ee7b7",
          strokeOpacity: 0.8,
          strokeWeight: 2,
          fillColor: "#6ee7b7",
          fillOpacity: 0.25,
          editable: true,
          map: drawMap,
        });
        syncPolygon({ type: google.maps.drawing.OverlayType.CIRCLE });
      }
    } catch (e) {
      // ignore
    }
  }
};

function syncPolygon(event) {
  const input = document.getElementById("polygonGeojson");
  if (!input || !currentPolygon) return;

  let geojson = null;
  if (event?.type === google.maps.drawing.OverlayType.POLYGON) {
    const path = currentPolygon.getPath().getArray().map((latLng) => [latLng.lng(), latLng.lat()]);
    if (path.length) {
      const [firstLng, firstLat] = path[0];
      const [lastLng, lastLat] = path[path.length - 1];
      if (firstLng !== lastLng || firstLat !== lastLat) {
        path.push([firstLng, firstLat]);
      }
    }
    geojson = { type: "Polygon", coordinates: [path] };
  }
  if (event?.type === google.maps.drawing.OverlayType.RECTANGLE) {
    const b = currentPolygon.getBounds();
    const ne = b.getNorthEast();
    const sw = b.getSouthWest();
    const path = [
      [sw.lng(), sw.lat()],
      [ne.lng(), sw.lat()],
      [ne.lng(), ne.lat()],
      [sw.lng(), ne.lat()],
      [sw.lng(), sw.lat()],
    ];
    geojson = { type: "Polygon", coordinates: [path] };
  }
  if (event?.type === google.maps.drawing.OverlayType.CIRCLE) {
    const c = currentPolygon.getCenter();
    const r = currentPolygon.getRadius();
    geojson = { type: "Point", coordinates: [c.lng(), c.lat()], radius_m: r };
  }

  input.value = geojson ? JSON.stringify(geojson) : "";
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
              Descripción corta (imagen ${idx + 1})
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
      showError(`Máximo ${maxFiles} imágenes por envío.`);
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

document.addEventListener("DOMContentLoaded", () => {
  setupLinks();
  setupCategoryRequirements();
  setupProvinceMunicipality();
  setupImageValidation();
  const form = document.querySelector(".form-grid");
  const submit = form?.querySelector('button[type="submit"]');
  if (form && submit) {
    form.addEventListener("submit", () => {
      submit.disabled = true;
      submit.dataset.loading = "true";
      submit.textContent = "Enviando...";
    });
  }
});
