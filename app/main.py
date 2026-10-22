"""
FastAPI application for Highway Safety & Accident Prevention Autonomous Agent.
Integrates:
- Edge Perception Pipeline (YOLOv8 ONNX + 3D cuboids)
- Edge Trigger Engine (Stalled vehicles, Tailgating TTC, Wrong-Way driving)
- Evidence Ring Buffer (Snapshots, clips, deduplication)
- Cognitive Agent Worker & Mock Dispatch Endpoints
"""

import asyncio
from contextlib import asynccontextmanager
import cv2
import json
import numpy as np
import os
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.incident_schema import IncidentEvent, IncidentCandidate
from app.incident_rules import EdgeTriggerEngine
from app.evidence_buffer import EvidenceBuffer
from app.queue_boundary import incident_queue
from app.mock_dispatch import router as mock_router
from app.capture import LatestFrameReader
from app.detector import create_yolo_detector, BackgroundSubtractionDetector
from app.tracker import LineCrossingCounter
from app.dimensions_3d import draw_3d_bounding_box, build_3d_vehicle_record
from agent.worker import agent_worker


# Config
RTSP_URL = os.getenv("RTSP_URL", "demo_videos/drone/DJI_0011.MP4")
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "models/yolov8n.onnx")
PROCESS_WIDTH = int(os.getenv("PROCESS_WIDTH", "640"))
OUTPUT_FPS = float(os.getenv("OUTPUT_FPS", "15.0"))
CAMERA_CONFIG_PATH = os.getenv("CAMERA_CONFIG_PATH", "config/camera_config.json")
SAFETY_RULES_PATH = os.getenv("SAFETY_RULES_PATH", "config/safety_rules.json")

# State
evidence_buffer = EvidenceBuffer(max_seconds=10.0, fps=OUTPUT_FPS, cooldown_seconds=25.0)
trigger_engine = EdgeTriggerEngine(CAMERA_CONFIG_PATH, SAFETY_RULES_PATH)
tracker = LineCrossingCounter(line=((0, 200), (640, 200)))
latest_jpeg: Optional[bytes] = None
latest_frame: Optional[np.ndarray] = None
active_incidents: List[IncidentEvent] = []
frame_lock = asyncio.Lock()


def get_detector():
    if os.path.isfile(YOLO_MODEL_PATH):
        return create_yolo_detector(YOLO_MODEL_PATH, input_size=320, conf_threshold=0.35)
    return BackgroundSubtractionDetector()


detector = get_detector()
capture_source = int(RTSP_URL) if RTSP_URL.isdigit() else RTSP_URL
reader = LatestFrameReader(capture_source)


async def perception_loop():
    """Runs synchronous perception and non-blocking trigger evaluation."""
    global latest_jpeg, latest_frame
    frame_interval = 1.0 / OUTPUT_FPS

    while True:
        frame = reader.read()
        if frame is None:
            await asyncio.sleep(0.04)
            continue

        h, w = frame.shape[:2]
        scale = PROCESS_WIDTH / float(w)
        frame_resized = cv2.resize(frame, (PROCESS_WIDTH, int(h * scale)))
        rh, rw = frame_resized.shape[:2]

        now = time.time()
        # Push to ring buffer
        evidence_buffer.push_frame(frame_resized, now)

        # Perception: detect & track
        detections = detector.detect(frame_resized)
        tracks, _ = tracker.update(detections)

        # Update track geometry in edge rule engine
        track_inputs = [(float(t.box[0]), float(t.box[1]), float(t.box[2]), float(t.box[3]), t.label, t.id) for t in tracks]
        trigger_engine.update_tracks(track_inputs, now)

        # Evaluate safety rules
        fired_candidates = trigger_engine.evaluate_rules(rw, rh, now)

        for cand in fired_candidates:
            # Check dedupe cooldown
            if not evidence_buffer.should_suppress_dedupe(cand.camera_id, cand.incident_type, cand.primary_track_id, now):
                # Save snapshot & MP4 clip
                involved_boxes = [(int(v.box[0]), int(v.box[1]), int(v.box[2]), int(v.box[3]), v.label) for v in cand.involved_vehicles]
                snap_path = evidence_buffer.save_snapshot(cand.incident_id, frame_resized, involved_boxes)
                cand.evidence_snapshot_path = snap_path

                # Push candidate to agent queue without blocking
                incident_queue.put_nowait(cand)

        # Draw clean overlay
        for t in tracks:
            x, y, bw, bh = t.box
            draw_3d_bounding_box(frame_resized, x, y, bw, bh, t.label, 1.0, track_id=t.id, show_dims=False)

        # Render top status bar
        active_hazard_count = len(agent_worker.get_all_incidents())
        header = f"NH-16 KM 42.4 | VEHICLES: {len(tracks)} | INCIDENTS DISPATCHED: {active_hazard_count}"
        cv2.rectangle(frame_resized, (0, 0), (rw, 28), (15, 20, 28), -1)
        cv2.putText(frame_resized, header, (10, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 240, 255), 1, cv2.LINE_AA)

        ok, buf = cv2.imencode(".jpg", frame_resized, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            latest_jpeg = buf.tobytes()
            latest_frame = frame_resized

        await asyncio.sleep(frame_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start perception task
    p_task = asyncio.create_task(perception_loop())
    # Start cognitive agent worker
    a_task = asyncio.create_task(agent_worker.run())
    yield
    p_task.cancel()
    a_task.cancel()
    reader.stop()


app = FastAPI(
    title="Highway Safety & Accident Prevention Autonomous Agent",
    description="Edge Perception + Cognitive Safety Agent for RTIH & AP Innovation Challenge 2026",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include mock stakeholder routes
app.include_router(mock_router)


@app.get("/incidents")
def get_incidents():
    return {"incidents": agent_worker.get_all_incidents()}


@app.get("/config")
def get_config():
    return {
        "camera_config": trigger_engine.camera_cfg,
        "safety_rules": trigger_engine.rules_cfg,
    }


def _mjpeg_generator():
    boundary = b"--frame"
    while True:
        if latest_jpeg is not None:
            yield (
                boundary + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(latest_jpeg)).encode() + b"\r\n\r\n"
                + latest_jpeg + b"\r\n"
            )
        time.sleep(1.0 / OUTPUT_FPS)


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(_mjpeg_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/evidence/snapshots/{filename}")
def get_snapshot(filename: str):
    path = os.path.join("evidence", "snapshots", filename)
    if os.path.isfile(path):
        return FileResponse(path, media_type="image/jpeg")
    return JSONResponse(status_code=404, content={"error": "Snapshot not found"})
