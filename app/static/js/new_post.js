let drawMap;
let drawingManager;
let currentPolygon;

const PLACEHOLDER_BY_SLUG = {
  "accion-represiva": {
    title: "Ej: Detención masiva en parque",
    description: "Incluye fecha, tipo de operativo, cantidad de detenidos, fuerzas presentes y puntos de referencia visibles.",
  },
  "residencia-represor": {
    title: "Ej: Residencia de funcionario local",
    description: "Describe la ubicación exacta, referencias cercanas, horarios frecuentes y evidencias visibles.",
  },
  "centro-penitenciario": {
    title: "Ej: Centro penitenciario provincial",
    description: "Anota nombre del centro, capacidad aproximada, accesos, y cualquier dato verificable.",
  },
  "estacion-policia": {
    title: "Ej: Estación de policía",
    description: "Incluye la dirección, nombre del distrito, patrullas visibles y horarios de mayor actividad.",
  },
  "escuela-pcc": {
    title: "Ej: Escuela de formación del PCC",
    description: "Detalla el nombre, ubicación, horarios, entradas y cualquier señalización.",
  },
  "sede-pcc": {
    title: "Ej: Sede municipal del PCC",
    description: "Describe la sede, accesos, señales y eventos recurrentes.",
  },
  "sede-seguridad-estado": {
    title: "Ej: Sede de Seguridad del Estado",
    description: "Incluye la ubicación precisa, accesos, presencia de vigilancia y referencias cercanas.",
  },
  "unidad-militar": {
    title: "Ej: Unidad militar",
    description: "Anota el tipo de unidad, accesos, perímetro y presencia visible.",
  },
  "base-espionaje": {
    title: "Ej: Base de espionaje",
    description: "Describe infraestructura, antenas, instalaciones cercanas y evidencia observable.",
  },
};

function applyPlaceholders() {
  const select = document.getElementById("categorySelect");
  const title = document.getElementById("titleInput");
  const desc = document.getElementById("descriptionInput");
  if (!select || !title || !desc) return;

  const selected = select.options[select.selectedIndex];
  const slug = selected?.dataset?.slug;
  const sample = PLACEHOLDER_BY_SLUG[slug];
  if (sample) {
    title.placeholder = sample.title;
    desc.placeholder = sample.description;
  }
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

window.initDrawMap = function () {
  const mapEl = document.getElementById("drawMap");
  if (!mapEl) return;

  const lat = parseFloat(mapEl.dataset.lat);
  const lng = parseFloat(mapEl.dataset.lng);
  const zoom = parseFloat(mapEl.dataset.zoom);
  const hasPreset = Number.isFinite(lat) && Number.isFinite(lng);
  const center = hasPreset ? { lat, lng } : { lat: 21.521757, lng: -77.781167 };
  const hasZoom = Number.isFinite(zoom);

  drawMap = new google.maps.Map(mapEl, {
    center,
    zoom: hasZoom ? zoom : hasPreset ? 14 : 7,
    minZoom: hasZoom ? Math.min(7, zoom) : 7,
    mapId: mapEl.dataset.mapId || undefined,
    mapTypeId: "hybrid",
    disableDefaultUI: true,
  });

  if (hasPreset) {
    new google.maps.Marker({ position: center, map: drawMap });
  }

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
    geojson = {
      type: "Point",
      coordinates: [c.lng(), c.lat()],
      radius_m: r,
    };
  }

  input.value = geojson ? JSON.stringify(geojson) : "";
}

function setupProvinceMunicipality() {
  const provSelect = document.getElementById("provinceSelect");
  const munSelect = document.getElementById("municipalitySelect");
  const municipalities = window.CUBA_MUNICIPALITIES || {};
  if (!provSelect || !munSelect) return;

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

  renderMunicipalities(provSelect.value, munSelect.value);
  provSelect.addEventListener("change", () => {
    renderMunicipalities(provSelect.value, "");
  });
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
  const select = document.getElementById("categorySelect");
  if (select) {
    select.addEventListener("change", applyPlaceholders);
  }
  applyPlaceholders();
  setupLinks();
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
