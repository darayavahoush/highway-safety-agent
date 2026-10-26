"""Preprocessing/decoding variants and robust latency summaries for detector evaluation.

This module intentionally does not change the default production detector. The
`deployed` + `argmax` path in eval_detector.py must continue to call the legacy
postprocessor to preserve its historical behaviour.
"""
from __future__ import annotations

import math
import time
from typing import Any

import cv2
import numpy as np

COCO_VEHICLE_CLASSES = {2: "Car", 3: "Motorbike", 5: "Bus", 7: "Truck"}
PREPROCESS_MODES = ("deployed", "letterbox")
DECODE_MODES = ("argmax", "fused")
NMS_MODES = ("class-aware", "class-agnostic")


def _validate_frame(frame: np.ndarray) -> None:
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must be a HxWx3 NumPy BGR image")
    if frame.shape[0] <= 0 or frame.shape[1] <= 0:
        raise ValueError("frame dimensions must be positive")


def preprocess_frame(frame: np.ndarray, input_size: int, mode: str = "deployed"):
    """Return (NCHW float32 RGB blob, transform metadata, preprocess_ms).

    `deployed` exactly reproduces the current stretch-to-square preprocessing.
    `letterbox` preserves aspect ratio and pads with 114, as common YOLO exports do.
    Transform metadata is used to map predictions back to original image coordinates.
    """
    _validate_frame(frame)
    if input_size <= 0:
        raise ValueError("input_size must be positive")
    if mode not in PREPROCESS_MODES:
        raise ValueError(f"unsupported preprocess mode: {mode}")

    started = time.perf_counter()
    height, width = frame.shape[:2]
    if mode == "deployed":
        resized = cv2.resize(frame, (input_size, input_size))
        transform = {
            "mode": "deployed",
            "original_width": width,
            "original_height": height,
            "scale_x": input_size / width,
            "scale_y": input_size / height,
            "pad_x": 0,
            "pad_y": 0,
            "input_size": input_size,
        }
    else:
        scale = min(input_size / width, input_size / height)
        resized_width = max(1, int(round(width * scale)))
        resized_height = max(1, int(round(height * scale)))
        resized = cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
        pad_x = (input_size - resized_width) // 2
        pad_y = (input_size - resized_height) // 2
        canvas = np.full((input_size, input_size, 3), 114, dtype=frame.dtype)
        canvas[pad_y:pad_y + resized_height, pad_x:pad_x + resized_width] = resized
        resized = canvas
        transform = {
            "mode": "letterbox",
            "original_width": width,
            "original_height": height,
            "scale": scale,
            "pad_x": pad_x,
            "pad_y": pad_y,
            "resized_width": resized_width,
            "resized_height": resized_height,
            "input_size": input_size,
        }
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    blob = np.transpose(rgb, (2, 0, 1))[np.newaxis, ...]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return blob, transform, elapsed_ms


def _box_to_original(cx, cy, bw, bh, transform):
    """Convert model-input xywh-centre boxes to original-image xywh.

    For stretch mode, retain the production path's int truncation and width/height
    scaling so the decoder experiment doesn't accidentally change coordinate math.
    Letterbox mode inverts padding and the resize ratio, then clips to the image.
    """
    if transform["mode"] == "deployed":
        sx = float(transform["original_width"]) / transform["input_size"]
        sy = float(transform["original_height"]) / transform["input_size"]
        return [
            int((float(cx) - float(bw) / 2) * sx),
            int((float(cy) - float(bh) / 2) * sy),
            int(float(bw) * sx),
            int(float(bh) * sy),
        ]

    scale = float(transform["scale"])
    x1 = (float(cx) - float(bw) / 2 - transform["pad_x"]) / scale
    y1 = (float(cy) - float(bh) / 2 - transform["pad_y"]) / scale
    x2 = (float(cx) + float(bw) / 2 - transform["pad_x"]) / scale
    y2 = (float(cy) + float(bh) / 2 - transform["pad_y"]) / scale
    width = int(transform["original_width"])
    height = int(transform["original_height"])
    x1 = max(0.0, min(float(width), x1))
    y1 = max(0.0, min(float(height), y1))
    x2 = max(0.0, min(float(width), x2))
    y2 = max(0.0, min(float(height), y2))
    ix1, iy1, ix2, iy2 = int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))
    return [ix1, iy1, max(0, ix2 - ix1), max(0, iy2 - iy1)]


def decode_yolo_output(
    output: np.ndarray,
    transform: dict[str, Any],
    conf_threshold: float,
    nms_threshold: float,
    mode: str = "argmax",
    nms_mode: str = "class-agnostic",
):
    """Decode YOLOv8-style [1, 4+C, N] output into detector tuples.

    `argmax` is the classic single-class-per-candidate decoder. `fused` independently
    thresholds only the four configured COCO vehicle classes, so a high non-vehicle
    class score cannot discard a vehicle hypothesis. The comparison CLI uses class-agnostic NMS to match the legacy global NMS policy:
    class-agnostic NMS may suppress a motorcycle because its box overlaps a car box.
    A class-agnostic ablation remains available explicitly.
    """
    if mode not in DECODE_MODES:
        raise ValueError(f"unsupported decode mode: {mode}")
    if nms_mode not in NMS_MODES:
        raise ValueError(f"unsupported NMS mode: {nms_mode}")
    arr = np.asarray(output)
    if arr.ndim != 3 or arr.shape[0] != 1 or arr.shape[1] < 12:
        raise ValueError(
            f"expected COCO-style YOLO output [1,4+C,N] with class IDs through 7, got {arr.shape}"
        )
    preds = arr[0].T
    candidates = []

    if mode == "argmax" and transform["mode"] == "deployed":
        # Exact copy of the legacy COCO decoder: argmax over all 80 classes,
        # int truncation, no clipping, then the same OpenCV NMS call. Keep this
        # branch as a direct regression oracle for the currently deployed path.
        x_scale = transform["original_width"] / transform["input_size"]
        y_scale = transform["original_height"] / transform["input_size"]
        boxes, confidences, class_ids = [], [], []
        for row in preds:
            scores = row[4:]
            class_id = int(np.argmax(scores))
            confidence = float(scores[class_id])
            if confidence < conf_threshold or class_id not in COCO_VEHICLE_CLASSES:
                continue
            cx, cy, bw, bh = row[:4]
            box = [int((cx - bw / 2) * x_scale), int((cy - bh / 2) * y_scale),
                   int(bw * x_scale), int(bh * y_scale)]
            boxes.append(box)
            confidences.append(confidence)
            class_ids.append(class_id)
        results = []
        if boxes:
            indices = cv2.dnn.NMSBoxes(boxes, confidences, conf_threshold, nms_threshold)
            for i in np.asarray(indices).flatten():
                x, y, bw, bh = boxes[i]
                results.append((x, y, bw, bh, COCO_VEHICLE_CLASSES[class_ids[i]], confidences[i]))
        return results

    if mode == "argmax":
        for row in preds:
            scores = row[4:]
            class_id = int(np.argmax(scores))
            confidence = float(scores[class_id])
            if confidence < conf_threshold or class_id not in COCO_VEHICLE_CLASSES:
                continue
            box = _box_to_original(*row[:4], transform)
            if box[2] > 0 and box[3] > 0:
                candidates.append((box, confidence, class_id, COCO_VEHICLE_CLASSES[class_id]))
    else:
        for row in preds:
            # Only decode the four target vehicle classes. Non-vehicle logits cannot
            # suppress their hypotheses. Multiple labels are permitted per candidate.
            for class_id, label in COCO_VEHICLE_CLASSES.items():
                confidence = float(row[4 + class_id])
                if confidence < conf_threshold:
                    continue
                box = _box_to_original(*row[:4], transform)
                if box[2] > 0 and box[3] > 0:
                    candidates.append((box, confidence, class_id, label))

    if not candidates:
        return []

    keep_global = []
    if nms_mode == "class-agnostic":
        boxes = [c[0] for c in candidates]
        scores = [c[1] for c in candidates]
        indices = cv2.dnn.NMSBoxes(boxes, scores, conf_threshold, nms_threshold)
        keep_global = np.asarray(indices, dtype=int).reshape(-1).tolist() if len(indices) else []
    else:
        # Class-wise NMS avoids suppressing an overlapping but distinct vehicle class.
        for class_id in COCO_VEHICLE_CLASSES:
            candidate_indices = [i for i, c in enumerate(candidates) if c[2] == class_id]
            if not candidate_indices:
                continue
            boxes = [candidates[i][0] for i in candidate_indices]
            scores = [candidates[i][1] for i in candidate_indices]
            indices = cv2.dnn.NMSBoxes(boxes, scores, conf_threshold, nms_threshold)
            kept_local = np.asarray(indices, dtype=int).reshape(-1).tolist() if len(indices) else []
            keep_global.extend(candidate_indices[j] for j in kept_local)

    keep_global = sorted(set(keep_global), key=lambda i: candidates[i][1], reverse=True)
    return [(*candidates[i][0], candidates[i][3], float(candidates[i][1])) for i in keep_global]


def latency_summary(samples_ms):
    """Robust latency distribution including extreme-tail diagnostics."""
    values = np.asarray(list(samples_ms), dtype=np.float64)
    if values.size == 0:
        return {
            "count": 0, "p50": None, "p90": None, "p95": None, "p99": None,
            "p99_9": None, "max": None, "mean": None, "count_over_3x_p50": 0,
            "tail_ratio_p99_over_p50": None,
        }
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError("latency samples must be finite non-negative milliseconds")
    p50 = float(np.percentile(values, 50))
    p99 = float(np.percentile(values, 99))
    return {
        "count": int(values.size),
        "p50": round(p50, 3),
        "p90": round(float(np.percentile(values, 90)), 3),
        "p95": round(float(np.percentile(values, 95)), 3),
        "p99": round(p99, 3),
        "p99_9": round(float(np.percentile(values, 99.9)), 3),
        "max": round(float(np.max(values)), 3),
        "mean": round(float(np.mean(values)), 3),
        "count_over_3x_p50": int(np.count_nonzero(values > 3 * p50)) if p50 > 0 else int(np.count_nonzero(values > 0)),
        "tail_ratio_p99_over_p50": round(p99 / p50, 3) if p50 > 0 else None,
    }


def factorial_attribution(metrics_by_config):
    """Two-factor Shapley-style attribution for a 2x2 preprocess/decode experiment.

    Keys: deployed_argmax, deployed_fused, letterbox_argmax, letterbox_fused.
    Metrics are COCO AP values in [0,1]. The two average marginal effects sum to
    the diagonal total delta; an interaction diagnostic is reported separately.
    Domain gap cannot be inferred because all runs use the same dataset.
    """
    required = ("deployed_argmax", "deployed_fused", "letterbox_argmax", "letterbox_fused")
    for key in required:
        if key not in metrics_by_config or not isinstance(metrics_by_config[key], dict):
            raise ValueError(f"missing metrics for configuration {key}")
    metric_names = sorted(set.intersection(*(set(metrics_by_config[k]) for k in required)))
    result = {}
    for metric in metric_names:
        vals = {k: float(metrics_by_config[k][metric]) for k in required}
        if not all(math.isfinite(v) for v in vals.values()):
            raise ValueError(f"non-finite metric {metric}")
        a, b = vals["deployed_argmax"], vals["deployed_fused"]
        c, d = vals["letterbox_argmax"], vals["letterbox_fused"]
        total = d - a
        preprocess_effect = ((c - a) + (d - b)) / 2
        decode_effect = ((b - a) + (d - c)) / 2
        interaction = (d - c) - (b - a)
        result[metric] = {
            "deployed_argmax": a,
            "deployed_fused": b,
            "letterbox_argmax": c,
            "letterbox_fused": d,
            "total_delta": total,
            "preprocessing_average_marginal_effect": preprocess_effect,
            "decoding_average_marginal_effect": decode_effect,
            "interaction_diagnostic": interaction,
            "decomposition_sum_check": preprocess_effect + decode_effect,
            "domain_gap": None,
            "domain_gap_status": "NOT_ESTIMATED",
        }
    return result
