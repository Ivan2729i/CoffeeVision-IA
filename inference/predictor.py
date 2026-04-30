from pathlib import Path
import torch
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = BASE_DIR / "ml" / "weights" / "coffeequal_best.pt"

_model = None
_device = None
_use_half = False


def get_device():
    global _device

    if _device is None:
        _device = "cuda:0" if torch.cuda.is_available() else "cpu"

    return _device


def get_model():
    """
    Instancia global compartida.
    Para análisis simple / imagen estática.
    """
    global _model, _use_half

    if _model is None:
        device = get_device()
        _model = YOLO(str(MODEL_PATH))
        _model.to(device)

        # Half precision solo cuando hay GPU CUDA
        _use_half = device.startswith("cuda")

    return _model


def build_model():
    # Devuelve una instancia NUEVA del modelo.

    global _use_half

    device = get_device()
    model = YOLO(str(MODEL_PATH))
    model.to(device)

    _use_half = device.startswith("cuda")
    return model


def get_infer_kwargs():
    # Devuelve kwargs comunes de inferencia para no repetirlos.

    device = get_device()
    half = device.startswith("cuda")

    return {
        "device": device,
        "half": half,
    }


def get_runtime_info():
    device = get_device()
    return {
        "model_path": str(MODEL_PATH),
        "device": device,
        "cuda_available": torch.cuda.is_available(),
        "half": device.startswith("cuda"),
    }


def predict(source, conf: float = 0.25, imgsz: int = 640):

    model = get_model()
    infer_kwargs = get_infer_kwargs()

    results = model.predict(
        source=source,
        conf=conf,
        imgsz=imgsz,
        verbose=False,
        **infer_kwargs,
    )
    return results


def predict_frame(frame, conf: float = 0.25, imgsz: int = 640):
    # Atajo semántico para cuando el source es un frame de OpenCV.
    return predict(source=frame, conf=conf, imgsz=imgsz)


def track_frame(
    frame,
    conf: float = 0.25,
    imgsz: int = 640,
    tracker: str = "bytetrack.yaml",
    persist: bool = True,
):

    # Tracking sobre frame para mantener IDs entre frames.

    model = get_model()
    infer_kwargs = get_infer_kwargs()

    results = model.track(
        source=frame,
        conf=conf,
        imgsz=imgsz,
        tracker=tracker,
        persist=persist,
        verbose=False,
        **infer_kwargs,
    )
    return results
