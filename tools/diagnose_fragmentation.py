"""
Diagnostic script for Task 1:
Analyze track fragmentation on DJI_0025.MP4 before making tracker modifications.
Dumps per-frame detections, track associations, and diagnoses 10 specific vehicle trajectories.
"""

import sys
import os
import cv2
import numpy as np
from collections import defaultdict

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.detector import create_yolo_detector
from app.tracker import LineCrossingCounter, calculate_iou_matrix


def run_diagnostics(video_path="demo_videos/drone/DJI_0025.MP4", process_width=640):
    detector = create_yolo_detector(model_path="models/yolov8n.onnx")
    tracker = LineCrossingCounter(
        line=((0, 200), (process_width, 200)),
        min_hits=5,
        max_lost_time_s=1.0,
        conf_high=0.35,
        conf_low=0.15,
        iou_threshold=0.20,
    )

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error opening {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 50.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    print(f"Analyzing {video_path}: {total_frames} frames @ {fps} FPS")

    # Record all detections, tracks, and matches per frame
    frame_records = []
    track_max_hits = defaultdict(int)
    track_first_frame = {}
    track_last_frame = {}
    track_boxes_history = defaultdict(list)

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        current_ts = frame_idx / fps
        h, w = frame.shape[:2]
        scale = process_width / float(w)
        frame_resized = cv2.resize(frame, (process_width, int(h * scale)))

        # Run detector
        raw_dets = detector.detect(frame_resized)
        # raw_dets is list of (box, label, conf) where box is (x, y, w, h)

        # Record active tracks before update
        pre_tracks = {tid: (t.box, t.is_confirmed, t.hits) for tid, t in tracker._tracks.items()}

        # Run tracker update
        active_tracks, events = tracker.update(raw_dets, now=current_ts)

        post_tracks = {t.id: (t.box, t.is_confirmed, t.hits, t.label, t.confidence) for t in active_tracks}
        for t in active_tracks:
            track_max_hits[t.id] = max(track_max_hits[t.id], t.hits)
            if t.id not in track_first_frame:
                track_first_frame[t.id] = frame_idx
            track_last_frame[t.id] = frame_idx
            track_boxes_history[t.id].append((frame_idx, t.box))

        frame_records.append({
            "frame_idx": frame_idx,
            "ts": current_ts,
            "raw_dets": raw_dets,
            "active_tracks": post_tracks,
        })
        frame_idx += 1

    cap.release()

    total_instantiated_ids = len(track_first_frame)
    confirmed_tracks = {tid for tid, hits in track_max_hits.items() if hits >= 5}
    unconfirmed_tracks = {tid for tid, hits in track_max_hits.items() if hits < 5}

    print("\n" + "="*60)
    print("TRACK INSTANTIATION BREAKDOWN:")
    print("="*60)
    print(f"Total Track IDs Instantiated:   {total_instantiated_ids}")
    print(f"Confirmed Tracks (hits >= 5):    {len(confirmed_tracks)} ({len(confirmed_tracks)/total_instantiated_ids*100:.1f}%)")
    print(f"Unconfirmed Tracks (hits < 5):  {len(unconfirmed_tracks)} ({len(unconfirmed_tracks)/total_instantiated_ids*100:.1f}%)")

    hit_dist = defaultdict(int)
    for tid, hits in track_max_hits.items():
        hit_dist[hits] += 1
    print("Hit count distribution:")
    for h in sorted(hit_dist.keys()):
        print(f"  hits={h}: {hit_dist[h]} tracks")

    # Analyze overlapping / duplicate raw detections
    print("\n" + "="*60)
    print("ANALYSIS OF RAW DETECTIONS (NMS / OVERLAP CHECK):")
    print("="*60)
    frames_with_dupe_boxes = 0
    total_dupe_pairs = 0
    for rec in frame_records:
        dets = rec["raw_dets"]
        if len(dets) >= 2:
            boxes = [d[:4] for d in dets]
            iou_mat = calculate_iou_matrix(boxes, boxes)
            dupes = []
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    if iou_mat[i, j] > 0.40:
                        dupes.append((i, j, iou_mat[i, j], dets[i][1], dets[j][1]))
            if dupes:
                frames_with_dupe_boxes += 1
                total_dupe_pairs += len(dupes)

    print(f"Frames with overlapping detection boxes (IoU > 0.40): {frames_with_dupe_boxes} / {len(frame_records)}")
    print(f"Total overlapping detection pairs: {total_dupe_pairs}")

    # Inspect 10 sample confirmed tracks across the video
    print("\n" + "="*60)
    print("INSPECTING 10 REPRESENTATIVE VEHICLE TRAJECTORIES:")
    print("="*60)
    sample_tracks = sorted(list(confirmed_tracks))[:10]
    for tid in sample_tracks:
        start_f = track_first_frame[tid]
        end_f = track_last_frame[tid]
        duration_s = (end_f - start_f + 1) / fps
        total_hits = track_max_hits[tid]
        boxes = track_boxes_history[tid]
        first_box = boxes[0][1]
        last_box = boxes[-1][1]
        print(f"\n--- Vehicle Track #{tid} ---")
        print(f"  Span: frames {start_f} -> {end_f} ({duration_s:.2f}s, {total_hits} hits)")
        print(f"  Trajectory: (x={first_box[0]:.1f}, y={first_box[1]:.1f}) -> (x={last_box[0]:.1f}, y={last_box[1]:.1f})")

        # Check why it ended or if another track started nearby right after
        nearby_new_tracks = []
        for other_id in sorted(list(track_first_frame.keys())):
            if other_id == tid:
                continue
            other_start = track_first_frame[other_id]
            # If other track started within 15 frames of this track ending
            if 0 <= (other_start - end_f) <= 15:
                other_first_box = track_boxes_history[other_id][0][1]
                # Check spatial distance
                dist = np.hypot(other_first_box[0] - last_box[0], other_first_box[1] - last_box[1])
                if dist < 80:  # within 80 pixels
                    nearby_new_tracks.append((other_id, other_start, other_start - end_f, dist, track_max_hits[other_id]))

        if nearby_new_tracks:
            for n_tid, n_start, gap, dist, n_hits in nearby_new_tracks:
                print(f"  [POTENTIAL FRAGMENTATION] Track #{n_tid} spawned {gap} frames later at distance {dist:.1f}px (hits={n_hits})")
        else:
            if end_f >= total_frames - 5:
                print(f"  [NORMAL EXIT] Track reached end of video clip.")
            else:
                print(f"  [DISAPPEARED] Track ended at frame {end_f} with no nearby successor.")


if __name__ == "__main__":
    run_diagnostics()
