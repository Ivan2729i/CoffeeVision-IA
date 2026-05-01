from pathlib import Path
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
DATA_YAML = BASE_DIR / "datasets" / "coffee_mega_merged" / "data.yaml"

def main():
    model = YOLO("weights/coffeequal_best.pt")

    model.train(
        data=str(DATA_YAML),
        imgsz=640,
        epochs=100,
        batch=16,
        device="cpu",
        workers=4,
        project=str(BASE_DIR / "runs"),
        name="coffeequal_mega_scratch",
    )

if __name__ == "__main__":
    main()