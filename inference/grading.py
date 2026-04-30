from collections import Counter
from dashboard.models import DefectCatalog

IGNORED_CLASSES = {"coffee_bean"}


def grade_from_totals(primary_total: int, secondary_total: int, defects_total: int) -> int:
    if primary_total == 0 and secondary_total <= 5:
        return 1

    if defects_total <= 18:
        return 2

    if defects_total <= 30:
        return 3

    return 4


def grade_from_counts(raw_counts: dict) -> dict:
    raw_counts = raw_counts or {}

    defects = DefectCatalog.objects.all()
    defects_by_code = {d.code: d for d in defects}

    primary_counts = {}
    secondary_counts = {}
    details = []

    primary_total = 0
    secondary_total = 0

    for code, value in raw_counts.items():
        if code in IGNORED_CLASSES:
            continue

        defect = defects_by_code.get(code)
        if not defect:
            continue

        try:
            raw_count = int(value)
        except (TypeError, ValueError):
            raw_count = 0

        if raw_count <= 0:
            continue

        official_count = raw_count // defect.equivalence

        if official_count <= 0:
            continue

        details.append({
            "defect_id": defect.id,
            "code": defect.code,
            "name": defect.name,
            "defect_type": defect.defect_type,
            "equivalence": defect.equivalence,
            "raw_count": raw_count,
            "official_count": official_count,
        })

        if defect.defect_type == DefectCatalog.TYPE_PRIMARY:
            primary_counts[defect.code] = official_count
            primary_total += official_count

        elif defect.defect_type == DefectCatalog.TYPE_SECONDARY:
            secondary_counts[defect.code] = official_count
            secondary_total += official_count

    defects_total = primary_total + secondary_total
    grade = grade_from_totals(primary_total, secondary_total, defects_total)

    return {
        "counts": {
            "primary": primary_counts,
            "secondary": secondary_counts,
        },
        "details": details,
        "primary_total": primary_total,
        "secondary_total": secondary_total,
        "defects_total": defects_total,
        "score": defects_total,
        "grade": grade,
    }


def counts_from_results(results, names) -> dict:
    boxes = results[0].boxes
    cls_ids = boxes.cls.int().tolist()
    cls_names = [names[i] for i in cls_ids]
    return dict(Counter(cls_names))

