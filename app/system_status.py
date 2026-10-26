"""
Runtime Readiness & System Status Engine.
Accurately reports live / degraded / demo states, telemetry readiness,
detector model state, and proof-of-life timestamps.
Strictly separates deployment service liveness from camera perception health.
"""

import os
import time
from typing import Any, Dict, Optional


class SystemStatusReporter:
    def __init__(
        self,
        reader=None,
        camera_health=None,
        detector=None,
        model_path: str = "models/yolov8n.onnx",
        is_demo_mode: Optional[bool] = None,
    ):
        self.service_start_time = time.time()
        self.reader = reader
        self.camera_health = camera_health
        self.detector = detector
        self.model_path = model_path
        self._explicit_demo_mode = is_demo_mode

        # Processing loop counters & timestamps
        self.frames_processed = 0
        self.last_frame_processed_at: Optional[float] = None
        self.measured_fps: Optional[float] = None
        self.measured_rule_ms: Optional[float] = None
        self.measured_cpu_ms: Optional[float] = None
        self.agent_latency_ms: Optional[float] = None
        self.detect_to_dispatch_s: Optional[float] = None

    def record_frame_processed(
        self,
        now: Optional[float] = None,
        fps: Optional[float] = None,
        rule_ms: Optional[float] = None,
        cpu_ms: Optional[float] = None,
    ):
        """Called whenever a frame is successfully run through detector & rules."""
        cur = time.time() if now is None else now
        self.frames_processed += 1
        self.last_frame_processed_at = cur
        if fps is not None:
            self.measured_fps = fps
        if rule_ms is not None:
            self.measured_rule_ms = rule_ms
        if cpu_ms is not None:
            self.measured_cpu_ms = cpu_ms

    def record_agent_dispatch_latency(
        self,
        agent_latency_ms: Optional[float] = None,
        detect_to_dispatch_s: Optional[float] = None,
    ):
        """Records agent response and dispatch timing once measured on live incident."""
        if agent_latency_ms is not None:
            self.agent_latency_ms = agent_latency_ms
        if detect_to_dispatch_s is not None:
            self.detect_to_dispatch_s = detect_to_dispatch_s

    def get_liveness(self) -> Dict[str, Any]:
        """Deployment service liveness check (e.g. for Render/Kubernetes probes).

        Must remain 200 OK even when camera or video stream is temporarily interrupted,
        preventing unnecessary container reboot cycles.
        """
        return {
            "status": "ok",
            "service": "highway-safety-agent",
            "uptime_s": round(time.time() - self.service_start_time, 2),
        }

    def get_status(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Full system status reporting video source, detector, telemetry and health."""
        cur = time.time() if now is None else now

        # 1. Video capture status
        if self.reader and hasattr(self.reader, "get_status"):
            cap_stat = self.reader.get_status(now=cur)
        else:
            cap_stat = {
                "source": "unknown",
                "source_type": "unknown",
                "connected": False,
                "state": "disconnected",
                "frames_captured": 0,
                "last_frame_captured_at": None,
                "frame_age_s": None,
                "is_stale": False,
                "reason": "No video capture reader attached",
            }

        # 2. Detector state
        model_exists = bool(self.model_path and os.path.isfile(self.model_path))
        using_fallback = False
        det_type = "yolov8"

        if self.detector is not None:
            from app.detector import BackgroundSubtractionDetector
            if isinstance(self.detector, BackgroundSubtractionDetector):
                using_fallback = True
                det_type = "background_subtraction"
            else:
                det_type = "yolov8"
        else:
            using_fallback = not model_exists
            det_type = "yolov8" if model_exists else "background_subtraction"

        detector_info = {
            "model_loaded": model_exists and not using_fallback,
            "model_path": self.model_path,
            "detector_type": det_type,
            "using_fallback": using_fallback,
        }

        # 3. Processing timestamps
        last_proc_ts = self.last_frame_processed_at
        proc_age_s = (cur - last_proc_ts) if last_proc_ts is not None else None

        # 4. Mode determination (Live vs Demo vs Degraded)
        env_mode = os.getenv("DATA_MODE") or os.getenv("VITE_DATA_MODE") or ""
        is_demo = False
        if self._explicit_demo_mode is not None:
            is_demo = self._explicit_demo_mode
        elif env_mode.lower() == "demo":
            is_demo = True
        elif cap_stat["source_type"] in ("file", "directory", "synthetic_demo"):
            is_demo = True
        elif not cap_stat["connected"]:
            is_demo = False

        is_live = not is_demo and cap_stat["connected"]

        # 5. Feed health & diagnostics
        feed_reason = None
        if cap_stat["state"] == "stale" or (proc_age_s is not None and proc_age_s > 5.0 and self.frames_processed > 0):
            feed_status = "stale"
            stalled_secs = proc_age_s if proc_age_s is not None else (cap_stat.get("frame_age_s") or 5.0)
            feed_reason = f"Video stream stalled: no frame received for {stalled_secs:.1f}s"
        elif not cap_stat["connected"]:
            feed_status = "unavailable"
            feed_reason = cap_stat["reason"] or f"Video source disconnected: {cap_stat['source']}"
        elif self.frames_processed == 0:
            feed_status = "not_started"
            feed_reason = "No video frames processed yet"
        elif using_fallback:
            feed_status = "degraded"
            feed_reason = f"Running on CPU fallback detector ({det_type}) because YOLO model {self.model_path} is unavailable"
        else:
            feed_status = "healthy"
            feed_reason = None

        mode_label = "live" if is_live else ("demo" if is_demo else "degraded")
        if feed_status in ("unavailable", "stale"):
            mode_label = "degraded"

        # 6. Camera health snapshot
        cam_snap = None
        if self.camera_health and hasattr(self.camera_health, "snapshot"):
            cam_snap = self.camera_health.snapshot(now=cur)

        return {
            "service": {
                "status": "ok",
                "uptime_s": round(cur - self.service_start_time, 2),
                "api_healthy": True,
            },
            "video_source": {
                "source": cap_stat["source"],
                "type": cap_stat["source_type"],
                "connected": cap_stat["connected"],
                "state": cap_stat["state"],
            },
            "last_frame": {
                "captured_at": cap_stat["last_frame_captured_at"],
                "processed_at": last_proc_ts,
                "age_s": round(proc_age_s, 2) if proc_age_s is not None else None,
                "frames_captured": cap_stat["frames_captured"],
                "frames_processed": self.frames_processed,
            },
            "telemetry": {
                "fps": self.measured_fps,
                "inference_latency_ms": self.measured_cpu_ms,
                "rule_latency_ms": self.measured_rule_ms,
                "agent_latency_ms": self.agent_latency_ms,
                "detect_to_dispatch_s": self.detect_to_dispatch_s,
            },
            "detector": detector_info,
            "mode": {
                "mode": mode_label,
                "is_demo": is_demo,
                "is_live": is_live,
            },
            "feed_health": {
                "status": feed_status,
                "reason": feed_reason,
            },
            "camera_health": cam_snap,
        }


# Global reporter instance attached to app components
system_status_reporter = SystemStatusReporter()
