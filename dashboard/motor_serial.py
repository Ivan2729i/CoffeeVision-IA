import threading
import time

from django.conf import settings

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None


class MotorSerialController:
    def __init__(self):
        self._serial = None
        self._lock = threading.Lock()

        self.current_port = None
        self.last_speed = 50
        self.last_running = False
        self.last_response = ""

    def available_ports(self):
        if list_ports is None:
            return []

        ports = []

        for port in list_ports.comports():
            ports.append({
                "device": port.device,
                "description": port.description,
                "manufacturer": port.manufacturer,
                "hwid": port.hwid,
                "vid": port.vid,
                "pid": port.pid,
            })

        return ports

    def _close_serial(self):
        try:
            if self._serial and self._serial.is_open:
                self._serial.close()
        except Exception:
            pass

        self._serial = None

    def _read_lines(self, ser, seconds=1.0):
        responses = []
        start = time.time()

        while time.time() - start < seconds:
            raw = ser.readline()

            if not raw:
                continue

            text = raw.decode("utf-8", errors="ignore").strip()

            if text:
                responses.append(text)

        return "\n".join(responses)

    def _ordered_ports(self):
        ports = list(list_ports.comports())

        keywords = [
            "esp32",
            "espressif",
            "cp210",
            "silicon labs",
            "ch340",
            "wch",
            "usb serial",
            "usb-serial",
            "uart",
        ]

        def score(port):
            text = " ".join([
                str(port.description or ""),
                str(port.manufacturer or ""),
                str(port.hwid or ""),
            ]).lower()

            return 0 if any(keyword in text for keyword in keywords) else 1

        return sorted(ports, key=score)

    def _try_open_and_identify(self, port_device):
        baudrate = int(getattr(settings, "MOTOR_SERIAL_BAUDRATE", 115200))
        timeout = float(getattr(settings, "MOTOR_SERIAL_TIMEOUT", 1))
        device_id = getattr(settings, "MOTOR_SERIAL_ID", "COFFEEVISION_MOTOR_ESP32")

        ser = None

        try:
            ser = serial.Serial(
                port=port_device,
                baudrate=baudrate,
                timeout=timeout,
                write_timeout=timeout,
            )

            # Muchos ESP32 se reinician al abrir el puerto.
            time.sleep(2)

            ser.reset_input_buffer()
            ser.reset_output_buffer()

            # Preguntamos si es nuestro ESP32.
            ser.write(b"I\n")
            ser.flush()

            response = self._read_lines(ser, seconds=1.2)

            if device_id in response:
                ser.reset_input_buffer()
                ser.reset_output_buffer()

                self.current_port = port_device
                self.last_response = response

                return ser

            ser.close()
            return None

        except Exception:
            try:
                if ser and ser.is_open:
                    ser.close()
            except Exception:
                pass

            return None

    def _auto_connect(self):
        if list_ports is None:
            raise RuntimeError("No se pudo usar serial.tools.list_ports. Revisa pyserial.")

        ports = self._ordered_ports()

        if not ports:
            raise RuntimeError("No se encontraron puertos COM disponibles.")

        # Si ya habíamos encontrado un puerto antes, intentamos primero ese.
        if self.current_port:
            ser = self._try_open_and_identify(self.current_port)
            if ser:
                return ser

        # Escanear todos los COM.
        for port in ports:
            ser = self._try_open_and_identify(port.device)

            if ser:
                return ser

        available = ", ".join([f"{p.device} ({p.description})" for p in ports])

        raise RuntimeError(
            "No se encontró el ESP32 de CoffeeVision. "
            "Verifica que esté conectado, que el Monitor Serial esté cerrado "
            "y que el ESP32 tenga cargado el código con DEVICE_ID. "
            f"Puertos detectados: {available}"
        )

    def _connect(self):
        if serial is None:
            raise RuntimeError("pyserial no está instalado. Ejecuta: pip install pyserial")

        configured_port = str(getattr(settings, "MOTOR_SERIAL_PORT", "AUTO")).strip()

        if self._serial and self._serial.is_open:
            return self._serial

        if configured_port.upper() == "AUTO":
            self._serial = self._auto_connect()
            return self._serial

        baudrate = int(getattr(settings, "MOTOR_SERIAL_BAUDRATE", 115200))
        timeout = float(getattr(settings, "MOTOR_SERIAL_TIMEOUT", 1))

        try:
            self._serial = serial.Serial(
                port=configured_port,
                baudrate=baudrate,
                timeout=timeout,
                write_timeout=timeout,
            )

            time.sleep(2)

            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()

            self.current_port = configured_port

            return self._serial

        except Exception as e:
            raise RuntimeError(
                f"No se pudo abrir el puerto {configured_port}. "
                f"Detalle: {e}"
            )

    def _write_line(self, line: str):
        with self._lock:
            try:
                ser = self._connect()

                ser.write((line.strip() + "\n").encode("utf-8"))
                ser.flush()

                time.sleep(0.08)

                response = self._read_lines(ser, seconds=0.5)

                self.last_response = response

                return response

            except Exception:
                self._close_serial()
                raise

    def command(self, command: str, speed=None):
        command = (command or "").lower().strip()

        if speed is not None:
            speed = max(0, min(100, int(speed)))

        if command == "start":
            if speed is not None:
                self._write_line(f"V{speed}")
                self.last_speed = speed

            response = self._write_line("E")
            self.last_running = True

        elif command == "stop":
            response = self._write_line("S")
            self.last_running = False

        elif command == "speed":
            if speed is None:
                raise ValueError("Falta la velocidad.")

            response = self._write_line(f"V{speed}")
            self.last_speed = speed

        elif command == "faster":
            response = self._write_line("A")

        elif command == "slower":
            response = self._write_line("B")

        elif command == "identify":
            response = self._write_line("I")

        else:
            raise ValueError("Comando no válido.")

        return {
            "running": self.last_running,
            "speed": self.last_speed,
            "port": self.current_port,
            "port_response": response,
        }


motor_serial = MotorSerialController()
