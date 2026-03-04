const state = {
  charts: {},
};

const formatDateInput = (date) => date.toISOString().slice(0, 10);

const getDateRange = () => {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - 90);
  return {
    start: formatDateInput(start),
    end: formatDateInput(end),
  };
};

const buildQuery = () => {
  const start = document.getElementById("analyticsStart").value;
  const end = document.getElementById("analyticsEnd").value;
  const category = document.getElementById("analyticsCategory").value;
  const province = document.getElementById("analyticsProvince").value;
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  if (category) params.set("category_id", category);
  if (province) params.set("province", province);
  return params.toString();
};

const fetchAnalytics = async () => {
  const query = buildQuery();
  const res = await fetch(`/api/v1/analytics?${query}`);
  if (!res.ok) {
    throw new Error("No se pudo cargar analíticas");
  }
  return res.json();
};

const buildLine = (ctx, label, labels, data, extra = {}) =>
  new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label,
          data,
          borderColor: "#6ee7b7",
          backgroundColor: "rgba(110, 231, 183, 0.2)",
          tension: 0.25,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        y: { beginAtZero: true },
      },
      ...extra,
    },
  });

const buildMultiLine = (ctx, labels, datasets) =>
  new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true } },
    },
  });

const buildBar = (ctx, labels, data, horizontal = false) =>
  new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          data,
          backgroundColor: "rgba(155, 209, 255, 0.75)",
          borderColor: "#9bd1ff",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: horizontal ? "y" : "x",
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true },
        y: { beginAtZero: true },
      },
    },
  });

const buildDonut = (ctx, labels, data) =>
  new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data,
          backgroundColor: ["#6ee7b7", "#fcd34d", "#f97316", "#94a3b8"],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
    },
  });

const destroyChart = (id) => {
  if (state.charts[id]) {
    state.charts[id].destroy();
    delete state.charts[id];
  }
};

const ensureCanvasHeight = () => {
  document.querySelectorAll(".analytics-card canvas").forEach((canvas) => {
    canvas.parentElement.style.height = "320px";
  });
};

const renderCharts = (payload) => {
  ensureCanvasHeight();

  destroyChart("reportsOverTime");
  destroyChart("moderationStatus");
  destroyChart("categoryDistribution");
  destroyChart("provinceDistribution");
  destroyChart("municipalityDistribution");
  destroyChart("topVerified");
  destroyChart("commentsOverTime");
  destroyChart("editStatus");

  const reportLabels = payload.reports_over_time.map((item) => item.date);
  const reportData = payload.reports_over_time.map((item) => item.count);
  state.charts.reportsOverTime = buildLine(
    document.getElementById("reportsOverTime"),
    "Reportes",
    reportLabels,
    reportData
  );

  const moderation = payload.moderation_status || {};
  state.charts.moderationStatus = buildDonut(
    document.getElementById("moderationStatus"),
    ["Aprobados", "Pendientes", "Rechazados", "Ocultos"],
    [
      moderation.approved || 0,
      moderation.pending || 0,
      moderation.rejected || 0,
      moderation.hidden || 0,
    ]
  );

  const categoryLabels = payload.category_distribution.map((item) => item.name);
  const categoryData = payload.category_distribution.map((item) => item.count);
  state.charts.categoryDistribution = buildBar(
    document.getElementById("categoryDistribution"),
    categoryLabels,
    categoryData,
    true
  );

  const provinceLabels = payload.province_distribution.map((item) => item.name);
  const provinceData = payload.province_distribution.map((item) => item.count);
  state.charts.provinceDistribution = buildBar(
    document.getElementById("provinceDistribution"),
    provinceLabels,
    provinceData,
    true
  );

  const municipalityLabels = payload.municipality_distribution.map((item) => item.name);
  const municipalityData = payload.municipality_distribution.map((item) => item.count);
  state.charts.municipalityDistribution = buildBar(
    document.getElementById("municipalityDistribution"),
    municipalityLabels,
    municipalityData,
    true
  );

  const topLabels = payload.top_verified.map((item) =>
    item.title.length > 28 ? `${item.title.slice(0, 28)}…` : item.title
  );
  const topData = payload.top_verified.map((item) => item.verify_count);
  state.charts.topVerified = buildBar(
    document.getElementById("topVerified"),
    topLabels,
    topData
  );

  const commentLabels = payload.comments_over_time.labels;
  state.charts.commentsOverTime = buildMultiLine(
    document.getElementById("commentsOverTime"),
    commentLabels,
    [
      {
        label: "Comentarios en reportes",
        data: payload.comments_over_time.report_counts,
        borderColor: "#6ee7b7",
        backgroundColor: "rgba(110, 231, 183, 0.2)",
        tension: 0.25,
      },
      {
        label: "Comentarios en discusiones",
        data: payload.comments_over_time.discussion_counts,
        borderColor: "#9bd1ff",
        backgroundColor: "rgba(155, 209, 255, 0.2)",
        tension: 0.25,
      },
    ]
  );

  const editStatus = payload.edit_status || {};
  state.charts.editStatus = buildBar(
    document.getElementById("editStatus"),
    ["Pendientes", "Aprobadas", "Rechazadas"],
    [editStatus.pending || 0, editStatus.approved || 0, editStatus.rejected || 0]
  );
};

const initFilters = () => {
  const { start, end } = getDateRange();
  const startInput = document.getElementById("analyticsStart");
  const endInput = document.getElementById("analyticsEnd");
  if (startInput && !startInput.value) startInput.value = start;
  if (endInput && !endInput.value) endInput.value = end;
};

const attachHandlers = () => {
  const refreshBtn = document.getElementById("analyticsRefresh");
  if (!refreshBtn) return;
  refreshBtn.addEventListener("click", async () => {
    refreshBtn.disabled = true;
    refreshBtn.textContent = "Cargando...";
    try {
      const data = await fetchAnalytics();
      renderCharts(data);
    } catch (err) {
      console.error(err);
    } finally {
      refreshBtn.disabled = false;
      refreshBtn.textContent = "Actualizar";
    }
  });
};

const boot = async () => {
  initFilters();
  attachHandlers();
  try {
    const data = await fetchAnalytics();
    renderCharts(data);
  } catch (err) {
    console.error(err);
  }
};

document.addEventListener("DOMContentLoaded", boot);
