from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from inference.analyze import analyze_image
import os
import tempfile
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db import transaction
from .models import Batch, Provider, Evaluation, Packing, ActivityLog, Alert, EvaluationDefect, QualitySettings, MoistureAnalysis, MoistureSettings
from .forms import ProviderForm, BatchCreateForm
from django.http import StreamingHttpResponse, HttpResponse
import cv2
from django.core.cache import cache
import time
from inference.live_session import LiveEvalSession
from datetime import date
from django.db.models import Count, Sum, IntegerField, Case, When, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
import io
import csv
from collections import Counter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from decimal import Decimal
from .camera_hub import get_camera_worker
import json
from django.conf import settings
from decimal import Decimal, InvalidOperation



# ========= Inicio: Vistas SideBar =============

TEMPLATE = "dashboard/index.html"


@login_required(login_url="login")
def dashboard_view(request):
    return render(request, TEMPLATE, {
        "page_title": "Dashboard",
        "active": "dashboard",
    })


@login_required(login_url="login")
def library_view(request):
    return render(request, TEMPLATE, {
        "page_title": "Defect Library",
        "active": "library",
    })


@login_required(login_url="login")
def camera_view(request):
    return render(request, TEMPLATE, {
        "page_title": "Camera Monitoring",
        "active": "camera",
    })


@login_required(login_url="login")
def machine_view(request):
    return render(request, TEMPLATE, {
        "page_title": "Machine Control",
        "active": "machine",
    })


@login_required(login_url="login")
def quality_view(request):
    return render(request, TEMPLATE, {
        "page_title": "Quality Assessment",
        "active": "quality",
    })


@login_required(login_url="login")
def moisture_view(request):
    return render(request, TEMPLATE, {
        "page_title": "Moisture Analysis",
        "active": "moisture",
    })


@login_required(login_url="login")
def batch_metrics_view(request):
    return render(request, TEMPLATE, {
        "page_title": "Batch Metrics",
        "active": "batch",
    })


@login_required(login_url="login")
def packaging_view(request):
    providers = Provider.objects.order_by("first_name", "last_name")

    return render(request, TEMPLATE, {
        "page_title": "Packaging and Distribution",
        "active": "packaging",
        "providers": providers,
    })


@login_required(login_url="login")
def activity_log_view(request):
    return render(request, TEMPLATE, {
        "page_title": "Activity Log",
        "active": "activity",
    })


@login_required(login_url="login")
def reports_view(request):
    evaluated_batches = (
        Batch.objects
        .select_related("provider")
        .filter(evaluation__isnull=False)
        .order_by("-created_at")
    )

    providers = Provider.objects.order_by("last_name", "first_name")

    now = timezone.localtime(timezone.now())
    current_year = now.year
    years = list(range(2024, current_year + 1))

    return render(request, TEMPLATE, {
        "page_title": "Report Generation",
        "active": "reports",
        "evaluated_batches": evaluated_batches,
        "providers": providers,
        "years": years,
        "current_year": current_year,
        "current_month": now.month,
    })


@login_required(login_url="login")
def alerts_view(request):
    return render(request, TEMPLATE, {
        "page_title": "Alerts and Notifications",
        "active": "alerts",
    })


@login_required(login_url="login")
def settings_view(request):
    return render(request, TEMPLATE, {
        "page_title": "System Settings",
        "active": "settings",
    })


# ========= Fin: Vistas SideBar =============


# ========= Inicio: Settings/Providers =============
# Render
@login_required(login_url="login")
@require_http_methods(["GET"])
def settings_providers(request):
    form = ProviderForm()
    providers = Provider.objects.order_by("-created_at")

    return render(request, TEMPLATE, {
        "page_title": "System settings",
        "active": "settings",
        "settings_section": "providers",
        "form": form,
        "providers": providers,
    })


# Crear proveedores
@login_required(login_url="login")
@require_http_methods(["POST"])
def providers_create(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({
            "ok": False,
            "message": "Solicitud inválida."
        }, status=400)

    form = ProviderForm(data)

    if not form.is_valid():
        return JsonResponse({
            "ok": False,
            "message": "No se pudo guardar. Revisa los campos marcados.",
            "errors": form.errors,
        }, status=400)

    p = form.save()

    log_activity(
        request=request,
        module=ActivityLog.MODULE_SETTINGS,
        action="provider_created",
        description=f"Se registró el proveedor {p}",
        level=ActivityLog.LEVEL_SUCCESS,
        obj=p,
        metadata={
            "contact": p.contact,
        },
    )

    return JsonResponse({
        "ok": True,
        "message": f"Proveedor '{p}' creado correctamente.",
        "provider": {
            "id": p.id,
            "first_name": p.first_name,
            "last_name": p.last_name,
            "contact": p.contact,
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M"),
        }
    })


# Editar proveedores
@login_required(login_url="login")
@require_http_methods(["POST"])
def providers_update(request, pk):
    provider = get_object_or_404(Provider, pk=pk)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({
            "ok": False,
            "message": "Solicitud inválida."
        }, status=400)

    old_data = {
        "first_name": provider.first_name,
        "last_name": provider.last_name,
        "contact": provider.contact,
    }

    form = ProviderForm(data, instance=provider)

    if not form.is_valid():
        return JsonResponse({
            "ok": False,
            "message": "No se pudo actualizar. Revisa los campos marcados.",
            "errors": form.errors,
        }, status=400)

    provider = form.save()

    log_activity(
        request=request,
        module=ActivityLog.MODULE_SETTINGS,
        action="provider_updated",
        description=f"Se actualizó el proveedor {provider}",
        level=ActivityLog.LEVEL_INFO,
        obj=provider,
        metadata={
            "before": old_data,
            "after": {
                "first_name": provider.first_name,
                "last_name": provider.last_name,
                "contact": provider.contact,
            },
        },
    )

    return JsonResponse({
        "ok": True,
        "message": f"Proveedor '{provider}' actualizado correctamente.",
        "provider": {
            "id": provider.id,
            "first_name": provider.first_name,
            "last_name": provider.last_name,
            "contact": provider.contact,
        }
    })


# Borrar proveedores
@login_required(login_url="login")
@require_http_methods(["POST"])
def providers_delete(request, pk):
    provider = get_object_or_404(Provider, pk=pk)
    provider_name = str(provider)

    log_activity(
        request=request,
        module=ActivityLog.MODULE_SETTINGS,
        action="provider_deleted",
        description=f"Se eliminó el proveedor {provider_name}",
        level=ActivityLog.LEVEL_WARNING,
        obj=provider,
        metadata={
            "first_name": provider.first_name,
            "last_name": provider.last_name,
            "contact": provider.contact,
        },
    )

    provider.delete()

    return JsonResponse({
        "ok": True,
        "message": f"Proveedor '{provider_name}' eliminado correctamente."
    })


# ========= Fin: Settings/Providers =============


# ========= Inicio: Quality helpers =============

def totals_from_counts(counts: dict) -> tuple[int, int, int]:
    p = counts.get("primary") or {}
    s = counts.get("secondary") or {}

    def safe_sum(d):
        total = 0
        for v in d.values():
            try:
                total += int(v)
            except:
                pass
        return total

    primary_total = safe_sum(p)
    secondary_total = safe_sum(s)
    return primary_total, secondary_total, primary_total + secondary_total

def save_evaluation_defects(evaluation, details):
    details = details or []

    objs = []

    for item in details:
        defect_id = item.get("defect_id")
        if not defect_id:
            continue

        objs.append(EvaluationDefect(
            evaluation=evaluation,
            defect_id=defect_id,
            raw_count=int(item.get("raw_count") or 0),
            official_count=int(item.get("official_count") or 0),
        ))

    if objs:
        EvaluationDefect.objects.bulk_create(objs)

def get_visual_counts_from_evaluation(evaluation):
    visual_counts = {
        "primary": {},
        "secondary": {},
    }

    rows = (
        EvaluationDefect.objects
        .select_related("defect")
        .filter(evaluation=evaluation)
        .order_by("defect__defect_type", "defect__code")
    )

    for row in rows:
        if row.defect.defect_type == row.defect.TYPE_PRIMARY:
            visual_counts["primary"][row.defect.code] = row.raw_count

        elif row.defect.defect_type == row.defect.TYPE_SECONDARY:
            visual_counts["secondary"][row.defect.code] = row.raw_count

    return visual_counts


def visual_counts_from_details(details):
    visual_counts = {
        "primary": {},
        "secondary": {},
    }

    for item in details or []:
        defect_type = item.get("defect_type")
        code = item.get("code")
        raw_count = int(item.get("raw_count") or 0)

        if not code or raw_count <= 0:
            continue

        if defect_type == "primary":
            visual_counts["primary"][code] = raw_count

        elif defect_type == "secondary":
            visual_counts["secondary"][code] = raw_count

    return visual_counts

# ========= Fin: Quality helpers =============


# ========= Inicio: Quality =============

@login_required(login_url="login")
@require_POST
@csrf_protect
def evaluate_image(request):
    batch_id = request.POST.get("batch_id")
    if not batch_id:
        return JsonResponse({"ok": False, "error": "Falta batch_id."}, status=400)

    batch = get_object_or_404(Batch, pk=batch_id)

    # Si ya tiene evaluación, no duplicar
    if hasattr(batch, "evaluation"):
        ev = batch.evaluation
        return JsonResponse({
            "ok": True,
            "already_evaluated": True,
            "grade": ev.grade,
            "score": float(ev.score) if ev.score is not None else None,
            "primary_total": ev.primary_total,
            "secondary_total": ev.secondary_total,
            "defects_total": ev.defects_total,
            "counts": ev.counts,
            "visual_counts": get_visual_counts_from_evaluation(ev),
        })

    f = request.FILES.get("image")
    if not f:
        return JsonResponse({"ok": False, "error": "Falta el archivo 'image'."}, status=400)

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
        with os.fdopen(fd, "wb") as tmp:
            for chunk in f.chunks():
                tmp.write(chunk)

        # IA
        res = analyze_image(tmp_path, conf=0.25)

        if not isinstance(res, dict):
            return JsonResponse({"ok": False, "error": "Respuesta inválida del modelo."}, status=500)

        counts = res.get("counts") or {"primary": {}, "secondary": {}}
        details = res.get("details") or []

        primary_total = int(res.get("primary_total") or 0)
        secondary_total = int(res.get("secondary_total") or 0)
        defects_total = int(res.get("defects_total") or 0)

        grade = int(res.get("grade") or 4)
        score = res.get("score")

        with transaction.atomic():
            ev = Evaluation.objects.create(
                batch=batch,
                method=Evaluation.METHOD_IMAGE,
                grade=grade,
                score=score,
                counts=counts,
                primary_total=primary_total,
                secondary_total=secondary_total,
                defects_total=defects_total,
            )
            save_evaluation_defects(ev, details)

        if ev.primary_total > 15:
            create_primary_defects_alert(ev, created_by=request.user)

        log_activity(
            request=request,
            module=ActivityLog.MODULE_QUALITY,
            action="evaluation_saved",
            description=f"Se guardó la evaluación por imagen del lote {batch.code} con grado {ev.grade}",
            level=ActivityLog.LEVEL_SUCCESS,
            obj=batch,
            metadata={
                "method": ev.method,
                "grade": ev.grade,
                "score": float(ev.score) if ev.score is not None else None,
                "primary_total": ev.primary_total,
                "secondary_total": ev.secondary_total,
                "defects_total": ev.defects_total,
            },
        )

        return JsonResponse({
            "ok": True,
            "already_evaluated": False,
            "grade": ev.grade,
            "score": float(ev.score) if ev.score is not None else None,
            "primary_total": ev.primary_total,
            "secondary_total": ev.secondary_total,
            "defects_total": ev.defects_total,
            "counts": ev.counts,
            "visual_counts": visual_counts_from_details(details),
        })


    except Exception as e:
        create_evaluation_error_alert(
            batch=batch,
            error_message=f"Ocurrió un error al evaluar por imagen el lote {batch.code}: {str(e)}",
            created_by=request.user,
            metadata={
                "source": "evaluate_image",
                "batch_code": batch.code,
                "error": str(e),
            },
        )

        log_activity(
            request=request,
            module=ActivityLog.MODULE_QUALITY,
            action="evaluation_error",
            description=f"Error al evaluar por imagen el lote {batch.code}",
            level=ActivityLog.LEVEL_ERROR,
            obj=batch,
            metadata={

                "error": str(e),

            },
        )
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def quality_home(request):
    if request.method == "POST":
        form = BatchCreateForm(request.POST)
        if form.is_valid():
            batch = form.save()

            log_activity(
                request=request,
                module=ActivityLog.MODULE_QUALITY,
                action="batch_created",
                description=f"Se creó el lote {batch.code}",
                level=ActivityLog.LEVEL_SUCCESS,
                obj=batch,
                metadata={
                    "provider": str(batch.provider),
                    "provider_id": batch.provider_id,
                    "weight_kg": str(batch.weight_kg),
                },
            )

            messages.success(request, f"Lote {batch.code} creado.")
            return redirect("dashboard:quality_batch_detail", batch_id=batch.id)
        messages.error(request, "No se pudo crear el lote. Revisa los campos.")
    else:
        form = BatchCreateForm()

    batches = Batch.objects.select_related("provider").order_by("-created_at")

    quality_settings = QualitySettings.get_current()

    return render(request, TEMPLATE, {
        "page_title": "Quality assessment",
        "active": "quality",
        "quality_section": "home",
        "form": form,
        "batches": batches,
        "sample_size_grams": quality_settings.sample_size_grams,
    })


@login_required(login_url="login")
def quality_batch_detail(request, batch_id: int):
    batch = get_object_or_404(Batch.objects.select_related("provider"), pk=batch_id)
    evaluation = batch.evaluation if hasattr(batch, "evaluation") else None

    quality_settings = QualitySettings.get_current()

    evaluation_visual_counts = {
        "primary": {},
        "secondary": {},
    }

    if evaluation:
        evaluation_visual_counts = get_visual_counts_from_evaluation(evaluation)

    return render(request, TEMPLATE, {
        "page_title": "Quality assessment",
        "active": "quality",
        "quality_section": "detail",
        "batch": batch,
        "evaluation": evaluation,
        "sample_size_grams": quality_settings.sample_size_grams,
        "evaluation_visual_counts": evaluation_visual_counts,
    })

# ========= Fin: Quality =============


def normalize_camera_sources(raw_sources):
    if not raw_sources:
        return []

    if isinstance(raw_sources, list):
        return [s for s in raw_sources if isinstance(s, dict)]

    if isinstance(raw_sources, tuple):
        return [s for s in raw_sources if isinstance(s, dict)]

    if isinstance(raw_sources, dict):
        # Caso: una sola config de cámara
        if any(k in raw_sources for k in ("type", "index", "url")):
            return [raw_sources]

        # Caso: {"primary": {...}, "fallback": {...}}
        ordered_keys = ["primary", "main", "fallback", "backup", "secondary"]
        ordered = []

        for key in ordered_keys:
            value = raw_sources.get(key)
            if isinstance(value, dict):
                ordered.append(value)

        # Agrega cualquier otra config adicional no repetida
        for key, value in raw_sources.items():
            if key in ordered_keys:
                continue
            if isinstance(value, dict):
                ordered.append(value)

        return ordered

    return []

## ===== Inicio: Camera streaming (MJPEG) =====

def _mjpeg_generator(cam_id: str, sources: list[dict]):
    worker = get_camera_worker(cam_id, sources)

    while True:
        frame = worker.get_frame()
        if frame is None:
            time.sleep(0.05)
            continue

        ok, jpg = cv2.imencode(".jpg", frame)
        if not ok:
            time.sleep(0.02)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"
        )


@login_required(login_url="login")
def camera_stream(request, cam_id: str):
    raw_sources = settings.CAMERA_SOURCES.get(cam_id)
    sources = normalize_camera_sources(raw_sources)

    if not sources:
        return JsonResponse({"ok": False, "error": "Cámara no configurada."}, status=404)

    try:
        return StreamingHttpResponse(
            _mjpeg_generator(cam_id, sources),
            content_type="multipart/x-mixed-replace; boundary=frame"
        )
    except Exception as e:
        create_camera_error_alert(
            message=f"No se pudo iniciar el stream de la cámara {cam_id}: {str(e)}",
            created_by=request.user,
            metadata={
                "source": "camera_stream",
                "camera_id": cam_id,
                "error": str(e),
            },
        )

        log_activity(
            request=request,
            module=ActivityLog.MODULE_QUALITY,
            action="camera_stream_error",
            description=f"Error al iniciar stream de la cámara {cam_id}",
            level=ActivityLog.LEVEL_ERROR,
            metadata={
                "camera": cam_id,
                "error": str(e),
            },
        )
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

# ===== Fin: Camera streaming (MJPEG) =====

# ===== Inicio: Quality/Live sessions Camera =====

LIVE_SESSIONS = {}

# reutiliza mapeo RTSP
#CAMERA_RTSP = {
#    "cam1": "rtsp://192.168.100.10:8554/live/gopro", # cambia la ip cada vez que se pruebe
#    "cam2": None,
#}

@login_required(login_url="login")
def live_annotated_stream(request, cam_id: str):
    """
    Stream MJPEG del frame anotado por la sesión.
    Si aún no hay frame anotado, usa preview normal.
    """
    sess: LiveEvalSession | None = LIVE_SESSIONS.get(cam_id)
    if not sess or sess.status()["state"] not in ("running", "finished"):
        return JsonResponse({"ok": False, "error": "No hay sesión activa."}, status=404)

    raw_sources = settings.CAMERA_SOURCES.get(cam_id)
    sources = normalize_camera_sources(raw_sources)
    worker = get_camera_worker(cam_id, sources) if sources else None

    def gen():
        while True:
            st = sess.status()["state"]
            jpg = sess.get_latest_jpeg()

            if jpg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                )
            else:
                frame = worker.get_frame() if worker else None
                if frame is not None:
                    ok, fallback_jpg = cv2.imencode(".jpg", frame)
                    if ok:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + fallback_jpg.tobytes() + b"\r\n"
                        )
                    else:
                        time.sleep(0.05)
                else:
                    time.sleep(0.05)

            if st == "error":
                break

            if st == "finished":
                time.sleep(0.05)

    return StreamingHttpResponse(
        gen(),
        content_type="multipart/x-mixed-replace; boundary=frame"
    )


def _resolve_optional_secondary_camera(primary_cam_id: str):
    """
    Intenta resolver una cámara secundaria opcional.
    Regla simple:
    - si la principal es cam1, intenta usar cam2
    - si la principal es cam2, intenta usar cam1
    - si no existe config o no da video, se ignora sin romper el flujo
    """
    candidate_cam_id = None

    if primary_cam_id == "cam1":
        candidate_cam_id = "cam2"
    elif primary_cam_id == "cam2":
        candidate_cam_id = "cam1"
    else:
        # Si en el futuro agregas más cámaras, aquí puedes cambiar la lógica.
        return None, None, False, "no_candidate"

    raw_sources = settings.CAMERA_SOURCES.get(candidate_cam_id)
    sources = normalize_camera_sources(raw_sources)

    if not sources:
        return candidate_cam_id, None, False, "not_configured"

    worker = get_camera_worker(candidate_cam_id, sources)

    active_source = None
    for _ in range(15):  # ~1.5 s
        active_name = worker.get_active_source_name()
        if active_name:
            active_source = next(
                (src for src in sources if src.get("name") == active_name),
                None
            )
            if active_source:
                break
        time.sleep(0.1)

    if active_source is None and sources:
        active_source = sources[0]

    probe_frame = None
    for _ in range(15):  # ~1.5 s
        probe_frame = worker.get_frame()
        if probe_frame is not None:
            break
        time.sleep(0.1)

    if probe_frame is None:
        return candidate_cam_id, None, False, "no_video"

    return candidate_cam_id, active_source, True, "ok"


@login_required(login_url="login")
@require_POST
@csrf_protect
def live_start(request):
    cam_id = request.POST.get("cam_id", "cam1")
    batch_id = request.POST.get("batch_id")

    if not batch_id:
        return JsonResponse({"ok": False, "error": "Falta batch_id."}, status=400)

    batch = get_object_or_404(Batch, pk=batch_id)

    if hasattr(batch, "evaluation"):
        ev = batch.evaluation
        return JsonResponse({
            "ok": True,
            "already_evaluated": True,
            "grade": ev.grade,
            "score": float(ev.score) if ev.score is not None else None,
            "primary_total": ev.primary_total,
            "secondary_total": ev.secondary_total,
            "defects_total": ev.defects_total,
            "counts": ev.counts,
        })

    raw_sources = settings.CAMERA_SOURCES.get(cam_id)
    sources = normalize_camera_sources(raw_sources)

    if not sources:
        create_camera_error_alert(
            message=f"La cámara {cam_id} no está configurada en el sistema.",
            batch=batch,
            created_by=request.user,
            metadata={
                "camera_id": cam_id,
                "source": "live_start",
            },
        )
        return JsonResponse({"ok": False, "error": "Cámara no configurada."}, status=400)

    old = LIVE_SESSIONS.get(cam_id)
    if old:
        try:
            old.stop()
        except Exception:
            pass

    worker = get_camera_worker(cam_id, sources)

    # Detectar fuente activa principal
    active_source = None
    for _ in range(20):  # ~2 segundos
        active_name = worker.get_active_source_name()
        if active_name:
            active_source = next(
                (src for src in sources if src.get("name") == active_name),
                None
            )
            if active_source:
                break
        time.sleep(0.1)

    if active_source is None:
        active_source = sources[0]

    # Verificar video real principal
    probe_frame = None
    for _ in range(20):  # ~2 segundos
        probe_frame = worker.get_frame()
        if probe_frame is not None:
            break
        time.sleep(0.1)

    if probe_frame is None:
        create_camera_error_alert(
            message=f"No se pudo obtener video desde ninguna fuente activa para la cámara {cam_id}.",
            batch=batch,
            created_by=request.user,
            metadata={
                "camera_id": cam_id,
                "source": "live_start",
                "sources_count": len(sources),
            },
        )

        log_activity(
            request=request,
            module=ActivityLog.MODULE_QUALITY,
            action="live_evaluation_start_error",
            description=f"No hay video disponible para iniciar evaluación en vivo del lote {batch.code} en {cam_id}",
            level=ActivityLog.LEVEL_ERROR,
            obj=batch,
            metadata={
                "camera": cam_id,
                "reason": "no_active_video_source",
                "sources_count": len(sources),
            },
        )

        return JsonResponse({
            "ok": False,
            "error": "No hay video disponible desde la cámara seleccionada.",
        }, status=400)

    # Resolver cámara secundaria opcional
    secondary_cam_id, secondary_source_config, secondary_enabled, secondary_reason = _resolve_optional_secondary_camera(cam_id)

    sess = LiveEvalSession(
        cam_id=cam_id,
        source_config=active_source,
        duration_s=30,
        no_grain_timeout_s=6.0,
        min_session_s=3.0,
        conf_display=0.25,
        conf_count=0.40,
        tracker_cfg="bytetrack.yaml",
        imgsz=640,
        count_axis="y",
        count_direction="down",
        primary_line_ratio=0.62,
        secondary_line_ratio=0.62,
        max_box_area=9000,
        secondary_cam_id=secondary_cam_id if secondary_enabled else None,
        secondary_source_config=secondary_source_config if secondary_enabled else None,
        sync_min_delay_s=0.05,
        sync_max_delay_s=0.80,
        pending_timeout_s=1.10,
        strong_primary_conf=0.70,
        secondary_confirm_conf=0.35,
        fallback_primary_conf=0.55,
    )
    sess.batch_id = int(batch.id)

    LIVE_SESSIONS[cam_id] = sess

    try:
        sess.start()
    except Exception as e:
        create_camera_error_alert(
            message=f"No se pudo iniciar la sesión de evaluación en vivo para la cámara {cam_id}: {str(e)}",
            batch=batch,
            created_by=request.user,
            metadata={
                "camera_id": cam_id,
                "source": "live_start",
                "error": str(e),
            },
        )

        log_activity(
            request=request,
            module=ActivityLog.MODULE_QUALITY,
            action="live_evaluation_start_error",
            description=f"Error al iniciar evaluación en vivo del lote {batch.code} en {cam_id}",
            level=ActivityLog.LEVEL_ERROR,
            obj=batch,
            metadata={
                "camera": cam_id,
                "error": str(e),
            },
        )
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

    log_activity(
        request=request,
        module=ActivityLog.MODULE_QUALITY,
        action="live_evaluation_started",
        description=f"Se inició una evaluación en vivo del lote {batch.code} en {cam_id}",
        level=ActivityLog.LEVEL_INFO,
        obj=batch,
        metadata={
            "camera": cam_id,
            "no_grain_timeout_s": 6,
            "mode": "detection_based",
            "active_source": active_source.get("name", "Sin nombre"),
            "sources_count": len(sources),
            "secondary_enabled": secondary_enabled,
            "secondary_camera": secondary_cam_id,
            "secondary_reason": secondary_reason,
        },
    )

    return JsonResponse({
        "ok": True,
        "state": "running",
        "cam_id": cam_id,
        "no_grain_timeout_s": 6,
        "mode": "detection_based",
        "secondary_enabled": secondary_enabled,
        "secondary_camera": secondary_cam_id,
        "secondary_reason": secondary_reason,
    })


@login_required(login_url="login")
@require_POST
@csrf_protect
def live_stop(request):
    cam_id = request.POST.get("cam_id", "cam1")
    sess: LiveEvalSession | None = LIVE_SESSIONS.get(cam_id)
    if not sess:
        return JsonResponse({"ok": False, "error": "No hay sesión."}, status=404)

    sess.stop()
    return JsonResponse({"ok": True})


@login_required(login_url="login")
def live_status(request):
    cam_id = request.GET.get("cam_id", "cam1")
    batch_id = request.GET.get("batch_id")

    sess: LiveEvalSession | None = LIVE_SESSIONS.get(cam_id)
    if not sess:
        return JsonResponse({"ok": True, "state": "idle"})

    try:
        req_batch = int(batch_id) if batch_id else None
    except:
        req_batch = None

    if req_batch is not None and getattr(sess, "batch_id", None) != req_batch:
        return JsonResponse({"ok": True, "state": "idle"})

    status_data = sess.status()

    if status_data.get("state") == "error":
        session_batch_id = getattr(sess, "batch_id", None)
        if session_batch_id:
            try:
                batch = Batch.objects.get(pk=session_batch_id)
                persist_live_session_error(
                    request,
                    batch=batch,
                    cam_id=cam_id,
                    status_data=status_data,
                )
            except Batch.DoesNotExist:
                pass

    return JsonResponse({
        "ok": True,
        **status_data,
    })


@login_required(login_url="login")
@require_POST
@csrf_protect
def live_save(request):
    cam_id = request.POST.get("cam_id", "cam1")
    sess: LiveEvalSession | None = LIVE_SESSIONS.get(cam_id)
    if not sess:
        return JsonResponse({"ok": False, "error": "No hay sesión."}, status=404)

    st = sess.status()

    if st.get("state") == "error":
        batch_id = getattr(sess, "batch_id", None)
        if batch_id:
            try:
                batch = Batch.objects.get(pk=batch_id)
                persist_live_session_error(
                    request,
                    batch=batch,
                    cam_id=cam_id,
                    status_data=st,
                )
            except Batch.DoesNotExist:
                pass

        return JsonResponse({
            "ok": False,
            "error": (st.get("final") or {}).get("error") or "La sesión terminó con error.",
        }, status=400)

    if st["state"] != "finished":
        return JsonResponse({"ok": False, "error": "La sesión aún no ha terminado."}, status=400)

    payload = st.get("final") or {}
    if not payload:
        return JsonResponse({"ok": False, "error": "No hay resultados."}, status=400)

    batch_id = getattr(sess, "batch_id", None)
    if not batch_id:
        return JsonResponse({"ok": False, "error": "Sesión sin batch ligado."}, status=400)

    batch = get_object_or_404(Batch, pk=batch_id)
    if hasattr(batch, "evaluation"):
        return JsonResponse({"ok": True, "already_evaluated": True})

    counts = payload.get("counts") or {"primary": {}, "secondary": {}}
    details = payload.get("details") or []

    primary_total = int(payload.get("primary_total") or 0)
    secondary_total = int(payload.get("secondary_total") or 0)
    defects_total = int(payload.get("defects_total") or 0)

    grade = payload.get("grade")
    score = payload.get("score")

    with transaction.atomic():
        ev = Evaluation.objects.create(
            batch=batch,
            method=Evaluation.METHOD_CAMERA,
            grade=grade,
            score=score,
            counts=counts,
            primary_total=primary_total,
            secondary_total=secondary_total,
            defects_total=defects_total,
        )
        save_evaluation_defects(ev, details)

    if ev.primary_total > 15:
        create_primary_defects_alert(ev, created_by=request.user)

    try:
        sess.stop()
    except Exception:
        pass

    LIVE_SESSIONS.pop(cam_id, None)
    cache.delete(f"live_batch:{cam_id}")

    log_activity(
        request=request,
        module=ActivityLog.MODULE_QUALITY,
        action="live_evaluation_saved",
        description=f"Se guardó la evaluación por cámara del lote {batch.code} con grado {ev.grade}",
        level=ActivityLog.LEVEL_SUCCESS,
        obj=batch,
        metadata={
            "camera": cam_id,
            "method": ev.method,
            "grade": ev.grade,
            "score": float(ev.score) if ev.score is not None else None,
            "primary_total": ev.primary_total,
            "secondary_total": ev.secondary_total,
            "defects_total": ev.defects_total,
            "total_unique": int(payload.get("total_unique") or 0),
            "used_secondary": bool(payload.get("used_secondary")),
            "secondary_active": bool(payload.get("secondary_active")),
            "confirmed_by_secondary": int(payload.get("confirmed_by_secondary") or 0),
            "counted_by_primary_only": int(payload.get("counted_by_primary_only") or 0),
            "discarded_pending": int(payload.get("discarded_pending") or 0),
            "pending_left": int(payload.get("pending_left") or 0),
        },
    )

    return JsonResponse({
        "ok": True,
        "grade": ev.grade,
        "score": float(ev.score) if ev.score is not None else None,
        "primary_total": ev.primary_total,
        "secondary_total": ev.secondary_total,
        "defects_total": ev.defects_total,
        "counts": ev.counts,
        "visual_counts": visual_counts_from_details(details),
        "total_unique": int(payload.get("total_unique") or 0),
        "used_secondary": bool(payload.get("used_secondary")),
        "secondary_active": bool(payload.get("secondary_active")),
        "confirmed_by_secondary": int(payload.get("confirmed_by_secondary") or 0),
        "counted_by_primary_only": int(payload.get("counted_by_primary_only") or 0),
        "discarded_pending": int(payload.get("discarded_pending") or 0),
        "pending_left": int(payload.get("pending_left") or 0),
    })

# ===== Fin: Quality/Live sessions Camera =====

# ===== Inicio: Dashboard/Graficas Dashboard =====

MONTH_NAMES_ES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]


def _safe_pct(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return round((num / den) * 100.0, 2)


def _year_month_bounds(year: int, month: int) -> tuple[date, date]:
    # inicio mes, inicio mes siguiente
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def dashboard_summary_api(request):
    now = timezone.localtime(timezone.now())
    year = now.year
    current_month = now.month
    prev_month = current_month - 1 if current_month > 1 else 12
    prev_year = year if current_month > 1 else year - 1

    # ========= 1) Series por mes =========
    monthly_qs = (
        Evaluation.objects
        .filter(created_at__year=year)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(
            lots=Count("id"),
            kg=Sum("batch__weight_kg"),
            accepted=Count(Case(When(grade__in=[1, 2, 3], then=1), output_field=IntegerField())),
            total=Count("id"),
        )
        .order_by("month")
    )

    # Rellenar meses faltantes (1..12) con 0
    lots_by_month = {m: 0 for m in range(1, 13)}
    kg_by_month = {m: 0.0 for m in range(1, 13)}
    acc_by_month = {m: 0 for m in range(1, 13)}
    total_by_month = {m: 0 for m in range(1, 13)}

    for row in monthly_qs:
        month_num = row["month"].month
        lots_by_month[month_num] = int(row["lots"] or 0)
        kg_by_month[month_num] = float(row["kg"] or 0.0)
        acc_by_month[month_num] = int(row["accepted"] or 0)
        total_by_month[month_num] = int(row["total"] or 0)

    labels = MONTH_NAMES_ES
    lots_series = [lots_by_month[m] for m in range(1, 13)]
    kg_series = [round(kg_by_month[m], 2) for m in range(1, 13)]

    # ========= 2) KPIs globales =========
    global_qs = Evaluation.objects.all().aggregate(
        total_lots=Count("id"),
        total_kg=Sum("batch__weight_kg"),
        accepted=Count(Case(When(grade__in=[1, 2, 3], then=1), output_field=IntegerField())),
        rejected=Count(Case(When(grade=4, then=1), output_field=IntegerField())),
    )

    total_lots = int(global_qs["total_lots"] or 0)
    total_kg = float(global_qs["total_kg"] or 0.0)
    accepted = int(global_qs["accepted"] or 0)
    rejected = int(global_qs["rejected"] or 0)

    quality_pct = _safe_pct(accepted, total_lots)
    reject_pct = _safe_pct(rejected, total_lots)

    # ========= 3) Comparativa mes actual vs anterior =========
    cur_start, cur_end = _year_month_bounds(year, current_month)
    prev_start, prev_end = _year_month_bounds(prev_year, prev_month)

    cur = Evaluation.objects.filter(created_at__date__gte=cur_start, created_at__date__lt=cur_end).aggregate(
        lots=Count("id"),
        kg=Sum("batch__weight_kg"),
        accepted=Count(Case(When(grade__in=[1, 2, 3], then=1), output_field=IntegerField())),
    )
    prev = Evaluation.objects.filter(created_at__date__gte=prev_start, created_at__date__lt=prev_end).aggregate(
        lots=Count("id"),
        kg=Sum("batch__weight_kg"),
        accepted=Count(Case(When(grade__in=[1, 2, 3], then=1), output_field=IntegerField())),
    )

    cur_lots = int(cur["lots"] or 0)
    prev_lots = int(prev["lots"] or 0)

    cur_kg = float(cur["kg"] or 0.0)
    prev_kg = float(prev["kg"] or 0.0)

    cur_quality = _safe_pct(int(cur["accepted"] or 0), cur_lots)
    prev_quality = _safe_pct(int(prev["accepted"] or 0), prev_lots)

    def delta_pct(cur_val: float, prev_val: float) -> float:
        if prev_val == 0:
            return 0.0 if cur_val == 0 else 100.0
        return round(((cur_val - prev_val) / prev_val) * 100.0, 2)

    comparison = {
        "current": {"year": year, "month": current_month},
        "previous": {"year": prev_year, "month": prev_month},
        "lots": {"current": cur_lots, "previous": prev_lots, "delta_pct": delta_pct(cur_lots, prev_lots)},
        "kg": {"current": round(cur_kg, 2), "previous": round(prev_kg, 2), "delta_pct": delta_pct(cur_kg, prev_kg)},
        "quality": {
            "current": cur_quality,
            "previous": prev_quality,
            "delta_points": round(cur_quality - prev_quality, 2),
        },
    }

    payload = {
        "year": year,
        "has_data": total_lots > 0,
        "kpis": {
            "total_lots": total_lots,
            "total_kg": round(total_kg, 2),
            "quality_pct": quality_pct,
            "reject_pct": reject_pct,
        },
        "charts": {
            "labels": labels,
            "lots_by_month": lots_series,
            "kg_by_month": kg_series,
        },
        "comparison": comparison,
    }
    return JsonResponse(payload)

# ===== Fin: Dashboard/Graficas Dashboard =====


# ===== Inicio: Reports/Reports helpers =====

MONTH_NAMES_ES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

def _safe_pct(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return round((num / den) * 100.0, 2)

def _validate_year_month(year: int | None, month: int | None):
    if year is None or month is None:
        return False, "Faltan parámetros year y month."
    if year < 2024:
        return False, "El año mínimo permitido es 2024."
    if month < 1 or month > 12:
        return False, "El mes debe estar entre 1 y 12."
    return True, ""

def _month_bounds(year: int, month: int):
    start = timezone.datetime(year, month, 1, tzinfo=timezone.get_current_timezone())
    if month == 12:
        end = timezone.datetime(year + 1, 1, 1, tzinfo=timezone.get_current_timezone())
    else:
        end = timezone.datetime(year, month + 1, 1, tzinfo=timezone.get_current_timezone())
    return start, end

def _normalize_counts(counts: dict) -> tuple[dict, dict]:
    counts = counts or {}
    primary = counts.get("primary") or {}
    secondary = counts.get("secondary") or {}
    return dict(primary), dict(secondary)

def _aggregate_defects(evals):
    # suma todas las keys del JSON counts en primarios/secundarios
    prim = Counter()
    sec = Counter()

    for ev in evals:
        primary, secondary = _normalize_counts(ev.counts)
        for k, v in primary.items():
            try: prim[k] += int(v)
            except: pass
        for k, v in secondary.items():
            try: sec[k] += int(v)
            except: pass

    # top 10
    return dict(prim.most_common(10)), dict(sec.most_common(10))

def _summary_from_evals(evals_qs):
    # evals_qs: QuerySet[Evaluation]
    total_lots = evals_qs.count()
    total_kg = float(
        evals_qs.aggregate(s=Sum("batch__weight_kg"))["s"] or 0.0
    )

    accepted = evals_qs.filter(grade__in=[1, 2, 3]).count()
    rejected = evals_qs.filter(grade=4).count()

    quality_pct = _safe_pct(accepted, total_lots)
    reject_pct = _safe_pct(rejected, total_lots)

    top_primary, top_secondary = _aggregate_defects(evals_qs)

    return {
        "total_lots": total_lots,
        "total_kg": round(total_kg, 3),
        "accepted": accepted,
        "rejected": rejected,
        "quality_pct": quality_pct,
        "reject_pct": reject_pct,
        "top_defects": {
            "primary": top_primary,
            "secondary": top_secondary,
        }
    }

def _pdf_response(title: str, filename: str, meta_lines: list[str], summary: dict, extra_sections: list[tuple[str, dict]] = None):
    extra_sections = extra_sections or []

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 16)
    c.drawString(0.8 * inch, height - 0.9 * inch, title)

    c.setFont("Helvetica", 10)
    y = height - 1.25 * inch
    for line in meta_lines:
        c.drawString(0.8 * inch, y, line)
        y -= 0.2 * inch

    y -= 0.15 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.8 * inch, y, "Resumen")
    y -= 0.25 * inch

    c.setFont("Helvetica", 10)
    lines = [
        f"Lotes evaluados: {summary['total_lots']}",
        f"KG procesados: {summary['total_kg']:.3f} kg",
        f"Calidad (% Grado 1-2): {summary['quality_pct']:.2f}%",
        f"Rechazo (% Grado 4): {summary['reject_pct']:.2f}%",
    ]
    for line in lines:
        c.drawString(0.8 * inch, y, line)
        y -= 0.2 * inch

    def draw_top(title_s: str, data: dict, y0: float) -> float:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(0.8 * inch, y0, title_s)
        y = y0 - 0.25 * inch

        c.setFont("Helvetica", 10)
        if not data:
            c.drawString(0.9 * inch, y, "Sin datos.")
            return y - 0.25 * inch

        for k, v in data.items():
            if y < 1.2 * inch:
                c.showPage()
                y = height - 1.0 * inch
                c.setFont("Helvetica", 10)
            c.drawString(0.9 * inch, y, str(k))
            c.drawRightString(5.6 * inch, y, str(v))
            y -= 0.18 * inch
        return y - 0.18 * inch

    y -= 0.2 * inch
    y = draw_top("Defectos Primarios", summary["top_defects"]["primary"], y)
    y = draw_top("Defectos Secundarios", summary["top_defects"]["secondary"], y)

    for section_title, section_data in extra_sections:
        y -= 0.15 * inch
        y = draw_top(section_title, section_data, y)

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(0.8 * inch, 0.8 * inch, "Generado por CoffeeVision AI.")

    c.showPage()
    c.save()

    pdf = buf.getvalue()
    buf.close()

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

def _csv_response(filename: str, header: list[str], rows: list[dict]):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=header)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

    resp = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

# ===== Fin: Reports/Reports helpers =====


# ===== Inicio: Reports/Generar reportes =====

# ===== Inicio: Reports/Generar reportes por Lote =====
@login_required(login_url="login")
def reports_lote_api(request, batch_id: int):
    batch = get_object_or_404(Batch.objects.select_related("provider"), pk=batch_id)
    if not hasattr(batch, "evaluation"):
        return JsonResponse({"ok": True, "has_data": False, "error": "Este lote no tiene evaluación."})

    ev = batch.evaluation
    provider_name = f"{batch.provider.first_name} {batch.provider.last_name}".strip()

    primary, secondary = _normalize_counts(ev.counts)

    return JsonResponse({
        "ok": True,
        "mode": "lote",
        "has_data": True,
        "batch": {
            "id": batch.id,
            "code": batch.code,
            "weight_kg": float(batch.weight_kg),
            "status": batch.status,
            "created_at": batch.created_at.isoformat(),
            "provider": {"id": batch.provider_id, "name": provider_name, "contact": getattr(batch.provider, "contact", "")}
        },
        "evaluation": {
            "method": ev.method,
            "grade": ev.grade,
            "score": float(ev.score) if ev.score is not None else None,
            "primary_total": ev.primary_total,
            "secondary_total": ev.secondary_total,
            "defects_total": ev.defects_total,
            "created_at": ev.created_at.isoformat(),
            "counts": {"primary": primary, "secondary": secondary}
        }
    })


@login_required(login_url="login")
def reports_lote_pdf(request, batch_id: int):
    batch = get_object_or_404(Batch.objects.select_related("provider"), pk=batch_id)
    if not hasattr(batch, "evaluation"):
        create_report_error_alert(
            batch=batch,
            message=f"No se pudo generar el reporte PDF del lote {batch.code} porque no tiene evaluación.",
            created_by=request.user,
            metadata={
                "format": "pdf",
                "scope": "batch",
                "batch_code": batch.code,
                "reason": "sin_evaluacion",
            },
        )
        return HttpResponse("Este lote no tiene evaluación.", status=404)

    ev = batch.evaluation
    provider_name = f"{batch.provider.first_name} {batch.provider.last_name}".strip()

    summary = _summary_from_evals(Evaluation.objects.filter(batch=batch))

    meta = [
        f"Tipo: Lote",
        f"Lote: {batch.code} (ID {batch.id})",
        f"Proveedor: {provider_name}",
        f"Peso: {float(batch.weight_kg):.3f} kg",
        f"Fecha evaluación: {ev.created_at.strftime('%Y-%m-%d %H:%M')}",
        f"Grado: {ev.grade if ev.grade is not None else '—'} | Score: {float(ev.score):.2f}" if ev.score is not None else f"Grado: {ev.grade if ev.grade is not None else '—'} | Score: —",
        f"Totales: P {ev.primary_total} | S {ev.secondary_total} | Total {ev.defects_total}",
    ]

    filename = f"reporte_lote_{batch.code}.pdf"

    log_activity(
        request=request,
        module=ActivityLog.MODULE_REPORTS,
        action="report_lote_pdf_generated",
        description=f"Se generó el reporte PDF del lote {batch.code}",
        level=ActivityLog.LEVEL_SUCCESS,
        obj=batch,
        metadata={
            "format": "pdf",
            "scope": "batch",
        },
    )

    return _pdf_response("CoffeeVision AI - Reporte por Lote", filename, meta, summary)


@login_required(login_url="login")
def reports_lote_csv(request, batch_id: int):
    batch = get_object_or_404(Batch.objects.select_related("provider"), pk=batch_id)
    if not hasattr(batch, "evaluation"):
        create_report_error_alert(
            batch=batch,
            message=f"No se pudo generar el reporte CSV del lote {batch.code} porque no tiene evaluación.",
            created_by=request.user,
            metadata={
                "format": "csv",
                "scope": "batch",
                "batch_code": batch.code,
                "reason": "sin_evaluacion",
            },
        )
        return HttpResponse("Este lote no tiene evaluación.", status=404)

    ev = batch.evaluation
    provider_name = f"{batch.provider.first_name} {batch.provider.last_name}".strip()

    primary, secondary = _normalize_counts(ev.counts)
    row = {
        "mode": "lote",
        "batch_id": batch.id,
        "batch_code": batch.code,
        "provider": provider_name,
        "weight_kg": float(batch.weight_kg),
        "batch_created_at": batch.created_at.isoformat(),
        "evaluation_created_at": ev.created_at.isoformat(),
        "method": ev.method,
        "grade": ev.grade,
        "score": float(ev.score) if ev.score is not None else "",
        "primary_total": ev.primary_total,
        "secondary_total": ev.secondary_total,
        "defects_total": ev.defects_total,
    }
    # agrega counts
    for k, v in primary.items():
        row[f"primary_{k}"] = v
    for k, v in secondary.items():
        row[f"secondary_{k}"] = v

    header = list(row.keys())

    log_activity(
        request=request,
        module=ActivityLog.MODULE_REPORTS,
        action="report_lote_csv_generated",
        description=f"Se generó el reporte CSV del lote {batch.code}",
        level=ActivityLog.LEVEL_SUCCESS,
        obj=batch,
        metadata={
            "format": "csv",
            "scope": "batch",
        },
    )

    return _csv_response(f"reporte_lote_{batch.code}.csv", header, [row])
# ===== Fin: Reports/Generar reportes por Lote =====

# ===== Inicio: Reports/Generar reportes por mes =====
@login_required(login_url="login")
def reports_month_api(request):
    try:
        year = int(request.GET.get("year"))
        month = int(request.GET.get("month"))
    except:
        return JsonResponse({"ok": False, "error": "year y month deben ser enteros."}, status=400)

    ok, msg = _validate_year_month(year, month)
    if not ok:
        return JsonResponse({"ok": False, "error": msg}, status=400)

    start, end = _month_bounds(year, month)
    qs = Evaluation.objects.filter(created_at__gte=start, created_at__lt=end)

    summary = _summary_from_evals(qs)

    return JsonResponse({
        "ok": True,
        "mode": "month",
        "has_data": summary["total_lots"] > 0,
        "period": {"year": year, "month": month, "label": f"{MONTH_NAMES_ES[month-1]} {year}"},
        "summary": summary,
    })


@login_required(login_url="login")
def reports_month_pdf(request):
    try:
        year = int(request.GET.get("year"))
        month = int(request.GET.get("month"))
    except:
        return HttpResponse("year y month deben ser enteros.", status=400)

    ok, msg = _validate_year_month(year, month)
    if not ok:
        return HttpResponse(msg, status=400)

    start, end = _month_bounds(year, month)
    qs = Evaluation.objects.filter(created_at__gte=start, created_at__lt=end)
    summary = _summary_from_evals(qs)

    if summary["total_lots"] <= 0:
        create_report_error_alert(
            message=f"No se pudo generar el reporte PDF del periodo {year}-{month:02d} porque no existen datos.",
            created_by=request.user,
            metadata={
                "format": "pdf",
                "scope": "month",
                "year": year,
                "month": month,
                "reason": "sin_datos",
            },
        )
        return HttpResponse("Sin datos para ese periodo.", status=404)

    meta = [f"Tipo: Mes", f"Periodo: {MONTH_NAMES_ES[month-1]} {year}"]
    filename = f"reporte_mes_{year}_{month:02d}.pdf"

    log_activity(
        request=request,
        module=ActivityLog.MODULE_REPORTS,
        action="report_month_pdf_generated",
        description=f"Se generó el reporte PDF del periodo {year}-{month:02d}",
        level=ActivityLog.LEVEL_SUCCESS,
        metadata={
            "format": "pdf",
            "scope": "month",
            "year": year,
            "month": month,
        },
    )

    return _pdf_response("CoffeeVision AI - Reporte Mensual", filename, meta, summary)


@login_required(login_url="login")
def reports_month_csv(request):
    try:
        year = int(request.GET.get("year"))
        month = int(request.GET.get("month"))
    except:
        return HttpResponse("year y month deben ser enteros.", status=400)

    ok, msg = _validate_year_month(year, month)
    if not ok:
        return HttpResponse(msg, status=400)

    start, end = _month_bounds(year, month)
    qs = Evaluation.objects.filter(created_at__gte=start, created_at__lt=end)
    summary = _summary_from_evals(qs)
    if summary["total_lots"] <= 0:
        create_report_error_alert(
            message=f"No se pudo generar el reporte CSV del periodo {year}-{month:02d} porque no existen datos.",
            created_by=request.user,
            metadata={
                "format": "csv",
                "scope": "month",
                "year": year,
                "month": month,
                "reason": "sin_datos",
            },
        )
        return HttpResponse("Sin datos para ese periodo.", status=404)

    # 1 fila resumen + filas por lote
    rows = [{
        "mode": "month",
        "year": year,
        "month": month,
        "total_lots": summary["total_lots"],
        "total_kg": summary["total_kg"],
        "quality_pct": summary["quality_pct"],
        "reject_pct": summary["reject_pct"],
    }]

    header = list(rows[0].keys())

    log_activity(
        request=request,
        module=ActivityLog.MODULE_REPORTS,
        action="report_month_csv_generated",
        description=f"Se generó el reporte CSV del periodo {year}-{month:02d}",
        level=ActivityLog.LEVEL_SUCCESS,
        metadata={
            "format": "csv",
            "scope": "month",
            "year": year,
            "month": month,
        },
    )

    return _csv_response(f"reporte_mes_{year}_{month:02d}.csv", header, rows)
# ===== Fin: Reports/Generar reportes por mes =====

# ===== Inicio: Reports/Generar reportes por Global =====

@login_required(login_url="login")
def reports_global_api(request):
    qs = Evaluation.objects.all()
    summary = _summary_from_evals(qs)
    return JsonResponse({"ok": True, "mode": "global", "has_data": summary["total_lots"] > 0, "summary": summary})


@login_required(login_url="login")
def reports_global_pdf(request):
    qs = Evaluation.objects.all()
    summary = _summary_from_evals(qs)
    if summary["total_lots"] <= 0:
        create_report_error_alert(
            message="No se pudo generar el reporte global en PDF porque no existen evaluaciones registradas.",
            created_by=request.user,
            metadata={
                "format": "pdf",
                "scope": "global",
                "reason": "sin_datos",
            },
        )
        return HttpResponse("Sin datos.", status=404)

    meta = ["Tipo: Global", "Periodo: Todos los lotes evaluados"]

    log_activity(
        request=request,
        module=ActivityLog.MODULE_REPORTS,
        action="report_global_pdf_generated",
        description="Se generó el reporte global en PDF",
        level=ActivityLog.LEVEL_SUCCESS,
        metadata={
            "format": "pdf",
            "scope": "global",
        },
    )

    return _pdf_response("CoffeeVision AI - Reporte Global", "reporte_global.pdf", meta, summary)


@login_required(login_url="login")
def reports_global_csv(request):
    qs = Evaluation.objects.all()
    summary = _summary_from_evals(qs)
    if summary["total_lots"] <= 0:
        create_report_error_alert(
            message="No se pudo generar el reporte global en CSV porque no existen evaluaciones registradas.",
            created_by=request.user,
            metadata={
                "format": "csv",
                "scope": "global",
                "reason": "sin_datos",
            },
        )
        return HttpResponse("Sin datos.", status=404)

    rows = [{
        "mode": "global",
        "total_lots": summary["total_lots"],
        "total_kg": summary["total_kg"],
        "quality_pct": summary["quality_pct"],
        "reject_pct": summary["reject_pct"],
    }]

    log_activity(
        request=request,
        module=ActivityLog.MODULE_REPORTS,
        action="report_global_csv_generated",
        description="Se generó el reporte global en CSV",
        level=ActivityLog.LEVEL_SUCCESS,
        metadata={
            "format": "csv",
            "scope": "global",
        },
    )

    return _csv_response("reporte_global.csv", list(rows[0].keys()), rows)
# ===== Fin: Reports/Generar reportes Global =====

# ===== Inicio: Reports/Generar reportes por Proveedor =====
@login_required(login_url="login")
def reports_provider_api(request, provider_id: int):
    provider = get_object_or_404(Provider, pk=provider_id)
    qs = Evaluation.objects.filter(batch__provider=provider)

    summary = _summary_from_evals(qs)
    provider_name = f"{provider.first_name} {provider.last_name}".strip()

    return JsonResponse({
        "ok": True,
        "mode": "provider",
        "has_data": summary["total_lots"] > 0,
        "provider": {"id": provider.id, "name": provider_name, "contact": getattr(provider, "contact", "")},
        "summary": summary,
    })


@login_required(login_url="login")
def reports_provider_pdf(request, provider_id: int):
    provider = get_object_or_404(Provider, pk=provider_id)
    provider_name = f"{provider.first_name} {provider.last_name}".strip()

    qs = Evaluation.objects.filter(batch__provider=provider)
    summary = _summary_from_evals(qs)
    if summary["total_lots"] <= 0:
        create_report_error_alert(
            message=f"No se pudo generar el reporte PDF del proveedor {provider_name} porque no existen evaluaciones registradas.",
            created_by=request.user,
            metadata={
                "format": "pdf",
                "scope": "provider",
                "provider_id": provider.id,
                "reason": "sin_datos",
            },
        )
        return HttpResponse("Sin datos para este proveedor.", status=404)

    meta = ["Tipo: Proveedor", f"Proveedor: {provider_name}"]
    filename = f"reporte_proveedor_{provider.id}.pdf"

    log_activity(
        request=request,
        module=ActivityLog.MODULE_REPORTS,
        action="report_provider_pdf_generated",
        description=f"Se generó el reporte PDF del proveedor {provider_name}",
        level=ActivityLog.LEVEL_SUCCESS,
        obj=provider,
        metadata={
            "format": "pdf",
            "scope": "provider",
            "provider_id": provider.id,
        },
    )

    return _pdf_response("CoffeeVision AI - Reporte por Proveedor", filename, meta, summary)


@login_required(login_url="login")
def reports_provider_csv(request, provider_id: int):
    provider = get_object_or_404(Provider, pk=provider_id)
    provider_name = f"{provider.first_name} {provider.last_name}".strip()

    qs = Evaluation.objects.filter(batch__provider=provider)
    summary = _summary_from_evals(qs)
    if summary["total_lots"] <= 0:
        create_report_error_alert(
            message=f"No se pudo generar el reporte CSV del proveedor {provider_name} porque no existen evaluaciones registradas.",
            created_by=request.user,
            metadata={
                "format": "csv",
                "scope": "provider",
                "provider_id": provider.id,
                "reason": "sin_datos",
            },
        )
        return HttpResponse("Sin datos para este proveedor.", status=404)

    rows = [{
        "mode": "provider",
        "provider_id": provider.id,
        "provider": provider_name,
        "total_lots": summary["total_lots"],
        "total_kg": summary["total_kg"],
        "quality_pct": summary["quality_pct"],
        "reject_pct": summary["reject_pct"],
    }]

    log_activity(
        request=request,
        module=ActivityLog.MODULE_REPORTS,
        action="report_provider_csv_generated",
        description=f"Se generó el reporte CSV del proveedor {provider_name}",
        level=ActivityLog.LEVEL_SUCCESS,
        obj=provider,
        metadata={
            "format": "csv",
            "scope": "provider",
            "provider_id": provider.id,
        },
    )

    return _csv_response(f"reporte_proveedor_{provider.id}.csv", list(rows[0].keys()), rows)
# ===== Fin: Reports/Generar reportes por Proveedor =====

# ===== Fin: Reports/Generar reportes =====


# ===== Inicio: Batch/Historial y filtros =====
def _to_int(val, default=None):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _safe_pct(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round((num / den) * 100.0, 2)

def _get_sample_size_g():
    qs = QualitySettings.objects.order_by("-id").first()
    if qs and qs.sample_size_grams:
        return float(qs.sample_size_grams)
    return 350.0

@login_required(login_url="login")
def batch_metrics_summary_api(request):

    now = timezone.localtime(timezone.now())
    year = _to_int(request.GET.get("year"), now.year)
    month = _to_int(request.GET.get("month"))
    provider_id = _to_int(request.GET.get("provider"))
    status = (request.GET.get("status") or "").strip().lower()   # draft | evaluated | all | ""
    search = (request.GET.get("search") or "").strip()
    selected_code = (request.GET.get("selected") or "").strip()
    limit = _to_int(request.GET.get("limit"), 50)
    limit = max(1, min(limit, 1500))
    sample_size_g = _get_sample_size_g()

    # regla del módulo
    if year < 2024:
        year = 2024

    # Query base lotes
    qs = (
        Batch.objects
        .select_related("provider")
        .select_related("evaluation")
        .all()
        .order_by("-created_at", "-id")
    )

    # año siempre aplica
    qs = qs.filter(created_at__year=year)

    if month:
        if month < 1 or month > 12:
            return JsonResponse({"ok": False, "error": "month debe estar entre 1 y 12."}, status=400)
        qs = qs.filter(created_at__month=month)

    if provider_id:
        qs = qs.filter(provider_id=provider_id)

    if search:
        qs = qs.filter(code__icontains=search)

    if status in ("evaluated", "evaluado"):
        qs = qs.filter(evaluation__isnull=False)
    elif status in ("draft", "borrador"):
        qs = qs.filter(evaluation__isnull=True)


    # KPIs
    total_batches = qs.count()

    evaluated_qs = qs.filter(evaluation__isnull=False)
    evaluated_batches = evaluated_qs.count()

    total_weight_kg = evaluated_qs.aggregate(s=Sum("weight_kg"))["s"] or Decimal("0")

    # calidad: grado 1-3
    accepted = evaluated_qs.filter(evaluation__grade__in=[1, 2, 3]).count()

    quality_pct = _safe_pct(accepted, evaluated_batches)
    rejection_pct = round(100.0 - quality_pct, 2) if evaluated_batches else 0.0

    kpis = {
        "total_batches": total_batches,
        "evaluated_batches": evaluated_batches,
        "total_weight_kg": float(round(total_weight_kg, 3)),
        "quality_pct": quality_pct,
        "rejection_pct": rejection_pct,
    }


    # Tabla lista de lotes
    batches = []
    for b in qs[:limit]:
        ev = b.evaluation if hasattr(b, "evaluation") else None
        provider_name = str(b.provider) if b.provider_id else None

        batches.append({
            "id": b.id,
            "code": b.code,
            "provider": {"id": b.provider_id, "name": provider_name},
            "weight_kg": float(b.weight_kg),
            "status": b.status,
            "created_at": b.created_at.isoformat(),
            "evaluation": None if not ev else {
                "method": ev.method,
                "grade": ev.grade,
                "score": float(ev.score) if ev.score is not None else None,
                "primary_total": ev.primary_total,
                "secondary_total": ev.secondary_total,
                "defects_total": ev.defects_total,
                "created_at": ev.created_at.isoformat(),
            }
        })

    # Panel detalle
    detail = None
    if selected_code:
        b = (
            Batch.objects
            .select_related("provider")
            .select_related("evaluation")
            .filter(code=selected_code)
            .first()
        )
        if b:
            ev = b.evaluation if hasattr(b, "evaluation") else None
            provider_name = str(b.provider) if b.provider_id else None
            detail = {
                "id": b.id,
                "code": b.code,
                "provider": {
                    "id": b.provider_id,
                    "name": provider_name,
                    "contact": b.provider.contact if b.provider_id else None,
                },
                "sample_size_g": sample_size_g,
                "weight_kg": float(b.weight_kg),
                "status": b.status,
                "created_at": b.created_at.isoformat(),
                "evaluation": None if not ev else {
                    "method": ev.method,
                    "grade": ev.grade,
                    "score": float(ev.score) if ev.score is not None else None,
                    "primary_total": ev.primary_total,
                    "secondary_total": ev.secondary_total,
                    "defects_total": ev.defects_total,
                    "counts": ev.counts,
                    "created_at": ev.created_at.isoformat(),
                }
            }

    # filtros aplica
    provider_obj = Provider.objects.filter(id=provider_id).first() if provider_id else None
    filters_applied = {
        "year": year,
        "month": month,
        "provider": None if not provider_obj else {"id": provider_obj.id, "name": str(provider_obj)},
        "status": status or "all",
        "search": search or None,
        "selected": selected_code or None,
        "limit": limit,
    }

    return JsonResponse({
        "ok": True,
        "kpis": kpis,
        "filters_applied": filters_applied,
        "batches": batches,
        "detail": detail,
    })

# ===== Fin: Batch/Historial y filtros =====

# ===== Inicio: Packing/Registro y control =====
# Resumen
@login_required(login_url="login")
@require_GET
def packaging_summary_api(request):
    today = date.today()

    evaluated_batches = Batch.objects.filter(status=Batch.STATUS_EVALUATED)

    pending_batches = evaluated_batches.filter(packing__isnull=True) | evaluated_batches.filter(
        packing__status=Packing.STATUS_PENDING
    )

    pending_count = pending_batches.distinct().count()
    pending_kg = pending_batches.distinct().aggregate(total=Sum("weight_kg"))["total"] or 0

    packed_today_count = Packing.objects.filter(
        packed_at=today
    ).count()

    packed_kg = Packing.objects.filter(
        status__in=[Packing.STATUS_PACKED, Packing.STATUS_SENT]
    ).aggregate(total=Sum("batch__weight_kg"))["total"] or 0

    return JsonResponse({
        "success": True,
        "summary": {
            "pending_lots": pending_count,
            "packed_today": packed_today_count,
            "pending_kg": float(pending_kg),
            "packed_kg": float(packed_kg),
        }
    })


# Lista con filtros
@login_required(login_url="login")
@require_GET
def packaging_list_api(request):
    today = date.today()

    qs = (
        Batch.objects
        .filter(status=Batch.STATUS_EVALUATED)
        .select_related("provider", "evaluation", "packing")
        .order_by("created_at", "id")
    )

    rows = []

    for batch in qs:
        try:
            packing = batch.packing
            packing_status = packing.status
            packing_status_label = packing.get_status_display()
            packed_at = packing.packed_at.isoformat() if packing.packed_at else None
            sent_at = packing.sent_at.isoformat() if packing.sent_at else None
            notes = packing.notes or ""
        except Packing.DoesNotExist:
            packing = None
            packing_status = Packing.STATUS_PENDING
            packing_status_label = "Pendiente"
            packed_at = None
            sent_at = None
            notes = ""

        evaluation = batch.evaluation if hasattr(batch, "evaluation") else None

        pending_days = None
        if packing_status == Packing.STATUS_PENDING:
            pending_days = (today - batch.created_at.date()).days

        rows.append({
            "batch_id": batch.id,
            "code": batch.code,
            "provider": {
                "id": batch.provider.id,
                "name": str(batch.provider),
            },
            "weight_kg": float(batch.weight_kg),
            "created_at": batch.created_at.strftime("%Y-%m-%d %H:%M"),
            "created_date": batch.created_at.date().isoformat(),
            "grade": evaluation.grade if evaluation else None,
            "packing_status": packing_status,
            "packing_status_label": packing_status_label,
            "packed_at": packed_at,
            "sent_at": sent_at,
            "notes": notes,
            "pending_days": pending_days,
        })

    return JsonResponse({
        "success": True,
        "count": len(rows),
        "results": rows,
    })


# Detalle
@login_required(login_url="login")
@require_GET
def packaging_detail_api(request, batch_id):
    batch = get_object_or_404(
        Batch.objects.select_related("provider", "evaluation"),
        pk=batch_id,
        status=Batch.STATUS_EVALUATED,
    )

    packing, _ = Packing.objects.get_or_create(batch=batch)
    evaluation = batch.evaluation if hasattr(batch, "evaluation") else None

    primary_counts = {}
    secondary_counts = {}

    if evaluation and evaluation.counts:
        primary_counts = evaluation.counts.get("primary", {}) or {}
        secondary_counts = evaluation.counts.get("secondary", {}) or {}

    return JsonResponse({
        "success": True,
        "detail": {
            "batch": {
                "id": batch.id,
                "code": batch.code,
                "weight_kg": float(batch.weight_kg),
                "created_at": batch.created_at.strftime("%Y-%m-%d %H:%M"),
                "status": batch.status,
                "status_label": batch.get_status_display(),
            },
            "provider": {
                "id": batch.provider.id,
                "name": str(batch.provider),
                "contact": batch.provider.contact,
            },
            "evaluation": {
                "method": evaluation.method if evaluation else None,
                "method_label": evaluation.get_method_display() if evaluation else None,
                "grade": evaluation.grade if evaluation else None,
                "primary_total": evaluation.primary_total if evaluation else 0,
                "secondary_total": evaluation.secondary_total if evaluation else 0,
                "defects_total": evaluation.defects_total if evaluation else 0,
                "primary_counts": primary_counts,
                "secondary_counts": secondary_counts,
                "created_at": evaluation.created_at.strftime("%Y-%m-%d %H:%M") if evaluation else None,
            },
            "packing": {
                "status": packing.status,
                "status_label": packing.get_status_display(),
                "packed_at": packing.packed_at.isoformat() if packing.packed_at else None,
                "sent_at": packing.sent_at.isoformat() if packing.sent_at else None,
                "notes": packing.notes or "",
            }
        }
    })


# Update
@login_required(login_url="login")
@require_http_methods(["PATCH", "POST"])
def packaging_update_api(request, batch_id):
    batch = get_object_or_404(
        Batch.objects.select_related("provider", "evaluation"),
        pk=batch_id,
        status=Batch.STATUS_EVALUATED,
    )

    packing, _ = Packing.objects.get_or_create(batch=batch)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({
            "success": False,
            "message": "JSON inválido."
        }, status=400)

    status_value = (payload.get("status") or "").strip()
    notes = (payload.get("notes") or "").strip()

    valid_statuses = {
        Packing.STATUS_PENDING,
        Packing.STATUS_PACKED,
        Packing.STATUS_SENT,
    }

    if status_value not in valid_statuses:
        return JsonResponse({
            "success": False,
            "message": "Estado de packing inválido."
        }, status=400)

    today = date.today()

    packing.status = status_value
    packing.notes = notes

    if status_value == Packing.STATUS_PENDING:
        packing.packed_at = None
        packing.sent_at = None

    elif status_value == Packing.STATUS_PACKED:
        packing.packed_at = today
        packing.sent_at = None

    elif status_value == Packing.STATUS_SENT:
        if not packing.packed_at:
            packing.packed_at = today
        packing.sent_at = today

    try:
        packing.save()
    except Exception as e:
        log_activity(
            request=request,
            module=ActivityLog.MODULE_PACKAGING,
            action="packing_update_error",
            description=f"Error al actualizar el packing del lote {batch.code}",
            level=ActivityLog.LEVEL_ERROR,
            obj=batch,
            metadata={
                "error": str(e),
                "requested_status": status_value,
            },
        )
        return JsonResponse({
            "success": False,
            "message": f"Error al guardar packing: {e}",
        }, status=400)

    log_activity(
        request=request,
        module=ActivityLog.MODULE_PACKAGING,
        action="packing_updated",
        description=f"Se actualizó el packing del lote {batch.code} a {packing.get_status_display()}",
        level=ActivityLog.LEVEL_SUCCESS,
        obj=batch,
        metadata={
            "status": packing.status,
            "status_label": packing.get_status_display(),
            "packed_at": packing.packed_at.isoformat() if packing.packed_at else None,
            "sent_at": packing.sent_at.isoformat() if packing.sent_at else None,
            "notes": packing.notes or "",
        },
    )

    return JsonResponse({
        "success": True,
        "message": "Estado actualizado correctamente.",
        "packing": {
            "status": packing.status,
            "status_label": packing.get_status_display(),
            "packed_at": packing.packed_at.isoformat() if packing.packed_at else None,
            "sent_at": packing.sent_at.isoformat() if packing.sent_at else None,
            "notes": packing.notes or "",
        }
    })

# ===== Fin: Packing/Registro y control =====

# ===== Inicio: Logs/Registro de logs =====
def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_activity(
    request,
    module,
    action,
    description,
    level="info",
    obj=None,
    metadata=None,
    user=None,
):
    if user is None:
        if hasattr(request, "user") and request.user.is_authenticated:
            user = request.user
        else:
            user = None

    object_type = None
    object_id = None
    object_label = None

    if obj is not None:
        object_type = obj.__class__.__name__.lower()
        object_id = getattr(obj, "id", None)
        object_label = str(obj)

    ActivityLog.objects.create(
        user=user,
        module=module,
        action=action,
        description=description,
        level=level,
        object_type=object_type,
        object_id=object_id,
        object_label=object_label,
        metadata=metadata or {},
        ip_address=get_client_ip(request),
    )

# API vista Log
def activity_logs_list_api(request):
    qs = ActivityLog.objects.select_related("user").all()

    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    user_id = request.GET.get("user", "").strip()
    module = request.GET.get("module", "").strip()
    level = request.GET.get("level", "").strip()

    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)

    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    if user_id:
        qs = qs.filter(user_id=user_id)

    if module:
        qs = qs.filter(module=module)

    if level:
        qs = qs.filter(level=level)

    results = []
    for log in qs[:300]:
        results.append({
            "id": log.id,
            "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "user": log.user.get_username() if log.user else "Sistema",
            "module": log.module,
            "action": log.action,
            "description": log.description,
            "level": log.level,
            "object_label": log.object_label or "",
        })

    return JsonResponse({"results": results})


# API detalle Log
def activity_log_detail_api(request, log_id):
    try:
        log = ActivityLog.objects.select_related("user").get(pk=log_id)
    except ActivityLog.DoesNotExist:
        return JsonResponse({"detail": "Log no encontrado."}, status=404)

    return JsonResponse({
        "id": log.id,
        "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "user": log.user.get_username() if log.user else "Sistema",
        "module": log.module,
        "action": log.action,
        "description": log.description,
        "level": log.level,
        "object_label": log.object_label,
    })


# API filtros
def activity_logs_users_api(request):
    users_data = (
        ActivityLog.objects
        .select_related("user")
        .filter(user__isnull=False)
        .values("user_id", "user__username")
        .distinct()
        .order_by("user__username")
    )

    results = []
    seen = set()

    for item in users_data:
        uid = item["user_id"]
        username = item["user__username"]
        if uid not in seen:
            seen.add(uid)
            results.append({
                "id": uid,
                "username": username,
            })

    return JsonResponse({"results": results})


# ===== Fin: Logs/Registro de logs =====


# ===== Inicio: Alerts/Registro de alerts =====
# Helpers
def persist_live_session_error(request, *, batch, cam_id, status_data):
    final_data = status_data.get("final") or {}
    error_message = (
        final_data.get("error")
        or status_data.get("error")
        or "Ocurrió un error desconocido durante la evaluación en vivo."
    )

    already_logged = ActivityLog.objects.filter(
        module=ActivityLog.MODULE_QUALITY,
        action="live_evaluation_runtime_error",
        object_type="batch",
        object_id=batch.id,
        metadata__camera=cam_id,
        metadata__error=error_message,
    ).exists()

    already_alerted = Alert.objects.filter(
        category=Alert.CATEGORY_CAMERA,
        batch=batch,
        is_active=True,
        metadata__source="live_session_runtime",
        metadata__camera_id=cam_id,
        metadata__error=error_message,
    ).exists()

    if not already_alerted:
        create_camera_error_alert(
            message=f"Error durante la evaluación en vivo del lote {batch.code} en la cámara {cam_id}: {error_message}",
            batch=batch,
            created_by=request.user if hasattr(request, "user") and request.user.is_authenticated else None,
            metadata={
                "source": "live_session_runtime",
                "camera_id": cam_id,
                "batch_id": batch.id,
                "batch_code": batch.code,
                "error": error_message,
            },
        )

    if not already_logged:
        log_activity(
            request=request,
            module=ActivityLog.MODULE_QUALITY,
            action="live_evaluation_runtime_error",
            description=f"Error en evaluación en vivo del lote {batch.code} en {cam_id}",
            level=ActivityLog.LEVEL_ERROR,
            obj=batch,
            metadata={
                "camera": cam_id,
                "error": error_message,
            },
        )


def create_alert(
    *,
    title,
    message,
    severity=Alert.SEVERITY_WARNING,
    category=Alert.CATEGORY_SYSTEM,
    batch=None,
    evaluation=None,
    created_by=None,
    metadata=None,
):
    return Alert.objects.create(
        title=title,
        message=message,
        severity=severity,
        category=category,
        batch=batch,
        evaluation=evaluation,
        created_by=created_by,
        metadata=metadata or {},
    )


def create_primary_defects_alert(evaluation, created_by=None):
    batch = evaluation.batch
    primary_total = evaluation.primary_total or 0

    if primary_total <= 15:
        return None

    already_exists = Alert.objects.filter(
        category=Alert.CATEGORY_QUALITY,
        batch=batch,
        evaluation=evaluation,
        is_active=True,
        is_seen=False,
    ).exists()

    if already_exists:
        return None

    return create_alert(
        title="Exceso de defectos primarios detectado",
        message=f"El lote {batch.code} superó el límite permitido con {primary_total} defectos primarios.",
        severity=Alert.SEVERITY_CRITICAL,
        category=Alert.CATEGORY_QUALITY,
        batch=batch,
        evaluation=evaluation,
        created_by=created_by,
        metadata={
            "batch_code": batch.code,
            "primary_total": primary_total,
        },
    )


def create_evaluation_error_alert(*, batch=None, error_message="", created_by=None, metadata=None):
    return create_alert(
        title="Error en evaluación",
        message=error_message or "Ocurrió un error durante el proceso de evaluación del lote.",
        severity=Alert.SEVERITY_ERROR,
        category=Alert.CATEGORY_EVALUATION,
        batch=batch,
        created_by=created_by,
        metadata=metadata or {},
    )


def create_camera_error_alert(*, message, batch=None, created_by=None, metadata=None):
    return create_alert(
        title="Error de conexión con la cámara",
        message=message,
        severity=Alert.SEVERITY_CRITICAL,
        category=Alert.CATEGORY_CAMERA,
        batch=batch,
        created_by=created_by,
        metadata=metadata or {},
    )


def create_report_error_alert(*, batch=None, message="", created_by=None, metadata=None):
    return create_alert(
        title="Error al generar reporte",
        message=message or "No se pudo generar el reporte solicitado.",
        severity=Alert.SEVERITY_ERROR,
        category=Alert.CATEGORY_REPORT,
        batch=batch,
        created_by=created_by,
        metadata=metadata or {},
    )


# APIS
@login_required(login_url="login")
@require_GET
def alerts_summary_api(request):
    qs = Alert.objects.filter(is_active=True)

    return JsonResponse({
        "ok": True,
        "summary": {
            "total": qs.count(),
            "unseen": qs.filter(is_seen=False).count(),
            "warning": qs.filter(severity=Alert.SEVERITY_WARNING).count(),
            "error": qs.filter(severity=Alert.SEVERITY_ERROR).count(),
            "critical": qs.filter(severity=Alert.SEVERITY_CRITICAL).count(),
        }
    })


@login_required(login_url="login")
@require_GET
def alerts_list_api(request):
    qs = (
        Alert.objects
        .select_related("batch", "evaluation", "created_by")
        .order_by("is_seen", "-created_at")
    )

    severity = (request.GET.get("severity") or "").strip()
    category = (request.GET.get("category") or "").strip()
    status = (request.GET.get("status") or "").strip()
    search = (request.GET.get("search") or "").strip()

    if severity:
        qs = qs.filter(severity=severity)

    if category:
        qs = qs.filter(category=category)

    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    elif status == "unseen":
        qs = qs.filter(is_seen=False)

    if search:
        qs = qs.filter(
            Q(title__icontains=search) |
            Q(message__icontains=search) |
            Q(batch__code__icontains=search)
        )

    results = []
    for alert in qs[:100]:
        results.append({
            "id": alert.id,
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity,
            "category": alert.category,
            "is_active": alert.is_active,
            "is_seen": alert.is_seen,
            "created_at": alert.created_at.isoformat(),
            "seen_at": alert.seen_at.isoformat() if alert.seen_at else None,
            "batch_id": alert.batch_id,
            "batch_code": alert.batch.code if alert.batch else None,
            "evaluation_id": alert.evaluation_id,
            "created_by": alert.created_by.get_username() if alert.created_by else None,
            "metadata": alert.metadata or {},
        })

    return JsonResponse({
        "ok": True,
        "results": results,
    })


@login_required(login_url="login")
@require_GET
def alerts_active_api(request):
    qs = (
        Alert.objects
        .filter(is_active=True)
        .select_related("batch", "evaluation")
        .order_by("is_seen", "-created_at")
    )

    only_unseen = request.GET.get("only_unseen")
    limit_raw = request.GET.get("limit", "10")

    try:
        limit = max(1, min(int(limit_raw), 50))
    except (TypeError, ValueError):
        limit = 10

    if only_unseen in {"1", "true", "True"}:
        qs = qs.filter(is_seen=False)

    results = []
    for alert in qs[:limit]:
        results.append({
            "id": alert.id,
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity,
            "category": alert.category,
            "is_active": alert.is_active,
            "is_seen": alert.is_seen,
            "created_at": alert.created_at.isoformat(),
            "seen_at": alert.seen_at.isoformat() if alert.seen_at else None,
            "batch_id": alert.batch_id,
            "batch_code": alert.batch.code if alert.batch else None,
            "evaluation_id": alert.evaluation_id,
            "metadata": alert.metadata or {},
        })

    return JsonResponse({
        "ok": True,
        "results": results,
    })


@login_required(login_url="login")
@require_POST
def alert_mark_seen_api(request, alert_id):
    try:
        alert = Alert.objects.get(pk=alert_id, is_active=True)
    except Alert.DoesNotExist:
        return JsonResponse({
            "ok": False,
            "message": "Alerta no encontrada.",
        }, status=404)

    if not alert.is_seen:
        alert.is_seen = True
        alert.seen_at = timezone.now()
        alert.save(update_fields=["is_seen", "seen_at"])

    return JsonResponse({
        "ok": True,
        "message": "Alerta marcada como vista.",
    })


@login_required(login_url="login")
@require_POST
def alert_deactivate_api(request, alert_id):
    try:
        alert = Alert.objects.get(pk=alert_id)
    except Alert.DoesNotExist:
        return JsonResponse({
            "ok": False,
            "message": "Alerta no encontrada.",
        }, status=404)

    if alert.is_active:
        alert.is_active = False
        alert.save(update_fields=["is_active"])

    return JsonResponse({
        "ok": True,
        "message": "Alerta desactivada.",
    })


# ===== Fin: Alerts/Registro de alerts =====


# ===== Inicio: Moisture Analysis =====

@require_GET
def moisture_batches_api(request):
    batches = Batch.objects.select_related("provider").order_by("-created_at")

    data = []
    for batch in batches:
        analysis = getattr(batch, "moisture_analysis", None)

        data.append({
            "id": batch.id,
            "code": batch.code,
            "provider": str(batch.provider),
            "weight_kg": str(batch.weight_kg),
            "created_at": batch.created_at.strftime("%Y-%m-%d %H:%M"),
            "moisture_status": "evaluated" if analysis else "draft",
            "moisture_label": "Evaluado" if analysis else "Borrador",
            "moisture_result": analysis.result if analysis else None,
            "moisture_result_label": analysis.get_result_display() if analysis else None,
        })

    return JsonResponse({"ok": True, "batches": data})


@require_GET
def moisture_batch_detail_api(request, batch_id):
    try:
        batch = Batch.objects.select_related("provider").get(id=batch_id)
    except Batch.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Lote no encontrado."}, status=404)

    analysis = getattr(batch, "moisture_analysis", None)

    data = {
        "id": batch.id,
        "code": batch.code,
        "provider": str(batch.provider),
        "weight_kg": str(batch.weight_kg),
        "created_at": batch.created_at.strftime("%Y-%m-%d %H:%M"),
        "moisture_status": "evaluated" if analysis else "draft",
        "moisture_label": "Evaluado" if analysis else "Borrador",
        "analysis": None,
    }

    if analysis:
        data["analysis"] = {
            "moisture_percent": str(analysis.moisture_percent),
            "result": analysis.result,
            "result_label": analysis.get_result_display(),
            "created_at": analysis.created_at.strftime("%Y-%m-%d %H:%M"),
        }

    return JsonResponse({"ok": True, "batch": data})


@csrf_exempt
@require_POST
def moisture_analyze_api(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido."}, status=400)

    batch_id = payload.get("batch_id")
    moisture_percent = payload.get("moisture_percent")

    if not batch_id:
        return JsonResponse({"ok": False, "error": "Falta el lote."}, status=400)

    if moisture_percent in [None, ""]:
        return JsonResponse({"ok": False, "error": "Falta la lectura de humedad."}, status=400)

    try:
        batch = Batch.objects.get(id=batch_id)
    except Batch.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Lote no encontrado."}, status=404)

    if hasattr(batch, "moisture_analysis"):
        return JsonResponse({
            "ok": False,
            "error": "Este lote ya tiene análisis de humedad."
        }, status=400)

    try:
        moisture_value = Decimal(str(moisture_percent))
    except (InvalidOperation, ValueError):
        return JsonResponse({"ok": False, "error": "Lectura de humedad inválida."}, status=400)

    settings_obj = MoistureSettings.get_current()

    if moisture_value < settings_obj.min_moisture:
        result = MoistureAnalysis.RESULT_LOW
    elif moisture_value > settings_obj.max_moisture:
        result = MoistureAnalysis.RESULT_HIGH
    else:
        result = MoistureAnalysis.RESULT_OPTIMAL

    analysis = MoistureAnalysis.objects.create(
        batch=batch,
        moisture_percent=moisture_value,
        result=result,
    )

    return JsonResponse({
        "ok": True,
        "message": "Análisis de humedad guardado correctamente.",
        "analysis": {
            "batch_id": batch.id,
            "batch_code": batch.code,
            "moisture_percent": str(analysis.moisture_percent),
            "result": analysis.result,
            "result_label": analysis.get_result_display(),
            "created_at": analysis.created_at.strftime("%Y-%m-%d %H:%M"),
        }
    })

# ===== Fin: Moisture Analysis =====


