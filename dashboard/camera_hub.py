import time
import threading
import cv2


CAMERA_SEARCH_TIMEOUT_SECONDS = 40

def source_is_enabled(source: dict) -> bool:
    value = source.get("enabled", True)

    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off", "")

    return bool(value)


def normalize_camera_sources(raw_sources):
    if not raw_sources:
        return []

    if isinstance(raw_sources, list):
        return [s for s in raw_sources if isinstance(s, dict) and source_is_enabled(s)]

    if isinstance(raw_sources, tuple):
        return [s for s in raw_sources if isinstance(s, dict) and source_is_enabled(s)]

    if isinstance(raw_sources, dict):
        if any(k in raw_sources for k in ("type", "index", "url")):
            return [raw_sources] if source_is_enabled(raw_sources) else []

        ordered_keys = ["primary", "main", "fallback", "backup", "secondary"]
        ordered = []

        for key in ordered_keys:
            value = raw_sources.get(key)
            if isinstance(value, dict) and source_is_enabled(value):
                ordered.append(value)

        for key, value in raw_sources.items():
            if key in ordered_keys:
                continue
            if isinstance(value, dict) and source_is_enabled(value):
                ordered.append(value)

        return ordered

    return []


class CameraWorker:
    def __init__(self, sources, search_timeout_seconds=CAMERA_SEARCH_TIMEOUT_SECONDS):
        self.sources = normalize_camera_sources(sources)
        self.current_source_index = 0
        self.current_source = None

        self.cap = None
        self.running = False
        self.thread = None

        self.lock = threading.Lock()
        self.latest_frame = None
        self.last_ok_at = 0.0
        self._last_frame_signature = None
        self._same_frame_count = 0

        self.search_timeout_seconds = search_timeout_seconds
        self.search_started_at = None
        self.search_expired = False

    def _open_capture(self, source: dict):
        source_type = source.get("type")

        if source_type == "device":
            index = int(source.get("index", 0))

            cap = cv2.VideoCapture(index, cv2.CAP_V4L2)

            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(source.get("width", 640)))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(source.get("height", 480)))
            cap.set(cv2.CAP_PROP_FPS, int(source.get("fps", 15)))

            return cap

        if source_type == "rtsp":
            return cv2.VideoCapture(str(source.get("url")), cv2.CAP_FFMPEG)

        if source_type == "http":
            return cv2.VideoCapture(str(source.get("url")))

        raise ValueError(f"Tipo de fuente no soportado: {source_type}")

    def _try_open_any_source(self):
        total = len(self.sources)

        if total <= 0:
            print("[WARN] No hay fuentes configuradas para esta cámara.")
            self.current_source = None
            self.cap = None
            return False

        for i in range(total):
            idx = (self.current_source_index + i) % total
            source = self.sources[idx]

            try:
                cap = self._open_capture(source)
                time.sleep(0.2)

                if cap is not None and cap.isOpened():
                    self.current_source_index = idx
                    self.current_source = source

                    try:
                        if self.cap is not None:
                            self.cap.release()
                    except Exception:
                        pass

                    self.cap = cap

                    self.search_started_at = None
                    self.search_expired = False

                    print(f"[INFO] Fuente activa: {source.get('name', 'unknown')}")
                    return True

                if cap is not None:
                    cap.release()

            except Exception as e:
                print(f"[WARN] No se pudo abrir fuente {source.get('name', 'unknown')}: {e}")

        self.current_source = None
        self.cap = None
        return False

    def start(self):
        if self.running:
            return

        self.running = True
        self.search_started_at = None
        self.search_expired = False

        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _search_time_expired(self):
        if self.search_timeout_seconds is None:
            return False

        if self.search_started_at is None:
            self.search_started_at = time.time()
            return False

        return (time.time() - self.search_started_at) >= self.search_timeout_seconds

    def _loop(self):
        fail_count = 0

        while self.running:
            if self.cap is None or not self.cap.isOpened():
                if self._search_time_expired():
                    print("[WARN] Tiempo máximo de búsqueda agotado. Cámara marcada como offline.")
                    self.search_expired = True
                    self.running = False
                    break

                ok = self._try_open_any_source()

                if not ok:
                    time.sleep(1.0)
                    continue

            try:
                ok, frame = self.cap.read()
            except cv2.error:
                ok, frame = False, None
            except Exception:
                ok, frame = False, None

            if not ok or frame is None:
                fail_count += 1
                time.sleep(0.05)

                if fail_count >= 20:
                    print("[WARN] Fallos consecutivos. Intentando otra fuente...")

                    try:
                        if self.cap is not None:
                            self.cap.release()
                    except Exception:
                        pass

                    self.cap = None
                    fail_count = 0

                continue

            # Detectar si la cámara está entregando el mismo frame congelado.
            try:
                small = cv2.resize(frame, (64, 36))
                signature = hash(small.tobytes())

                if self._last_frame_signature == signature:
                    self._same_frame_count += 1
                else:
                    self._same_frame_count = 0
                    self._last_frame_signature = signature

                if self._same_frame_count >= 90:
                    print("[WARN] Cámara congelada: mismo frame repetido. Reiniciando captura...")

                    try:
                        if self.cap is not None:
                            self.cap.release()
                    except Exception:
                        pass

                    self.cap = None
                    self._same_frame_count = 0
                    self._last_frame_signature = None
                    fail_count = 0
                    time.sleep(0.4)
                    continue

            except Exception:
                pass

            fail_count = 0

            with self.lock:
                self.latest_frame = frame.copy()
                self.last_ok_at = time.time()

        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass

        self.cap = None

    def get_frame(self):
        with self.lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

    def get_active_source_name(self):
        if not self.current_source:
            return None
        return self.current_source.get("name")

    def switch_to_source(self, source_name: str):
        for idx, source in enumerate(self.sources):
            if source.get("name") == source_name:
                self.current_source_index = idx
                self.search_started_at = None
                self.search_expired = False

                try:
                    if self.cap is not None:
                        self.cap.release()
                except Exception:
                    pass

                self.cap = None

                if not self.running:
                    self.start()

                print(f"[INFO] Cambio manual a fuente: {source_name}")
                return True

        return False

    def stop(self):
        self.running = False

        if self.thread is not None:
            self.thread.join(timeout=1.5)

    def is_live(self):
        with self.lock:
            return self.latest_frame is not None and (time.time() - self.last_ok_at) <= 3

    def is_offline(self):
        return self.search_expired or not self.running


CAMERA_WORKERS = {}
CAMERA_WORKERS_LOCK = threading.Lock()


def get_camera_worker(cam_id: str, sources) -> CameraWorker:
    normalized_sources = normalize_camera_sources(sources)

    with CAMERA_WORKERS_LOCK:
        worker = CAMERA_WORKERS.get(cam_id)

        if worker is None:
            worker = CameraWorker(sources=normalized_sources)
            CAMERA_WORKERS[cam_id] = worker
            worker.start()
            return worker

        # Si ya está corriendo, NO lo reinicies.
        # Esto evita reabrir /dev/video mientras live_sessions lo está usando.
        if worker.running and not worker.search_expired:
            return worker

        # Si quedó offline o muerto, crear uno nuevo.
        try:
            worker.stop()
        except Exception:
            pass

        worker = CameraWorker(sources=normalized_sources)
        CAMERA_WORKERS[cam_id] = worker
        worker.start()
        return worker
