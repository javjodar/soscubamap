let drawMap;
let drawingManager;
let currentPolygon;

window.initDrawMap = function () {
  const mapEl = document.getElementById("drawMap");
  if (!mapEl) return;

  const lat = parseFloat(mapEl.dataset.lat);
  const lng = parseFloat(mapEl.dataset.lng);
  const hasPreset = Number.isFinite(lat) && Number.isFinite(lng);
  const center = hasPreset ? { lat, lng } : { lat: 21.521757, lng: -77.781167 };

  drawMap = new google.maps.Map(mapEl, {
    center,
    zoom: hasPreset ? 14 : 7,
    minZoom: 7,
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
