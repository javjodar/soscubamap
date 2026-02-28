let map;
let markers = [];
let clickInfo;
let recentTimer;
let searchBox;
let autocomplete;

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

function buildMarkerContent(iconClass) {
  const wrapper = document.createElement("div");
  wrapper.className = "pin-icon";
  wrapper.innerHTML = `<i class="fa-solid ${iconClass}"></i>`;
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
    let marker;

    if (google.maps.marker && google.maps.marker.AdvancedMarkerElement) {
      marker = new google.maps.marker.AdvancedMarkerElement({
        position,
        map,
        title: post.title,
        content: buildMarkerContent(iconClass),
      });
    } else {
      marker = new google.maps.Marker({
        position,
        map,
        title: post.title,
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
          ${post.address ? `<div style="font-size:12px;color:#666;">${post.address}</div>` : ""}
        </div>
      `,
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

async function applyFilters() {
  const categoryId = document.getElementById("categoryFilter").value;
  const posts = await loadPosts(categoryId);
  renderMarkers(posts);
}

async function loadRecent() {
  const res = await fetch("/api/posts?limit=6");
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
          </div>
        </div>
      `
    )
    .join("");
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
  if (!apiKey) {
    refreshRecent();
    return;
  }

  map = new google.maps.Map(mapEl, {
    center: { lat: 21.521757, lng: -77.781167 },
    zoom: 7,
    minZoom: 7,
    mapId: mapEl.dataset.mapId || undefined,
    tilt: 0,
    heading: 0,
    rotateControl: true,
    gestureHandling: "greedy",
    styles: [
      { elementType: "geometry", stylers: [{ color: "#1f1f1f" }] },
      { elementType: "labels.text.stroke", stylers: [{ color: "#1f1f1f" }] },
      { elementType: "labels.text.fill", stylers: [{ color: "#8b96a3" }] },
      { featureType: "administrative", elementType: "geometry", stylers: [{ color: "#323232" }] },
      { featureType: "poi", elementType: "labels.text.fill", stylers: [{ color: "#6ee7b7" }] },
      { featureType: "road", elementType: "geometry", stylers: [{ color: "#2a2a2a" }] },
      { featureType: "water", elementType: "geometry", stylers: [{ color: "#0b2430" }] },
    ],
  });

  const searchInput = document.getElementById("mapSearch");
  if (searchInput && google.maps.places) {
    const cubaBounds = new google.maps.LatLngBounds(
      { lat: 19.8, lng: -85.2 },
      { lat: 23.7, lng: -73.9 }
    );
    searchBox = new google.maps.places.SearchBox(searchInput, {
      bounds: cubaBounds,
    });
    searchBox.setBounds(cubaBounds);
    autocomplete = new google.maps.places.Autocomplete(searchInput, {
      bounds: cubaBounds,
      componentRestrictions: { country: "cu" },
      fields: ["geometry", "name"],
      types: ["geocode"],
    });
    autocomplete.addListener("place_changed", () => {
      const place = autocomplete.getPlace();
      if (!place.geometry || !place.geometry.location) return;
      map.panTo(place.geometry.location);
      map.setZoom(Math.max(map.getZoom(), 12));
    });

    map.addListener("bounds_changed", () => {
      searchBox.setBounds(map.getBounds());
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
        <div style="font-weight:600;margin-bottom:8px;">Crear reporte aqui</div>
        <button id="createReportBtn" style="background:#6ee7b7;border:none;padding:8px 10px;border-radius:6px;cursor:pointer;">Abrir formulario</button>
      </div>
    `);
    clickInfo.setPosition(event.latLng);
    clickInfo.open(map);

    google.maps.event.addListenerOnce(clickInfo, "domready", () => {
      const btn = document.getElementById("createReportBtn");
      if (btn) {
        btn.addEventListener("click", () => {
          window.location.href = `${newUrl}?lat=${lat}&lng=${lng}`;
        });
      }
    });
  });

  if (recentTimer) {
    clearInterval(recentTimer);
  }
  recentTimer = setInterval(refreshRecent, 15000);
};
