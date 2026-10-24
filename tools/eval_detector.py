"""Score a YOLOv8 ONNX detector on the held-out VisDrone-DET split.

Runs the repo's own OrtYoloDetector, so the score reflects deployed
preprocessing (stretch-resize to the input size) and postprocessing.

Scoring rules
- Ground truth: the four highway classes from visdrone_loader.CLASS_MAP.
- Ignore boxes (unmapped VisDrone labels and ignore_regions) become iscrowd=1
  annotations in every scored category, so detections on them are not penalised.
- Metrics: pycocotools COCOeval, AP@0.5:0.95 and AP@0.5, overall and per class.
"""
import argparse
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import visdrone_loader as vl  # noqa: E402

CATEGORIES = ["car", "motorcycle", "truck", "bus"]
CAT_ID = {name: i + 1 for i, name in enumerate(CATEGORIES)}
DETECTOR_LABEL_TO_CAT = {"Car": "car", "Motorbike": "motorcycle", "Truck": "truck", "Bus": "bus"}


def _xyxy_to_xywh(box):
    x1, y1, x2, y2 = box
    return [x1, y1, x2 - x1, y2 - y1]


def build_coco_gt(samples):
    """COCO ground truth. Image ids are 1..N in list order."""
    images, anns = [], []
    next_ann = 1
    for img_id, s in enumerate(samples, start=1):
        images.append({"id": img_id, "file_name": s["filepath"],
                       "width": s["metadata"]["width"], "height": s["metadata"]["height"]})
        scored, ignore = vl.split_boxes(s)
        for d in scored:
            bb = _xyxy_to_xywh(d["box"])
            anns.append({"id": next_ann, "image_id": img_id, "category_id": CAT_ID[d["cls"]],
                         "bbox": bb, "area": bb[2] * bb[3], "iscrowd": 0})
            next_ann += 1
        for box in ignore:
            bb = _xyxy_to_xywh(box)
            for cat_id in CAT_ID.values():
                anns.append({"id": next_ann, "image_id": img_id, "category_id": cat_id,
                             "bbox": bb, "area": bb[2] * bb[3], "iscrowd": 1})
                next_ann += 1
    cats = [{"id": CAT_ID[n], "name": n} for n in CATEGORIES]
    return {"images": images, "annotations": anns, "categories": cats}


def detections_to_coco(image_id, detections):
    """Convert detector tuples (x, y, w, h, label, conf) to COCO results.
    Labels outside the highway taxonomy are dropped."""
    out = []
    for x, y, w, h, label, conf in detections:
        cat = DETECTOR_LABEL_TO_CAT.get(label)
        if cat is None:
            continue
        out.append({"image_id": image_id, "category_id": CAT_ID[cat],
                    "bbox": [float(x), float(y), float(w), float(h)], "score": float(conf)})
    return out


def _metric_or_none(v):
    return float(v) if v >= 0 else None


def _coco_metrics(coco_gt, coco_dt, cat_ids=None):
    from pycocotools.cocoeval import COCOeval
    ev = COCOeval(coco_gt, coco_dt, "bbox")
    if cat_ids:
        ev.params.catIds = cat_ids
    ev.evaluate()
    ev.accumulate()
    ev.summarize()
    return {"AP50_95": _metric_or_none(ev.stats[0]), "AP50": _metric_or_none(ev.stats[1])}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(model_path, split_path, conf, limit, out_path):
    from pycocotools.coco import COCO
    from app.detector import OrtYoloDetector

    with open(split_path) as f:
        split = json.load(f)
    samples = vl.fetch_samples(tag=None)
    _, test = vl.partition(samples, split)
    if limit:
        test = test[:limit]

    coco_gt = COCO()
    coco_gt.dataset = build_coco_gt(test)
    coco_gt.createIndex()

    det = OrtYoloDetector(model_path, input_size=320, conf_threshold=conf, nms_threshold=0.45)
    preds = []
    for img_id, s in enumerate(test, start=1):
        frame = vl.fetch_image(s["filepath"])
        preds.extend(detections_to_coco(img_id, det.detect(frame)))

    report = {
        "model": model_path,
        "model_sha256": _sha256(model_path),
        "split": split_path,
        "split_version": split.get("version"),
        "taxonomy_version": vl.TAXONOMY_VERSION,
        "conf_threshold": conf,
        "images": len(test),
        "gt_scored_boxes": sum(1 for a in coco_gt.dataset["annotations"] if a["iscrowd"] == 0),
        "predictions": len(preds),
    }
    if preds:
        coco_dt = coco_gt.loadRes(preds)
        report["overall"] = _coco_metrics(coco_gt, coco_dt)
        report["per_class"] = {n: _coco_metrics(coco_gt, coco_dt, [CAT_ID[n]]) for n in CATEGORIES}
    else:
        report["status"] = "no detections; check model, conf threshold and input"

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != "per_class"}, indent=2))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=os.path.join(ROOT, "models", "yolov8n_coco_320.onnx"))
    ap.add_argument("--split", default=os.path.join(ROOT, "configs", "visdrone_det_split_v1.json"))
    ap.add_argument("--conf", type=float, default=0.001,
                    help="low threshold for mAP; the deployed detector uses 0.4")
    ap.add_argument("--limit", type=int, default=0, help="score only the first N test images")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports", "detector_baseline.json"))
    args = ap.parse_args(argv)
    run(args.model, args.split, args.conf, args.limit, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
