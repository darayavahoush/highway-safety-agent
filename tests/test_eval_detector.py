import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
import eval_detector as ev  # noqa: E402


def _sample(fp, dets):
    return {
        "filepath": fp,
        "tags": ["train"],
        "metadata": {"width": 100, "height": 100},
        "ground_truth": {"detections": dets},
    }


def test_scored_box_is_normal_and_ignore_box_is_crowd_in_every_category():
    s = _sample("data/0000002_00005_d_0000014.jpg", [
        {"label": "car", "bounding_box": [0.1, 0.1, 0.2, 0.2], "truncation": 0, "occlusion": 0},
        {"label": "pedestrian", "bounding_box": [0.5, 0.5, 0.1, 0.1], "truncation": 0, "occlusion": 0},
    ])
    anns = ev.build_coco_gt([s])["annotations"]
    normal = [a for a in anns if a["iscrowd"] == 0]
    crowd = [a for a in anns if a["iscrowd"] == 1]
    assert len(normal) == 1
    assert normal[0]["category_id"] == ev.CAT_ID["car"]
    assert normal[0]["bbox"] == pytest.approx([10.0, 10.0, 20.0, 20.0])
    assert sorted(a["category_id"] for a in crowd) == sorted(ev.CAT_ID.values())


def test_detections_map_to_categories_and_unknown_labels_are_dropped():
    dets = [(1, 2, 3, 4, "Car", 0.9), (5, 6, 7, 8, "Van", 0.8), (0, 0, 1, 1, "Bus", 0.5)]
    out = ev.detections_to_coco(7, dets)
    assert [o["category_id"] for o in out] == [ev.CAT_ID["car"], ev.CAT_ID["bus"]]
    assert all(o["image_id"] == 7 for o in out)


def test_missing_model_file_raises_filenotfounderror(tmp_path):
    split_file = tmp_path / "split.json"
    split_file.write_text('{"version": "v1", "holdout_sequences": []}')
    missing_model = tmp_path / "missing_model.onnx"
    with pytest.raises(FileNotFoundError, match="Model file not found"):
        ev.run(str(missing_model), str(split_file))


def test_invalid_split_path_raises_filenotfounderror(tmp_path):
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"dummy onnx content")
    missing_split = tmp_path / "missing_split.json"
    with pytest.raises(FileNotFoundError, match="Dataset split file not found"):
        ev.run(str(model_file), str(missing_split))


def test_empty_detections_reports_zero_ap_without_crashing(tmp_path):
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"fake model")
    split_file = tmp_path / "split.json"
    split_file.write_text('{"version": "v1", "holdout_sequences": ["0000001"]}')
    out_file = tmp_path / "out.json"

    dummy_sample = _sample("data/0000001_00001_d_0000001.jpg", [
        {"label": "car", "bounding_box": [0.1, 0.1, 0.2, 0.2]}
    ])

    fake_det = MagicMock()
    fake_det.input_size = 320
    fake_det.conf_threshold = 0.5
    fake_det.nms_threshold = 0.45
    fake_det.input_name = "images"
    fake_det.session.run.return_value = [np.zeros((1, 84, 2100), dtype=np.float32)]

    with patch("tools.visdrone_loader.fetch_samples", return_value=[dummy_sample]), \
         patch("tools.visdrone_loader.fetch_image", return_value=np.zeros((100, 100, 3), dtype=np.uint8)), \
         patch("app.detector.OrtYoloDetector", return_value=fake_det), \
         patch("app.detector._postprocess_yolo_output", return_value=[]):
        report = ev.run(str(model_file), str(split_file), conf=0.5, limit=1, out_path=str(out_file), min_bench_iters=5)

    assert report["overall"]["AP50_95"] == 0.0
    assert report["overall"]["AP50"] == 0.0
    assert report["status"] == "no detections"
    assert report["per_class"]["car"]["AP50_95"] == 0.0


def test_report_schema_and_latency_metadata_populated(tmp_path):
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"dummy onnx bytes for hashing")
    split_file = tmp_path / "split.json"
    split_file.write_text('{"version": "visdrone-v1", "holdout_sequences": ["0000001"]}')
    out_file = tmp_path / "out.json"

    dummy_sample = _sample("data/0000001_00001_d_0000001.jpg", [
        {"label": "car", "bounding_box": [0.1, 0.1, 0.2, 0.2]}
    ])

    fake_det = MagicMock()
    fake_det.input_size = 320
    fake_det.conf_threshold = 0.001
    fake_det.nms_threshold = 0.45
    fake_det.input_name = "images"
    fake_det.session.run.return_value = [np.zeros((1, 84, 2100), dtype=np.float32)]

    with patch("tools.visdrone_loader.fetch_samples", return_value=[dummy_sample]), \
         patch("tools.visdrone_loader.fetch_image", return_value=np.zeros((100, 100, 3), dtype=np.uint8)), \
         patch("app.detector.OrtYoloDetector", return_value=fake_det), \
         patch("app.detector._postprocess_yolo_output", return_value=[(10, 10, 20, 20, "Car", 0.9)]):
        report = ev.run(str(model_file), str(split_file), conf=0.001, limit=1, out_path=str(out_file), min_bench_iters=5)

    # Required top-level keys
    required_keys = [
        "model", "model_size_bytes", "model_sha256", "split", "split_version",
        "taxonomy_version", "conf_threshold", "nms_threshold", "input_resolution",
        "images", "gt_scored_boxes", "gt_boxes_per_class", "predictions",
        "system_metadata", "latency_benchmark", "warmup_iterations",
        "measured_iterations", "steady_state_fps", "steady_state_fps_full_pipeline",
        "inference_latency_ms", "full_pipeline_latency_ms", "overall", "per_class",
    ]
    for key in required_keys:
        assert key in report, f"Missing required report key: {key}"

    # Required system metadata
    meta = report["system_metadata"]
    for mkey in ["cpu_model", "ram_total_gb", "os", "python_version", "onnxruntime_version", "thread_count"]:
        assert mkey in meta, f"Missing system metadata key: {mkey}"

    # Latency percentiles
    inf_lat = report["latency_benchmark"]["inference_latency_ms"]
    for pkey in ["p50", "p95", "p99", "mean"]:
        assert pkey in inf_lat
        assert isinstance(inf_lat[pkey], (int, float))

    assert report["latency_benchmark"]["steady_state_fps_inference_only"] > 0
    assert report["latency_benchmark"]["steady_state_fps_full_pipeline"] > 0
