"""
Video Replay Benchmark Harness for Highway Safety & Accident Prevention Autonomous Agent.
Strictly executes the full edge perception pipeline headlessly:
- Frame ingestion & scaling
- EvidenceBuffer ring caching & deduplication
- YOLOv8 ONNX object detection (or fallback)
- Centroid multi-object tracking (LineCrossingCounter)
- 3D bounding & projection
- EdgeTriggerEngine rule evaluation (Stalled, Wrong-way, Tailgating TTC)

Outputs results.json, evidence assets (snapshots & clips), index.html contact sheet, and labels.csv.
"""

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import time
from typing import Dict, List, Optional

import cv2
import numpy as np

# Ensure project root is in python path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.incident_schema import IncidentCandidate, IncidentType
from app.incident_rules import EdgeTriggerEngine
from app.evidence_buffer import EvidenceBuffer
from app.detector import create_yolo_detector, BackgroundSubtractionDetector
from app.tracker import LineCrossingCounter
from app.dimensions_3d import draw_3d_bounding_box


def get_cpu_model() -> str:
    """Reads CPU brand/model name from macOS sysctl or Linux /proc/cpuinfo."""
    if platform.system() == "Darwin":
        try:
            brand = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], stderr=subprocess.DEVNULL)
            return brand.decode().strip()
        except Exception:
            pass
    elif os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
    return platform.processor() or "Unknown CPU"


def parse_args():
    parser = argparse.ArgumentParser(description="Headless video replay harness for highway safety rules.")
    parser.add_argument("--video", required=True, help="Path to video file (MP4/MKV/AVI).")
    parser.add_argument("--camera-config", default="config/camera_config.json", help="Path to camera_config.json.")
    parser.add_argument("--rules", default="config/safety_rules.json", help="Path to safety_rules.json.")
    parser.add_argument("--max-seconds", type=float, default=None, help="Max video seconds to process.")
    parser.add_argument("--out", default=None, help="Output directory (default: replay_output/<clip_name>).")
    parser.add_argument("--process-width", type=int, default=640, help="Frame width to scale to.")
    parser.add_argument("--model-path", default="models/yolov8n.onnx", help="Path to YOLO ONNX model.")
    parser.add_argument("--process-hz", type=float, default=None, help="Process rate limit in Hz (default: process all frames).")
    parser.add_argument("--stationary-s", type=float, default=None, help="Override min stationary seconds for stalled vehicle rule.")
    parser.add_argument("--ttc-s", type=float, default=None, help="Override critical TTC seconds for tailgating rule.")
    parser.add_argument("--cooldown-s", type=float, default=None, help="Override deduplication cooldown seconds.")
    parser.add_argument("--expected-vehicles", type=int, default=None, help="Ground-truth distinct vehicle count for fragmentation ratio calculation.")
    parser.add_argument("--save-report", default=None, help="Optional path to append/save run result summary JSON.")
    return parser.parse_args()


def generate_contact_sheet(
    html_path: str,
    clip_name: str,
    cpu_model: str,
    timing: dict,
    incidents: list,
    thresholds: dict,
):
    """Generates a clean HTML contact sheet showcasing incident evidence & telemetry."""
    rows_html = ""
    if not incidents:
        rows_html = """
        <tr>
            <td colspan="7" style="text-align: center; padding: 32px; color: #8899a6;">
                No incidents triggered on this clip with current thresholds.
            </td>
        </tr>
        """
    else:
        for inc in incidents:
            snap_rel = os.path.relpath(inc.get("snapshot_file", ""), os.path.dirname(html_path)) if inc.get("snapshot_file") else ""
            clip_rel = os.path.relpath(inc.get("clip_file", ""), os.path.dirname(html_path)) if inc.get("clip_file") else ""
            
            thumb_cell = f'<a href="{snap_rel}" target="_blank"><img src="{snap_rel}" style="width: 160px; height: auto; border-radius: 4px; border: 1px solid #334455;" /></a>' if snap_rel else "No Snapshot"
            clip_cell = f'<a href="{clip_rel}" target="_blank" style="color: #38bdf8;">View MP4 Clip</a>' if clip_rel else "No Clip"
            
            sev_badge = '<span style="background: #ef4444; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">P0</span>' if inc.get("severity") == "P0" else '<span style="background: #f59e0b; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">P1</span>'
            
            rows_html += f"""
            <tr style="border-bottom: 1px solid #223344;">
                <td style="padding: 10px; font-family: monospace; font-size: 12px;">{inc['id']}</td>
                <td style="padding: 10px;">{sev_badge} <b style="color: #f0f4f8;">{inc['type']}</b></td>
                <td style="padding: 10px; font-variant-numeric: tabular-nums;">{inc['timestamp_s']:.2f}s</td>
                <td style="padding: 10px;">Track #{inc['track_id']}</td>
                <td style="padding: 10px; font-size: 12px; color: #cbd5e1; max-width: 320px;">{inc.get('rule_reason', '')}</td>
                <td style="padding: 10px;">{thumb_cell}</td>
                <td style="padding: 10px;">{clip_cell}</td>
            </tr>
            """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Replay Evidence Contact Sheet: {clip_name}</title>
    <style>
        body {{
            background: #0c121b;
            color: #e2e8f0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 24px;
        }}
        .header {{
            background: #16202e;
            padding: 20px 24px;
            border-radius: 8px;
            border: 1px solid #243447;
            margin-bottom: 24px;
        }}
        h1 {{ margin: 0 0 12px 0; font-size: 22px; color: #38bdf8; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 16px;
            margin-top: 14px;
        }}
        .stat-card {{
            background: #090e15;
            padding: 12px 14px;
            border-radius: 6px;
            border: 1px solid #1a2736;
        }}
        .stat-val {{ font-size: 20px; font-weight: bold; color: #10b981; font-family: monospace; }}
        .stat-lbl {{ font-size: 12px; color: #94a3b8; margin-top: 2px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: #16202e;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #243447;
        }}
        th {{
            background: #1a2736;
            color: #94a3b8;
            text-align: left;
            padding: 12px 10px;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Safety Agent Incident Contact Sheet & Evidence Replay</h1>
        <div><b>Clip:</b> <code>{clip_name}</code> &nbsp;|&nbsp; <b>CPU:</b> {cpu_model}</div>
        <div style="font-size: 12px; color: #94a3b8; margin-top: 6px;">
            <b>Thresholds:</b> Stationary: {thresholds['stationary_s']}s &nbsp;|&nbsp; TTC: {thresholds['ttc_s']}s &nbsp;|&nbsp; Cooldown: {thresholds['cooldown_s']}s
        </div>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-val">{timing['total_frames']}</div>
                <div class="stat-lbl">Processed Frames</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{timing['avg_fps']:.1f}</div>
                <div class="stat-lbl">Average FPS</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{timing['p95_latency_ms']:.1f} ms</div>
                <div class="stat-lbl">p95 Frame Latency</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{timing['video_duration_s']:.2f} s</div>
                <div class="stat-lbl">Clip Duration</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{len(incidents)}</div>
                <div class="stat-lbl">Incidents Fired</div>
            </div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Incident ID</th>
                <th>Type & Severity</th>
                <th>Video Time</th>
                <th>Track</th>
                <th>Rule Reasoning</th>
                <th>Evidence Snapshot</th>
                <th>Evidence Clip</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)


def replay_video():
    args = parse_args()

    if not os.path.isfile(args.video):
        print(f"ERROR: Video file not found at: {args.video}", file=sys.stderr)
        sys.exit(1)

    clip_basename = os.path.basename(args.video)
    clip_name = os.path.splitext(clip_basename)[0]

    out_dir = args.out or os.path.join(ROOT_DIR, "replay_output", clip_name)
    evidence_dir = os.path.join(out_dir, "evidence")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(evidence_dir, exist_ok=True)

    # 1. Initialize Pipeline Components
    print(f"\n=======================================================")
    print(f"STARTING HEADLESS REPLAY PIPELINE: {clip_basename}")
    print(f"=======================================================")

    camera_cfg_path = os.path.abspath(args.camera_config)
    rules_cfg_path = os.path.abspath(args.rules)

    trigger_engine = EdgeTriggerEngine(camera_cfg_path, rules_cfg_path)

    # Apply threshold overrides if provided
    rules_cfg = trigger_engine.rules_cfg
    stalled_cfg = rules_cfg.setdefault("stalled_vehicle", {})
    ttc_cfg = rules_cfg.setdefault("tailgating_ttc", {})
    op_cfg = rules_cfg.setdefault("operational", {})

    if args.stationary_s is not None:
        stalled_cfg["min_stationary_seconds"] = args.stationary_s
    if args.ttc_s is not None:
        ttc_cfg["critical_ttc_seconds"] = args.ttc_s
    if args.cooldown_s is not None:
        op_cfg["dedupe_cooldown_seconds"] = args.cooldown_s

    cooldown_s = float(op_cfg.get("dedupe_cooldown_seconds", 25.0))
    stationary_s = float(stalled_cfg.get("min_stationary_seconds", 3.0))
    ttc_s = float(ttc_cfg.get("critical_ttc_seconds", 1.2))

    print(f"Active Thresholds: stationary={stationary_s}s, ttc={ttc_s}s, cooldown={cooldown_s}s")

    # Detector & Tracker
    if os.path.isfile(args.model_path):
        print(f"Loading YOLOv8 ONNX Detector from {args.model_path}...")
        detector = create_yolo_detector(args.model_path, input_size=320, conf_threshold=0.30)
    else:
        print("WARNING: Model file not found. Falling back to BackgroundSubtractionDetector.")
        detector = BackgroundSubtractionDetector()

    tracker_cfg = rules_cfg.get("tracker", {})
    tracker = LineCrossingCounter(
        line=((0, 200), (args.process_width, 200)),
        min_hits=int(tracker_cfg.get("min_hits", 5)),
        max_lost_time_s=float(tracker_cfg.get("max_lost_time_s", 1.0)),
        conf_high=float(tracker_cfg.get("conf_threshold_high", 0.35)),
        conf_low=float(tracker_cfg.get("conf_threshold_low", 0.15)),
        iou_threshold=float(tracker_cfg.get("iou_threshold", 0.20)),
    )

    # Open Video
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: Could not open video capture for {args.video}", file=sys.stderr)
        sys.exit(1)

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    video_dur_s = total_video_frames / native_fps if native_fps > 0 else 0.0

    print(f"Video Info: {total_video_frames} frames @ {native_fps:.1f} FPS (~{video_dur_s:.2f}s)")

    evidence_buffer = EvidenceBuffer(
        max_seconds=10.0,
        fps=native_fps,
        evidence_dir=evidence_dir,
        cooldown_seconds=cooldown_s,
    )

    cpu_model = get_cpu_model()
    print(f"Host CPU Model: {cpu_model}")

    # Process Hz rate limiter
    min_frame_interval_s = (1.0 / float(args.process_hz)) if args.process_hz and args.process_hz > 0 else 0.0
    last_processed_ts: Optional[float] = None

    # Collect tracker health metrics
    track_first_seen: Dict[int, float] = {}
    track_last_seen: Dict[int, float] = {}
    all_speed_samples: List[float] = []

    # Replay Loop
    latencies_ms: List[float] = []
    latencies_burst_ms: List[float] = []
    latencies_idle_ms: List[float] = []
    fired_incidents: List[dict] = []
    frame_idx = 0
    t_start_wall = time.perf_counter()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        current_video_ts = frame_idx / native_fps
        if args.max_seconds is not None and current_video_ts > args.max_seconds:
            break

        # Step 1: Resize to process width
        h, w = frame.shape[:2]
        scale = args.process_width / float(w)
        frame_resized = cv2.resize(frame, (args.process_width, int(h * scale)))
        rh, rw = frame_resized.shape[:2]

        # Step 2: Push to evidence ring buffer (simulation timestamp)
        evidence_buffer.push_frame(frame_resized, current_video_ts)

        # Check process-hz skip
        if min_frame_interval_s > 0 and last_processed_ts is not None:
            if (current_video_ts - last_processed_ts) < (min_frame_interval_s - 1e-4):
                frame_idx += 1
                continue

        last_processed_ts = current_video_ts
        t_frame_0 = time.perf_counter()

        # Step 3: Detection
        detections = detector.detect(frame_resized)

        # Step 4: Tracking (passing current_video_ts)
        tracks, _ = tracker.update(detections, now=current_video_ts)

        # Track appearances & lifetimes (confirmed tracks)
        for t in tracks:
            tid = t.id
            if tid not in track_first_seen:
                track_first_seen[tid] = current_video_ts
            track_last_seen[tid] = current_video_ts

        # Step 5: Update Track History in Rule Engine (including is_confirmed flag)
        track_inputs = [
            (float(t.box[0]), float(t.box[1]), float(t.box[2]), float(t.box[3]), t.label, t.id, t.is_confirmed)
            for t in tracks
        ]
        trigger_engine.update_tracks(track_inputs, now=current_video_ts)

        # Collect speed samples from active tracks
        for t in tracks:
            th = trigger_engine.tracks.get(t.id)
            if th is not None and len(th.history) >= 2:
                all_speed_samples.append(float(th.current_speed_kmh))

        # Step 6: Rule Evaluation
        candidates = trigger_engine.evaluate_rules(rw, rh, now=current_video_ts)

        # Step 7: Deduplication & Evidence Capture (Asynchronous encoding)
        for cand in candidates:
            inc_type_str = cand.incident_type.value if hasattr(cand.incident_type, "value") else str(cand.incident_type)
            is_suppressed = evidence_buffer.should_suppress_dedupe(
                cand.camera_id, inc_type_str, cand.primary_track_id, now=current_video_ts
            )
            if not is_suppressed:
                # Save snapshot & clip asynchronously
                involved_boxes = [
                    (int(v.box[0]), int(v.box[1]), int(v.box[2]), int(v.box[3]), v.label)
                    for v in cand.involved_vehicles
                ]
                snap_path = evidence_buffer.save_snapshot(cand.incident_id, frame_resized, involved_boxes)
                clip_path = evidence_buffer.save_clip(cand.incident_id, async_write=True)

                # Match confidence from primary track
                primary_conf = 0.90
                for t in tracks:
                    if t.id == cand.primary_track_id:
                        primary_conf = float(t.confidence)
                        break

                inc_record = {
                    "id": cand.incident_id,
                    "type": inc_type_str,
                    "severity": cand.severity.value if hasattr(cand.severity, "value") else str(cand.severity),
                    "timestamp_s": round(current_video_ts, 3),
                    "frame_idx": frame_idx,
                    "track_id": cand.primary_track_id,
                    "rule_score": round(float(cand.rule_score), 3),
                    "confidence": round(primary_conf, 3),
                    "rule_reason": cand.rule_reason,
                    "evidence_details": getattr(cand, "evidence_details", {}),
                    "snapshot_file": snap_path,
                    "clip_file": clip_path or "",
                }
                fired_incidents.append(inc_record)
                print(f"  [INCIDENT FIRED @ {current_video_ts:.2f}s] {inc_type_str} (Track #{cand.primary_track_id}) - {cand.rule_reason}")

        # Step 8: 3D bounding projection (completes pipeline code path)
        for t in tracks:
            x, y, bw, bh = t.box
            draw_3d_bounding_box(frame_resized, x, y, bw, bh, t.label, 1.0, track_id=t.id, show_dims=False)

        t_frame_1 = time.perf_counter()
        frame_time_ms = (t_frame_1 - t_frame_0) * 1000.0
        latencies_ms.append(frame_time_ms)
        if len(candidates) > 0:
            latencies_burst_ms.append(frame_time_ms)
        else:
            latencies_idle_ms.append(frame_time_ms)

        frame_idx += 1

    cap.release()
    evidence_buffer.wait_all_pending()
    t_end_wall = time.perf_counter()

    elapsed_wall_s = t_end_wall - t_start_wall
    avg_fps = frame_idx / max(1e-4, elapsed_wall_s)
    p95_latency_ms = float(np.percentile(latencies_ms, 95)) if latencies_ms else 0.0
    mean_latency_ms = float(np.mean(latencies_ms)) if latencies_ms else 0.0

    burst_fps = round(1000.0 / float(np.mean(latencies_burst_ms)), 2) if latencies_burst_ms else round(avg_fps, 2)
    idle_fps = round(1000.0 / float(np.mean(latencies_idle_ms)), 2) if latencies_idle_ms else round(avg_fps, 2)
    burst_vs_idle_diff_pct = round(abs(idle_fps - burst_fps) / max(1e-3, idle_fps) * 100.0, 2)

    timing = {
        "total_frames": frame_idx,
        "video_duration_s": round(video_dur_s, 2),
        "elapsed_time_s": round(elapsed_wall_s, 2),
        "avg_fps": round(avg_fps, 2),
        "burst_fps": burst_fps,
        "idle_fps": idle_fps,
        "burst_vs_idle_diff_pct": burst_vs_idle_diff_pct,
        "p95_latency_ms": round(p95_latency_ms, 2),
        "mean_latency_ms": round(mean_latency_ms, 2),
        "min_latency_ms": round(float(np.min(latencies_ms)), 2) if latencies_ms else 0.0,
        "max_latency_ms": round(float(np.max(latencies_ms)), 2) if latencies_ms else 0.0,
    }

    # Compute Tracker Health Metrics
    unique_track_ids = len(track_first_seen)
    lifetimes = [track_last_seen[tid] - track_first_seen[tid] for tid in track_first_seen]
    median_track_lifetime_s = round(float(np.median(lifetimes)), 3) if lifetimes else 0.0
    tracks_under_0_5s = sum(1 for lt in lifetimes if lt < 0.5)
    pct_tracks_under_0_5s = round((tracks_under_0_5s / max(1, unique_track_ids)) * 100.0, 2)

    total_speed_samples = len(all_speed_samples)
    speeds_above_150 = sum(1 for s in all_speed_samples if s > 150.0)
    pct_speed_samples_above_150kmh = round((speeds_above_150 / max(1, total_speed_samples)) * 100.0, 2)
    max_speed_kmh = round(float(np.max(all_speed_samples)), 1) if all_speed_samples else 0.0

    incidents_by_type: Dict[str, int] = {}
    for inc in fired_incidents:
        it = inc["type"]
        incidents_by_type[it] = incidents_by_type.get(it, 0) + 1

    id_to_vehicle_ratio = None
    if args.expected_vehicles is not None and args.expected_vehicles > 0:
        id_to_vehicle_ratio = round(unique_track_ids / float(args.expected_vehicles), 2)

    tracker_health = {
        "unique_track_ids": unique_track_ids,
        "expected_vehicles": args.expected_vehicles,
        "id_to_vehicle_ratio": id_to_vehicle_ratio,
        "median_track_lifetime_s": median_track_lifetime_s,
        "percent_tracks_under_0_5s": pct_tracks_under_0_5s,
        "total_speed_samples": total_speed_samples,
        "percent_speed_samples_above_150kmh": pct_speed_samples_above_150kmh,
        "max_speed_kmh": max_speed_kmh,
        "incidents_by_type": incidents_by_type,
    }

    # Dump results.json
    results_payload = {
        "metadata": {
            "clip_name": clip_name,
            "video_path": os.path.abspath(args.video),
            "camera_config": camera_cfg_path,
            "rules_config": rules_cfg_path,
            "cpu_model": cpu_model,
            "timestamp": time.time(),
        },
        "thresholds": {
            "stationary_s": stationary_s,
            "ttc_s": ttc_s,
            "cooldown_s": cooldown_s,
        },
        "timing": timing,
        "tracker_health": tracker_health,
        "incidents": fired_incidents,
    }

    results_json_path = os.path.join(out_dir, "results.json")
    with open(results_json_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)

    # Dump index.html
    html_path = os.path.join(out_dir, "index.html")
    generate_contact_sheet(
        html_path=html_path,
        clip_name=clip_name,
        cpu_model=cpu_model,
        timing=timing,
        incidents=fired_incidents,
        thresholds=results_payload["thresholds"],
    )

    # Dump labels.csv template
    labels_csv_path = os.path.join(out_dir, "labels.csv")
    with open(labels_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["incident_id", "verdict", "notes"])
        for inc in fired_incidents:
            writer.writerow([inc["id"], "", ""])

    # Terminal Report
    print(f"\n=======================================================")
    print(f"REPLAY COMPLETE: {clip_basename}")
    print(f"=======================================================")
    print(f"CPU Model:          {cpu_model}")
    print(f"Total Frames:       {frame_idx} / {total_video_frames}")
    print(f"Elapsed Time:       {elapsed_wall_s:.2f} s")
    print(f"Average FPS:        {avg_fps:.1f} FPS")
    print(f"p95 Latency:        {p95_latency_ms:.2f} ms")
    print(f"Mean Latency:       {mean_latency_ms:.2f} ms")
    print(f"--- Tracker Health ---")
    print(f"Unique Track IDs:   {unique_track_ids}")
    if id_to_vehicle_ratio is not None:
        print(f"Expected Vehicles:  {args.expected_vehicles} (ID/Vehicle Ratio: {id_to_vehicle_ratio})")
    print(f"Median Lifetime:    {median_track_lifetime_s:.3f} s")
    print(f"Tracks < 0.5s:      {pct_tracks_under_0_5s:.1f}%")
    print(f"Speed Samples >150: {pct_speed_samples_above_150kmh:.1f}% ({speeds_above_150}/{total_speed_samples})")
    print(f"Max Speed:          {max_speed_kmh:.1f} km/h")
    print(f"Incidents by Type:  {incidents_by_type}")
    print(f"Incidents Fired:    {len(fired_incidents)}")
    for inc in fired_incidents:
        print(f"  - [{inc['id']}] {inc['type']} @ {inc['timestamp_s']:.2f}s (Track #{inc['track_id']}, score={inc['rule_score']})")
    print(f"Outputs written to: {out_dir}")
    print(f"  * {results_json_path}")
    print(f"  * {html_path}")
    print(f"  * {labels_csv_path}")
    print(f"=======================================================\n")

    if args.save_report:
        report_path = os.path.abspath(args.save_report)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        report_data = {}
        if os.path.exists(report_path):
            try:
                with open(report_path, "r", encoding="utf-8") as rf:
                    report_data = json.load(rf)
            except Exception:
                report_data = {}
        report_data[clip_basename] = results_payload
        with open(report_path, "w", encoding="utf-8") as wf:
            json.dump(report_data, wf, indent=2)
        print(f"Saved run report to {report_path}")


if __name__ == "__main__":
    replay_video()
