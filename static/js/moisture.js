document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.getElementById("moisture-batches-tbody");
  const batchCount = document.getElementById("moisture-batch-count");

  const totalBatches = document.getElementById("moisture-total-batches");
  const evaluatedBatches = document.getElementById("moisture-evaluated-batches");
  const optimalBatches = document.getElementById("moisture-optimal-batches");

  const btnRefresh = document.getElementById("btn-refresh-moisture");

  const emptyPanel = document.getElementById("moisture-detail-empty");
  const detailPanel = document.getElementById("moisture-detail-panel");

  const detailCode = document.getElementById("moisture-detail-code");
  const detailProvider = document.getElementById("moisture-detail-provider");
  const detailWeight = document.getElementById("moisture-detail-weight");
  const detailDate = document.getElementById("moisture-detail-date");
  const detailStatus = document.getElementById("moisture-detail-status");

  const readingValue = document.getElementById("moisture-reading-value");
  const readingHelper = document.getElementById("moisture-reading-helper");
  const resultLabel = document.getElementById("moisture-result-label");
  const resultDescription = document.getElementById("moisture-result-description");
  const btnStart = document.getElementById("btn-start-moisture-reading");

  let selectedBatchId = null;

  function badge(label, type) {
    const styles = {
      evaluated: "bg-green-50 text-green-700 border-green-200",
      draft: "bg-yellow-50 text-yellow-700 border-yellow-200",
    };

    return `
      <span class="px-3 py-1 rounded-full text-xs font-bold border ${styles[type] || styles.draft}">
        ${label}
      </span>
    `;
  }

  async function loadBatches() {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="px-5 py-10 text-center text-[#8a7467]">
          Cargando lotes...
        </td>
      </tr>
    `;

    const res = await fetch("/dashboard/api/moisture/batches/");
    const data = await res.json();

    if (!data.ok) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" class="px-5 py-10 text-center text-red-600">
            Error al cargar lotes.
          </td>
        </tr>
      `;
      return;
    }

    const batches = data.batches || [];

    totalBatches.textContent = batches.length;
    evaluatedBatches.textContent = batches.filter(b => b.moisture_status === "evaluated").length;
    batchCount.textContent = `${batches.length} registros`;

    optimalBatches.textContent = batches.filter(
      b => b.moisture_result === "optimal"
    ).length;

    if (batches.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" class="px-5 py-10 text-center text-[#8a7467]">
            No hay lotes registrados.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = batches.map(batch => `
      <tr class="hover:bg-[#fbf7f2] transition">
        <td class="px-5 py-4 font-bold text-[#2b1d16]">${batch.code}</td>
        <td class="px-5 py-4 text-[#5d4033]">${batch.provider}</td>
        <td class="px-5 py-4 text-[#5d4033]">${batch.weight_kg} kg</td>
        <td class="px-5 py-4">
          ${badge(batch.moisture_label, batch.moisture_status)}
        </td>
        <td class="px-5 py-4 text-right">
          <button
            type="button"
            class="btn-shine px-4 py-2 rounded-lg bg-[#2b1d16] text-white text-xs font-bold hover:bg-[#3a281f] transition"
            data-batch-id="${batch.id}">
            Ver
          </button>
        </td>
      </tr>
    `).join("");

    tbody.querySelectorAll("button[data-batch-id]").forEach(btn => {
      btn.addEventListener("click", () => loadBatchDetail(btn.dataset.batchId));
    });
  }

  async function loadBatchDetail(batchId) {
    selectedBatchId = batchId;

    const res = await fetch(`/dashboard/api/moisture/batches/${batchId}/`);
    const data = await res.json();

    if (!data.ok) {
      alert(data.error || "No se pudo cargar el lote.");
      return;
    }

    const batch = data.batch;

    emptyPanel.classList.add("hidden");
    detailPanel.classList.remove("hidden");

    detailCode.textContent = batch.code;
    detailProvider.textContent = batch.provider;
    detailWeight.textContent = `${batch.weight_kg} kg`;
    detailDate.textContent = batch.created_at;

    detailStatus.textContent = batch.moisture_label;
    detailStatus.className = "px-3 py-1 rounded-full text-xs font-bold border";

    if (batch.moisture_status === "evaluated") {
      detailStatus.classList.add("bg-green-50", "text-green-700", "border-green-200");
      btnStart.disabled = true;
      btnStart.textContent = "Análisis ya realizado";
      btnStart.classList.add("opacity-60", "cursor-not-allowed");

      readingValue.textContent = `${batch.analysis.moisture_percent}%`;
      readingHelper.textContent = `Evaluado el ${batch.analysis.created_at}`;
      resultLabel.textContent = batch.analysis.result_label;
      resultDescription.textContent = "Este lote ya cuenta con análisis de humedad guardado.";
    } else {
      detailStatus.classList.add("bg-yellow-50", "text-yellow-700", "border-yellow-200");
      btnStart.disabled = false;
      btnStart.textContent = "Start Sensor Reading";
      btnStart.classList.remove("opacity-60", "cursor-not-allowed");

      readingValue.textContent = "--%";
      readingHelper.textContent = "Esperando lectura...";
      resultLabel.textContent = "Sin análisis";
      resultDescription.textContent = "El resultado aparecerá después de capturar la humedad.";
    }
  }

  async function readMoistureFromSensor() {
    // Simulación temporal.
    // Aquí después conectamos el ESP32/sensor real.
    await new Promise(resolve => setTimeout(resolve, 1200));
    return (Math.random() * (14.5 - 8.5) + 8.5).toFixed(2);
  }

  async function startMoistureReading() {
    if (!selectedBatchId) {
      alert("Selecciona un lote primero.");
      return;
    }

    btnStart.disabled = true;
    btnStart.textContent = "Leyendo sensor...";
    readingHelper.textContent = "Capturando lectura desde el sensor...";

    const moistureValue = await readMoistureFromSensor();

    readingValue.textContent = `${moistureValue}%`;
    readingHelper.textContent = "Lectura recibida. Guardando análisis...";

    const res = await fetch("/dashboard/api/moisture/analyze/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        batch_id: selectedBatchId,
        moisture_percent: moistureValue,
      }),
    });

    const data = await res.json();

    if (!data.ok) {
      alert(data.error || "No se pudo guardar el análisis.");
      btnStart.disabled = false;
      btnStart.textContent = "Start Sensor Reading";
      return;
    }

    resultLabel.textContent = data.analysis.result_label;

    if (data.analysis.result === "optimal") {
      resultDescription.textContent = "La humedad del lote está dentro del rango óptimo.";
    } else if (data.analysis.result === "low_rejected") {
      resultDescription.textContent = "El lote queda en rechazo por humedad baja.";
    } else {
      resultDescription.textContent = "El lote queda en rechazo por humedad alta.";
    }

    btnStart.textContent = "Análisis guardado";
    await loadBatches();
    await loadBatchDetail(selectedBatchId);
  }

  btnRefresh?.addEventListener("click", loadBatches);
  btnStart?.addEventListener("click", startMoistureReading);

  loadBatches();
});
