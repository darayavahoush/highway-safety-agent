#!/usr/bin/env python3
"""Sample frames from drone clips for labelling.

Keeps a frame only if it is at least `gap` source frames after the last kept
frame (default: one second), which drops near-duplicate consecutive frames.
Writes one JPEG per kept frame and one manifest.csv for the whole run.

Usage:
  python tools/sample_frames.py demo_videos/drone/DJI_0011.MP4 --out labels/frames
"""
import argparse
import csv
import os
import sys

import cv2

MANIFEST_FIELDS = ["clip", "source_frame", "mot_frame", "timestamp_s", "image", "scene"]


def sample_video(video_path, out_dir, gap=None, max_frames=None):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = gap or max(1, round(fps))
    clip = os.path.splitext(os.path.basename(video_path))[0]
    rows, index, last_kept = [], -1, None
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            index += 1
            if last_kept is not None and index - last_kept < step:
                continue
            image = f"{clip}_{index:06d}.jpg"
            if not cv2.imwrite(os.path.join(out_dir, image), frame):
                raise SystemExit(f"failed to write {image}")
            rows.append({
                "clip": clip,
                "source_frame": index,
                "mot_frame": index + 1,
                "timestamp_s": round(index / fps, 3),
                "image": image,
                "scene": "",
            })
            last_kept = index
            if max_frames and len(rows) >= max_frames:
                break
    finally:
        cap.release()
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--out", default="labels/frames")
    ap.add_argument("--gap", type=int, default=None, help="minimum source frames between kept frames")
    ap.add_argument("--max-per-clip", type=int, default=None)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    all_rows = []
    for video in args.videos:
        rows = sample_video(video, args.out, args.gap, args.max_per_clip)
        print(f"{video}: kept {len(rows)} frames")
        all_rows.extend(rows)
    with open(os.path.join(args.out, "manifest.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
