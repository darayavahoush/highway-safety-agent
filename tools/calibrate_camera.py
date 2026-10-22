"""
Interactive Camera Calibration Tool for Highway Safety Agent.
Generates camera_config.json with:
- Slow Lane polygon (4 points)
- Fast Lane polygon (4 points)
- Expected traffic flow direction vector (2 points)
- Pixel-to-metre scale from a known road distance (2 points + metric input)

Supports both interactive OpenCV GUI clicking and scripted/headless fallback.
"""

import argparse
import json
import math
import os
import sys
import cv2
import numpy as np

HOMOGRAPHY_DISCLAIMER = """
========================================================================================
CALIBRATION GEOMETRIC NOTICE:
A single linear scale (pixels_per_meter) is an approximation strictly valid only for 
roughly top-down (nadir drone) or completely flat highway perspectives.
In a real roadside pole or overhead gantry camera, perspective foreshortening causes 
distant pixels to represent significantly more ground metres than near foreground pixels.
For high-speed highway enforcement, a 3x3 Inverse Perspective Mapping (IPM) homography 
matrix (cv2.findHomography / cv2.warpPerspective) is mathematically necessary to map 
trapezoidal road planes into an orthographic metric bird's-eye view.
========================================================================================
"""


def parse_args():
    parser = argparse.ArgumentParser(description="Calibrate highway camera lanes, flow, and scale.")
    parser.add_argument("--video", required=True, help="Path to reference video file.")
    parser.add_argument("--out", default="config/camera_config.json", help="Output path for camera_config.json.")
    parser.add_argument("--highway", default="NH-16 (Chennai - Kolkata Corridor)", help="Highway name.")
    parser.add_argument("--section", default="Vijayawada - Guntur Highway Stretch, Andhra Pradesh", help="Highway section.")
    parser.add_argument("--km", default="KM 42.4", help="Kilometer marker.")
    parser.add_argument("--camera-id", default="CAM-AP-NH16-KM42", help="Camera identifier.")
    parser.add_argument("--towards", default="Visakhapatnam", help="Direction towards.")
    parser.add_argument("--opposite", default="Vijayawada", help="Direction opposite.")
    parser.add_argument("--known-distance-m", type=float, default=10.0, help="Real-world reference distance in metres.")
    parser.add_argument("--headless", action="store_true", help="Run without opening an X11/Cocoa GUI window.")
    return parser.parse_args()


class CalibrationSession:
    def __init__(self, frame: np.ndarray, known_dist_m: float = 10.0):
        self.orig_frame = frame
        self.h, self.w = frame.shape[:2]
        self.known_dist_m = known_dist_m
        
        self.slow_lane_pts = []  # 4 pts
        self.fast_lane_pts = []  # 4 pts
        self.flow_pts = []       # 2 pts (start -> end)
        self.scale_pts = []      # 2 pts
        
        self.step = 0  # 0: slow, 1: fast, 2: flow, 3: scale, 4: done

    def on_mouse(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        if self.step == 0:
            self.slow_lane_pts.append((x, y))
            if len(self.slow_lane_pts) == 4:
                print(f"[Calibrator] Slow lane defined: {self.slow_lane_pts}")
                self.step = 1
        elif self.step == 1:
            self.fast_lane_pts.append((x, y))
            if len(self.fast_lane_pts) == 4:
                print(f"[Calibrator] Fast lane defined: {self.fast_lane_pts}")
                self.step = 2
        elif self.step == 2:
            self.flow_pts.append((x, y))
            if len(self.flow_pts) == 2:
                print(f"[Calibrator] Direction vector defined: {self.flow_pts[0]} -> {self.flow_pts[1]}")
                self.step = 3
        elif self.step == 3:
            self.scale_pts.append((x, y))
            if len(self.scale_pts) == 2:
                px_dist = math.hypot(self.scale_pts[1][0] - self.scale_pts[0][0], self.scale_pts[1][1] - self.scale_pts[0][1])
                print(f"[Calibrator] Scale reference points: {self.scale_pts}, pixel length = {px_dist:.1f}px")
                self.step = 4

    def render(self) -> np.ndarray:
        display = self.orig_frame.copy()

        # Step overlay banner
        banner_text = ""
        if self.step == 0:
            banner_text = f"STEP 1/4: Click 4 points for SLOW LANE polygon ({len(self.slow_lane_pts)}/4)"
        elif self.step == 1:
            banner_text = f"STEP 2/4: Click 4 points for FAST LANE polygon ({len(self.fast_lane_pts)}/4)"
        elif self.step == 2:
            banner_text = f"STEP 3/4: Click 2 points for FLOW DIRECTION arrow ({len(self.flow_pts)}/2)"
        elif self.step == 3:
            banner_text = f"STEP 4/4: Click 2 points for {self.known_dist_m}m KNOWN DISTANCE ({len(self.scale_pts)}/2)"
        else:
            banner_text = "CALIBRATION COMPLETE: Press any key to save and exit"

        cv2.rectangle(display, (0, 0), (self.w, 40), (20, 30, 45), -1)
        cv2.putText(display, banner_text, (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (56, 189, 248), 2)

        # Draw slow lane (Amber)
        for pt in self.slow_lane_pts:
            cv2.circle(display, pt, 5, (0, 165, 255), -1)
        if len(self.slow_lane_pts) >= 2:
            pts_arr = np.array(self.slow_lane_pts, np.int32).reshape((-1, 1, 2))
            cv2.polylines(display, [pts_arr], len(self.slow_lane_pts) == 4, (0, 165, 255), 2)

        # Draw fast lane (Green)
        for pt in self.fast_lane_pts:
            cv2.circle(display, pt, 5, (0, 255, 128), -1)
        if len(self.fast_lane_pts) >= 2:
            pts_arr = np.array(self.fast_lane_pts, np.int32).reshape((-1, 1, 2))
            cv2.polylines(display, [pts_arr], len(self.fast_lane_pts) == 4, (0, 255, 128), 2)

        # Draw flow direction (Blue Arrow)
        if len(self.flow_pts) == 1:
            cv2.circle(display, self.flow_pts[0], 5, (255, 100, 0), -1)
        elif len(self.flow_pts) == 2:
            cv2.arrowedLine(display, self.flow_pts[0], self.flow_pts[1], (255, 100, 0), 3, tipLength=0.2)

        # Draw scale line (Pink)
        if len(self.scale_pts) == 1:
            cv2.circle(display, self.scale_pts[0], 5, (255, 0, 255), -1)
        elif len(self.scale_pts) == 2:
            cv2.line(display, self.scale_pts[0], self.scale_pts[1], (255, 0, 255), 2)
            mid = ((self.scale_pts[0][0] + self.scale_pts[1][0]) // 2, (self.scale_pts[0][1] + self.scale_pts[1][1]) // 2)
            cv2.putText(display, f"{self.known_dist_m}m", mid, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

        return display


def run_calibration():
    args = parse_args()
    print(HOMOGRAPHY_DISCLAIMER)

    if not os.path.isfile(args.video):
        print(f"ERROR: Video file not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    cap = cv2.VideoCapture(args.video)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print(f"ERROR: Failed to read initial frame from {args.video}", file=sys.stderr)
        sys.exit(1)

    h, w = frame.shape[:2]
    print(f"Loaded frame resolution: {w}x{h} from {args.video}")

    session = CalibrationSession(frame, known_dist_m=args.known_distance_m)

    can_use_gui = not args.headless and bool(os.getenv("DISPLAY") or sys.platform == "darwin")

    if can_use_gui:
        try:
            window_name = "Highway Camera Calibration (Click points)"
            cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
            cv2.setMouseCallback(window_name, session.on_mouse)

            while session.step < 4:
                disp = session.render()
                cv2.imshow(window_name, disp)
                key = cv2.waitKey(30) & 0xFF
                if key == 27 or key == ord("q"):
                    print("Calibration aborted by user.")
                    cv2.destroyAllWindows()
                    sys.exit(0)

            # Show final state briefly
            disp = session.render()
            cv2.imshow(window_name, disp)
            cv2.waitKey(1000)
            cv2.destroyAllWindows()
        except cv2.error as e:
            print(f"[Calibrator] OpenCV GUI unavailable ({e}). Falling back to robust default calibration.")
            can_use_gui = False

    if not can_use_gui or session.step < 4:
        # Default top-down drone corridor geometry (normalized for 640x360 or scaled)
        session.slow_lane_pts = [(0, int(h * 0.45)), (w, int(h * 0.45)), (w, int(h * 0.85)), (0, int(h * 0.85))]
        session.fast_lane_pts = [(0, int(h * 0.15)), (w, int(h * 0.15)), (w, int(h * 0.45)), (0, int(h * 0.45))]
        session.flow_pts = [(int(w * 0.2), int(h * 0.3)), (int(w * 0.8), int(h * 0.3))]
        session.scale_pts = [(int(w * 0.3), int(h * 0.5)), (int(w * 0.3 + 220), int(h * 0.5))]

    # 1. Compute scale (pixels_per_meter)
    p1, p2 = session.scale_pts
    pixel_dist = max(1.0, math.hypot(p2[0] - p1[0], p2[1] - p1[1]))
    pixels_per_meter = round(pixel_dist / max(0.1, args.known_distance_m), 2)

    # 2. Compute normalized flow direction vector
    f1, f2 = session.flow_pts
    raw_dx = float(f2[0] - f1[0])
    raw_dy = float(f2[1] - f1[1])
    flow_mag = max(1e-4, math.hypot(raw_dx, raw_dy))
    lane_dir = [round(raw_dx / flow_mag, 3), round(raw_dy / flow_mag, 3)]

    # 3. Format lane polygons in normalized 0..1 coordinates
    def norm_poly(pts):
        return [[round(x / float(w), 3), round(y / float(h), 3)] for (x, y) in pts]

    config_payload = {
        "camera_id": args.camera_id,
        "highway": args.highway,
        "section": args.section,
        "km_marker": args.km,
        "towards": args.towards,
        "opposite": args.opposite,
        "gps": {
            "latitude": 16.5412,
            "longitude": 80.6421,
        },
        "pixels_per_meter": pixels_per_meter,
        "lanes": [
            {
                "id": "lane_1_fast",
                "name": "Fast / Overtaking Lane (Right)",
                "type": "travel",
                "direction": lane_dir,
                "polygon": norm_poly(session.fast_lane_pts),
                "speed_limit_kmh": 100,
                "allowed_classes": ["Car", "Van"],
            },
            {
                "id": "lane_2_slow",
                "name": "Heavy Vehicle & Mixed Lane (Left)",
                "type": "travel",
                "direction": lane_dir,
                "polygon": norm_poly(session.slow_lane_pts),
                "speed_limit_kmh": 80,
                "allowed_classes": ["Truck", "Bus", "Car", "Van", "Motorbike"],
            },
            {
                "id": "lane_3_shoulder",
                "name": "Emergency Shoulder",
                "type": "shoulder",
                "direction": lane_dir,
                "polygon": [[0.0, 0.85], [1.0, 0.85], [1.0, 1.0], [0.0, 1.0]],
                "speed_limit_kmh": 0,
                "allowed_classes": [],
            },
        ],
        "emergency_contacts": {
            "police_control_room": "Mangalagiri Highway Police Station (+91-8645-230000)",
            "medical_trauma_108": "AIIMS Mangalagiri Trauma Center (108)",
            "nhai_patrol_crane": "Kaza NHAI Toll Plaza Route Patrol (+91-1033)",
            "vms_gantry_id": "VMS-NH16-GANTRY-04",
        },
    }

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(config_payload, f, indent=2)

    print(f"\n[Calibrator] SUCCESS: Calibration saved to: {out_path}")
    print(f"  * Pixels per metre: {pixels_per_meter} px/m (measured {pixel_dist:.1f}px for {args.known_distance_m}m)")
    print(f"  * Flow axis: '{primary_axis}', sign: {direction_sign}")
    print(f"  * Fast lane polygon: {norm_poly(session.fast_lane_pts)}")
    print(f"  * Slow lane polygon: {norm_poly(session.slow_lane_pts)}")


if __name__ == "__main__":
    run_calibration()
