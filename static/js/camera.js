document.addEventListener("DOMContentLoaded", () => {
  setupCameraPreview({
    camId: "cam1",
    timeoutMs: null,
    searchingText: "Buscando cámara principal...",
    liveText: "Monitoreo en vivo",
    offlineText: "Conecta la cámara principal para mostrarla aquí."
  });

  setupCameraPreview({
    camId: "cam2",
    timeoutMs: 40000,
    searchingText: "Buscando segunda cámara...",
    liveText: "Monitoreo en vivo",
    offlineText: "Conecta una segunda cámara para mostrarla aquí."
  });
});

function setupCameraPreview(config) {
  const img = document.getElementById(`${config.camId}-img`);
  if (!img) return;

  let hasVideo = false;
  let stoppedByTimeout = false;

  setCameraState(config.camId, "searching", config.searchingText);

  const checkVideoInterval = setInterval(() => {
    if (stoppedByTimeout) {
      clearInterval(checkVideoInterval);
      return;
    }

    if (img.naturalWidth > 0 && img.naturalHeight > 0) {
      hasVideo = true;
      setCameraState(config.camId, "live", config.liveText);
      clearInterval(checkVideoInterval);
    }
  }, 500);

  img.addEventListener("load", () => {
    if (stoppedByTimeout) return;

    hasVideo = true;
    setCameraState(config.camId, "live", config.liveText);
    clearInterval(checkVideoInterval);
  });

  img.addEventListener("error", () => {
    if (stoppedByTimeout) return;

    setCameraState(config.camId, "offline", config.offlineText);
    clearInterval(checkVideoInterval);
  });

  if (config.timeoutMs !== null) {
    setTimeout(() => {
      if (hasVideo) return;

      stoppedByTimeout = true;
      clearInterval(checkVideoInterval);

      img.removeAttribute("src");
      setCameraState(config.camId, "offline", config.offlineText);
    }, config.timeoutMs);
  }
}

function setCameraState(camId, state, message) {
  const img = document.getElementById(`${camId}-img`);
  const badge = document.getElementById(`${camId}-badge`);
  const text = document.getElementById(`${camId}-text`);
  const placeholder = document.getElementById(`${camId}-placeholder`);

  if (!img || !badge || !text || !placeholder) return;

  badge.className = "text-xs px-3 py-1 rounded-full border";
  text.textContent = message;

  if (state === "live") {
    badge.textContent = "EN VIVO";
    badge.classList.add("bg-green-50", "text-green-700", "border-green-200");

    img.classList.remove("hidden");
    placeholder.classList.add("hidden");
    return;
  }

  if (state === "searching") {
    badge.textContent = "BUSCANDO";
    badge.classList.add("bg-yellow-50", "text-yellow-700", "border-yellow-200");

    img.classList.remove("hidden");
    placeholder.classList.add("hidden");
    return;
  }

  badge.textContent = "OFFLINE";
  badge.classList.add("bg-red-50", "text-red-700", "border-red-200");

  img.classList.add("hidden");
  placeholder.classList.remove("hidden");
}
