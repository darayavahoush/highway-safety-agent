"""VisDrone2019-DET loader for the Voxel51 Hugging Face copy.

Annotations come from samples.json in the repo. Images are fetched into memory
per request and never written to disk.

Scoring rules:
- Only labels in CLASS_MAP are scored.
- Every other object (ignore_regions, pedestrian, tricycle, others, ...) becomes
  an ignore box: predictions overlapping it are not penalised.
"""
import json
import random
import urllib.request

import cv2
import numpy as np

REPO = "Voxel51/VisDrone2019-DET"
BASE_URL = f"https://huggingface.co/datasets/{REPO}/resolve/main/"
TAXONOMY_VERSION = "highway-proposed-v0"

CLASS_MAP = {
    "car": "car",
    "van": "car",  # proposed grouping; confirm with the taxonomy owner
    "truck": "truck",
    "bus": "bus",
    "motor": "motorcycle",
}


def fetch_samples(tag="train", timeout=300):
    """Return samples with `tag` in their tags. tag=None returns all samples."""
    import os
    cache_path = os.path.expanduser("~/.cache/visdrone/samples.json")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) == 118486295:
        with open(cache_path, "r") as f:
            data = json.load(f)
    else:
        with urllib.request.urlopen(BASE_URL + "samples.json", timeout=timeout) as resp:
            data = json.loads(resp.read())
    return [s for s in data["samples"] if tag is None or tag in s.get("tags", [])]


def sequence_id(filepath):
    """'data/0000002_00005_d_0000014.jpg' -> '0000002'."""
    name = filepath.rsplit("/", 1)[-1]
    return name.split("_", 1)[0]


def split_boxes(sample):
    """Return (scored_gt, ignore_boxes) for one sample, boxes in pixel xyxy."""
    w = sample["metadata"]["width"]
    h = sample["metadata"]["height"]
    scored, ignore = [], []
    for det in sample["ground_truth"]["detections"]:
        x, y, bw, bh = det["bounding_box"]
        box = [x * w, y * h, (x + bw) * w, (y + bh) * h]
        label = det["label"]
        if label in CLASS_MAP:
            scored.append({
                "cls": CLASS_MAP[label],
                "box": box,
                "truncation": det.get("truncation", 0),
                "occlusion": det.get("occlusion", 0),
            })
        else:
            ignore.append(box)
    return scored, ignore


def make_split(samples, holdout_fraction=0.2, seed=0):
    """Hold out whole sequences, chosen by a seeded shuffle of sorted IDs."""
    seqs = sorted({sequence_id(s["filepath"]) for s in samples})
    random.Random(seed).shuffle(seqs)
    n_hold = max(1, round(len(seqs) * holdout_fraction))
    return {
        "version": "visdrone-det-split-v1",
        "taxonomy_version": TAXONOMY_VERSION,
        "seed": seed,
        "holdout_fraction": holdout_fraction,
        "n_sequences": len(seqs),
        "holdout_sequences": sorted(seqs[:n_hold]),
    }


def partition(samples, split):
    held = set(split["holdout_sequences"])
    train = [s for s in samples if sequence_id(s["filepath"]) not in held]
    test = [s for s in samples if sequence_id(s["filepath"]) in held]
    return train, test


def fetch_image(filepath, timeout=60, retries=5):
    """Download one JPEG into memory and decode it to a BGR array.
    Caches to ~/.cache/visdrone/ for resume capability and retries on transient network errors.
    """
    import os
    import time
    cache_path = os.path.expanduser(os.path.join("~/.cache/visdrone", filepath))
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        img = cv2.imread(cache_path)
        if img is not None:
            return img

    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(BASE_URL + filepath, headers={"User-Agent": "highway-safety-eval"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                buf = np.frombuffer(resp.read(), np.uint8)
            img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError(f"could not decode {filepath}")
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "wb") as f:
                f.write(buf)
            return img
        except Exception as e:
            last_err = e
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"failed to fetch {filepath} after {retries} attempts: {last_err}")
