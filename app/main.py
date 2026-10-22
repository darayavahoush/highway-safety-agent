"""
FastAPI application for Highway Safety & Accident Prevention Autonomous Agent.
Strictly implements the Frontend ↔ Backend Contract (src/api/CONTRACT.md).
Provides:
- Edge Perception Pipeline (YOLOv8 ONNX + 3D cuboids)
- Edge Trigger Engine (Stalled vehicles, Tailgating TTC, Wrong-Way driving)
- Evidence Ring Buffer & Quality Gates
- Cognitive Safety Agent Worker with 15s Operator Cancel Window
- Real-time WebSocket (/ws/incidents) broadcasting full Incident updates and telemetry metrics
- SQLite Persistence and Blackspot Analytics
- Complete REST APIs for Snapshots, Cancellation, Feedback, and MJPEG Video
"""

import asyncio
from contextlib import asynccontextmanager
import cv2
import json
import numpy as np
import os
import time
from typing import Dict, List, Optional, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.incident_schema import IncidentEvent, IncidentCandidate, IncidentStatus
from app.incident_rules import EdgeTriggerEngine
from app.evidence_buffer import EvidenceBuffer
from app.queue_boundary import incident_queue
from app.mock_dispatch import router as mock_router
from app.capture import LatestFrameReader
from app.detector import create_yolo_detector, BackgroundSubtractionDetector
from app.tracker import LineCrossingCounter
from app.dimensions_3d import draw_3d_bounding_box
from app import db
from agent.worker import agent_worker


# Environment & Paths
VIDEO_SOURCE = os.getenv("VIDEO_SOURCE") or os.getenv("RTSP_URL") or "demo_videos/drone/DJI_0011.MP4"
RTSP_URL = VIDEO_SOURCE
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "models/yolov8n.onnx")
PROCESS_WIDTH = int(os.getenv("PROCESS_WIDTH", "640"))
OUTPUT_FPS = float(os.getenv("OUTPUT_FPS", "15.0"))
CAMERA_CONFIG_PATH = os.getenv("CAMERA_CONFIG_PATH", "config/camera_config.json")
SAFETY_RULES_PATH = os.getenv("SAFETY_RULES_PATH", "config/safety_rules.json")

# Core Engine Components
evidence_buffer = EvidenceBuffer(max_seconds=10.0, fps=OUTPUT_FPS, cooldown_seconds=25.0)
trigger_engine = EdgeTriggerEngine(CAMERA_CONFIG_PATH, SAFETY_RULES_PATH)
tracker = LineCrossingCounter(line=((0, 200), (640, 200)))

# Runtime Telemetry State
latest_jpeg: Optional[bytes] = None
latest_frame: Optional[np.ndarray] = None
telemetry_stats = {
    "fps": 15.0,
    "ruleMs": 0.12,
    "cpuMsPerFrame": 32.0,
    "agentLatencyMs": 1400.0,
    "detectToDispatchS": 1.4,
}

# Active WebSocket Clients
connected_websockets: Set[WebSocket] = set()


def get_detector():
    if os.path.isfile(YOLO_MODEL_PATH):
        return create_yolo_detector(YOLO_MODEL_PATH, input_size=320, conf_threshold=0.35)
    return BackgroundSubtractionDetector()


detector = get_detector()
capture_source = int(RTSP_URL) if RTSP_URL.isdigit() else RTSP_URL
reader = LatestFrameReader(capture_source)


async def broadcast_ws(payload: dict):
    """Broadcasts a JSON message to all connected frontend clients."""
    if not connected_websockets:
        return
    text = json.dumps(payload)
    disconnected = set()
    for ws in connected_websockets:
        try:
            await ws.send_text(text)
        except Exception:
            disconnected.add(ws)
    for ws in disconnected:
        connected_websockets.discard(ws)


# Connect Agent Worker broadcast callback
agent_worker.broadcast_callback = broadcast_ws


async def perception_loop():
    """Runs synchronous perception, edge rule evaluation, and ring buffer caching."""
    global latest_jpeg, latest_frame, telemetry_stats
    frame_interval = 1.0 / OUTPUT_FPS

    while True:
        t_start = time.time()
        frame = reader.read()
        if frame is None:
            await asyncio.sleep(0.04)
            continue

        h, w = frame.shape[:2]
        scale = PROCESS_WIDTH / float(w)
        frame_resized = cv2.resize(frame, (PROCESS_WIDTH, int(h * scale)))
        rh, rw = frame_resized.shape[:2]

        now = time.time()
        evidence_buffer.push_frame(frame_resized, now)

        # Perception: Detection & Tracking
        t_detect_start = time.time()
        detections = detector.detect(frame_resized)
        tracks, _ = tracker.update(detections)
        t_detect_end = time.time()

        # Update Track History
        track_inputs = [(float(t.box[0]), float(t.box[1]), float(t.box[2]), float(t.box[3]), t.label, t.id) for t in tracks]
        trigger_engine.update_tracks(track_inputs, now)

        # Rule Engine Evaluation
        t_rules_start = time.time()
        fired_candidates = trigger_engine.evaluate_rules(rw, rh, now)
        t_rules_end = time.time()

        # Handle Triggered Incidents
        for cand in fired_candidates:
            if not evidence_buffer.should_suppress_dedupe(cand.camera_id, cand.incident_type, cand.primary_track_id, now):
                involved_boxes = [(int(v.box[0]), int(v.box[1]), int(v.box[2]), int(v.box[3]), v.label) for v in cand.involved_vehicles]
                snap_path = evidence_buffer.save_snapshot(cand.incident_id, frame_resized, involved_boxes)
                cand.evidence_snapshot_path = f"/evidence/snapshots/{cand.incident_id}.jpg"
                # Push candidate to agent worker queue (zero perception latency)
                incident_queue.put_nowait(cand)

        # Draw Clean Tactical Overlay
        for t in tracks:
            x, y, bw, bh = t.box
            draw_3d_bounding_box(frame_resized, x, y, bw, bh, t.label, 1.0, track_id=t.id, show_dims=False)

        # Header HUD
        header = f"NH-16 KM 42.4 | ACTIVE VEHICLES: {len(tracks)} | INCIDENTS: {len(db.get_all_incidents(10))}"
        cv2.rectangle(frame_resized, (0, 0), (rw, 26), (15, 20, 28), -1)
        cv2.putText(frame_resized, header, (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (0, 240, 255), 1, cv2.LINE_AA)

        ok, buf = cv2.imencode(".jpg", frame_resized, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            latest_jpeg = buf.tobytes()
            latest_frame = frame_resized

        t_end = time.time()
        elapsed = t_end - t_start
        telemetry_stats["fps"] = round(1.0 / max(1e-3, elapsed), 1)
        telemetry_stats["ruleMs"] = round((t_rules_end - t_rules_start) * 1000.0, 2)
        telemetry_stats["cpuMsPerFrame"] = round((t_detect_end - t_detect_start) * 1000.0, 1)

        await asyncio.sleep(max(0.001, frame_interval - elapsed))


async def telemetry_broadcaster():
    """Periodically broadcasts telemetry metrics every 1.5 seconds."""
    while True:
        await asyncio.sleep(1.5)
        if connected_websockets:
            await broadcast_ws({
                "metrics": {
                    "fps": telemetry_stats["fps"],
                    "ruleMs": telemetry_stats["ruleMs"],
                    "cpuMsPerFrame": telemetry_stats["cpuMsPerFrame"],
                    "agentLatencyMs": telemetry_stats["agentLatencyMs"],
                    "detectToDispatchS": telemetry_stats["detectToDispatchS"],
                }
            })


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite schema
    db.init_db()
    # Start background video capture thread
    reader.start()
    # Start background perception, agent worker, and metrics broadcaster
    p_task = asyncio.create_task(perception_loop())
    a_task = asyncio.create_task(agent_worker.run())
    m_task = asyncio.create_task(telemetry_broadcaster())
    yield
    p_task.cancel()
    a_task.cancel()
    m_task.cancel()
    reader.stop()


app = FastAPI(
    title="Highway Safety Autonomous Agent",
    description="AP Innovation & RTIH 2026 - Edge Sentry & Cognitive Incident Command Control",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for Vite Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Mock Government Endpoints
app.include_router(mock_router)

# Mount Evidence Assets (snapshots & clips)
os.makedirs("evidence/snapshots", exist_ok=True)
os.makedirs("evidence/clips", exist_ok=True)
app.mount("/evidence", StaticFiles(directory="evidence"), name="evidence")


# -----------------------------------------------------------------
# CONTRACT REST ROUTES
# -----------------------------------------------------------------

@app.get("/api/incidents")
def get_incidents_snapshot():
    """
    CONTRACT.md: Snapshot of recent incidents, blackspot aggregations, and camera metadata.
    """
    incidents = db.get_all_incidents(limit=50)
    blackspots = db.get_blackspots_summary()
    camera_cfg = trigger_engine.camera_cfg
    camera_data = {
        "id": camera_cfg.get("camera_id", "CAM-AP-NH16-KM42"),
        "highway": camera_cfg.get("highway", "NH-16"),
        "km": float(str(camera_cfg.get("km_marker", "42.4")).replace("KM", "").strip() or 42.4),
        "lat": camera_cfg.get("gps", {}).get("latitude", 16.5412),
        "lng": camera_cfg.get("gps", {}).get("longitude", 80.6421),
        "towards": camera_cfg.get("towards", "Visakhapatnam"),
        "opposite": camera_cfg.get("opposite", "Vijayawada"),
    }
    return {
        "incidents": incidents,
        "blackspots": blackspots,
        "camera": camera_data,
    }


@app.get("/api/corridors")
def get_corridors_registry():
    """Official Andhra Pradesh highway corridor registry, blackspots, and trauma care network."""
    corridors_path = "config/ap_highway_corridors.json"
    if os.path.isfile(corridors_path):
        with open(corridors_path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Corridor configuration not found")


class ClipSelectPayload(BaseModel):
    clip_id: Optional[str] = None
    path: Optional[str] = None


@app.get("/api/clips")
def list_available_clips():
    """Lists available real-world highway sample clips (including HuggingFace drone footage)."""
    current_source = getattr(reader, "source", VIDEO_SOURCE)
    clips = [
        {
            "id": "drone_0011",
            "name": "DJI_0011.MP4 (HF Drone Overhead)",
            "path": "demo_videos/drone/DJI_0011.MP4",
            "description": "High-altitude top-down perspective from HuggingFace anabaena/drone-vehicle-clips. Demonstrates multi-lane tracking.",
            "source_type": "HF Drone Sentry (AP Highway Simulation)",
            "highway": "NH-16 Vijayawada - Guntur",
        },
        {
            "id": "drone_0025",
            "name": "DJI_0025.MP4 (HF Drone Angled)",
            "path": "demo_videos/drone/DJI_0025.MP4",
            "description": "Low-altitude angled perspective from HuggingFace anabaena/drone-vehicle-clips with fast lane overtaking.",
            "source_type": "HF Drone Sentry (AP Highway Simulation)",
            "highway": "NH-16 Kaza Toll Plaza Stretch",
        },
        {
            "id": "sideview_cctv",
            "name": "sideview.mp4 (Fixed Pole CCTV)",
            "path": "demo_videos/sideview.mp4",
            "description": "Fixed highway pole camera sideview showing vehicles passing across lanes with tripwire counting.",
            "source_type": "NHAI Fixed Sentry CCTV",
            "highway": "NH-16 KM 42.4",
        },
    ]
    available = [c for c in clips if os.path.isfile(c["path"])]
    current_filename = os.path.basename(str(current_source))
    return {
        "clips": available,
        "active_clip": current_filename,
        "active_source": str(current_source),
    }


@app.post("/api/clips/select")
async def select_active_clip(payload: ClipSelectPayload):
    """Dynamically switches the active video feed to another sample clip."""
    clip_path = payload.path
    if not clip_path and payload.clip_id:
        lookup = {
            "drone_0011": "demo_videos/drone/DJI_0011.MP4",
            "drone_0025": "demo_videos/drone/DJI_0025.MP4",
            "sideview_cctv": "demo_videos/sideview.mp4",
        }
        clip_path = lookup.get(payload.clip_id)

    if not clip_path or not os.path.isfile(clip_path):
        raise HTTPException(status_code=404, detail=f"Clip file not found: {clip_path}")

    ok = reader.set_source(clip_path)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to initialize video capture on selected clip")

    # Reset tracking state for clean transition
    tracker.reset()
    trigger_engine.reset()

    await broadcast_ws({
        "clip_changed": {
            "path": clip_path,
            "filename": os.path.basename(clip_path),
        }
    })

    return {"status": "SUCCESS", "active_clip": os.path.basename(clip_path), "path": clip_path}


@app.post("/api/incidents/{incident_id}/dispatches/{dispatch_id}/cancel")
async def cancel_queued_dispatch(incident_id: str, dispatch_id: str):
    """
    CONTRACT.md: Operator cancels a queued dispatch during the 15-second window.
    Prevents the mock endpoint from being called.
    """
    ok = agent_worker.cancel_dispatch(incident_id, dispatch_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Dispatch is not queued or does not exist")
    
    # Broadcast updated state
    incidents = db.get_all_incidents()
    for inc in incidents:
        if inc["id"] == incident_id:
            await broadcast_ws({"incident": inc})
            return {"status": "SUCCESS", "message": f"Dispatch {dispatch_id} cancelled."}
    
    return {"status": "SUCCESS"}


class FeedbackPayload(BaseModel):
    verdict: str  # "confirmed" | "false_alarm"


@app.post("/api/incidents/{incident_id}/feedback")
async def set_incident_feedback(incident_id: str, payload: FeedbackPayload):
    """
    CONTRACT.md: Human-in-the-loop operator feedback loop.
    Persists verdict and updates status to 'false_alarm' if rejected.
    """
    if payload.verdict not in ["confirmed", "false_alarm"]:
        raise HTTPException(status_code=400, detail="Verdict must be 'confirmed' or 'false_alarm'")

    updated = db.set_incident_feedback(incident_id, payload.verdict)
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Broadcast updated incident
    incidents = db.get_all_incidents()
    for inc in incidents:
        if inc["id"] == incident_id:
            await broadcast_ws({"incident": inc})
            break

    return {"status": "SUCCESS", "verdict": payload.verdict}


# -----------------------------------------------------------------
# WEBSOCKET ROUTE: /ws/incidents
# -----------------------------------------------------------------

@app.websocket("/ws/incidents")
async def ws_incidents_endpoint(websocket: WebSocket):
    """
    CONTRACT.md WebSocket connection.
    Sends full snapshot on connect, then listens for client lifecycle.
    """
    await websocket.accept()
    connected_websockets.add(websocket)
    try:
        # Send initial snapshot immediately upon connect
        snapshot = get_incidents_snapshot()
        await websocket.send_text(json.dumps(snapshot))

        # Keep alive loop
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        connected_websockets.discard(websocket)
    except Exception:
        connected_websockets.discard(websocket)


# -----------------------------------------------------------------
# VIDEO FEED & UTILITIES
# -----------------------------------------------------------------

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
    """MJPEG stream consumed by the LiveStage Camera tab."""
    return StreamingResponse(_mjpeg_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


ENABLE_SIMULATION = os.getenv("ENABLE_SIMULATION", "0") == "1"


@app.post("/api/simulate_incident/{incident_type}")
def simulate_incident(incident_type: str):
    """Testing helper to trigger an incident. Gated behind ENABLE_SIMULATION=1."""
    if not ENABLE_SIMULATION:
        raise HTTPException(
            status_code=403,
            detail="Simulation endpoints are disabled. Run with ENABLE_SIMULATION=1 for testing without a video feed."
        )
    from app.incident_schema import VehicleTelemetry, IncidentType
    cand = IncidentCandidate(
        incident_type=IncidentType.STALLED_VEHICLE if incident_type == "stalled" else (
            IncidentType.WRONG_WAY if incident_type == "wrong_way" else IncidentType.TAILGATING
        ),
        severity="P0" if incident_type != "tailgating" else "P1",
        camera_id="CAM-AP-NH16-KM42",
        km_marker="KM 42.4",
        primary_track_id=88,
        lane_id="Fast / Overtaking Lane (Right)",
        rule_score=0.96,
        rule_reason=f"Simulated test incident for {incident_type}",
        involved_vehicles=[
            VehicleTelemetry(
                trackId=88,
                cls="truck",
                speedKmh=0.0,
                lane="Fast / Overtaking Lane (Right)",
                laneIndex=1,
                x=0.55,
                dir=1,
                plate=None,
            )
        ]
    )
    incident_queue.put_nowait(cand)
    return {"status": "QUEUED", "incident_id": cand.incident_id}
