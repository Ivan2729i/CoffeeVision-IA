(function () {
  // =========================
  // Tabs Imagen / En vivo
  // =========================
  const tabImage = document.getElementById("qaTabImage");
  const tabLive = document.getElementById("qaTabLive");
  const panelImage = document.getElementById("qaPanelImage");
  const panelLive = document.getElementById("qaPanelLive");

  function activate(which) {
    const isImage = which === "image";

    if (panelImage && panelLive) {
      panelImage.classList.toggle("hidden", !isImage);
      panelLive.classList.toggle("hidden", isImage);
    }

    if (tabImage && tabLive) {
      tabImage.classList.toggle("bg-[#f5efe7]", isImage);
      tabLive.classList.toggle("bg-[#f5efe7]", !isImage);
    }
  }

  if (tabImage && tabLive && panelImage && panelLive) {
    tabImage.addEventListener("click", () => activate("image"));
    tabLive.addEventListener("click", () => activate("live"));
    activate("image");
  }

  // =========================
  // Evaluar y guardar (imagen)
  // =========================
  const form = document.getElementById("qaForm");
  const fileInput = document.getElementById("qaFile");
  const btn = document.getElementById("qaBtn");
  const status = document.getElementById("qaStatus");
  const result = document.getElementById("qaResult");
  const urlEl = document.getElementById("qaUrl");
  const batchIdEl = document.getElementById("qaBatchId");
  const draftBox = document.getElementById("qaDraftBox");

  if (!form || !fileInput || !btn || !status || !urlEl || !batchIdEl || !draftBox) return;

  function showStatus(msg, isError = false) {
    status.classList.remove("hidden");
    status.textContent = msg;
    status.classList.toggle("text-red-600", isError);
    status.classList.toggle("text-gray-700", !isError);
  }

  function toNum(v, fallback = 0) {
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function renderDefectCards(obj, emptyText) {
    const entries = Object.entries(obj || {});
    if (!entries.length) {
      return `<p class="text-xs text-gray-500 col-span-2">${escapeHtml(emptyText)}</p>`;
    }

    return entries.map(([name, qty]) => `
      <div class="rounded-xl bg-[#f7f2ec] p-3 border border-[#eadfd3]">
        <p class="text-[11px] text-gray-500">${escapeHtml(name)}</p>
        <p class="text-sm font-bold text-gray-800">${escapeHtml(qty)}</p>
      </div>
    `).join("");
  }

  function renderEvaluatedBox(data) {
    const grade = data.grade ?? "-";
    const primary = toNum(data.primary_total, 0);
    const secondary = toNum(data.secondary_total, 0);
    const total = toNum(data.defects_total, primary + secondary);

    const counts = data.visual_counts || data.counts || {};
    const p = counts.primary || {};
    const s = counts.secondary || {};

    return `
      <div class="mt-6 rounded-2xl bg-green-50 border border-green-200 p-5" id="qaEvaluatedBox">
        <p class="text-sm font-semibold text-green-800">Este lote ya fue evaluado </p>

        <div class="mt-3 grid grid-cols-1 sm:grid-cols-4 gap-3">
          <div class="rounded-xl bg-white p-3 border border-green-200">
            <p class="text-xs text-gray-500">Grado</p>
            <p class="text-lg font-bold text-gray-800">${escapeHtml(grade)}</p>
          </div>

          <div class="rounded-xl bg-white p-3 border border-green-200">
            <p class="text-xs text-gray-500">Primarios</p>
            <p class="text-lg font-bold text-gray-800">${primary}</p>
          </div>

          <div class="rounded-xl bg-white p-3 border border-green-200">
            <p class="text-xs text-gray-500">Secundarios</p>
            <p class="text-lg font-bold text-gray-800">${secondary}</p>
          </div>

          <div class="rounded-xl bg-white p-3 border border-green-200">
            <p class="text-xs text-gray-500">Total</p>
            <p class="text-lg font-bold text-gray-800">${total}</p>
          </div>
        </div>

        <div class="mt-6">
          <p class="text-sm font-semibold text-gray-800">Conteo por defecto</p>

          <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="rounded-2xl bg-white border border-green-200 p-4">
              <p class="text-xs font-semibold text-gray-700">Primarios</p>
              <div class="mt-3 grid grid-cols-2 gap-2">
                ${renderDefectCards(p, "Sin defectos primarios.")}
              </div>
            </div>

            <div class="rounded-2xl bg-white border border-green-200 p-4">
              <p class="text-xs font-semibold text-gray-700">Secundarios</p>
              <div class="mt-3 grid grid-cols-2 gap-2">
                ${renderDefectCards(s, "Sin defectos secundarios.")}
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  let busy = false;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;

    if (!fileInput.files || !fileInput.files[0]) {
      showStatus("Selecciona una imagen.", true);
      return;
    }

    busy = true;
    btn.disabled = true;
    showStatus("Evaluando y guardando...", false);

    if (result) {
      result.classList.add("hidden");
      result.innerHTML = "";
    }

    try {
      const fd = new FormData(form);
      fd.append("batch_id", batchIdEl.value);

      const resp = await fetch(urlEl.value, {
        method: "POST",
        body: fd,
        credentials: "include",
      });

      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || "Error desconocido.");

      showStatus(
        data.already_evaluated ? "Este lote ya estaba evaluado" : "Evaluación guardada",
        false
      );

      draftBox.outerHTML = renderEvaluatedBox(data);

    } catch (err) {
      showStatus(err?.message || "Error al evaluar.", true);
    } finally {
      busy = false;
      btn.disabled = false;
    }
  });
})();
