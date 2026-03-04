const state = {
  charts: {},
};

const THEME = {
  accent: "#6ee7b7",
  accentSoft: "rgba(110, 231, 183, 0.2)",
  accent2: "#9bd1ff",
  accent2Soft: "rgba(155, 209, 255, 0.2)",
  grid: "rgba(110, 231, 183, 0.15)",
  text: "#c9f7db",
  muted: "#7fe7c0",
  warning: "#fcd34d",
  danger: "#f97316",
  neutral: "#94a3b8",
};

if (window.Chart) {
  Chart.defaults.color = THEME.text;
  Chart.defaults.font.family =
    "\"IBM Plex Mono\", \"Space Mono\", \"SFMono-Regular\", Menlo, Consolas, \"Liberation Mono\", monospace";
  Chart.defaults.font.size = 12;
}

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
          borderColor: THEME.accent,
          backgroundColor: THEME.accentSoft,
          tension: 0.25,
          fill: true,
          pointRadius: 2,
          pointHoverRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      layout: { padding: 8 },
      scales: {
        x: {
          grid: { color: THEME.grid },
          ticks: { color: THEME.muted },
        },
        y: {
          beginAtZero: true,
          grid: { color: THEME.grid },
          ticks: { color: THEME.muted },
        },
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
      scales: {
        x: { grid: { color: THEME.grid }, ticks: { color: THEME.muted } },
        y: { beginAtZero: true, grid: { color: THEME.grid }, ticks: { color: THEME.muted } },
      },
      layout: { padding: 8 },
      plugins: {
        legend: {
          labels: { color: THEME.text },
        },
      },
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
          backgroundColor: THEME.accent2Soft,
          borderColor: THEME.accent2,
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: horizontal ? "y" : "x",
      plugins: { legend: { display: false } },
      layout: { padding: 8 },
      scales: {
        x: { beginAtZero: true, grid: { color: THEME.grid }, ticks: { color: THEME.muted } },
        y: { beginAtZero: true, grid: { color: THEME.grid }, ticks: { color: THEME.muted } },
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
          backgroundColor: [THEME.accent, THEME.warning, THEME.danger, THEME.neutral],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: 8 },
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: THEME.text },
        },
      },
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
    canvas.style.height = "240px";
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
        borderColor: THEME.accent,
        backgroundColor: THEME.accentSoft,
        tension: 0.25,
        pointRadius: 2,
      },
      {
        label: "Comentarios en discusiones",
        data: payload.comments_over_time.discussion_counts,
        borderColor: THEME.accent2,
        backgroundColor: THEME.accent2Soft,
        tension: 0.25,
        pointRadius: 2,
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
