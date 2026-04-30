from pathlib import Path
import random
import shutil

BASE = Path(__file__).resolve().parent

# Dataset fusionado
SRC = BASE / "datasets" / "coffee_final"

# Nuevo dataset ya dividido
OUT = BASE / "datasets" / "dataset_coffee_final"

SPLITS = {
    "train": 0.80,
    "valid": 0.15,
    "test": 0.05,
}

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SEED = 42


def ensure_dirs():
    for split in SPLITS:
        (OUT / split / "images").mkdir(parents=True, exist_ok=True)
        (OUT / split / "labels").mkdir(parents=True, exist_ok=True)


def main():
    random.seed(SEED)

    if OUT.exists():
        shutil.rmtree(OUT)

    ensure_dirs()

    src_img = SRC / "train" / "images"
    src_lab = SRC / "train" / "labels"

    items = []

    for img in src_img.iterdir():
        if img.suffix.lower() not in IMG_EXTS:
            continue

        label = src_lab / f"{img.stem}.txt"
        if label.exists():
            items.append((img, label))

    random.shuffle(items)

    total = len(items)
    train_end = int(total * SPLITS["train"])
    valid_end = train_end + int(total * SPLITS["valid"])

    split_items = {
        "train": items[:train_end],
        "valid": items[train_end:valid_end],
        "test": items[valid_end:],
    }

    for split, files in split_items.items():
        for img, label in files:
            shutil.copy2(img, OUT / split / "images" / img.name)
            shutil.copy2(label, OUT / split / "labels" / label.name)

    # Copiar data.yaml y ajustar path
    data_yaml = SRC / "data.yaml"
    if data_yaml.exists():
        text = data_yaml.read_text(encoding="utf-8")
        lines = []
        for line in text.splitlines():
            if line.startswith("path:"):
                lines.append(f"path: {OUT.as_posix()}")
            elif line.startswith("val:"):
                lines.append("val: valid/images")
            elif line.startswith("train:"):
                lines.append("train: train/images")
            elif line.startswith("test:"):
                lines.append("test: test/images")
            else:
                lines.append(line)

        (OUT / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Dataset dividido creado en:", OUT)
    print("Total:", total)
    print("Train:", len(split_items["train"]))
    print("Valid:", len(split_items["valid"]))
    print("Test:", len(split_items["test"]))
    print("data.yaml:", OUT / "data.yaml")


if __name__ == "__main__":
    main()