import time
import threading
from collections import Counter

import cv2
import torch

from inference.predictor import build_model, get_infer_kwargs
from inference.grading import grade_from_counts
from dashboard.camera_hub import get_camera_worker


class LiveEvalSession:
    """
    Versión estable:
    - Un hilo para stream fluido.
    - Otro hilo para inferencia YOLO.
    - Dibuja solo línea + cajas.
    - Cuenta por zona de línea.
    - No usa ByteTrack por ahora.
    """

    def __init__(
        self,
        cam_id: str,
        source_config: dict,
        duration_s: int = 15,
        no_grain_timeout_s: float = 90.0,
        min_session_s: float = 3.0,
        conf_display: float = 0.06,
        conf_count: float = 0.08,
        tracker_cfg: str = "bytetrack.yaml",
        imgsz: int = 480,
        count_axis: str = "y",
        count_direction: str = "down",
        primary_line_ratio: float = 0.55,
        secondary_line_ratio: float = 0.62,
        max_box_area: float = 60000,
        secondary_cam_id: str | None = None,
        secondary_source_config: dict | None = None,
        sync_min_delay_s: float = 0.05,
        sync_max_delay_s: float = 0.80,
        pending_timeout_s: float = 1.10,
        strong_primary_conf: float = 0.75,
        secondary_confirm_conf: float = 0.40,
        fallback_primary_conf: float = 0.60,
        target_fps: float = 6.0,
        jpeg_quality: int = 65,
    ):
        self.cam_id = cam_id
        self.source_config = source_config

        self.duration_s = duration_s
        self.no_grain_timeout_s = no_grain_timeout_s
        self.min_session_s = min_session_s

        self.conf_display = conf_display
        self.conf_count = conf_count
        self.imgsz = imgsz
        self.tracker_cfg = tracker_cfg

        self.count_axis = count_axis
        self.count_direction = count_direction
        self.primary_line_ratio = primary_line_ratio
        self.secondary_line_ratio = secondary_line_ratio
        self.max_box_area = max_box_area

        self.target_fps = target_fps
        self.jpeg_quality = jpeg_quality

        self.line_zone_tolerance_px = 95
        self.line_zone_cooldown_s = 0.80
        self.line_zone_last_count_at = {}

        self._lock = threading.Lock()
        self._stop_flag = False

        self._stream_thread: threading.Thread | None = None
        self._infer_thread: threading.Thread | None = None

        self.state = "idle"
        self.started_at = None
        self.last_grain_seen_at = None
        self.error = None
        self.final_payload = None

        self.latest_jpeg: bytes | None = None
        self.latest_boxes = []
        self.latest_boxes_at = 0.0

        self.primary_model = None

        self.confirmed_counts: Counter = Counter()
        self.counted_event_ids: set[str] = set()

        self.total_unique = 0
        self.confirmed_by_secondary = 0
        self.counted_by_primary_only = 0
        self.discarded_pending = 0
        self.pending_events = {}

        self.secondary_active = False

    def is_running(self) -> bool:
        with self._lock:
            return self.state == "running"

    def start(self):
        with self._lock:
            if self.state == "running":
                return

            self._stop_flag = False
            self.error = None
            self.final_payload = None
            self.latest_jpeg = None
            self.latest_boxes = []
            self.latest_boxes_at = 0.0

            self.confirmed_counts = Counter()
            self.counted_event_ids = set()
            self.total_unique = 0
            self.confirmed_by_secondary = 0
            self.counted_by_primary_only = 0
            self.discarded_pending = 0
            self.pending_events = {}
            self.line_zone_last_count_at = {}

            self.state = "running"
            self.started_at = time.time()
            self.last_grain_seen_at = self.started_at

        self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._infer_thread = threading.Thread(target=self._infer_loop, daemon=True)

        self._stream_thread.start()
        self._infer_thread.start()

    def stop(self):
        with self._lock:
            self._stop_flag = True

    def status(self) -> dict:
        with self._lock:
            now = time.time()
            idle_s = None

            if self.state == "running" and self.last_grain_seen_at:
                idle_s = max(0, round(now - self.last_grain_seen_at, 1))

            return {
                "state": self.state,
                "remaining_s": None,
                "idle_s": idle_s,
                "no_grain_timeout_s": self.no_grain_timeout_s,
                "error": self.error,
                "final": self.final_payload,
                "total_unique": self.total_unique,
                "used_secondary": False,
                "secondary_active": False,
                "pending_count": 0,
                "confirmed_by_secondary": self.confirmed_by_secondary,
                "counted_by_primary_only": self.counted_by_primary_only,
                "discarded_pending": self.discarded_pending,
            }

    def get_latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self.latest_jpeg

    def _cls_name(self, names, cls_id: int) -> str:
        if isinstance(names, dict):
            return names.get(cls_id, str(cls_id))

        if isinstance(names, list) and 0 <= cls_id < len(names):
            return names[cls_id]

        return str(cls_id)

    def _line_pos(self, frame_shape, ratio: float) -> int:
        h, w = frame_shape[:2]

        if self.count_axis == "x":
            return int(w * ratio)

        return int(h * ratio)

    def _axis_center(self, x1, y1, x2, y2) -> float:
        if self.count_axis == "x":
            return (x1 + x2) / 2.0

        return (y1 + y2) / 2.0

    def _draw_line(self, frame):
        line_pos = self._line_pos(frame.shape, self.primary_line_ratio)
        h, w = frame.shape[:2]

        if self.count_axis == "x":
            cv2.line(frame, (line_pos, 0), (line_pos, h), (255, 255, 0), 2)
        else:
            cv2.line(frame, (0, line_pos), (w, line_pos), (255, 255, 0), 2)

    def _draw_boxes(self, frame):
        now = time.time()

        with self._lock:
            boxes = list(self.latest_boxes)
            boxes_at = self.latest_boxes_at

        if now - boxes_at > 0.45:
            return

        h, w = frame.shape[:2]

        for box in boxes:
            x1, y1, x2, y2 = box["box"]

            x1 = max(0, min(int(x1), w - 1))
            y1 = max(0, min(int(y1), h - 1))
            x2 = max(0, min(int(x2), w - 1))
            y2 = max(0, min(int(y2), h - 1))

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

    def _encode_and_store(self, frame):
        ok, jpg = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(self.jpeg_quality)]
        )

        if ok:
            with self._lock:
                self.latest_jpeg = jpg.tobytes()

    def _mark_grain_seen(self):
        with self._lock:
            self.last_grain_seen_at = time.time()

    def _should_finish_by_no_grain(self) -> bool:
        with self._lock:
            if not self.started_at or not self.last_grain_seen_at:
                return False

            if self._stop_flag:
                return True

            now = time.time()
            elapsed = now - self.started_at
            idle = now - self.last_grain_seen_at

            return elapsed >= self.min_session_s and idle >= self.no_grain_timeout_s

    def _count_detection_if_needed(self, det, frame_shape):
        cls_name = det["class"]
        conf = det["conf"]
        x1, y1, x2, y2 = det["box"]

        if conf < self.conf_count:
            return

        line_pos = self._line_pos(frame_shape, self.primary_line_ratio)
        pos = self._axis_center(x1, y1, x2, y2)

        if abs(pos - line_pos) > self.line_zone_tolerance_px:
            return

        cx = int((x1 + x2) / 2)
        bucket_x = int(cx / 70)

        now_ts = time.time()
        bucket_key = f"{cls_name}:{bucket_x}"

        last_count = self.line_zone_last_count_at.get(bucket_key, 0)

        if now_ts - last_count < self.line_zone_cooldown_s:
            return

        self.line_zone_last_count_at[bucket_key] = now_ts

        event_id = f"{bucket_key}:{int(now_ts * 1000)}"

        if event_id in self.counted_event_ids:
            return

        self.counted_event_ids.add(event_id)
        self.total_unique += 1
        self.counted_by_primary_only += 1

        if cls_name != "coffee_bean":
            self.confirmed_counts[cls_name] += 1
            print(
                f"[COUNT] class={cls_name} conf={conf:.2f} "
                f"total_unique={self.total_unique} "
                f"raw_defects={dict(self.confirmed_counts)}",
                flush=True
            )

    def _stream_loop(self):
        try:
            worker = get_camera_worker(self.cam_id, self.source_config)

            t0 = time.time()
            while worker.get_frame() is None:
                time.sleep(0.05)

                if time.time() - t0 > 10:
                    raise RuntimeError("No se pudo obtener frame de la cámara.")

            while True:
                with self._lock:
                    if self._stop_flag:
                        break

                if self._should_finish_by_no_grain():
                    break

                frame = worker.get_frame()

                if frame is None:
                    time.sleep(0.01)
                    continue

                drawn = frame.copy()
                self._draw_line(drawn)
                self._draw_boxes(drawn)
                self._encode_and_store(drawn)

                time.sleep(0.025)

            final_payload = self._finalize_counts()

            with self._lock:
                self.final_payload = final_payload
                self.state = "finished"

        except Exception as e:
            with self._lock:
                self.error = str(e)
                self.final_payload = {
                    "counts": dict(self.confirmed_counts),
                    "total_unique": self.total_unique,
                    "error": str(e),
                }
                self.state = "error"

    def _infer_loop(self):
        try:
            infer_kwargs = get_infer_kwargs()

            print("[LIVE] infer_kwargs:", infer_kwargs, flush=True)
            print("[LIVE] CUDA disponible:", torch.cuda.is_available(), flush=True)

            if torch.cuda.is_available():
                print("[LIVE] GPU:", torch.cuda.get_device_name(0), flush=True)

            worker = get_camera_worker(self.cam_id, self.source_config)

            t0 = time.time()
            while worker.get_frame() is None:
                time.sleep(0.05)

                if time.time() - t0 > 10:
                    raise RuntimeError("No se pudo obtener frame para inferencia.")

            self.primary_model = build_model()
            names = self.primary_model.names

            try:
                print(
                    "[LIVE] model device:",
                    next(self.primary_model.model.parameters()).device,
                    flush=True
                )
            except Exception:
                pass

            warm = worker.get_frame()

            if warm is not None:
                with torch.inference_mode():
                    _ = self.primary_model.predict(
                        source=warm,
                        conf=self.conf_display,
                        imgsz=self.imgsz,
                        verbose=False,
                        **infer_kwargs,
                    )

            print("[LIVE] warmup OK", flush=True)

            min_interval = 1.0 / max(1.0, self.target_fps)
            last_run = 0.0
            last_debug = 0.0

            while True:
                with self._lock:
                    if self._stop_flag or self.state != "running":
                        break

                now = time.time()

                if now - last_run < min_interval:
                    time.sleep(0.01)
                    continue

                last_run = now
                frame = worker.get_frame()

                if frame is None:
                    continue

                detections = []
                class_counter = Counter()

                with torch.inference_mode():
                    results = self.primary_model.predict(
                        source=frame,
                        conf=self.conf_display,
                        imgsz=self.imgsz,
                        verbose=False,
                        **infer_kwargs,
                    )

                if results and results[0].boxes is not None and len(results[0].boxes) > 0:
                    boxes = results[0].boxes
                    xyxy = boxes.xyxy.cpu().numpy()
                    confs = boxes.conf.cpu().numpy()
                    clss = boxes.cls.cpu().numpy()

                    h, w = frame.shape[:2]

                    for i in range(len(xyxy)):
                        x1, y1, x2, y2 = xyxy[i]
                        conf = float(confs[i])
                        cls_id = int(clss[i])
                        cls_name = self._cls_name(names, cls_id)
                        class_counter[cls_name] += 1

                        bw = max(1, x2 - x1)
                        bh = max(1, y2 - y1)
                        area = bw * bh

                        if area > self.max_box_area:
                            continue

                        det = {
                            "class": cls_name,
                            "conf": conf,
                            "box": (float(x1), float(y1), float(x2), float(y2)),
                        }

                        detections.append(det)
                        self._count_detection_if_needed(det, frame.shape)

                    if detections:
                        self._mark_grain_seen()

                with self._lock:
                    self.latest_boxes = detections
                    self.latest_boxes_at = time.time()

                if time.time() - last_debug >= 2.0:
                    top_conf = max([d["conf"] for d in detections], default=0)
                    print(
                        f"[LIVE] detections={len(detections)} "
                        f"classes={dict(class_counter)} "
                        f"top_conf={top_conf:.2f} "
                        f"total_unique={self.total_unique} "
                        f"raw_defects={dict(self.confirmed_counts)}",
                        flush=True
                    )
                    last_debug = time.time()

        except Exception as e:
            with self._lock:
                self.error = str(e)
                self.state = "error"

            print("[LIVE] infer error:", e, flush=True)

    def _finalize_counts(self) -> dict:
        raw_counts = dict(self.confirmed_counts)
        grading = grade_from_counts(raw_counts)

        return {
            "raw_counts": raw_counts,
            "total_unique": self.total_unique,
            "used_secondary": False,
            "secondary_active": False,
            "confirmed_by_secondary": self.confirmed_by_secondary,
            "counted_by_primary_only": self.counted_by_primary_only,
            "discarded_pending": self.discarded_pending,
            "pending_left": 0,
            **grading,
        }
