from pathlib import Path
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
DATA_YAML = BASE_DIR / "datasets" / "coffee_defects" / "data.yaml"

def main():
    model = YOLO("weights/coffeequal_best.pt")  # modelo base pequeño

    model.train(
        data=str(DATA_YAML),
        imgsz=640,
        epochs=80,
        batch=16,
        device="cpu",           # si tienes GPU NVIDIA pon device=0
        workers=4,
        project=str(BASE_DIR / "runs"),
        name="coffeequal_v1",
    )

if __name__ == "__main__":
    main()
