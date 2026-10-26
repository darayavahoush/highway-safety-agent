"""
Comprehensive tests for Runtime Readiness & System Status (PR: feat/runtime-readiness).

Validates:
1. Telemetry starts as unknown (None), never hard-coded 15 FPS or healthy camera before frames arrive.
2. System status endpoint reports video source type, connection state, timestamps, FPS, detector state.
3. Missing video files: unavailable feed with clear diagnostic reason; service liveness remains 200 OK.
4. Unavailable RTSP streams: disconnected with clear diagnostic reason; service liveness remains 200 OK.
5. Stalled frames: marks feed as stale with clear diagnostic reason.
6. Successful ingestion: actual measured FPS, proof-of-life timestamps, healthy feed.
7. Camera reconnection: transitioning from failed to available updates connection state.
8. Healthy API != Healthy Camera: deployment liveness is separate from camera health.
"""

import os
import sys
import time
from unittest.mock import MagicMock
import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.capture import LatestFrameReader
from app.camera_health import CameraHealthAnalyzer
from app.detector import BackgroundSubtractionDetector
from app.system_status import SystemStatusReporter
from app.main import app


# -----------------------------------------------------------------------------
# 1. Telemetry Initialisation (Requirement 2)
# -----------------------------------------------------------------------------

def test_telemetry_starts_unknown_not_hardcoded_values():
    """Do not show 15 FPS or healthy camera status before a real frame has been processed."""
    reporter = SystemStatusReporter(reader=None, camera_health=CameraHealthAnalyzer())
    status = reporter.get_status()

    # FPS and latencies must start as None (unknown)
    assert status["telemetry"]["fps"] is None, "FPS must not start with hardcoded value (e.g. 15.0)"
    assert status["telemetry"]["inference_latency_ms"] is None
    assert status["telemetry"]["rule_latency_ms"] is None

    # Processing counts & timestamps must start at 0 / None
    assert status["last_frame"]["processed_at"] is None
    assert status["last_frame"]["frames_processed"] == 0

    # Feed health before any processing is not healthy
    assert status["feed_health"]["status"] in ("unavailable", "not_started")
    assert status["feed_health"]["reason"] is not None

    # Camera health starts with no proof of life
    cam = status["camera_health"]
    assert cam["camera_stability"] is None
    assert cam["frame_age_s"] is None
    assert cam["frames_analysed"] == 0


# -----------------------------------------------------------------------------
# 2. Missing Video Files (Requirement 1, 4)
# -----------------------------------------------------------------------------

def test_missing_video_file_reports_unavailable_with_clear_reason(tmp_path):
    """Missing video file must report file_not_found with exact path, without crashing."""
    fake_path = str(tmp_path / "does_not_exist_drone.mp4")
    reader = LatestFrameReader(fake_path)

    # Initial check before thread
    status = reader.get_status(now=1000.0)
    assert status["connected"] is False
    assert status["state"] == "file_not_found"
    assert "Video file not found at path" in status["reason"]
    assert fake_path in status["reason"]

    # In SystemStatusReporter
    reporter = SystemStatusReporter(reader=reader)
    sys_status = reporter.get_status(now=1000.0)
    assert sys_status["video_source"]["connected"] is False
    assert sys_status["video_source"]["state"] == "file_not_found"
    assert sys_status["feed_health"]["status"] == "unavailable"
    assert "Video file not found" in sys_status["feed_health"]["reason"]

    # Service liveness probe must remain OK
    liveness = reporter.get_liveness()
    assert liveness["status"] == "ok"
    assert liveness["service"] == "highway-safety-agent"


# -----------------------------------------------------------------------------
# 3. Unavailable RTSP Stream (Requirement 1, 4)
# -----------------------------------------------------------------------------

def test_unavailable_rtsp_stream_reports_disconnected_with_clear_reason():
    """Unreachable RTSP stream must report disconnected with clear network/stream reason."""
    rtsp_url = "rtsp://127.0.0.1:59999/live/stream"
    reader = LatestFrameReader(rtsp_url)

    # Simulate connection failure in open
    reader._cap = None
    reader._connected = False
    reader._last_error = f"Unable to connect to RTSP stream: {rtsp_url}"

    status = reader.get_status(now=2000.0)
    assert status["source_type"] == "rtsp"
    assert status["connected"] is False
    assert status["state"] == "disconnected"
    assert "Unable to connect to RTSP stream" in status["reason"]

    reporter = SystemStatusReporter(reader=reader)
    sys_status = reporter.get_status(now=2000.0)
    assert sys_status["feed_health"]["status"] == "unavailable"
    assert "Unable to connect to RTSP stream" in sys_status["feed_health"]["reason"]
    assert sys_status["mode"]["is_live"] is False


# -----------------------------------------------------------------------------
# 4. Stalled Frames (Requirement 1, 4)
# -----------------------------------------------------------------------------

def test_stalled_frames_marks_feed_as_stale_with_duration():
    """If frames stop arriving (> 5s), status transitions from healthy to stale."""
    reader = LatestFrameReader("demo_videos/drone/DJI_0011.MP4")
    reader._connected = True
    reader._frames_captured = 100
    reader._last_frame_ts = 1000.0

    # 1 second after last frame: fresh and healthy
    fresh = reader.get_status(now=1001.0)
    assert fresh["connected"] is True
    assert fresh["state"] == "connected"
    assert fresh["is_stale"] is False
    assert fresh["reason"] is None

    # 8 seconds after last frame: stalled!
    stalled = reader.get_status(now=1008.0)
    assert stalled["connected"] is False
    assert stalled["state"] == "stale"
    assert stalled["is_stale"] is True
    assert "Video stream stalled" in stalled["reason"]
    assert "8.0s" in stalled["reason"]

    # System status reports stale feed
    reporter = SystemStatusReporter(reader=reader)
    reporter.record_frame_processed(now=1000.0, fps=15.0)
    sys_status = reporter.get_status(now=1008.0)
    assert sys_status["feed_health"]["status"] == "stale"
    assert "stalled" in sys_status["feed_health"]["reason"]


# -----------------------------------------------------------------------------
# 5. Successful Ingestion & Measured Telemetry (Requirement 1, 2)
# -----------------------------------------------------------------------------

def test_successful_ingestion_populates_actual_measured_telemetry():
    """When frames arrive, status reports actual measured FPS, timestamps, and healthy status."""
    reader = LatestFrameReader("demo_videos/drone/DJI_0011.MP4")
    reader._connected = True
    reader._frames_captured = 50
    reader._last_frame_ts = 3000.0

    cam = CameraHealthAnalyzer()
    dummy_frame = np.full((360, 640, 3), 120, np.uint8)
    cam.analyze_frame(dummy_frame, now=3000.0)

    reporter = SystemStatusReporter(reader=reader, camera_health=cam, model_path="models/yolov8n.onnx")
    reporter.record_frame_processed(now=3000.1, fps=24.5, rule_ms=0.45, cpu_ms=28.2)

    status = reporter.get_status(now=3000.2)
    assert status["feed_health"]["status"] == "healthy"
    assert status["feed_health"]["reason"] is None
    assert status["telemetry"]["fps"] == 24.5
    assert status["telemetry"]["inference_latency_ms"] == 28.2
    assert status["telemetry"]["rule_latency_ms"] == 0.45
    assert status["last_frame"]["frames_processed"] == 1
    assert status["last_frame"]["processed_at"] == 3000.1
    assert status["last_frame"]["age_s"] == 0.1
    assert status["camera_health"]["camera_stability"] == "STATIC_LOCKED"
    assert status["camera_health"]["frame_age_s"] == 0.2


# -----------------------------------------------------------------------------
# 6. Camera Reconnection (Requirement 4)
# -----------------------------------------------------------------------------

def test_camera_reconnection_transitions_state_to_connected():
    """Transitioning from connection error to successful read restores connected state."""
    reader = LatestFrameReader("demo_videos/drone/DJI_0011.MP4")
    reader._connected = False
    reader._last_error = "Connection dropped"

    broken = reader.get_status(now=4000.0)
    assert broken["connected"] is False
    assert broken["state"] == "disconnected"

    # Simulate camera reconnecting and receiving frame
    reader._connected = True
    reader._last_error = None
    reader._last_frame_ts = 4002.0
    reader._frames_captured += 1

    restored = reader.get_status(now=4002.2)
    assert restored["connected"] is True
    assert restored["state"] == "connected"
    assert restored["reason"] is None


# -----------------------------------------------------------------------------
# 7. Fallback Detector State (Requirement 1)
# -----------------------------------------------------------------------------

def test_fallback_detector_state_reporting():
    """If YOLO model is absent, detector state explicitly reports using_fallback."""
    fb_detector = BackgroundSubtractionDetector()
    reporter = SystemStatusReporter(
        detector=fb_detector,
        model_path="models/nonexistent.onnx",
    )
    status = reporter.get_status(now=5000.0)
    det = status["detector"]
    assert det["using_fallback"] is True
    assert det["detector_type"] == "background_subtraction"
    assert det["model_loaded"] is False


# -----------------------------------------------------------------------------
# 8. Healthy API != Healthy Camera (Requirement 4, 6)
# -----------------------------------------------------------------------------

def test_healthy_api_cannot_be_mistaken_for_healthy_camera():
    """Liveness probe /healthz returns 200 OK even when camera feed is unavailable."""
    client = TestClient(app)

    # Liveness check must always return 200 OK
    resp_liveness = client.get("/healthz")
    assert resp_liveness.status_code == 200
    assert resp_liveness.json()["status"] == "ok"
    assert resp_liveness.json()["service"] == "highway-safety-agent"

    # API health check alias
    resp_api_health = client.get("/api/health")
    assert resp_api_health.status_code == 200
    assert resp_api_health.json()["status"] == "ok"

    # Status endpoint must exist and return full schema
    resp_status = client.get("/api/status")
    assert resp_status.status_code == 200
    data = resp_status.json()
    assert "video_source" in data
    assert "last_frame" in data
    assert "telemetry" in data
    assert "detector" in data
    assert "feed_health" in data
    assert "service" in data
    assert data["service"]["api_healthy"] is True

    # /api/system/status alias
    resp_sys_status = client.get("/api/system/status")
    assert resp_sys_status.status_code == 200
    assert resp_sys_status.json()["service"]["status"] == "ok"

    # Existing /api/incidents contract must remain backward-compatible
    resp_incidents = client.get("/api/incidents")
    assert resp_incidents.status_code == 200
    inc_data = resp_incidents.json()
    assert "incidents" in inc_data
    assert "blackspots" in inc_data
    assert "camera" in inc_data


# -----------------------------------------------------------------------------
# 9. Labelled Demo Mode (Requirement 5)
# -----------------------------------------------------------------------------

def test_explicit_labelled_demo_mode():
    """Explicit labelled demo mode generates synthetic frames, reports is_demo=True and healthy status."""
    reader = LatestFrameReader("synthetic_demo")
    status = reader.get_status(now=6000.0)
    assert status["source_type"] == "synthetic_demo"
    assert status["connected"] is True
    assert status["state"] == "connected"

    reporter = SystemStatusReporter(reader=reader)
    sys_status = reporter.get_status(now=6000.0)
    assert sys_status["mode"]["is_demo"] is True
    assert sys_status["mode"]["is_live"] is False
    assert sys_status["video_source"]["type"] == "synthetic_demo"
