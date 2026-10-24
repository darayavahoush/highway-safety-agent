import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import visdrone_loader as vl  # noqa: E402


def _sample(fp, dets, w=960, h=540):
    return {"filepath": fp, "tags": ["train"],
            "metadata": {"width": w, "height": h},
            "ground_truth": {"detections": dets}}


def _det(label, box):
    return {"label": label, "bounding_box": box, "truncation": 0, "occlusion": 1}


def test_sequence_id_is_first_field():
    assert vl.sequence_id("data/0000002_00005_d_0000014.jpg") == "0000002"


def test_boxes_are_scaled_to_pixels_and_unmapped_labels_become_ignore():
    s = _sample("data/0000002_00005_d_0000014.jpg", [
        _det("car", [0.5, 0.5, 0.1, 0.2]),
        _det("motor", [0.0, 0.0, 0.05, 0.1]),
        _det("pedestrian", [0.25, 0.25, 0.02, 0.04]),
        _det("ignore_regions", [0.7, 0.0, 0.2, 0.2]),
    ])
    scored, ignore = vl.split_boxes(s)
    assert [d["cls"] for d in scored] == ["car", "motorcycle"]
    assert scored[0]["box"] == pytest.approx([480.0, 270.0, 576.0, 378.0])
    assert len(ignore) == 2


def test_split_is_by_sequence_and_deterministic():
    samples = [_sample(f"data/{seq:07d}_00001_d_0000001.jpg", [])
               for seq in range(20) for _ in range(3)]
    a = vl.make_split(samples, holdout_fraction=0.25, seed=7)
    b = vl.make_split(samples, holdout_fraction=0.25, seed=7)
    assert a == b
    assert len(a["holdout_sequences"]) == 5
    train, test = vl.partition(samples, a)
    assert len(train) + len(test) == len(samples)
    train_seqs = {vl.sequence_id(s["filepath"]) for s in train}
    test_seqs = {vl.sequence_id(s["filepath"]) for s in test}
    assert train_seqs.isdisjoint(test_seqs)
