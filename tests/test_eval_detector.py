import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import eval_detector as ev  # noqa: E402


def _sample(fp, dets):
    return {"filepath": fp, "tags": ["train"],
            "metadata": {"width": 100, "height": 100},
            "ground_truth": {"detections": dets}}


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
