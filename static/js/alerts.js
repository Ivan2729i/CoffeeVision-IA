(() => {
  const root = document.getElementById("alerts-module");
  if (!root) return;

  const els = {
    kpiTotal: document.getElementById("alerts-kpi-total"),
    kpiUnseen: document.getElementById("alerts-kpi-unseen"),
    kpiCritical: document.getElementById("alerts-kpi-critical"),
    kpiError: document.getElementById("alerts-kpi-error"),

    severity: document.getElementById("alerts-severity"),
    category: document.getElementById("alerts-category"),
    status: document.getElementById("alerts-status"),

    tbody: document.getElementById("alerts-table-body"),
  };

  async function loadSummary() {
    try {
      const res = await fetch("/dashboard/api/alerts/summary/", {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });

      if (!res.ok) throw new Error("No se pudo cargar el resumen de alertas.");

      const data = await res.json();
      if (!data?.ok) throw new Error("Respuesta inválida.");

      const s = data.summary || {};
      els.kpiTotal.textContent = s.total ?? 0;
      els.kpiUnseen.textContent = s.unseen ?? 0;
      els.kpiCritical.textContent = s.critical ?? 0;
      els.kpiError.textContent = s.error ?? 0;
    } catch (err) {
      console.error(err);
    }
  }

  async function loadList() {
    setLoading();

    try {
      const params = new URLSearchParams();

      if (els.severity.value) params.set("severity", els.severity.value);
      if (els.category.value) params.set("category", els.category.value);
      if (els.status.value) params.set("status", els.status.value);

      const res = await fetch(`/dashboard/api/alerts/list/?${params.toString()}`, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });

      if (!res.ok) throw new Error("No se pudo cargar la lista de alertas.");

      const data = await res.json();
      if (!data?.ok) throw new Error("Respuesta inválida.");

      renderRows(data.results || []);
    } catch (err) {
      console.error(err);
      els.tbody.innerHTML = `
        <tr>
          <td colspan="7" class="px-6 py-10 text-center text-sm text-red-600">
            Ocurrió un error al cargar las alertas.
          </td>
        </tr>
      `;
    }
  }

  function setLoading() {
    els.tbody.innerHTML = `
      <tr>
        <td colspan="7" class="px-6 py-10 text-center text-sm text-[#8a6a58]">
          Cargando alertas...
        </td>
      </tr>
    `;
  }

  function renderRows(rows) {
    if (!rows.length) {
      els.tbody.innerHTML = `
        <tr>
          <td colspan="7" class="px-6 py-10 text-center text-sm text-[#8a6a58]">
            No hay alertas registradas con los filtros seleccionados.
          </td>
        </tr>
      `;
      return;
    }

    els.tbody.innerHTML = rows.map((alert) => {
      const severityBadge = renderSeverity(alert.severity);
      const categoryBadge = renderCategory(alert.category);
      const stateBadge = renderState(alert);
      const createdAt = formatDate(alert.created_at);
      const batchCode = alert.batch_code || "—";

      return `
        <tr class="border-b border-[#eadfd6] hover:bg-[#fcf7f2] transition">
          <td class="px-6 py-4 text-sm text-[#2b160b] whitespace-nowrap">${escapeHtml(createdAt)}</td>
          <td class="px-6 py-4">${severityBadge}</td>
          <td class="px-6 py-4">${categoryBadge}</td>
          <td class="px-6 py-4">
            <div class="font-semibold text-[#2b160b]">${escapeHtml(alert.title || "—")}</div>
            <div class="mt-1 text-sm text-[#8a6a58]">${escapeHtml(alert.message || "")}</div>
          </td>
          <td class="px-6 py-4 text-sm text-[#2b160b]">${escapeHtml(batchCode)}</td>
          <td class="px-6 py-4">${stateBadge}</td>
          <td class="px-6 py-4">
            <div class="flex justify-end gap-2">
              ${
                !alert.is_seen
                  ? `<button type="button"
                      class="rounded-xl border border-[#ddc7b8] px-3 py-2 text-xs font-medium text-[#2b160b] hover:bg-[#f7efe8]"
                      data-alert-seen="${alert.id}">
                      Marcar vista
                    </button>`
                  : ""
              }
              ${
                alert.is_active
                  ? `<button type="button"
                      class="rounded-xl border border-[#ddc7b8] px-3 py-2 text-xs font-medium text-[#2b160b] hover:bg-[#f7efe8]"
                      data-alert-deactivate="${alert.id}">
                      Desactivar
                    </button>`
                  : ""
              }
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }

  function renderSeverity(value) {
    const map = {
      warning: "bg-amber-50 text-amber-700 border-amber-200",
      error: "bg-red-50 text-red-700 border-red-200",
      critical: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
    };

    const label = {
      warning: "Warning",
      error: "Error",
      critical: "Critical",
    }[value] || "—";

    return `<span class="inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${map[value] || "border-[#ddc7b8] text-[#2b160b]"}">${label}</span>`;
  }

  function renderCategory(value) {
    const label = {
      quality: "Quality",
      evaluation: "Evaluation",
      camera: "Camera",
      report: "Report",
      system: "System",
    }[value] || "—";

    return `<span class="inline-flex rounded-full border border-[#ddc7b8] px-3 py-1 text-xs font-semibold text-[#2b160b] bg-white">${label}</span>`;
  }

  function renderState(alert) {
    if (!alert.is_active) {
      return `<span class="inline-flex rounded-full border border-[#ddc7b8] px-3 py-1 text-xs font-semibold text-[#8a6a58] bg-white">Inactiva</span>`;
    }

    if (!alert.is_seen) {
      return `<span class="inline-flex rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">No vista</span>`;
    }

    return `<span class="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">Vista</span>`;
  }

  async function markSeen(alertId) {
    try {
      const res = await fetch(`/dashboard/api/alerts/${alertId}/seen/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCSRFToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
        credentials: "same-origin",
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok || !data?.ok) {
        throw new Error(data?.message || "No se pudo marcar la alerta como vista.");
      }

      window.fsToast?.("Alerta marcada como vista.", "success");
      await Promise.all([loadSummary(), loadList()]);
    } catch (err) {
      console.error(err);
      window.fsToast?.("No se pudo marcar la alerta como vista.", "error");
    }
  }

  async function deactivateAlert(alertId) {
    try {
      const res = await fetch(`/dashboard/api/alerts/${alertId}/deactivate/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCSRFToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
        credentials: "same-origin",
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok || !data?.ok) {
        throw new Error(data?.message || "No se pudo desactivar la alerta.");
      }

      window.fsToast?.("Alerta desactivada.", "success");
      await Promise.all([loadSummary(), loadList()]);
    } catch (err) {
      console.error(err);
      window.fsToast?.("No se pudo desactivar la alerta.", "error");
    }
  }

  function attachEvents() {
    [els.severity, els.category, els.status].forEach((el) => {
      el?.addEventListener("change", loadList);
    });

    els.tbody?.addEventListener("click", (e) => {
      const seenBtn = e.target.closest("[data-alert-seen]");
      if (seenBtn) {
        markSeen(seenBtn.dataset.alertSeen);
        return;
      }

      const deactivateBtn = e.target.closest("[data-alert-deactivate]");
      if (deactivateBtn) {
        deactivateAlert(deactivateBtn.dataset.alertDeactivate);
      }
    });
  }

  function formatDate(value) {
    if (!value) return "—";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return value;
    return dt.toLocaleString("es-MX", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function getCSRFToken() {
    const cookie = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="));
    return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  attachEvents();
  loadSummary();
  loadList();
})();
