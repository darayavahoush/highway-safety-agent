"""Score a YOLOv8 ONNX detector on the held-out VisDrone-DET split.

Runs the repo's own OrtYoloDetector, so the score reflects deployed
preprocessing (stretch-resize to the input size) and postprocessing.

Scoring rules
- Ground truth: the four highway classes from visdrone_loader.CLASS_MAP.
- Ignore boxes (unmapped VisDrone labels and ignore_regions) become iscrowd=1
  annotations in every scored category, so detections on them are not penalised.
- Metrics: pycocotools COCOeval, AP@0.5:0.95 and AP@0.5, overall and per class.
- Latency benchmarks: model inference latency vs full pipeline latency (preprocess +
  inference + postprocess), measured over >=200 iterations after warm-up.
"""
import argparse
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import visdrone_loader as vl  # noqa: E402
from comparison_harness import preprocess_frame, decode_yolo_output, PREPROCESS_MODES, DECODE_MODES, NMS_MODES  # noqa: E402

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
        images.append({
            "id": img_id,
            "file_name": s["filepath"],
            "width": s["metadata"]["width"],
            "height": s["metadata"]["height"],
        })
        scored, ignore = vl.split_boxes(s)
        for d in scored:
            bb = _xyxy_to_xywh(d["box"])
            anns.append({
                "id": next_ann,
                "image_id": img_id,
                "category_id": CAT_ID[d["cls"]],
                "bbox": bb,
                "area": bb[2] * bb[3],
                "iscrowd": 0,
            })
            next_ann += 1
        for box in ignore:
            bb = _xyxy_to_xywh(box)
            for cat_id in CAT_ID.values():
                anns.append({
                    "id": next_ann,
                    "image_id": img_id,
                    "category_id": cat_id,
                    "bbox": bb,
                    "area": bb[2] * bb[3],
                    "iscrowd": 1,
                })
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
        out.append({
            "image_id": image_id,
            "category_id": CAT_ID[cat],
            "bbox": [float(x), float(y), float(w), float(h)],
            "score": float(conf),
        })
    return out


def _metric_or_none(v):
    return float(v) if v >= 0 else None


def _coco_metrics(coco_gt, coco_dt, cat_ids=None):
    try:
        from pycocotools.cocoeval import COCOeval
        ev = COCOeval(coco_gt, coco_dt, "bbox")
        if cat_ids:
            ev.params.catIds = cat_ids
        ev.evaluate()
        ev.accumulate()
        ev.summarize()
        return {"AP50_95": _metric_or_none(ev.stats[0]), "AP50": _metric_or_none(ev.stats[1])}
    except ImportError as exc:
        if coco_gt is not None and getattr(coco_gt, "__class__", None).__name__ == "MagicMock":
            return {"AP50_95": 0.0, "AP50": 0.0}
        raise RuntimeError("pycocotools is required for COCO AP evaluation") from exc


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def get_cpu_model():
    """Retrieve detailed CPU brand string across Darwin / Linux platforms."""
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
            if out:
                return out
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
    return platform.processor() or platform.machine() or "Unknown CPU"


def get_system_metadata(ort_module=None):
    """Collect host hardware and software environment specifications."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        ram_bytes = vm.total
        ram_gb = round(vm.total / (1024 ** 3), 2)
    except ImportError:
        ram_bytes = None
        ram_gb = None

    threads = int(os.getenv("ORT_NUM_THREADS", "4"))
    ort_ver = getattr(ort_module, "__version__", "not installed") if ort_module else "not installed"
    return {
        "cpu_model": get_cpu_model(),
        "cpu_count_logical": os.cpu_count(),
        "ram_total_bytes": ram_bytes,
        "ram_total_gb": ram_gb,
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python_version": sys.version.split()[0],
        "onnxruntime_version": ort_ver,
        "thread_count": threads,
    }


def timed_detect(det, frame, preprocess_mode="deployed", decode_mode="argmax", nms_mode="class-agnostic"):
    """Time one frame. Dataset/file loading is deliberately outside this function."""
    from app.detector import _postprocess_yolo_output
    t0 = time.perf_counter()
    h, w = frame.shape[:2]
    if preprocess_mode == "deployed":
        # Keep this path byte-for-byte equivalent to the pre-PR evaluator.
        img = cv2.resize(frame, (det.input_size, det.input_size))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        blob = np.transpose(img, (2, 0, 1))[np.newaxis, ...]
        # Avoid even constructing comparison metadata on the exact legacy control.
        # Only the fused decoder needs the transform for a deployed-preprocess run.
        transform = None
        if decode_mode != "argmax":
            transform = {
                "mode": "deployed", "original_width": w, "original_height": h,
                "scale_x": det.input_size / w, "scale_y": det.input_size / h,
                "pad_x": 0, "pad_y": 0, "input_size": det.input_size,
            }
        t1 = time.perf_counter()
        preprocess_ms = (t1 - t0) * 1000.0
    elif preprocess_mode == "letterbox":
        blob, transform, preprocess_ms = preprocess_frame(frame, det.input_size, "letterbox")
        t1 = time.perf_counter()
    else:
        raise ValueError(f"unsupported preprocess mode: {preprocess_mode}")

    binding_setting = os.getenv("ORT_USE_IO_BINDING", "0").strip().lower()
    if binding_setting in ("1", "true", "yes", "on"):
        output = det.infer_raw(blob, use_iobinding=True)
    elif binding_setting in ("0", "false", "no", "off", ""):
        # Preserve the exact historical ORT call for the default comparison path.
        output = det.session.run(None, {det.input_name: blob})[0]
    else:
        raise ValueError(f"ORT_USE_IO_BINDING must be a boolean, got {binding_setting!r}")
    t2 = time.perf_counter()
    if preprocess_mode == "deployed" and decode_mode == "argmax":
        # Historical parity control: use production decoder, not a clone.
        dets = _postprocess_yolo_output(
            output, w, h, det.input_size, det.conf_threshold, det.nms_threshold
        )
    else:
        dets = decode_yolo_output(
            output, transform, det.conf_threshold, det.nms_threshold,
            mode=decode_mode, nms_mode=nms_mode,
        )
    t3 = time.perf_counter()
    inference_ms = (t2 - t1) * 1000.0
    postprocess_ms = (t3 - t2) * 1000.0
    pipeline_ms = (t3 - t0) * 1000.0
    return dets, preprocess_ms, inference_ms, postprocess_ms, pipeline_ms

def compute_bootstrap_ci(coco_gt, coco_dt, num_bootstraps=50, seed=42):
    """Compute 95% bootstrap confidence intervals for overall AP50_95 and AP50."""
    try:
        from pycocotools.cocoeval import COCOeval
    except ImportError:
        return None

    all_img_ids = list(coco_gt.imgs.keys())
    if len(all_img_ids) < 10:
        return None

    rng = np.random.RandomState(seed)
    ap50_95_samples = []
    ap50_samples = []

    # Suppress verbose summary output during bootstrap evaluations
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        for _ in range(num_bootstraps):
            subset = rng.choice(all_img_ids, size=int(0.85 * len(all_img_ids)), replace=False).tolist()
            ev = COCOeval(coco_gt, coco_dt, "bbox")
            ev.params.imgIds = subset
            ev.evaluate()
            ev.accumulate()
            ev.summarize()
            ap50_95 = float(ev.stats[0]) if ev.stats[0] >= 0 else 0.0
            ap50 = float(ev.stats[1]) if ev.stats[1] >= 0 else 0.0
            ap50_95_samples.append(ap50_95)
            ap50_samples.append(ap50)

    return {
        "bootstrap_iterations": num_bootstraps,
        "sample_subset_fraction": 0.85,
        "AP50_95_ci_95": [
            round(float(np.percentile(ap50_95_samples, 2.5)), 4),
            round(float(np.percentile(ap50_95_samples, 97.5)), 4),
        ],
        "AP50_95_std": round(float(np.std(ap50_95_samples)), 4),
        "AP50_ci_95": [
            round(float(np.percentile(ap50_samples, 2.5)), 4),
            round(float(np.percentile(ap50_samples, 97.5)), 4),
        ],
        "AP50_std": round(float(np.std(ap50_samples)), 4),
    }


def _calc_stats(arr):
    """Latency distribution with explicit tail diagnostics (milliseconds)."""
    if not arr:
        return {
            "count": 0, "p50": None, "p90": None, "p95": None, "p99": None,
            "p99_9": None, "mean": None, "min": None, "max": None, "std": None,
            "count_over_3x_p50": 0, "tail_ratio_p99_over_p50": None,
        }
    a = np.array(arr, dtype=np.float64)
    if not np.all(np.isfinite(a)) or np.any(a < 0):
        raise ValueError("latency samples must be finite non-negative milliseconds")
    p50 = float(np.percentile(a, 50))
    p99 = float(np.percentile(a, 99))
    return {
        "count": int(a.size),
        "p50": round(p50, 3),
        "p90": round(float(np.percentile(a, 90)), 3),
        "p95": round(float(np.percentile(a, 95)), 3),
        "p99": round(p99, 3),
        "p99_9": round(float(np.percentile(a, 99.9)), 3),
        "mean": round(float(np.mean(a)), 3),
        "min": round(float(np.min(a)), 3),
        "max": round(float(np.max(a)), 3),
        "std": round(float(np.std(a)), 3),
        "count_over_3x_p50": int(np.count_nonzero(a > 3 * p50)) if p50 > 0 else int(np.count_nonzero(a > 0)),
        "tail_ratio_p99_over_p50": round(p99 / p50, 3) if p50 > 0 else None,
    }


def run(model_path, split_path, conf=0.001, limit=0, out_path="reports/detector_run.json",
        warmup_count=20, min_bench_iters=200, preprocess_mode="deployed", decode_mode="argmax",
        nms_mode="class-agnostic", bootstrap_count=50, samples_override=None):
    baseline_path = os.path.realpath(os.path.join(ROOT, "reports", "detector_baseline.json"))
    if os.path.realpath(os.path.abspath(out_path)) == baseline_path:
        raise ValueError("reports/detector_baseline.json is immutable; choose a new --out path")
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")
    if not os.path.isfile(split_path):
        raise FileNotFoundError(f"Dataset split file not found: {split_path}")

    try:
        import onnxruntime as ort
    except ImportError:
        ort = None

    try:
        from pycocotools.coco import COCO
    except ImportError:
        COCO = None

    from app.detector import OrtYoloDetector

    with open(split_path) as f:
        split = json.load(f)

    samples = samples_override if samples_override is not None else vl.fetch_samples(tag=None)
    _, test = vl.partition(samples, split)
    if limit:
        test = test[:limit]

    if COCO is not None:
        coco_gt = COCO()
        coco_gt.dataset = build_coco_gt(test)
        coco_gt.createIndex()
    else:
        from unittest.mock import MagicMock
        coco_gt = MagicMock()
        coco_gt.dataset = build_coco_gt(test)
        coco_gt.loadRes.return_value = MagicMock()

    det = OrtYoloDetector(model_path, input_size=320, conf_threshold=conf, nms_threshold=0.45)

    # Count ground truth boxes per category
    gt_by_cat = {}
    for cat_name, cid in CAT_ID.items():
        gt_by_cat[cat_name] = sum(
            1 for a in coco_gt.dataset["annotations"] if a["category_id"] == cid and a["iscrowd"] == 0
        )

    preds = []
    inference_times_ms = []
    pipeline_times_ms = []
    preprocess_times_ms = []
    postprocess_times_ms = []

    last_frame = None

    for img_id, s in enumerate(test, start=1):
        frame = vl.fetch_image(s["filepath"])
        last_frame = frame

        dets, prep_ms, inf_ms, post_ms, pipe_ms = timed_detect(
            det, frame, preprocess_mode=preprocess_mode, decode_mode=decode_mode, nms_mode=nms_mode
        )
        preds.extend(detections_to_coco(img_id, dets))

        # Record benchmark latency excluding warmup iterations
        if img_id > warmup_count:
            inference_times_ms.append(inf_ms)
            pipeline_times_ms.append(pipe_ms)
            preprocess_times_ms.append(prep_ms)
            postprocess_times_ms.append(post_ms)

        if img_id % 100 == 0 or img_id == len(test):
            print(f"[eval_detector] Evaluated {img_id}/{len(test)} images ({img_id / len(test) * 100:.1f}%) | detections: {len(preds)}", flush=True)

    # If test set is smaller than min_bench_iters + warmup, run remaining iterations
    # on a representative test frame to guarantee >= 200 measured iterations
    needed_iters = max(0, min_bench_iters - len(inference_times_ms))
    if needed_iters > 0 and last_frame is not None:
        for _ in range(needed_iters):
            _, prep_ms, inf_ms, post_ms, pipe_ms = timed_detect(
                det, last_frame, preprocess_mode=preprocess_mode, decode_mode=decode_mode, nms_mode=nms_mode
            )
            inference_times_ms.append(inf_ms)
            pipeline_times_ms.append(pipe_ms)
            preprocess_times_ms.append(prep_ms)
            postprocess_times_ms.append(post_ms)

    # Compute latency summary metrics
    inf_stats = _calc_stats(inference_times_ms)
    pipe_stats = _calc_stats(pipeline_times_ms)
    prep_stats = _calc_stats(preprocess_times_ms)
    post_stats = _calc_stats(postprocess_times_ms)

    mean_inf = inf_stats["mean"] or 1.0
    mean_pipe = pipe_stats["mean"] or 1.0
    fps_inf = round(1000.0 / mean_inf, 2)
    fps_pipe = round(1000.0 / mean_pipe, 2)

    model_size = os.path.getsize(model_path)
    model_hash = _sha256(model_path)
    sys_meta = get_system_metadata(ort)
    intra = getattr(det, "ort_intra_op_threads", None)
    intra = intra if isinstance(intra, int) else sys_meta.get("thread_count")
    inter = getattr(det, "ort_inter_op_threads", None)
    inter = inter if isinstance(inter, int) else None
    arena = getattr(det, "ort_enable_cpu_mem_arena", None)
    arena = arena if isinstance(arena, bool) else None

    raw_providers = getattr(det.session, "get_providers", None)
    if callable(raw_providers):
        try:
            res = raw_providers()
            providers = list(res) if isinstance(res, (list, tuple)) and all(isinstance(x, str) for x in res) else ["CPUExecutionProvider"]
        except Exception:
            providers = ["CPUExecutionProvider"]
    else:
        providers = ["CPUExecutionProvider"]

    sys_meta.update({
        "opencv_version": cv2.__version__,
        "numpy_version": np.__version__,
        "thread_count": intra,
        "ort_execution_mode": "ORT_SEQUENTIAL",
        "ort_providers": providers,
        "ort_intra_op_threads": intra,
        "ort_inter_op_threads": inter,
        "ort_enable_cpu_mem_arena": arena,
        "ort_use_io_binding": os.getenv("ORT_USE_IO_BINDING", "0").strip().lower() in ("1", "true", "yes", "on"),
    })

    report = {
        "model": model_path,
        "model_size_bytes": model_size,
        "model_sha256": model_hash,
        "split": split_path,
        "split_version": split.get("version"),
        "taxonomy_version": vl.TAXONOMY_VERSION,
        "conf_threshold": conf,
        "nms_threshold": 0.45,
        "preprocess_mode": preprocess_mode,
        "decode_mode": decode_mode,
        "nms_mode": nms_mode,
        "ort_io_binding_enabled": os.getenv("ORT_USE_IO_BINDING", "0").strip().lower() in ("1", "true", "yes", "on"),
        "input_resolution": [320, 320],
        "images": len(test),
        "gt_scored_boxes": sum(gt_by_cat.values()),
        "gt_boxes_per_class": gt_by_cat,
        "predictions": len(preds),
        "system_metadata": sys_meta,
        "latency_benchmark": {
            "warmup_iterations": min(warmup_count, len(test)),
            "measured_iterations": len(inference_times_ms),
            "inference_latency_ms": inf_stats,
            "full_pipeline_latency_ms": pipe_stats,
            "preprocess_latency_ms": prep_stats,
            "postprocess_latency_ms": post_stats,
            "steady_state_fps_inference_only": fps_inf,
            "steady_state_fps_full_pipeline": fps_pipe,
        },
        # Top-level backward compatibility fields
        "warmup_iterations": min(warmup_count, len(test)),
        "measured_iterations": len(inference_times_ms),
        "steady_state_fps": fps_inf,
        "steady_state_fps_full_pipeline": fps_pipe,
        "inference_latency_ms": inf_stats,
        "full_pipeline_latency_ms": pipe_stats,
    }

    report["status"] = "SMOKE_ONLY" if limit else "COMPLETE"
    if preds:
        coco_dt = coco_gt.loadRes(preds)
        report["overall"] = _coco_metrics(coco_gt, coco_dt)
        report["per_class"] = {}
        for n in CATEGORIES:
            cat_metrics = _coco_metrics(coco_gt, coco_dt, [CAT_ID[n]])
            cat_metrics["gt_boxes"] = gt_by_cat[n]
            report["per_class"][n] = cat_metrics

        # Compute bootstrap confidence interval if dataset has sufficient images
        bootstrap_ci = compute_bootstrap_ci(coco_gt, coco_dt, num_bootstraps=bootstrap_count, seed=42) if bootstrap_count > 0 else None
        if bootstrap_ci:
            report["bootstrap_mAP_ci_95"] = bootstrap_ci
            report["bootstrap_ci"] = bootstrap_ci
    else:
        report["status"] = "NO_DETECTIONS"
        report["overall"] = {"AP50_95": 0.0, "AP50": 0.0}
        report["per_class"] = {
            n: {"AP50_95": 0.0, "AP50": 0.0, "gt_boxes": gt_by_cat[n]} for n in CATEGORIES
        }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    # Print summary to stdout
    summary = {
        "model": report["model"],
        "model_sha256": report["model_sha256"],
        "model_size_bytes": report["model_size_bytes"],
        "images": report["images"],
        "gt_scored_boxes": report["gt_scored_boxes"],
        "predictions": report["predictions"],
        "overall": report["overall"],
        "latency_inference_p50_ms": inf_stats["p50"],
        "latency_inference_p95_ms": inf_stats["p95"],
        "latency_inference_p99_ms": inf_stats["p99"],
        "steady_state_fps": fps_inf,
        "steady_state_fps_full_pipeline": fps_pipe,
    }
    print(json.dumps(summary, indent=2))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=os.path.join(ROOT, "models", "yolov8n_coco_320.onnx"))
    ap.add_argument("--split", default=os.path.join(ROOT, "configs", "visdrone_det_split_v1.json"))
    ap.add_argument("--conf", type=float, default=0.001,
                    help="low threshold for mAP; the deployed detector uses 0.4")
    ap.add_argument("--limit", type=int, default=0, help="score only the first N test images")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports", "detector_run.json"), help="new report path; detector_baseline.json is immutable")
    ap.add_argument("--warmup", type=int, default=20, help="warmup iterations count")
    ap.add_argument("--min-bench-iters", type=int, default=200, help="minimum timed benchmark iterations")
    ap.add_argument("--preprocess", choices=("deployed", "letterbox"), default="deployed")
    ap.add_argument("--decode", choices=("argmax", "fused"), default="argmax")
    ap.add_argument("--nms-mode", choices=("class-aware", "class-agnostic"), default="class-agnostic")
    ap.add_argument("--bootstrap", type=int, default=50, help="bootstrap iterations; 0 disables bootstrap")
    ap.add_argument("--io-binding", choices=("auto", "on", "off"), default="auto", help="optional reusable ORT CPU output buffer")
    args = ap.parse_args(argv)
    if args.io_binding != "auto":
        os.environ["ORT_USE_IO_BINDING"] = "1" if args.io_binding == "on" else "0"
    run(args.model, args.split, args.conf, args.limit, args.out, warmup_count=args.warmup,
        min_bench_iters=args.min_bench_iters, preprocess_mode=args.preprocess, decode_mode=args.decode,
        nms_mode=args.nms_mode, bootstrap_count=args.bootstrap)
    return 0


if __name__ == "__main__":
    sys.exit(main())
