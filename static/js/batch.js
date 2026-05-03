(function () {
  const root = document.getElementById("batch-metrics");
  if (!root) return;

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString();
  }

  function kpiCard(title, value) {
    return `
      <div class="bg-white rounded-2xl border border-[#efe6df] p-4">
        <div class="text-xs font-semibold text-[#6b4b3e]">${title}</div>
        <div class="text-2xl font-bold text-[#2b1d16] mt-1">${value}</div>
      </div>
    `;
  }

  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function sortDefects(obj) {
    // ordena por cantidad desc
    const entries = Object.entries(obj || {}).map(([k, v]) => [k, Number(v || 0)]);
    entries.sort((a, b) => b[1] - a[1]);
    return entries;
  }

  function sumCounts(obj) {
    let t = 0;
    for (const v of Object.values(obj || {})) t += Number(v || 0);
    return t;
  }

  function renderDefectList(entries) {
    if (!entries.length) {
      return `<div class="text-sm text-[#6b4b3e]">Sin defectos.</div>`;
    }

    return `
      <ul class="mt-2 space-y-2">
        ${entries.map(([name, val]) => `
          <li class="flex items-center justify-between bg-[#fbf7f2] border border-[#efe6df] rounded-lg px-3 py-2">
            <span class="text-sm font-medium text-[#2b1d16]">${esc(name)}</span>
            <span class="text-sm font-semibold text-[#2b1d16]">${val}</span>
          </li>
        `).join("")}
      </ul>
    `;
  }

  async function bmFetch(params) {
    const url = new URL("/dashboard/api/batch-metrics/summary/", window.location.origin);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== "" && v !== null && v !== undefined) url.searchParams.set(k, v);
    });

    const res = await fetch(url, { credentials: "include" });
    const data = await res.json().catch(() => ({}));

    if (!res.ok || !data.ok) throw new Error(data.error || `API error ${res.status}`);
    return data;
  }

  function bmRenderKpis(kpis) {
    const el = document.getElementById("bm-kpis");
    el.innerHTML = [
      kpiCard("Lotes filtrados", kpis.total_batches),
      kpiCard("Lotes evaluados", kpis.evaluated_batches),
      kpiCard("KG procesados", `${Number(kpis.total_weight_kg).toFixed(3)} kg`),
      kpiCard("Calidad / Rechazo", `${kpis.quality_pct}% / ${kpis.rejection_pct}%`),
    ].join("");
  }

  function bmRenderTable(rows) {
    const tbody = document.getElementById("bm-table");
    const countEl = document.getElementById("bm-count");
    countEl.textContent = `${rows.length} registros`;

    if (!rows.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="p-4 text-sm text-[#6b4b3e]">Sin resultados con esos filtros.</td>
        </tr>`;
      return;
    }

    tbody.innerHTML = rows.map(r => {
      const grade = r.evaluation?.grade ?? "—";
      const status = (r.status === "evaluated") ? "Evaluado" : "Borrador";
      return `
        <tr class="border-t border-[#efe6df] hover:bg-[#fbf7f2] cursor-pointer" data-code="${esc(r.code)}">
          <td class="p-3 font-semibold">${esc(r.code)}</td>
          <td class="p-3">${esc(r.provider?.name ?? "—")}</td>
          <td class="p-3">${Number(r.weight_kg).toFixed(3)}</td>
          <td class="p-3">${status}</td>
          <td class="p-3">${grade}</td>
          <td class="p-3">${fmtDate(r.created_at)}</td>
        </tr>
      `;
    }).join("");
  }

  function bmRenderDetail(detail) {
    const el = document.getElementById("bm-detail");

    if (!detail) {
      el.innerHTML = `
        <div class="text-xs text-[#6b4b3e]">
          Consejo: si un lote está en <b>borrador</b>, no aparecerán totales ni defectos.
        </div>
      `;
      return;
    }

    const ev = detail.evaluation;
    const statusLabel = (detail.status === "evaluated") ? "Evaluado" : "Borrador";

    // si no hay evaluación
    if (!ev) {
      el.innerHTML = `
        <div class="space-y-2 text-sm text-[#2b1d16]">
          <div><span class="text-[#6b4b3e]">Código:</span> <b>${esc(detail.code)}</b></div>
          <div><span class="text-[#6b4b3e]">Proveedor:</span> ${esc(detail.provider?.name ?? "—")}</div>
          <div><span class="text-[#6b4b3e]">Contacto:</span> ${esc(detail.provider?.contact ?? "—")}</div>
          <div><span class="text-[#6b4b3e]">Muestra:</span> ${Number(detail.sample_size_g ?? 350).toFixed(0)} g</div>
          <div><span class="text-[#6b4b3e]">Peso:</span> ${Number(detail.weight_kg).toFixed(3)} kg</div>
          <div><span class="text-[#6b4b3e]">Estado:</span> ${statusLabel}</div>
          <div><span class="text-[#6b4b3e]">Creado:</span> ${fmtDate(detail.created_at)}</div>

          <hr class="border-[#efe6df] my-3"/>

          <div class="text-sm text-[#6b4b3e]">Sin evaluación todavía.</div>
        </div>
      `;
      return;
    }

    // counts formateados (primarios/secundarios)
    const counts = ev.counts || {};
    const primaryObj = counts.primary || {};
    const secondaryObj = counts.secondary || {};

    const primaryEntries = sortDefects(primaryObj);
    const secondaryEntries = sortDefects(secondaryObj);

    // totales
    const primaryTotal = Number(ev.primary_total ?? sumCounts(primaryObj));
    const secondaryTotal = Number(ev.secondary_total ?? sumCounts(secondaryObj));
    const defectsTotal = Number(ev.defects_total ?? (primaryTotal + secondaryTotal));

    el.innerHTML = `
      <div class="space-y-2 text-sm text-[#2b1d16]">
        <div><span class="text-[#6b4b3e]">Código:</span> <b>${esc(detail.code)}</b></div>
        <div><span class="text-[#6b4b3e]">Proveedor:</span> ${esc(detail.provider?.name ?? "—")}</div>
        <div><span class="text-[#6b4b3e]">Contacto:</span> ${esc(detail.provider?.contact ?? "—")}</div>
        <div><span class="text-[#6b4b3e]">Muestra:</span> ${Number(detail.sample_size_g ?? 350).toFixed(0)} g</div>
        <div><span class="text-[#6b4b3e]">Peso:</span> ${Number(detail.weight_kg).toFixed(3)} kg</div>
        <div><span class="text-[#6b4b3e]">Estado:</span> ${statusLabel}</div>
        <div><span class="text-[#6b4b3e]">Creado:</span> ${fmtDate(detail.created_at)}</div>

        <hr class="border-[#efe6df] my-3"/>

        <div class="flex items-center justify-between">
          <div class="text-sm font-semibold text-[#2b1d16]">Evaluación</div>
          <div class="text-xs text-[#6b4b3e]">${esc(ev.method || "")}</div>
        </div>

        <div class="bg-[#fbf7f2] border border-[#efe6df] rounded-xl p-3">
          <div class="flex items-center justify-between">
            <div class="text-xs font-semibold text-[#6b4b3e]">Grado</div>
            <div class="text-lg font-bold text-[#2b1d16]">${ev.grade ?? "—"}</div>
          </div>
          <div class="mt-3 grid grid-cols-3 gap-2 text-center">
          <div class="bg-white rounded-lg border border-[#efe6df] p-2">
            <div class="text-[11px] text-[#6b4b3e]">Primarios</div>
            <div class="font-bold text-[#2b1d16]">${primaryTotal}</div>
          </div>
        
          <div class="bg-white rounded-lg border border-[#efe6df] p-2">
            <div class="text-[11px] text-[#6b4b3e]">Secundarios</div>
            <div class="font-bold text-[#2b1d16]">${secondaryTotal}</div>
          </div>
        
          <div class="bg-white rounded-lg border border-[#efe6df] p-2">
            <div class="text-[11px] text-[#6b4b3e]">Total</div>
            <div class="font-bold text-[#2b1d16]">${defectsTotal}</div>
          </div>
        </div>
        </div>

        <!-- Primarios -->
        <div class="mt-3">
          <div class="flex items-center justify-between">
            <div class="text-sm font-semibold text-[#2b1d16]">Defectos primarios</div>
            <div class="text-sm font-bold text-[#2b1d16]">${primaryTotal}</div>
          </div>
          ${renderDefectList(primaryEntries)}
        </div>

        <!-- Secundarios -->
        <div class="mt-4">
          <div class="flex items-center justify-between">
            <div class="text-sm font-semibold text-[#2b1d16]">Defectos secundarios</div>
            <div class="text-sm font-bold text-[#2b1d16]">${secondaryTotal}</div>
          </div>
          ${renderDefectList(secondaryEntries)}
        </div>
      </div>
    `;
  }

  async function bmLoad(selected = "") {
    const year = document.getElementById("bm-year")?.value || "";
    const month = document.getElementById("bm-month")?.value || "";
    const status = document.getElementById("bm-status")?.value || "all";
    const search = document.getElementById("bm-search")?.value || "";

    try {
      const data = await bmFetch({ year, month, status, search, selected, limit: 50 });
      bmRenderKpis(data.kpis);
      bmRenderTable(data.batches);
      bmRenderDetail(data.detail);
    } catch (err) {
      document.getElementById("bm-table").innerHTML = `
        <tr><td colspan="6" class="p-4 text-sm text-red-700">Error cargando datos: ${esc(err.message)}</td></tr>`;
      document.getElementById("bm-detail").innerHTML = `
        <div class="text-sm text-red-700">Error cargando detalle: ${esc(err.message)}</div>`;
    }
  }

  function bmInit() {
    const now = new Date();
    const yearInput = document.getElementById("bm-year");
    if (yearInput && !yearInput.value) yearInput.value = now.getFullYear();

    document.getElementById("bm-apply")?.addEventListener("click", () => bmLoad(""));
    document.getElementById("bm-reset")?.addEventListener("click", () => {
      document.getElementById("bm-year").value = new Date().getFullYear();
      document.getElementById("bm-month").value = "";
      document.getElementById("bm-status").value = "all";
      document.getElementById("bm-search").value = "";
      bmLoad("");
    });

    document.getElementById("bm-table")?.addEventListener("click", (e) => {
      const tr = e.target.closest("tr[data-code]");
      if (!tr) return;
      bmLoad(tr.dataset.code);
    });

    bmLoad("");
  }

  document.addEventListener("DOMContentLoaded", bmInit);
})();
