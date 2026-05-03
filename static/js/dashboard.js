(function () {
  const root = document.getElementById("dashboardRoot");
  if (!root) return;

  const SUMMARY_URL = root.dataset.summaryUrl || "/api/dashboard/summary/";
  const MONTH_NAMES_ES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

  const $ = (id) => document.getElementById(id);
  const setText = (id, value) => { const el = $(id); if (el) el.textContent = value; };

  const fmtPct = (v) => `${Number(v).toFixed(2)}%`;
  const fmtKg  = (v) => `${Number(v).toFixed(2)} kg`;

  function showNoData(show) {
    const box = $("noDataBox");
    if (!box) return;
    box.classList.toggle("hidden", !show);
  }

  async function fetchDashboard() {
    const res = await fetch(SUMMARY_URL, { credentials: "include" });
    if (!res.ok) throw new Error("No se pudo cargar el dashboard");
    return await res.json();
  }

  let chartLots = null;
  let chartKg = null;
  let chartGauge = null;

  function renderKPIs(kpis) {
    setText("kpiLots", kpis.total_lots ?? "—");
    setText("kpiKg", fmtKg(kpis.total_kg ?? 0));
    setText("kpiQuality", fmtPct(kpis.quality_pct ?? 0));
    setText("kpiReject", fmtPct(kpis.reject_pct ?? 0));
  }

  function renderMeta(year) {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    setText("lastUpdated", `${hh}:${mm}`);
    setText("yearLabel1", `${year}`);
    setText("yearLabel2", `${year}`);
  }

  function renderComparison(comp) {
    const cm = comp?.current?.month;
    const pm = comp?.previous?.month;
    const cy = comp?.current?.year;

    if (cm && pm && cy) setText("compareTitle", `${MONTH_NAMES_ES[cm - 1]} vs ${MONTH_NAMES_ES[pm - 1]} ${cy}`);
    else setText("compareTitle", "—");

    const wrap = $("compareCards");
    if (!wrap) return;

    const items = [
      { title: "Lotes", cur: comp?.lots?.current ?? 0, prev: comp?.lots?.previous ?? 0, delta: comp?.lots?.delta_pct ?? 0, suffix: "", mode: "pct" },
      { title: "KG", cur: comp?.kg?.current ?? 0, prev: comp?.kg?.previous ?? 0, delta: comp?.kg?.delta_pct ?? 0, suffix: " kg", mode: "pct" },
      { title: "Calidad", cur: comp?.quality?.current ?? 0, prev: comp?.quality?.previous ?? 0, deltaPts: comp?.quality?.delta_points ?? 0, suffix: " %", mode: "pts" },
    ];

    wrap.innerHTML = items.map((it) => {
      const up = it.mode === "pts" ? (it.deltaPts >= 0) : (it.delta >= 0);
      const arrow = up ? "↑" : "↓";
      const deltaText = it.mode === "pts"
        ? `${arrow} ${Math.abs(it.deltaPts).toFixed(2)} pts`
        : `${arrow} ${Math.abs(it.delta).toFixed(2)}%`;

      return `
        <div class="rounded-2xl border border-zinc-200 bg-white/80 p-3 shadow-sm">
          <div class="text-xs uppercase tracking-wide text-zinc-500">${it.title}</div>
          <div class="mt-1 text-xl font-semibold text-zinc-900">${it.cur}${it.suffix}</div>
          <div class="mt-1 text-xs text-zinc-500">Mes anterior: ${it.prev}${it.suffix}</div>
          <div class="mt-2 text-sm font-medium ${up ? "text-emerald-700" : "text-rose-700"}">${deltaText}</div>
        </div>
      `;
    }).join("");
  }

  function renderCharts(charts, kpis) {
      if (!window.Chart) throw new Error("Chart.js no cargó (revisa el script CDN).");

      const labels = charts?.labels ?? MONTH_NAMES_ES;
      const lotsData = charts?.lots_by_month ?? new Array(12).fill(0);
      const kgData = charts?.kg_by_month ?? new Array(12).fill(0);

      // Paleta de colores
      const BLUE = "#2563EB";      // azul vivo
      const CYAN = "#06B6D4";      // cian
      const VIOLET = "#7C3AED";    // morado
      const ORANGE = "#F97316";    // naranja
      const GRID = "rgba(0,0,0,0.08)";

      const commonScales = {
        x: { grid: { color: GRID }, ticks: { color: "rgba(0,0,0,0.65)" } },
        y: { beginAtZero: true, grid: { color: GRID }, ticks: { color: "rgba(0,0,0,0.65)" } },
      };

      const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        scales: commonScales,
        plugins: {
          legend: { display: true, labels: { color: "rgba(0,0,0,0.7)" } },
          tooltip: { enabled: true },
        },
      };

      // LOTES (línea + área viva)
      const ctxLots = $("chartLots");
      if (ctxLots) {
        chartLots?.destroy();
        chartLots = new Chart(ctxLots, {
          type: "line",
          data: {
            labels,
            datasets: [{
              label: "Lotes evaluados",
              data: lotsData,
              fill: true,
              tension: 0.35,
              borderColor: BLUE,
              backgroundColor: "rgba(37,99,235,0.22)",
              pointBackgroundColor: ORANGE,
              pointBorderColor: "#FFFFFF",
              pointRadius: 4,
              pointHoverRadius: 6,
              borderWidth: 3,
            }]
          },
          options: commonOptions
        });
      }

      // KG (barras degradadas por barra)
      const ctxKg = $("chartKg");
      if (ctxKg) {
        chartKg?.destroy();

        const bgPerBar = labels.map((_, i) => {
          return i % 2 === 0 ? "rgba(6,182,212,0.35)" : "rgba(124,58,237,0.30)";
        });

        const borderPerBar = labels.map((_, i) => (i % 2 === 0 ? CYAN : VIOLET));

        chartKg = new Chart(ctxKg, {
          type: "bar",
          data: {
            labels,
            datasets: [{
              label: "KG procesados",
              data: kgData,
              backgroundColor: bgPerBar,
              borderColor: borderPerBar,
              borderWidth: 2,
              borderRadius: 10,
              maxBarThickness: 42,
            }]
          },
          options: commonOptions
        });
      }

      // Gauge
      const ctxGauge = $("chartGauge");
      if (ctxGauge) {
        chartGauge?.destroy();
        const val = Math.max(0, Math.min(100, Number(kpis?.quality_pct ?? 0)));

        chartGauge = new Chart(ctxGauge, {
          type: "doughnut",
          data: {
            labels: ["Aceptado", "Rechazo"],
            datasets: [{
              data: [val, 100 - val],
              cutout: "75%",
              backgroundColor: ["#22C55E", "rgba(0,0,0,0.08)"],
              borderWidth: 0,
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            rotation: 270,
            circumference: 180,
            plugins: { legend: { display: false }, tooltip: { enabled: false } }
          },
          plugins: [{
            id: "centerText",
            afterDraw(chart) {
              const { ctx } = chart;
              ctx.save();
              ctx.font = "800 22px ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial";
              ctx.fillStyle = "rgba(0,0,0,0.78)";
              ctx.textAlign = "center";
              ctx.textBaseline = "middle";
              const x = chart.chartArea.left + (chart.chartArea.right - chart.chartArea.left) / 2;
              const y = chart.chartArea.top + (chart.chartArea.bottom - chart.chartArea.top) / 1.15;
              ctx.fillText(`${val.toFixed(2)}%`, x, y);
              ctx.restore();
            }
          }]
        });
      }
  }

  (async function init() {
    try {
      const data = await fetchDashboard();

      renderMeta(data.year);
      renderKPIs(data.kpis);
      renderComparison(data.comparison);

      const totalLots = Number(data?.kpis?.total_lots ?? 0);
      const hasData = (typeof data.has_data === "boolean") ? data.has_data : (totalLots > 0);

      showNoData(!hasData);

      if (!hasData) return;

      renderCharts(data.charts, data.kpis);
    } catch (e) {
      console.error(e);
      showNoData(true);
    }
  })();
})();