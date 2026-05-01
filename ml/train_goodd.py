from pathlib import Path
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent

DATA_YAML = BASE_DIR / "datasets" / "dataset_coffee_final" / "data.yaml"

def main():
    model = YOLO("weights/coffeequal_best.pt")

    model.train(
        data=str(DATA_YAML),
        imgsz=640,
        epochs=80,
        batch=8,
        device=0,
        workers=4,
        project=str(BASE_DIR / "runs"),
        name="coffeequal_v1_rtx",
        patience=20,       # si deja de mejorar, se detiene
        cache=True,
    )

if __name__ == "__main__":
    main()