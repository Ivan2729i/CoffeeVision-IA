(() => {
  const batchIdEl = document.getElementById("qaLiveBatchId");
  if (!batchIdEl) return;

  const camId = document.getElementById("qaLiveCamId")?.value || "cam1";
  const batchId = batchIdEl.value;

  const urlStart  = document.getElementById("qaLiveUrlStart")?.value;
  const urlStop   = document.getElementById("qaLiveUrlStop")?.value;
  const urlSave   = document.getElementById("qaLiveUrlSave")?.value;
  const urlStatus = document.getElementById("qaLiveUrlStatus")?.value;

  // STREAMS
  const previewUrl = document.getElementById("qaLivePreviewUrl")?.value;
  const imgUrl     = document.getElementById("qaLiveImgUrl")?.value;

  const btnStart = document.getElementById("qaLiveStart");
  const btnStop  = document.getElementById("qaLiveStop");
  const btnSave  = document.getElementById("qaLiveSave");

  const img = document.getElementById("qaLiveImg");
  const badge = document.getElementById("qaLiveBadge");
  const remainingEl = document.getElementById("qaLiveRemaining");

  const primaryEl = document.getElementById("qaLivePrimary");
  const secondaryEl = document.getElementById("qaLiveSecondary");
  const gradeEl = document.getElementById("qaLiveGrade");
  const defectsEl = document.getElementById("qaLiveDefects");

  const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value;

  let pollTimer = null;
  let lastState = null;
  let hasPolledOnce = false;
  let startingLive = false;

  // ========= TOASTS =========
  const AUTO_CLOSE_MS = 2600;
  const ANIM_MS = 220;

  function ensureToastRoot() {
    let root = document.getElementById("fs-toast-root");
    if (root) return root;

    root = document.createElement("div");
    root.id = "fs-toast-root";
    root.className = "fixed inset-0 pointer-events-none z-[9999] grid place-items-start px-4 pt-6";

    const inner = document.createElement("div");
    inner.className = "w-full max-w-md space-y-3 pointer-events-auto";
    root.appendChild(inner);

    document.body.appendChild(root);
    return root;
  }

  function closeToast(el) {
    if (!el || el.dataset.closing === "1") return;
    el.dataset.closing = "1";
    el.classList.add("hide");
    setTimeout(() => el.remove(), ANIM_MS);
  }

  function toastTitle(type) {
    if (type === "success") return "Éxito";
    if (type === "error") return "Error";
    if (type === "warning") return "Aviso";
    return "Info";
  }

  function dotColor(type) {
    if (type === "success") return "#22c55e";
    if (type === "error") return "#ef4444";
    if (type === "warning") return "#f59e0b";
    return "#60a5fa";
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  function notify(type, message) {
    try {
      const root = ensureToastRoot();
      const container = root.querySelector("div");
      if (!container) return;

      const el = document.createElement("div");
      el.className = "fs-toast card-fs px-4 py-3 border border-card-border";
      el.innerHTML = `
        <div class="flex items-start gap-3">
          <div class="mt-1 h-2.5 w-2.5 rounded-full" style="background:${dotColor(type)}"></div>
          <div class="text-sm">
            <div class="font-semibold">${escapeHtml(toastTitle(type))}</div>
            <div class="text-text-muted">${escapeHtml(message)}</div>
          </div>
        </div>
      `;
      container.appendChild(el);
      setTimeout(() => closeToast(el), AUTO_CLOSE_MS);
    } catch (e) {
      console.log(`[${type}] ${message}`);
    }
  }

  // ========= STREAM helpers =========
  function setPreview() {
    if (!img || !previewUrl) return;
    img.src = `${previewUrl}?t=${Date.now()}`;
  }

  function setAnnotated() {
    if (!img || !imgUrl) return;
    img.src = `${imgUrl}?t=${Date.now()}`;
  }

  function clearImg() {
      if (!img) return;
      img.removeAttribute("src");
  }

  function setAnnotatedWithRetry(delay = 400) {
      setTimeout(() => {
        if (!img || !imgUrl) return;
        img.src = `${imgUrl}?t=${Date.now()}`;
      }, delay);
  }

  function isPreviewSrc() {
    return !!img?.src && previewUrl && img.src.includes(previewUrl);
  }

  // ========= UI helpers =========
  function setBadge(state) {
    // default
    let label = "LIVE";
    if (state === "running") label = "DETECTING";
    if (state === "finished") label = "FINISHED";
    if (state === "error") label = "ERROR";

    badge.textContent = label;

    badge.className = "ml-auto text-xs px-3 py-1 rounded-full border";
    if (state === "running") {
      badge.classList.add("bg-emerald-50", "text-emerald-700", "border-emerald-100");
    } else if (state === "finished") {
      badge.classList.add("bg-blue-50", "text-blue-700", "border-blue-100");
    } else if (state === "error") {
      badge.classList.add("bg-red-50", "text-red-700", "border-red-100");
    } else {
      // idle/preview
      badge.classList.add("bg-gray-50", "text-gray-700", "border-gray-200");
    }
  }

  function setSummaryEmpty(msg) {
    primaryEl.textContent = "—";
    secondaryEl.textContent = "—";
    gradeEl.textContent = "—";
    defectsEl.innerHTML = `<p class="text-sm text-gray-500">${escapeHtml(msg)}</p>`;
  }

  function renderFinal(final) {
    if (!final) {
      setSummaryEmpty("Sin resultados aún.");
      return;
    }

    primaryEl.textContent = final.primary_total ?? 0;
    secondaryEl.textContent = final.secondary_total ?? 0;
    gradeEl.textContent = final.grade ?? "—";

    const details = Array.isArray(final.details) ? final.details : [];

    const entries = details
      .filter((it) => Number(it.raw_count || 0) > 0)
      .sort((a, b) => Number(b.raw_count || 0) - Number(a.raw_count || 0));

    if (entries.length === 0) {
      defectsEl.innerHTML = `<p class="text-sm text-gray-500">No se detectaron defectos confirmados.</p>`;
      return;
    }

    defectsEl.innerHTML = entries.map((it) => {
      const typeLabel = it.defect_type === "primary" ? "Primario" : "Secundario";

      return `
        <div class="bg-white rounded-xl border border-gray-200 p-3">
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="text-[11px] text-gray-500">${escapeHtml(typeLabel)}</p>
              <p class="text-sm text-[#2b1d16] font-semibold truncate">${escapeHtml(it.code)}</p>
            </div>
            <div class="text-right">
              <p class="text-[11px] text-gray-500">Visual</p>
              <p class="text-sm font-bold text-gray-800">${escapeHtml(it.raw_count)}</p>
            </div>
          </div>
        </div>
      `;
    }).join("");
  }

  async function post(url, data) {
    const body = new URLSearchParams(data);
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
      credentials: "include",
    });
    return r.json();
  }

  async function poll() {
    const r = await fetch(
      `${urlStatus}?cam_id=${encodeURIComponent(camId)}&batch_id=${encodeURIComponent(batchId)}`,
      { credentials: "include" }
    );
    const j = await r.json();
    if (!j.ok) return;

    const state = j.state || "idle";
    setBadge(state);
    remainingEl.textContent = (j.idle_s ?? "—");

    if (!hasPolledOnce) {
      hasPolledOnce = true;
      lastState = state;
    } else if (state !== lastState) {
      if (state === "running") notify("info", "Inició la detección en vivo.");
      if (state === "finished") notify("success", "Detección finalizada. Ya puedes guardar.");
      if (state === "error") notify("error", `Error en detección: ${j.error || "desconocido"}`);
      lastState = state;
    }

    if (state === "idle") {
      btnStart.disabled = false;
      btnStop.disabled = true;

      btnSave.classList.add("hidden");
      btnSave.disabled = true;

      if (!img.src || !isPreviewSrc()) setPreview();
      setSummaryEmpty("Inicia una evaluación para ver resultados.");
      return;
    }

    if (state === "running") {
      btnStart.disabled = true;
      btnStop.disabled = false;

      btnSave.classList.add("hidden");
      btnSave.disabled = true;

      return;
    }

    if (state === "finished") {
      btnStart.disabled = false;
      btnStop.disabled = true;

      btnSave.classList.remove("hidden");
      btnSave.disabled = false;

      renderFinal(j.final);
      return;
    }

    if (state === "error") {
      btnStart.disabled = false;
      btnStop.disabled = true;

      btnSave.classList.add("hidden");
      btnSave.disabled = true;

      // vuelve a preview para que no quede negro
      if (!img.src || !isPreviewSrc()) setPreview();
      setSummaryEmpty(`Error: ${j.error || "desconocido"}`);
      return;
    }
  }

  btnStart?.addEventListener("click", async () => {
      if (!csrf) {
        notify("error", "CSRF no encontrado. Revisa tu template.");
        return;
      }

      startingLive = true;
      notify("info", "Iniciando detección en vivo...");
      setSummaryEmpty("Detectando...");
      setBadge("running");

      clearImg();

      await new Promise(resolve => setTimeout(resolve, 800));

      const j = await post(urlStart, {
        cam_id: camId,
        batch_id: batchId,
        csrfmiddlewaretoken: csrf,
      });

      if (j.already_evaluated) {
        startingLive = false;
        notify("warning", "Este lote ya fue evaluado.");
        window.location.reload();
        return;
      }

      if (!j.ok) {
        startingLive = false;
        notify("error", j.error || "No se pudo iniciar la detección.");
        setBadge("error");
        setPreview();
        setSummaryEmpty(j.error || "No se pudo iniciar.");
        return;
      }

      await new Promise(resolve => setTimeout(resolve, 500));
      setAnnotatedWithRetry(0);
      startingLive = false;
      await poll();
  });

  btnStop?.addEventListener("click", async () => {
      if (!csrf) return;

      notify("warning", "Deteniendo detección...");

      const j = await post(urlStop, { cam_id: camId, csrfmiddlewaretoken: csrf });

      if (!j.ok) {
        notify("error", j.error || "No se pudo detener.");
        return;
      }

      setBadge("idle");
      setPreview();
      setSummaryEmpty("Inicia una evaluación para ver resultados.");

      await poll();
  });

  btnSave?.addEventListener("click", async () => {
    if (!csrf) return;

    btnSave.disabled = true;
    notify("info", "Guardando evaluación...");

    const j = await post(urlSave, { cam_id: camId, csrfmiddlewaretoken: csrf });

    if (j.ok) {
      notify("success", "Evaluación guardada correctamente.");
      window.location.reload();
      return;
    }

    notify("error", j.error || "No se pudo guardar.");
    btnSave.disabled = false;
  });

  if (img) {
      img.onerror = () => {
        // si el stream anotado falla al primer intento, reintenta
        if (badge?.textContent === "DETECTING" || badge?.textContent === "FINISHED") {
          setAnnotatedWithRetry(700);
        }
      };
  }

  // ===== INIT =====
  setBadge("idle");
  setPreview();
  setSummaryEmpty("Inicia una evaluación para ver resultados.");

  poll();
  pollTimer = setInterval(poll, 2500);

  window.addEventListener("beforeunload", () => {
    if (pollTimer) clearInterval(pollTimer);
  });
})();
