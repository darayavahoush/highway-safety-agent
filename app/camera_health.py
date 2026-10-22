"""
Camera Health & Photometric Environmental Telemetry Engine.
Analyzes live video frames in real-time on CPU:
1. Camera Motion Stability: Static Locked vs Wind Vibration/Sway vs Moving/Drone Drift.
   Uses sparse optical flow on static background regions.
2. Photometric Lighting Quality:
   Evaluates mean luminance, RMS contrast, and dynamic range to categorize:
   - OPTIMAL_DAYLIGHT
   - LOW_LIGHT_DUSK (triggers dusk safety elevation)
   - NIGHT_VISION (triggers night safety protocol)
   - GLARE_OVEREXPOSURE
   - LOW_CONTRAST_FOG
"""

import math
import time
from typing import Dict, Any, Optional, Tuple, List
import cv2
import numpy as np


class CameraHealthAnalyzer:
    def __init__(
        self,
        motion_sample_interval_s: float = 0.5,
        static_drift_threshold_px: float = 1.8,
        sway_threshold_px: float = 5.0,
    ):
        self.motion_sample_interval_s = motion_sample_interval_s
        self.static_drift_threshold_px = static_drift_threshold_px
        self.sway_threshold_px = sway_threshold_px

        self.last_eval_time = 0.0
        self.prev_gray: Optional[np.ndarray] = None
        self.prev_pts: Optional[np.ndarray] = None

        # Cached telemetry state
        self.cached_health: Dict[str, Any] = {
            "is_static": True,
            "camera_stability": "STATIC_LOCKED",
            "background_drift_px": 0.0,
            "motion_status": "Static highway surveillance pole / gantry mount",
            "lighting_condition": "OPTIMAL_DAYLIGHT",
            "is_night_or_dusk": False,
            "avg_luminance": 128.0,
            "contrast_rms": 52.0,
            "visibility_score": 96.0,
            "evaluated_at": time.time() * 1000,
        }

    def analyze_frame(
        self,
        frame: np.ndarray,
        active_boxes: Optional[List[List[float]]] = None,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Analyzes frame luminance and background optical flow displacement.
        Downsampled to 320x180 for sub-millisecond execution.
        """
        cur_time = float(time.time() if now is None else now)
        if cur_time - self.last_eval_time < self.motion_sample_interval_s:
            return self.cached_health

        h, w = frame.shape[:2]
        small_w, small_h = 320, 180
        small_frame = cv2.resize(frame, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
        gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)

        # -------------------------------------------------------------
        # 1. Photometric Lighting & Visibility Analysis
        # -------------------------------------------------------------
        mean_lum = float(np.mean(gray))
        rms_contrast = float(np.std(gray))

        # Dynamic Range & Overexposure check
        high_pixel_ratio = float(np.sum(gray > 240) / gray.size)

        if mean_lum < 38.0:
            lighting = "NIGHT_VISION"
            is_night = True
            vis_score = max(30.0, mean_lum * 1.5)
        elif mean_lum < 75.0:
            lighting = "LOW_LIGHT_DUSK"
            is_night = True
            vis_score = 65.0 + (mean_lum - 38.0) * 0.6
        elif high_pixel_ratio > 0.20 or mean_lum > 215.0:
            lighting = "GLARE_OVEREXPOSURE"
            is_night = False
            vis_score = 70.0
        elif rms_contrast < 22.0:
            lighting = "LOW_CONTRAST_FOG"
            is_night = False
            vis_score = 55.0
        else:
            lighting = "OPTIMAL_DAYLIGHT"
            is_night = False
            vis_score = min(99.0, 80.0 + (rms_contrast / 60.0) * 19.0)

        # -------------------------------------------------------------
        # 2. Camera Motion Stability (Optical Flow on Background)
        # -------------------------------------------------------------
        drift_px = 0.0
        stability = "STATIC_LOCKED"
        is_static = True
        status_msg = "Static highway surveillance pole / gantry mount (Stable)"

        # Mask out active moving vehicle bounding boxes to measure true background drift
        bg_mask = np.ones((small_h, small_w), dtype=np.uint8) * 255
        scale_x = small_w / float(w)
        scale_y = small_h / float(h)

        if active_boxes:
            for box in active_boxes:
                bx, by, bw, bh = box[:4]
                sx = max(0, int(bx * scale_x))
                sy = max(0, int(by * scale_y))
                sw = min(small_w - sx, int(bw * scale_x))
                sh = min(small_h - sy, int(bh * scale_y))
                if sw > 0 and sh > 0:
                    bg_mask[sy : sy + sh, sx : sx + sw] = 0

        if self.prev_gray is not None and self.prev_pts is not None and len(self.prev_pts) > 6:
            # Calculate Lucas-Kanade optical flow
            cur_pts, status, _ = cv2.calcOpticalFlowPyrLK(
                self.prev_gray,
                gray,
                self.prev_pts,
                None,
                winSize=(15, 15),
                maxLevel=2,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
            )

            if cur_pts is not None and status is not None:
                good_prev = self.prev_pts[status == 1]
                good_cur = cur_pts[status == 1]

                if len(good_prev) >= 5:
                    displacements = np.linalg.norm(good_cur - good_prev, axis=1)
                    # Use median displacement to reject isolated moving foreground anomalies
                    med_disp = float(np.median(displacements))
                    # Scale back to original resolution coordinates
                    drift_px = round(med_disp * (w / small_w), 2)

                    if drift_px <= self.static_drift_threshold_px:
                        stability = "STATIC_LOCKED"
                        is_static = True
                        status_msg = f"Camera locked on fixed gantry. Background drift: {drift_px}px (sub-pixel stable)."
                    elif drift_px <= self.sway_threshold_px:
                        stability = "WIND_SWAY"
                        is_static = True
                        status_msg = f"Minor wind vibration or pole sway detected ({drift_px}px). Tracking filtered."
                    else:
                        stability = "PANNING_OR_DRIFT"
                        is_static = False
                        status_msg = f"Active camera motion or drone drift detected ({drift_px}px). Global motion compensated."

        # Re-detect Shi-Tomasi good features on static background for next cycle
        new_pts = cv2.goodFeaturesToTrack(
            gray,
            maxCorners=60,
            qualityLevel=0.04,
            minDistance=12,
            mask=bg_mask,
        )

        self.prev_gray = gray.copy()
        self.prev_pts = new_pts
        self.last_eval_time = cur_time

        self.cached_health = {
            "is_static": is_static,
            "camera_stability": stability,
            "background_drift_px": drift_px,
            "motion_status": status_msg,
            "lighting_condition": lighting,
            "is_night_or_dusk": is_night,
            "avg_luminance": round(mean_lum, 1),
            "contrast_rms": round(rms_contrast, 1),
            "visibility_score": round(vis_score, 1),
            "evaluated_at": cur_time * 1000,
        }

        return self.cached_health


# Singleton instance
camera_health_analyzer = CameraHealthAnalyzer()
