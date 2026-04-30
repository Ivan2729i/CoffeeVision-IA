from collections import Counter
from inference.predictor import predict
from inference.grading import grade_from_counts


def analyze_image(source, conf=0.25):
    results = predict(source=source, conf=conf)

    boxes = results[0].boxes
    cls_ids = boxes.cls.int().tolist()

    names = results[0].names
    cls_names = [names[i] for i in cls_ids]

    raw_counts = dict(Counter(cls_names))
    grading = grade_from_counts(raw_counts)

    return {
        "raw_counts": raw_counts,
        **grading,
    }
