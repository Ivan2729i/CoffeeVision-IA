document.addEventListener("DOMContentLoaded", () => {
  const btnStart = document.getElementById("mc-start");
  const btnStop = document.getElementById("mc-stop");
  const speedInput = document.getElementById("mc-speed");

  const statusBadge = document.getElementById("mc-status-badge");
  const statusText = document.getElementById("mc-status-text");
  const speedValue = document.getElementById("mc-speed-value");
  const lastAction = document.getElementById("mc-last-action");
  const previewText = document.getElementById("mc-preview-text");
  const dot = document.getElementById("mc-dot");
  const belt = document.getElementById("mc-belt");

  if (!speedInput || !statusBadge || !statusText || !speedValue || !previewText || !dot || !belt) {
    return;
  }

  const MOTOR_API_URL = "/dashboard/api/machine/motor/";

  let speedTimer = null;

  let isRunning = localStorage.getItem("mc_is_running") === "true";
  let currentSpeed = Number(localStorage.getItem("mc_speed") || speedInput.value || 50);

  speedInput.value = currentSpeed;

  function saveMachineState() {
    localStorage.setItem("mc_is_running", String(isRunning));
    localStorage.setItem("mc_speed", String(currentSpeed));
  }

  function getCookie(name) {
    const cookies = document.cookie ? document.cookie.split(";") : [];

    for (const cookie of cookies) {
      const trimmed = cookie.trim();

      if (trimmed.startsWith(name + "=")) {
        return decodeURIComponent(trimmed.substring(name.length + 1));
      }
    }

    return "";
  }

  function injectMachineStyles() {
    if (document.getElementById("machine-control-styles")) return;

    const style = document.createElement("style");
    style.id = "machine-control-styles";
    style.textContent = `
      @keyframes conveyorMove {
        from { transform: translateX(0); }
        to { transform: translateX(32px); }
      }

      @keyframes pulseDot {
        0%, 100% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.25); opacity: .65; }
      }

      @keyframes spin {
        from { transform: translateY(-50%) rotate(0deg); }
        to { transform: translateY(-50%) rotate(360deg); }
      }

      .mc-belt-running {
        animation-name: conveyorMove;
        animation-timing-function: linear;
        animation-iteration-count: infinite;
      }

      .mc-dot-running {
        animation: pulseDot 1s ease-in-out infinite;
      }

      .mc-roller-running {
        animation: spin 1s linear infinite;
      }
    `;
    document.head.appendChild(style);
  }

  function getAnimationDuration(speed) {
    const safeSpeed = Math.max(1, Number(speed));
    return `${Math.max(0.25, 3 - safeSpeed / 40)}s`;
  }

  function updateUI() {
    speedValue.textContent = currentSpeed;
    speedInput.value = currentSpeed;

    if (isRunning) {
      statusText.textContent = "En marcha";
      previewText.textContent = `Banda operando al ${currentSpeed}% de velocidad.`;
      statusBadge.textContent = "En marcha";

      statusBadge.className =
        "inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-green-50 text-green-700 border border-green-200";

      dot.className = "w-4 h-4 rounded-full bg-green-500 shadow mc-dot-running";

      belt.classList.add("mc-belt-running");
      belt.style.animationDuration = getAnimationDuration(currentSpeed);
    } else {
      statusText.textContent = "Detenida";
      previewText.textContent = "Sistema en espera.";
      statusBadge.textContent = "Detenida";

      statusBadge.className =
        "inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-[#f8e7df] text-[#8a3f24] border border-[#efc8b8]";

      dot.className = "w-4 h-4 rounded-full bg-[#c46a4a] shadow";

      belt.classList.remove("mc-belt-running");
      belt.style.animationDuration = "";
    }
  }

  async function sendMotorCommand(command, speed = currentSpeed) {
    const response = await fetch(MOTOR_API_URL, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        command: command,
        speed: Number(speed),
      }),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok || !data.ok) {
      throw new Error(data.error || "No se pudo enviar el comando al ESP32.");
    }

    console.log("Respuesta ESP32:", data);
    return data;
  }

  async function startBelt() {
    try {
      btnStart.disabled = true;

      await sendMotorCommand("start", currentSpeed);

      isRunning = true;
      lastAction.textContent = "Inicio";

      saveMachineState();
      updateUI();
    } catch (error) {
      console.error(error);
      lastAction.textContent = `Error: ${error.message}`;
    } finally {
      btnStart.disabled = false;
    }
  }

  async function stopBelt() {
    try {
      btnStop.disabled = true;

      await sendMotorCommand("stop", 0);

      isRunning = false;
      lastAction.textContent = "Detención";

      saveMachineState();
      updateUI();
    } catch (error) {
      console.error(error);
      lastAction.textContent = `Error: ${error.message}`;
    } finally {
      btnStop.disabled = false;
    }
  }

  async function changeSpeed(value) {
    currentSpeed = Number(value);
    speedValue.textContent = currentSpeed;

    saveMachineState();

    if (!isRunning) {
      updateUI();
      return;
    }

    try {
      await sendMotorCommand("speed", currentSpeed);

      lastAction.textContent = `Velocidad ${currentSpeed}%`;

      saveMachineState();
      updateUI();
    } catch (error) {
      console.error(error);
      lastAction.textContent = `Error: ${error.message}`;
    }
  }

  injectMachineStyles();
  updateUI();

  btnStart?.addEventListener("click", startBelt);
  btnStop?.addEventListener("click", stopBelt);

  speedInput?.addEventListener("input", (event) => {
    currentSpeed = Number(event.target.value);

    speedValue.textContent = currentSpeed;
    saveMachineState();
    updateUI();

    clearTimeout(speedTimer);

    speedTimer = setTimeout(() => {
      changeSpeed(currentSpeed);
    }, 180);
  });
});
