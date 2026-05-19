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
        self._serials = {}
        self._lock = threading.Lock()

        self.current_ports = []
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

    def _close_all(self):
        for ser in self._serials.values():
            try:
                if ser and ser.is_open:
                    ser.close()
            except Exception:
                pass

        self._serials = {}
        self.current_ports = []

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
            "ttyacm",
            "ttyusb",
        ]

        def score(port):
            text = " ".join([
                str(port.device or ""),
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

            # Muchos ESP32 se reinician cuando se abre el puerto serial.
            time.sleep(2)

            ser.reset_input_buffer()
            ser.reset_output_buffer()

            ser.write(b"I\n")
            ser.flush()

            response = self._read_lines(ser, seconds=1.2)

            if device_id in response:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
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

    def _connect_auto_all(self):
        if list_ports is None:
            raise RuntimeError("No se pudo usar serial.tools.list_ports. Revisa pyserial.")

        ports = self._ordered_ports()

        if not ports:
            raise RuntimeError("No se encontraron puertos seriales disponibles.")

        detected_serials = {}

        for port in ports:
            ser = self._try_open_and_identify(port.device)

            if ser:
                detected_serials[port.device] = ser

        if not detected_serials:
            available = ", ".join([
                f"{p.device} ({p.description})"
                for p in ports
            ])

            raise RuntimeError(
                "No se encontró ningún ESP32 de banda. "
                "Verifica que estén conectados, que el Monitor Serial esté cerrado "
                "y que tengan cargado el código con DEVICE_ID=COFFEEVISION_MOTOR_ESP32. "
                f"Puertos detectados: {available}"
            )

        self._serials = detected_serials
        self.current_ports = list(detected_serials.keys())

    def _connect_manual_ports(self, configured_port):
        baudrate = int(getattr(settings, "MOTOR_SERIAL_BAUDRATE", 115200))
        timeout = float(getattr(settings, "MOTOR_SERIAL_TIMEOUT", 1))

        ports = [
            port.strip()
            for port in configured_port.split(",")
            if port.strip()
        ]

        if not ports:
            raise RuntimeError("MOTOR_SERIAL_PORT está vacío.")

        detected_serials = {}

        for port in ports:
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    timeout=timeout,
                    write_timeout=timeout,
                )

                time.sleep(2)

                ser.reset_input_buffer()
                ser.reset_output_buffer()

                detected_serials[port] = ser

            except Exception as e:
                raise RuntimeError(
                    f"No se pudo abrir el puerto {port}. Detalle: {e}"
                )

        self._serials = detected_serials
        self.current_ports = list(detected_serials.keys())

    def _ensure_connected(self):
        if serial is None:
            raise RuntimeError("pyserial no está instalado. Ejecuta: pip install pyserial")

        opened = {
            port: ser
            for port, ser in self._serials.items()
            if ser and ser.is_open
        }

        if opened:
            self._serials = opened
            self.current_ports = list(opened.keys())
            return

        configured_port = str(getattr(settings, "MOTOR_SERIAL_PORT", "AUTO")).strip()

        if configured_port.upper() == "AUTO":
            self._connect_auto_all()
        else:
            self._connect_manual_ports(configured_port)

    def _write_line_to_all(self, line: str, read_seconds=0.5):
        self._ensure_connected()

        responses = {}
        errors = {}

        for port, ser in list(self._serials.items()):
            try:
                ser.write((line.strip() + "\n").encode("utf-8"))
                ser.flush()

                time.sleep(0.08)

                response = self._read_lines(ser, seconds=read_seconds)
                responses[port] = response

            except Exception as e:
                errors[port] = str(e)

        self.last_response = "\n".join([
            f"{port}: {response}"
            for port, response in responses.items()
        ])

        if errors:
            self._close_all()

            error_text = " | ".join([
                f"{port}: {error}"
                for port, error in errors.items()
            ])

            raise RuntimeError(
                f"Falló el envío de comando en una o más bandas: {error_text}"
            )

        return responses

    def command(self, command: str, speed=None):
        with self._lock:
            command = (command or "").lower().strip()

            if speed is not None:
                speed = max(0, min(100, int(speed)))

            if command == "start":
                if speed is not None:
                    self._write_line_to_all(f"V{speed}")
                    self.last_speed = speed

                responses = self._write_line_to_all("E")
                self.last_running = True

            elif command == "stop":
                responses = self._write_line_to_all("S")
                self.last_running = False

            elif command == "speed":
                if speed is None:
                    raise ValueError("Falta la velocidad.")

                responses = self._write_line_to_all(f"V{speed}")
                self.last_speed = speed

            elif command == "faster":
                responses = self._write_line_to_all("A")

            elif command == "slower":
                responses = self._write_line_to_all("B")

            elif command == "identify":
                responses = self._write_line_to_all("I")

            elif command == "rescan":
                self._close_all()
                self._ensure_connected()
                responses = self._write_line_to_all("I")

            else:
                raise ValueError("Comando no válido.")

            return {
                "running": self.last_running,
                "speed": self.last_speed,
                "ports": self.current_ports,
                "devices_count": len(self.current_ports),
                "port_response": responses,
            }


motor_serial = MotorSerialController()