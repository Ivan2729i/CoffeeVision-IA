import time
import threading
from collections import Counter
import cv2

from inference.predictor import build_model, get_infer_kwargs
from inference.grading import grade_from_counts
from dashboard.camera_hub import get_camera_worker


class LiveEvalSession:
    """
    Sesión en vivo robusta para banda continua.

    Soporta:
    - 1 cámara principal obligatoria
    - 1 cámara secundaria opcional
    - tracking independiente por cámara
    - conteo por track_id
    - línea virtual
    - sincronización básica entre cámaras por ventana de tiempo
    - mejora de calidad con cam2 en detecciones dudosas
    """

    def __init__(
        self,
        cam_id: str,
        source_config: dict,
        duration_s: int = 15,
        conf_display: float = 0.22,
        conf_count: float = 0.30,
        tracker_cfg: str = "bytetrack.yaml",
        imgsz: int = 640,
        count_axis: str = "y",              # "y" o "x"
        count_direction: str = "down",      # "down", "up", "right", "left"
        primary_line_ratio: float = 0.62,
        secondary_line_ratio: float = 0.62,
        max_box_area: float = 8000,
        secondary_cam_id: str | None = None,
        secondary_source_config: dict | None = None,
        sync_min_delay_s: float = 0.05,
        sync_max_delay_s: float = 0.80,
        pending_timeout_s: float = 1.10,
        strong_primary_conf: float = 0.75,
        secondary_confirm_conf: float = 0.40,
        fallback_primary_conf: float = 0.60,
    ):
        self.cam_id = cam_id
        self.source_config = source_config

        self.secondary_cam_id = secondary_cam_id
        self.secondary_source_config = secondary_source_config
        self.use_secondary = bool(secondary_cam_id and secondary_source_config)

        self.duration_s = duration_s
        self.conf_display = conf_display
        self.conf_count = conf_count
        self.tracker_cfg = tracker_cfg
        self.imgsz = imgsz

        self.count_axis = count_axis
        self.count_direction = count_direction
        self.primary_line_ratio = primary_line_ratio
        self.secondary_line_ratio = secondary_line_ratio
        self.max_box_area = max_box_area

        # sincronización / confirmación
        self.sync_min_delay_s = sync_min_delay_s
        self.sync_max_delay_s = sync_max_delay_s
        self.pending_timeout_s = pending_timeout_s
        self.strong_primary_conf = strong_primary_conf
        self.secondary_confirm_conf = secondary_confirm_conf
        self.fallback_primary_conf = fallback_primary_conf

        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_flag = False

        self.state = "idle"
        self.started_at = None
        self.ends_at = None
        self.error = None

        self.latest_jpeg: bytes | None = None
        self.final_payload: dict | None = None

        # modelos independientes por cámara
        self.primary_model = None
        self.secondary_model = None

        # tracking / conteo
        self.counted_event_ids: set[str] = set()
        self.confirmed_counts: Counter = Counter()
        self.primary_track_last_pos: dict[int, float] = {}
        self.secondary_track_last_pos: dict[int, float] = {}

        self.total_unique = 0
        self.confirmed_by_secondary = 0
        self.counted_by_primary_only = 0
        self.discarded_pending = 0

        # eventos pendientes de confirmación por cam2
        self.pending_events: dict[str, dict] = {}
        self._event_seq = 0

        # debug / estado
        self.secondary_active = False
        self.secondary_last_seen_at = None

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

            self.counted_event_ids = set()
            self.confirmed_counts = Counter()
            self.primary_track_last_pos = {}
            self.secondary_track_last_pos = {}
            self.total_unique = 0
            self.confirmed_by_secondary = 0
            self.counted_by_primary_only = 0
            self.discarded_pending = 0
            self.pending_events = {}
            self._event_seq = 0
            self.secondary_active = False
            self.secondary_last_seen_at = None

            self.state = "running"
            self.started_at = time.time()
            self.ends_at = self.started_at + self.duration_s

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        with self._lock:
            self._stop_flag = True

    def status(self) -> dict:
        with self._lock:
            now = time.time()
            remaining = None
            if self.state == "running" and self.ends_at:
                remaining = max(0, int(self.ends_at - now))

            return {
                "state": self.state,
                "remaining_s": remaining,
                "error": self.error,
                "final": self.final_payload,
                "total_unique": self.total_unique,
                "used_secondary": self.use_secondary,
                "secondary_active": self.secondary_active,
                "pending_count": len(self.pending_events),
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
        if isinstance(names, list):
            if 0 <= cls_id < len(names):
                return names[cls_id]
        return str(cls_id)

    def _next_event_id(self) -> str:
        self._event_seq += 1
        return f"ev-{self._event_seq}"

    def _axis_center(self, x1, y1, x2, y2) -> float:
        if self.count_axis == "x":
            return (x1 + x2) / 2.0
        return (y1 + y2) / 2.0

    def _line_pos(self, frame_shape, ratio: float) -> int:
        h, w = frame_shape[:2]
        if self.count_axis == "x":
            return int(w * ratio)
        return int(h * ratio)

    def _crossed_line(self, prev_pos: float, curr_pos: float, line_pos: float) -> bool:
        if self.count_direction == "down":
            return prev_pos < line_pos <= curr_pos
        if self.count_direction == "up":
            return prev_pos > line_pos >= curr_pos
        if self.count_direction == "right":
            return prev_pos < line_pos <= curr_pos
        if self.count_direction == "left":
            return prev_pos > line_pos >= curr_pos
        return prev_pos < line_pos <= curr_pos

    def _draw_line(self, frame, line_pos: int, color=(255, 255, 0)):
        h, w = frame.shape[:2]
        if self.count_axis == "x":
            cv2.line(frame, (line_pos, 0), (line_pos, h), color, 2)
        else:
            cv2.line(frame, (0, line_pos), (w, line_pos), color, 2)

    def _draw_header(self, frame, title: str, line_pos: int):
        self._draw_line(frame, line_pos)
        cv2.putText(
            frame,
            title,
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return frame

    def _draw_global_panel(self, frame):
        y = 28
        lines = [
            f"Unique: {self.total_unique}",
            f"Cam2 active: {'YES' if self.secondary_active else 'NO'}",
            f"Pending: {len(self.pending_events)}",
            f"Confirmed by cam2: {self.confirmed_by_secondary}",
            f"Primary only: {self.counted_by_primary_only}",
        ]
        for txt in lines:
            cv2.putText(
                frame,
                txt,
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            y += 26
        return frame

    def _count_event(self, event: dict, counted_via: str):
        event_id = event["event_id"]
        if event_id in self.counted_event_ids:
            return

        cls_name = event["final_class"]
        self.counted_event_ids.add(event_id)
        self.confirmed_counts[cls_name] += 1
        self.total_unique += 1

        if counted_via == "secondary":
            self.confirmed_by_secondary += 1
        else:
            self.counted_by_primary_only += 1

    def _create_pending_primary_event(self, cls_name: str, conf: float, crossed_at: float):
        event_id = self._next_event_id()
        self.pending_events[event_id] = {
            "event_id": event_id,
            "primary_class": cls_name,
            "final_class": cls_name,
            "primary_conf": float(conf),
            "secondary_conf": None,
            "crossed_at": crossed_at,
            "status": "pending_secondary",
        }

    def _resolve_pending_timeouts(self, now_ts: float):
        to_delete = []

        for event_id, ev in self.pending_events.items():
            age = now_ts - ev["crossed_at"]

            if age < self.pending_timeout_s:
                continue

            # si la primaria tuvo buena confianza, cuenta aunque cam2 no haya confirmado
            if ev["primary_conf"] >= self.fallback_primary_conf:
                ev["status"] = "counted_primary_timeout"
                self._count_event(ev, counted_via="primary")
            else:
                ev["status"] = "discarded_unconfirmed"
                self.discarded_pending += 1

            to_delete.append(event_id)

        for event_id in to_delete:
            self.pending_events.pop(event_id, None)

    def _try_match_secondary(self, cls_name: str, conf: float, crossed_at: float) -> bool:
        if conf < self.secondary_confirm_conf:
            return False

        best_event = None
        best_gap = None

        for ev in self.pending_events.values():
            if ev["status"] != "pending_secondary":
                continue

            dt = crossed_at - ev["crossed_at"]
            if dt < self.sync_min_delay_s or dt > self.sync_max_delay_s:
                continue

            # regla robusta:
            # preferimos misma clase; si no coincide, no confirma
            if ev["primary_class"] != cls_name:
                continue

            gap = abs(dt)
            if best_event is None or gap < best_gap:
                best_event = ev
                best_gap = gap

        if best_event is None:
            return False

        best_event["secondary_conf"] = float(conf)
        best_event["final_class"] = cls_name
        best_event["status"] = "counted_secondary_confirmed"
        self._count_event(best_event, counted_via="secondary")
        self.pending_events.pop(best_event["event_id"], None)
        return True

    def _process_camera_tracks(
        self,
        frame,
        results,
        names,
        line_ratio: float,
        last_positions: dict[int, float],
        title: str,
        role: str,
    ):
        drawn = frame.copy()
        line_pos = self._line_pos(drawn.shape, line_ratio)
        self._draw_header(drawn, title, line_pos)

        crossing_events = []

        if not results:
            return drawn, crossing_events

        r0 = results[0]
        boxes = r0.boxes
        if boxes is None or boxes.xyxy is None or len(boxes) <= 0:
            return drawn, crossing_events

        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy()

        track_ids = None
        if hasattr(boxes, "id") and boxes.id is not None:
            track_ids = boxes.id.int().cpu().tolist()

        h, w = drawn.shape[:2]

        for i in range(len(xyxy)):
            x1, y1, x2, y2 = xyxy[i]
            conf = float(confs[i])
            cls_id = int(clss[i])

            if conf < self.conf_display:
                continue

            bw = max(1, x2 - x1)
            bh = max(1, y2 - y1)
            area = bw * bh
            if area > self.max_box_area:
                continue

            track_id = None
            if track_ids is not None and i < len(track_ids):
                track_id = int(track_ids[i])

            cls_name = self._cls_name(names, cls_id)

            x1i = max(0, min(int(x1), w - 1))
            y1i = max(0, min(int(y1), h - 1))
            x2i = max(0, min(int(x2), w - 1))
            y2i = max(0, min(int(y2), h - 1))

            cx = int((x1i + x2i) / 2)
            cy = int((y1i + y2i) / 2)

            pos = self._axis_center(x1i, y1i, x2i, y2i)

            label = f"{cls_name} {conf:.2f}"
            if track_id is not None:
                label = f"ID {track_id} | {cls_name} {conf:.2f}"

            color = (0, 255, 0) if role == "primary" else (0, 180, 255)

            cv2.rectangle(drawn, (x1i, y1i), (x2i, y2i), color, 2)
            cv2.circle(drawn, (cx, cy), 3, (0, 0, 255), -1)
            cv2.putText(
                drawn,
                label,
                (x1i, max(15, y1i - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
                cv2.LINE_AA,
            )

            if track_id is None:
                continue

            prev_pos = last_positions.get(track_id)
            last_positions[track_id] = pos

            if (
                prev_pos is not None
                and conf >= self.conf_count
                and self._crossed_line(prev_pos, pos, line_pos)
            ):
                crossing_events.append({
                    "track_id": track_id,
                    "class": cls_name,
                    "conf": conf,
                    "crossed_at": time.time(),
                    "box": (x1i, y1i, x2i, y2i),
                })

                cv2.putText(
                    drawn,
                    "CROSS",
                    (x1i, min(h - 8, y2i + 18)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

        return drawn, crossing_events

    def _combine_frames(self, primary_frame, secondary_frame=None):
        if secondary_frame is None:
            return self._draw_global_panel(primary_frame)

        h1, w1 = primary_frame.shape[:2]
        h2, w2 = secondary_frame.shape[:2]

        if h2 != h1:
            new_w2 = int(w2 * (h1 / max(1, h2)))
            secondary_frame = cv2.resize(secondary_frame, (new_w2, h1))

        combined = cv2.hconcat([primary_frame, secondary_frame])
        return self._draw_global_panel(combined)

    def _finalize_counts(self) -> dict:
        counts = dict(self.confirmed_counts)
        grading = grade_from_counts(counts)

        return {
            "counts": counts,
            "total_unique": self.total_unique,
            "used_secondary": self.use_secondary,
            "secondary_active": self.secondary_active,
            "confirmed_by_secondary": self.confirmed_by_secondary,
            "counted_by_primary_only": self.counted_by_primary_only,
            "discarded_pending": self.discarded_pending,
            "pending_left": len(self.pending_events),
            **grading,
        }

    def _run_loop(self):
        try:
            infer_kwargs = get_infer_kwargs()

            self.primary_model = build_model()
            primary_names = self.primary_model.names

            if self.use_secondary:
                self.secondary_model = build_model()
                secondary_names = self.secondary_model.names
            else:
                secondary_names = None

            primary_worker = get_camera_worker(self.cam_id, self.source_config)

            t0 = time.time()
            while primary_worker.get_frame() is None:
                time.sleep(0.2)
                if time.time() - t0 > 10:
                    raise RuntimeError("No se pudo obtener frame de la cámara principal (timeout).")

            secondary_worker = None
            if self.use_secondary:
                try:
                    secondary_worker = get_camera_worker(self.secondary_cam_id, self.secondary_source_config)
                    t1 = time.time()
                    while secondary_worker.get_frame() is None:
                        time.sleep(0.15)
                        if time.time() - t1 > 3:
                            break

                    self.secondary_active = secondary_worker.get_frame() is not None
                except Exception:
                    secondary_worker = None
                    self.secondary_active = False

            while True:
                with self._lock:
                    if self._stop_flag:
                        break
                    if self.ends_at and time.time() >= self.ends_at:
                        break

                frame1 = primary_worker.get_frame()
                if frame1 is None:
                    time.sleep(0.02)
                    continue

                results1 = self.primary_model.track(
                    source=frame1,
                    conf=self.conf_display,
                    imgsz=self.imgsz,
                    tracker=self.tracker_cfg,
                    persist=True,
                    verbose=False,
                    **infer_kwargs,
                )

                drawn1, primary_crossings = self._process_camera_tracks(
                    frame=frame1,
                    results=results1,
                    names=primary_names,
                    line_ratio=self.primary_line_ratio,
                    last_positions=self.primary_track_last_pos,
                    title="CAM1 - PRIMARY",
                    role="primary",
                )

                # Procesar eventos de cam1
                for ev in primary_crossings:
                    if not self.use_secondary or not self.secondary_active:
                        counted_ev = {
                            "event_id": self._next_event_id(),
                            "primary_class": ev["class"],
                            "final_class": ev["class"],
                            "primary_conf": ev["conf"],
                            "secondary_conf": None,
                            "crossed_at": ev["crossed_at"],
                            "status": "counted_primary_single_cam",
                        }
                        self._count_event(counted_ev, counted_via="primary")
                        continue

                    # si es fuerte, cuenta de una vez
                    if ev["conf"] >= self.strong_primary_conf:
                        counted_ev = {
                            "event_id": self._next_event_id(),
                            "primary_class": ev["class"],
                            "final_class": ev["class"],
                            "primary_conf": ev["conf"],
                            "secondary_conf": None,
                            "crossed_at": ev["crossed_at"],
                            "status": "counted_primary_strong",
                        }
                        self._count_event(counted_ev, counted_via="primary")
                    else:
                        # si es dudoso, queda pendiente para que cam2 confirme
                        self._create_pending_primary_event(
                            cls_name=ev["class"],
                            conf=ev["conf"],
                            crossed_at=ev["crossed_at"],
                        )

                drawn2 = None

                # Procesar cam2 opcional
                if self.use_secondary and secondary_worker is not None:
                    frame2 = secondary_worker.get_frame()
                    if frame2 is not None:
                        self.secondary_active = True
                        self.secondary_last_seen_at = time.time()

                        results2 = self.secondary_model.track(
                            source=frame2,
                            conf=self.conf_display,
                            imgsz=self.imgsz,
                            tracker=self.tracker_cfg,
                            persist=True,
                            verbose=False,
                            **infer_kwargs,
                        )

                        drawn2, secondary_crossings = self._process_camera_tracks(
                            frame=frame2,
                            results=results2,
                            names=secondary_names,
                            line_ratio=self.secondary_line_ratio,
                            last_positions=self.secondary_track_last_pos,
                            title="CAM2 - SECONDARY",
                            role="secondary",
                        )

                        for ev in secondary_crossings:
                            self._try_match_secondary(
                                cls_name=ev["class"],
                                conf=ev["conf"],
                                crossed_at=ev["crossed_at"],
                            )
                    else:
                        if self.secondary_last_seen_at and (time.time() - self.secondary_last_seen_at) > 1.5:
                            self.secondary_active = False

                self._resolve_pending_timeouts(time.time())

                final_frame = self._combine_frames(drawn1, drawn2)

                ok2, jpg = cv2.imencode(".jpg", final_frame)
                if ok2:
                    with self._lock:
                        self.latest_jpeg = jpg.tobytes()

            # al cerrar, resolver pendientes restantes
            self._resolve_pending_timeouts(time.time() + self.pending_timeout_s + 0.1)

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
                    "used_secondary": self.use_secondary,
                    "secondary_active": self.secondary_active,
                    "confirmed_by_secondary": self.confirmed_by_secondary,
                    "counted_by_primary_only": self.counted_by_primary_only,
                    "discarded_pending": self.discarded_pending,
                    "pending_left": len(self.pending_events),
                    "error": str(e),
                }
                self.state = "error"

