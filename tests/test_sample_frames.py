import csv
import importlib.util
from pathlib import Path

import cv2
import numpy as np

_SPEC = importlib.util.spec_from_file_location(
    "sample_frames", Path(__file__).resolve().parents[1] / "tools" / "sample_frames.py")
sf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sf)


def _make_clip(path, n_frames=50, fps=10):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (160, 120))
    for i in range(n_frames):
        img = np.zeros((120, 160, 3), np.uint8)
        x = (i * 2) % 140
        cv2.rectangle(img, (x, 40), (x + 20, 70), (255, 255, 255), -1)
        writer.write(img)
    writer.release()


def test_default_gap_is_one_second_and_manifest_is_written(tmp_path):
    video = tmp_path / "clipA.mp4"
    _make_clip(video, n_frames=50, fps=10)
    out = tmp_path / "frames"
    assert sf.main([str(video), "--out", str(out)]) == 0
    with open(out / "manifest.csv") as f:
        rows = list(csv.DictReader(f))
    assert [int(r["source_frame"]) for r in rows] == [0, 10, 20, 30, 40]
    assert [int(r["mot_frame"]) for r in rows] == [1, 11, 21, 31, 41]
    assert all((out / r["image"]).is_file() for r in rows)
    assert all(r["clip"] == "clipA" for r in rows)


def test_gap_and_max_frames_are_respected(tmp_path):
    video = tmp_path / "clipB.mp4"
    _make_clip(video, n_frames=50, fps=10)
    rows = sf.sample_video(str(video), str(tmp_path), gap=5, max_frames=3)
    assert [r["source_frame"] for r in rows] == [0, 5, 10]
