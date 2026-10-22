"""
Benchmark script to satisfy User Requirement 5:
Re-measure FPS with EQUAL incident workloads (N forced incidents)
comparing Old Synchronous Evidence Path vs New Asynchronous Decoupled ThreadPool.
Reports Burst FPS, Idle FPS, Mean Latency, and p95 Latency.
"""

import os
import sys
import time
import cv2
import numpy as np

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.evidence_buffer import EvidenceBuffer
from app.detector import create_yolo_detector
from app.tracker import LineCrossingCounter


def run_benchmark(video_path="demo_videos/drone/DJI_0025.MP4", num_forced_incidents=20):
    print("=" * 70)
    print(f"BENCHMARK: EQUAL INCIDENT WORKLOAD (N={num_forced_incidents} Forced Incidents)")
    print("Testing Old Synchronous Encoding vs New Asynchronous ThreadPool Encoding")
    print("=" * 70)

    results = {}

    for mode in ["old_sync", "new_async"]:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 50.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 194)

        evidence_dir = f"/tmp/bench_evidence_{mode}"
        os.makedirs(evidence_dir, exist_ok=True)
        evidence_buffer = EvidenceBuffer(
            max_seconds=5.0,
            fps=fps,
            evidence_dir=evidence_dir,
            cooldown_seconds=0.0,
        )

        detector = create_yolo_detector(model_path="models/yolov8n.onnx")
        tracker = LineCrossingCounter(line=((0, 200), (640, 200)))

        latencies_ms = []
        latencies_burst_ms = []
        latencies_idle_ms = []

        # Determine which frames trigger an incident (evenly spaced)
        incident_frames = set(np.linspace(15, total_frames - 15, num_forced_incidents, dtype=int))
        incidents_fired_count = 0

        t_start_wall = time.perf_counter()
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            current_ts = frame_idx / fps
            h, w = frame.shape[:2]
            scale = 640.0 / float(w)
            frame_resized = cv2.resize(frame, (640, int(h * scale)))

            # Step 1: Push to buffer
            evidence_buffer.push_frame(frame_resized, current_ts)

            t_frame_0 = time.perf_counter()

            # Step 2: Detection
            dets = detector.detect(frame_resized)

            # Step 3: Tracking
            tracks, _ = tracker.update(dets, now=current_ts)

            # Step 4: Forced Incident Trigger
            is_burst = frame_idx in incident_frames
            if is_burst:
                inc_id = f"BENCH-INC-{mode.upper()}-{frame_idx}"
                # Save snapshot
                evidence_buffer.save_snapshot(inc_id, frame_resized, [(100, 100, 50, 30, "Car")])
                # Save clip
                if mode == "old_sync":
                    # Old path: synchronous on perception thread
                    evidence_buffer.save_clip(inc_id, async_write=False)
                else:
                    # New path: asynchronous thread pool
                    evidence_buffer.save_clip(inc_id, async_write=True)
                incidents_fired_count += 1

            t_frame_1 = time.perf_counter()
            frame_ms = (t_frame_1 - t_frame_0) * 1000.0

            latencies_ms.append(frame_ms)
            if is_burst:
                latencies_burst_ms.append(frame_ms)
            else:
                latencies_idle_ms.append(frame_ms)

            frame_idx += 1

        cap.release()
        evidence_buffer.wait_all_pending()
        t_end_wall = time.perf_counter()

        elapsed_s = t_end_wall - t_start_wall
        avg_fps = frame_idx / max(1e-4, elapsed_s)
        idle_fps = 1000.0 / float(np.mean(latencies_idle_ms)) if latencies_idle_ms else avg_fps
        burst_fps = 1000.0 / float(np.mean(latencies_burst_ms)) if latencies_burst_ms else avg_fps
        burst_vs_idle_drop = ((idle_fps - burst_fps) / idle_fps) * 100.0
        p95_lat = float(np.percentile(latencies_ms, 95))
        mean_lat = float(np.mean(latencies_ms))

        results[mode] = {
            "total_frames": frame_idx,
            "incidents_fired": incidents_fired_count,
            "elapsed_s": round(elapsed_s, 2),
            "avg_fps": round(avg_fps, 1),
            "idle_fps": round(idle_fps, 1),
            "burst_fps": round(burst_fps, 1),
            "burst_vs_idle_drop_pct": round(burst_vs_idle_drop, 1),
            "mean_latency_ms": round(mean_lat, 1),
            "p95_latency_ms": round(p95_lat, 1),
            "max_burst_latency_ms": round(float(np.max(latencies_burst_ms)), 1) if latencies_burst_ms else 0.0,
        }

    print("\n" + "=" * 70)
    print("BENCHMARK RESULTS (EQUAL N=20 INCIDENT LOAD):")
    print("=" * 70)
    print(f"{'Metric':<30} | {'Old Synchronous':<18} | {'New Asynchronous':<18}")
    print("-" * 72)
    print(f"{'Forced Incidents':<30} | {results['old_sync']['incidents_fired']:<18} | {results['new_async']['incidents_fired']:<18}")
    print(f"{'Elapsed Wall Time (s)':<30} | {results['old_sync']['elapsed_s']:<18} | {results['new_async']['elapsed_s']:<18}")
    print(f"{'Average Overall FPS':<30} | {results['old_sync']['avg_fps']:<18} | {results['new_async']['avg_fps']:<18}")
    print(f"{'Idle Perception FPS':<30} | {results['old_sync']['idle_fps']:<18} | {results['new_async']['idle_fps']:<18}")
    print(f"{'Burst Perception FPS':<30} | {results['old_sync']['burst_fps']:<18} | {results['new_async']['burst_fps']:<18}")
    print(f"{'Burst vs Idle Drop (%)':<30} | {results['old_sync']['burst_vs_idle_drop_pct']}%{'':<15} | {results['new_async']['burst_vs_idle_drop_pct']}%{'':<15}")
    print(f"{'Mean Frame Latency (ms)':<30} | {results['old_sync']['mean_latency_ms']:<18} | {results['new_async']['mean_latency_ms']:<18}")
    print(f"{'p95 Frame Latency (ms)':<30} | {results['old_sync']['p95_latency_ms']:<18} | {results['new_async']['p95_latency_ms']:<18}")
    print(f"{'Max Burst Frame Stall (ms)':<30} | {results['old_sync']['max_burst_latency_ms']:<18} | {results['new_async']['max_burst_latency_ms']:<18}")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
