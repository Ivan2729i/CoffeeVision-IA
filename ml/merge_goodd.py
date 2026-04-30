from pathlib import Path
import shutil
import yaml

BASE = Path(__file__).resolve().parent

MAIN_DS = BASE / "datasets" / "Dataset1"
GOOD_DS = BASE / "datasets" / "Dataset2"

OUT = BASE / "datasets" / "coffee_final"

# Clases finales
FINAL_NAMES = [
    "broken_cut_bitten",
    "coffee_bean",
    "dry_cherry",
    "floater",
    "foreign",
    "full_black",
    "full_sour",
    "fungus_damage",
    "immature",
    "parchment",
    "partial_black",
    "partial_sour",
    "severe_insect_damage",
    "shell",
    "slight_insect_damage",
]

SPLITS = ["train", "valid", "test"]


def read_names(dataset_path):
    data_yaml = dataset_path / "data.yaml"
    data = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    return data["names"]


def ensure_dirs(root):
    for split in SPLITS:
        (root / split / "images").mkdir(parents=True, exist_ok=True)
        (root / split / "labels").mkdir(parents=True, exist_ok=True)


def remap_label_file(src_label, dst_label, old_names, class_map):
    lines_out = []

    for line in src_label.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if not parts:
            continue

        old_id = int(parts[0])
        old_class = old_names[old_id]

        if old_class not in class_map:
            continue

        new_class = class_map[old_class]
        new_id = FINAL_NAMES.index(new_class)

        parts[0] = str(new_id)
        lines_out.append(" ".join(parts))

    if lines_out:
        dst_label.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
        return True

    return False


def copy_dataset_with_remap(src, prefix, class_map):
    old_names = read_names(src)

    copied = 0

    for split in SPLITS:
        src_img_dir = src / split / "images"
        src_lab_dir = src / split / "labels"

        dst_img_dir = OUT / split / "images"
        dst_lab_dir = OUT / split / "labels"

        if not src_img_dir.exists() or not src_lab_dir.exists():
            continue

        for img in src_img_dir.glob("*.*"):
            label = src_lab_dir / f"{img.stem}.txt"
            if not label.exists():
                continue

            new_stem = f"{prefix}_{img.stem}"
            new_img = dst_img_dir / f"{new_stem}{img.suffix.lower()}"
            new_label = dst_lab_dir / f"{new_stem}.txt"

            ok = remap_label_file(label, new_label, old_names, class_map)

            if ok:
                shutil.copy2(img, new_img)
                copied += 1

    return copied


def main():
    if OUT.exists():
        shutil.rmtree(OUT)

    ensure_dirs(OUT)

    # Mapa para dataset principal
    main_map = {
        "broken_cut_bitten": "broken_cut_bitten",
        "coffee_bean": "coffee_bean",
        "dry_cherry": "dry_cherry",
        "floater": "floater",
        "foreign": "foreign",
        "full_black": "full_black",
        "full_sour": "full_sour",
        "fungus_damage": "fungus_damage",
        "immature": "immature",
        "parchment": "parchment",
        "partial_black": "partial_black",
        "partial_sour": "partial_sour",
        "severe_insect_damage": "severe_insect_damage",
        "shell": "shell",
        "slight_insect_damage": "slight_insect_damage",
    }

    # Mapa para dataset nuevo
    good_map = {
        "green-coffee-beans": "coffee_bean",
        "good_green_bean": "coffee_bean",
        "Good Green Bean": "coffee_bean",
    }

    c1 = copy_dataset_with_remap(MAIN_DS, "main", main_map)
    c2 = copy_dataset_with_remap(GOOD_DS, "good", good_map)

    data_yaml = {
        "path": OUT.as_posix(),
        "train": "train/images",
        "val": "valid/images",
        "test": "test/images",
        "nc": len(FINAL_NAMES),
        "names": FINAL_NAMES,
    }

    (OUT / "data.yaml").write_text(
        yaml.dump(data_yaml, sort_keys=False, allow_unicode=True),
        encoding="utf-8"
    )

    print("Dataset fusionado creado en:", OUT)
    print("Imágenes copiadas del dataset principal:", c1)
    print("Imágenes copiadas del dataset good:", c2)
    print("Clases finales:", FINAL_NAMES)


if __name__ == "__main__":
    main()

