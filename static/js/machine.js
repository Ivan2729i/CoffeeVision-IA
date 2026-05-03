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

  let isRunning = false;
  let currentSpeed = Number(speedInput?.value || 50);

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

      @keyframes spin {
        from { transform: translateY(-50%) rotate(0deg); }
        to { transform: translateY(-50%) rotate(360deg); }
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

  // Aquí el motor real
  async function sendMotorCommand(command, speed = currentSpeed) {
    console.log("Comando simulado:", {
      command,
      speed,
    });

    /*
      await fetch("http://IP_DEL_ESP32/motor", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          command: command,
          speed: speed,
        }),
      });
    */

    return true;
  }

  async function startBelt() {
    await sendMotorCommand("start", currentSpeed);

    isRunning = true;
    lastAction.textContent = "Inicio";
    updateUI();
  }

  async function stopBelt() {
    await sendMotorCommand("stop", 0);

    isRunning = false;
    lastAction.textContent = "Detención";
    updateUI();
  }

  async function changeSpeed(value) {
    currentSpeed = Number(value);
    speedValue.textContent = currentSpeed;

    if (isRunning) {
      await sendMotorCommand("speed", currentSpeed);
      lastAction.textContent = `Velocidad ${currentSpeed}%`;
      updateUI();
    }
  }

  injectMachineStyles();
  updateUI();

  btnStart?.addEventListener("click", startBelt);
  btnStop?.addEventListener("click", stopBelt);

  speedInput?.addEventListener("input", (event) => {
    changeSpeed(event.target.value);
  });
});
