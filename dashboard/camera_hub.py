import time
import threading
import cv2


def normalize_camera_sources(raw_sources):
    """
    Normaliza cualquier formato de configuración a lista de dicts.
    Soporta:
    - dict simple: {"type": "...", "index": 0}
    - lista: [{...}, {...}]
    - dict jerárquico: {"primary": {...}, "fallback": {...}}
    """
    if not raw_sources:
        return []

    if isinstance(raw_sources, list):
        return [s for s in raw_sources if isinstance(s, dict)]

    if isinstance(raw_sources, tuple):
        return [s for s in raw_sources if isinstance(s, dict)]

    if isinstance(raw_sources, dict):
        # Caso: una sola cámara
        if any(k in raw_sources for k in ("type", "index", "url")):
            return [raw_sources]

        # Caso: principal / fallback / backup
        ordered_keys = ["primary", "main", "fallback", "backup", "secondary"]
        ordered = []

        for key in ordered_keys:
            value = raw_sources.get(key)
            if isinstance(value, dict):
                ordered.append(value)

        for key, value in raw_sources.items():
            if key in ordered_keys:
                continue
            if isinstance(value, dict):
                ordered.append(value)

        return ordered

    return []


class CameraWorker:
    def __init__(self, sources):
        """
        sources: lista de fuentes en orden de prioridad.
        También acepta dict simple o dict con primary/fallback.
        """
        self.sources = normalize_camera_sources(sources)
        self.current_source_index = 0
        self.current_source = None

        self.cap = None
        self.running = False
        self.thread = None

        self.lock = threading.Lock()
        self.latest_frame = None
        self.last_ok_at = 0.0

    def _open_capture(self, source: dict):
        source_type = source.get("type")

        if source_type == "device":
            index = int(source.get("index", 0))

            cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 30)

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
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        fail_count = 0

        while self.running:
            if self.cap is None or not self.cap.isOpened():
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

                # tras varios fallos seguidos, intenta cambiar de fuente
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
                try:
                    if self.cap is not None:
                        self.cap.release()
                except Exception:
                    pass
                self.cap = None
                print(f"[INFO] Cambio manual a fuente: {source_name}")
                return True
        return False

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=1.5)


CAMERA_WORKERS = {}


def get_camera_worker(cam_id: str, sources) -> CameraWorker:
    normalized_sources = normalize_camera_sources(sources)
    worker = CAMERA_WORKERS.get(cam_id)

    if worker is None:
        worker = CameraWorker(sources=normalized_sources)
        CAMERA_WORKERS[cam_id] = worker
        worker.start()
        return worker

    if worker.sources != normalized_sources:
        try:
            worker.stop()
        except Exception:
            pass

        worker = CameraWorker(sources=normalized_sources)
        CAMERA_WORKERS[cam_id] = worker
        worker.start()

    elif not worker.running:
        worker.start()

    return worker
