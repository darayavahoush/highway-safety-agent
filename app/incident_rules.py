"""
Edge Trigger & Incident Rule Engine.
Ultra-lightweight pure Python/NumPy logic running on live tracks.
Zero LLM in the perception loop — keeps FPS at 15-30 on CPU/Raspberry Pi.
"""

from collections import deque
import json
import math
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.incident_schema import (
    IncidentCandidate,
    IncidentSeverity,
    IncidentType,
    VehicleTelemetry,
)


class TrackHistory:
    """Keeps rolling positional & velocity history for a single track."""
    def __init__(
        self,
        track_id: int,
        label: str,
        max_points: int = 300,
        is_confirmed: bool = False,
    ):
        self.track_id = track_id
        self.label = label
        self.is_confirmed = is_confirmed
        # Deque of (timestamp, cx, cy, w, h, ground_x, ground_y) - 300 points holds 6s @ 50fps or 25s @ 12hz
        self.history: deque = deque(maxlen=max_points)
        self.first_seen_ts = 0.0
        self.last_seen_ts = 0.0
        self.current_speed_kmh = 0.0
        self.is_speed_valid = True
        self.invalid_speed_count = 0

    def update(
        self,
        box: Tuple[float, float, float, float],
        timestamp: float,
        px_per_meter: float = 22.0,
        max_plausible_kmh: float = 200.0,
        speed_window_s: float = 0.5,
    ):
        x, y, w, h = box
        cx = float(x + w / 2.0)
        cy = float(y + h / 2.0)
        ground_x = cx / px_per_meter
        ground_y = (y + h) / px_per_meter

        if not self.history:
            self.first_seen_ts = timestamp
            self.current_speed_kmh = 0.0
            self.is_speed_valid = True
        else:
            # Multi-frame windowed speed calculation (window >= speed_window_s)
            target_past_ts = timestamp - speed_window_s
            past_point = None

            # Find past observation closest to target_past_ts (or oldest if window not reached)
            for pt in self.history:
                if pt[0] <= target_past_ts:
                    past_point = pt
                else:
                    if past_point is None:
                        past_point = pt
                    break

            if past_point is None and self.history:
                past_point = self.history[0]

            prev_step = self.history[-1]
            dt_step = max(1e-4, timestamp - prev_step[0])
            step_dx_m = (cx - prev_step[1]) / px_per_meter
            step_dy_m = (cy - prev_step[2]) / px_per_meter
            instant_speed_kmh = (math.hypot(step_dx_m, step_dy_m) / dt_step) * 3.6

            prev_ts, prev_cx, prev_cy = past_point[0], past_point[1], past_point[2]
            dt = timestamp - prev_ts

            if dt >= 0.10:
                dx_m = (cx - prev_cx) / px_per_meter
                dy_m = (cy - prev_cy) / px_per_meter
                dist_m = math.hypot(dx_m, dy_m)
                speed_ms = dist_m / dt
                computed_kmh = speed_ms * 3.6

                if computed_kmh > max_plausible_kmh or instant_speed_kmh > max_plausible_kmh:
                    self.is_speed_valid = False
                    self.invalid_speed_count += 1
                    # Do not pass spike value to rules!
                    self.current_speed_kmh = 0.0
                else:
                    self.is_speed_valid = True
                    # EMA smoothing over valid windowed speeds
                    if self.current_speed_kmh > 0.0:
                        self.current_speed_kmh = 0.70 * computed_kmh + 0.30 * self.current_speed_kmh
                    else:
                        self.current_speed_kmh = computed_kmh

        self.history.append((timestamp, cx, cy, float(w), float(h), ground_x, ground_y))
        self.last_seen_ts = timestamp

    @property
    def displacement_vector(self) -> Tuple[float, float]:
        """Total displacement (dx, dy) in pixels over rolling history."""
        if len(self.history) < 2:
            return 0.0, 0.0
        start = self.history[0]
        end = self.history[-1]
        return end[1] - start[1], end[2] - start[2]

    @property
    def duration_seconds(self) -> float:
        if len(self.history) < 2:
            return 0.0
        if self.first_seen_ts > 0.0:
            return max(0.0, self.history[-1][0] - self.first_seen_ts)
        return self.history[-1][0] - self.history[0][0]


class EdgeTriggerEngine:
    def __init__(
        self,
        camera_config_path: str = "config/camera_config.json",
        rules_config_path: str = "config/safety_rules.json",
    ):
        with open(camera_config_path, "r", encoding="utf-8") as f:
            self.camera_cfg = json.load(f)
        with open(rules_config_path, "r", encoding="utf-8") as f:
            self.rules_cfg = json.load(f)

        self.camera_id = self.camera_cfg.get("camera_id", "CAM-01")
        self.km_marker = self.camera_cfg.get("km_marker", "KM 42.4")
        self.gps = self.camera_cfg.get("gps", {"latitude": 16.5412, "longitude": 80.6421})
        # Standardize lat/lng vs latitude/longitude
        if "latitude" in self.gps and "lat" not in self.gps:
            self.gps["lat"] = self.gps["latitude"]
            self.gps["lng"] = self.gps["longitude"]

        self.px_per_m = float(self.camera_cfg.get("pixels_per_meter", 22.0))
        self.lanes: List[Dict[str, Any]] = self.camera_cfg.get("lanes", [])

        # Motion & threshold parameters
        motion_cfg = self.rules_cfg.get("motion", {})
        self.speed_window_s = float(motion_cfg.get("speed_window_seconds", 0.5))
        self.max_plausible_kmh = float(motion_cfg.get("max_plausible_speed_kmh", 200.0))

        # Track history store: track_id -> TrackHistory
        self.tracks: Dict[int, TrackHistory] = {}
        # Tailgating duration tracker: (follower_id, leader_id) -> start_ts
        self._tailgate_pairs: Dict[Tuple[int, int], float] = {}

    def update_tracks(
        self,
        active_detections: List[Any],
        now: Optional[float] = None,
    ):
        """
        active_detections: list of tuples:
          (x, y, w, h, label, track_id) or (x, y, w, h, label, track_id, is_confirmed)
        """
        current_time = float(time.time() if now is None else now)
        active_ids = set()

        for det in active_detections:
            x, y, w, h, label, track_id = det[:6]
            is_confirmed = bool(det[6]) if len(det) > 6 else True

            active_ids.add(track_id)
            if track_id not in self.tracks:
                self.tracks[track_id] = TrackHistory(
                    track_id=track_id,
                    label=str(label),
                    is_confirmed=is_confirmed,
                )

            th = self.tracks[track_id]
            th.is_confirmed = is_confirmed
            th.label = str(label)
            th.update(
                (float(x), float(y), float(w), float(h)),
                current_time,
                px_per_meter=self.px_per_m,
                max_plausible_kmh=self.max_plausible_kmh,
                speed_window_s=self.speed_window_s,
            )

        # Evict stale tracks unseen in > 3.0s
        to_evict = [tid for tid, th in self.tracks.items() if current_time - th.last_seen_ts > 3.0]
        for tid in to_evict:
            del self.tracks[tid]

        # Clean up tailgate pairs where a vehicle disappeared
        self._tailgate_pairs = {
            pair: ts for pair, ts in self._tailgate_pairs.items()
            if pair[0] in self.tracks and pair[1] in self.tracks
        }

    def _resolve_lane(self, cx: float, cy: float, frame_w: int, frame_h: int) -> Dict[str, Any]:
        """Resolves lane configuration for centroid (cx, cy)."""
        nx = float(cx) / max(1.0, float(frame_w))
        ny = float(cy) / max(1.0, float(frame_h))

        # Check precise polygon containment
        for idx, lane in enumerate(self.lanes):
            poly = lane.get("polygon", [])
            if poly and len(poly) >= 3:
                poly_arr = np.array(poly, dtype=np.float32)
                if cv2.pointPolygonTest(poly_arr, (nx, ny), False) >= 0:
                    lane_copy = dict(lane)
                    lane_copy["_index"] = idx + 1
                    return lane_copy

        # Fallback to vertical Y band
        for idx, lane in enumerate(self.lanes):
            poly = lane.get("polygon", [])
            if poly and len(poly) >= 3:
                y_min = min(p[1] for p in poly)
                y_max = max(p[1] for p in poly)
                if y_min <= ny <= y_max:
                    lane_copy = dict(lane)
                    lane_copy["_index"] = idx + 1
                    return lane_copy

        # Default fallback travel lane
        return {
            "id": "lane_default",
            "name": "Active Highway Lane",
            "type": "travel",
            "direction": [1.0, 0.0],
            "_index": 1,
        }

    def _resolve_lane_name(self, y_fraction: float) -> str:
        for lane in self.lanes:
            poly = lane.get("polygon", [])
            if poly and len(poly) >= 3:
                y_min = min(p[1] for p in poly)
                y_max = max(p[1] for p in poly)
                if y_min <= y_fraction <= y_max:
                    return lane.get("name", lane.get("id"))
        return "Active Highway Lane"

    def _resolve_lane_index(self, y_fraction: float) -> int:
        for idx, lane in enumerate(self.lanes):
            poly = lane.get("polygon", [])
            if poly and len(poly) >= 3:
                y_min = min(p[1] for p in poly)
                y_max = max(p[1] for p in poly)
                if y_min <= y_fraction <= y_max:
                    return idx + 1
        return 1

    def evaluate_rules(self, frame_w: int, frame_h: int, now: Optional[float] = None) -> List[IncidentCandidate]:
        """
        Evaluates safety rules on active confirmed tracks.
        Enforces strict validation: zero invalid speeds or unconfirmed tracks evaluated.
        """
        current_time = float(time.time() if now is None else now)
        candidates: List[IncidentCandidate] = []

        # STRICT RULE: Ignore unconfirmed tracks AND ignore invalid speed samples (>200 km/h)
        track_list = [
            th for th in self.tracks.values()
            if th.is_confirmed and th.is_speed_valid and len(th.history) >= 4
        ]

        # -----------------------------------------------------------------
        # 1. Stalled Vehicle Detection (Travel lanes = P0, Shoulder = P2)
        # -----------------------------------------------------------------
        stalled_cfg = self.rules_cfg.get("stalled_vehicle", {})
        if stalled_cfg.get("enabled", True):
            min_sec = float(stalled_cfg.get("min_stationary_seconds", 3.0))
            max_kmh = float(stalled_cfg.get("max_speed_kmh", 3.5))
            congestion_thresh_kmh = float(stalled_cfg.get("congestion_threshold_kmh", 15.0))

            for th in track_list:
                if th.duration_seconds >= min_sec and th.current_speed_kmh <= max_kmh:
                    _, cx, cy, w, h, gx, gy = th.history[-1]
                    lane = self._resolve_lane(cx, cy, frame_w, frame_h)
                    lane_type = lane.get("type", "travel")
                    lane_name = lane.get("name", "Active Highway Lane")
                    lane_idx = lane.get("_index", 1)

                    if lane_type == "travel":
                        # Congestion check: median speed of other confirmed tracks in same lane
                        other_speeds = []
                        for other_th in track_list:
                            if other_th.track_id != th.track_id:
                                _, ocx, ocy, _, _, _, _ = other_th.history[-1]
                                other_lane = self._resolve_lane(ocx, ocy, frame_w, frame_h)
                                if other_lane.get("id") == lane.get("id"):
                                    other_speeds.append(other_th.current_speed_kmh)

                        if other_speeds and float(np.median(other_speeds)) < congestion_thresh_kmh:
                            # Traffic congestion / slowdown: suppress stalled alert
                            continue

                        # Travel Lane Stalled: P0 Critical hazard
                        vt = VehicleTelemetry(
                            trackId=th.track_id,
                            cls=th.label.lower(),
                            speedKmh=round(th.current_speed_kmh, 1),
                            lane=lane_name,
                            laneIndex=lane_idx,
                            x=round(float(cx / frame_w), 2),
                            dir=1,
                            plate=None,
                            box=[float(cx - w/2), float(cy - h/2), float(w), float(h)],
                            ground_pos=[round(gx, 2), round(gy, 2)],
                        )
                        cand = IncidentCandidate(
                            incident_type=IncidentType.STALLED_VEHICLE,
                            severity=IncidentSeverity.P0,
                            camera_id=self.camera_id,
                            km_marker=self.km_marker,
                            gps=self.gps,
                            timestamp=current_time,
                            primary_track_id=th.track_id,
                            lane_id=lane_name,
                            rule_score=0.98,
                            rule_reason=f"Vehicle #{th.track_id} ({th.label}) stationary for {round(th.duration_seconds, 1)}s in {lane_name} (speed: {round(th.current_speed_kmh, 1)} km/h). Severe collision hazard.",
                            involved_vehicles=[vt],
                            evidence_details={
                                "track_age_s": round(th.duration_seconds, 2),
                                "measured_speed_kmh": round(th.current_speed_kmh, 1),
                                "stationary_duration_s": round(th.duration_seconds, 2),
                                "lane_type": lane_type,
                                "lane_name": lane_name,
                            },
                        )
                        candidates.append(cand)

                    elif lane_type == "shoulder":
                        # Shoulder stop: P2 non-critical, ZERO dispatch
                        vt = VehicleTelemetry(
                            trackId=th.track_id,
                            cls=th.label.lower(),
                            speedKmh=round(th.current_speed_kmh, 1),
                            lane=lane_name,
                            laneIndex=lane_idx,
                            x=round(float(cx / frame_w), 2),
                            dir=1,
                            plate=None,
                            box=[float(cx - w/2), float(cy - h/2), float(w), float(h)],
                            ground_pos=[round(gx, 2), round(gy, 2)],
                        )
                        cand = IncidentCandidate(
                            incident_type=IncidentType.STALLED_VEHICLE,
                            severity=IncidentSeverity.P2,
                            camera_id=self.camera_id,
                            km_marker=self.km_marker,
                            gps=self.gps,
                            timestamp=current_time,
                            primary_track_id=th.track_id,
                            lane_id=lane_name,
                            rule_score=0.75,
                            rule_reason=f"Vehicle #{th.track_id} ({th.label}) stationary on {lane_name}. Non-critical shoulder stop, monitoring only.",
                            involved_vehicles=[vt],
                            evidence_details={
                                "track_age_s": round(th.duration_seconds, 2),
                                "measured_speed_kmh": round(th.current_speed_kmh, 1),
                                "stationary_duration_s": round(th.duration_seconds, 2),
                                "lane_type": lane_type,
                                "lane_name": lane_name,
                            },
                        )
                        candidates.append(cand)

        # -----------------------------------------------------------------
        # 2. Wrong-Way Driving Detection (Travel lanes only, age >= 2.0s, disp >= 5m)
        # -----------------------------------------------------------------
        wrong_cfg = self.rules_cfg.get("wrong_way", {})
        if wrong_cfg.get("enabled", True):
            min_age_s = float(wrong_cfg.get("min_age_seconds", 2.0))
            min_speed = float(wrong_cfg.get("min_speed_kmh", 15.0))
            min_disp_m = float(wrong_cfg.get("min_displacement_m", 5.0))
            min_angle_deg = float(wrong_cfg.get("min_angle_deg", 135.0))
            cos_threshold = math.cos(math.radians(min_angle_deg))  # -0.7071 for 135 deg

            for th in track_list:
                if th.duration_seconds < min_age_s or th.current_speed_kmh < min_speed:
                    continue

                _, cx, cy, w, h, gx, gy = th.history[-1]
                lane = self._resolve_lane(cx, cy, frame_w, frame_h)
                if lane.get("type") != "travel":
                    continue  # Only evaluate in authorized travel corridors

                # Expected lane direction unit vector
                ldir = lane.get("direction", [1.0, 0.0])
                mag = max(1e-4, math.hypot(ldir[0], ldir[1]))
                ux = ldir[0] / mag
                uy = ldir[1] / mag

                # Net displacement in metres over history
                start_pt = th.history[0]
                end_pt = th.history[-1]
                dx_m = (end_pt[1] - start_pt[1]) / self.px_per_m
                dy_m = (end_pt[2] - start_pt[2]) / self.px_per_m
                disp_norm = math.hypot(dx_m, dy_m)

                if disp_norm < min_disp_m:
                    continue

                # Dot product with authorized lane direction
                dot = (dx_m * ux + dy_m * uy)
                cos_angle = dot / disp_norm

                # Must oppose flow: dot < 0 and angle > 135 deg (cos < -0.7071)
                # and net displacement along lane opposing direction >= min_disp_m
                if cos_angle < cos_threshold and (-dot) >= min_disp_m:
                    # Verify condition was sustained across observations
                    opposing_steps = 0
                    for k in range(1, len(th.history)):
                        step_dx = (th.history[k][1] - th.history[k-1][1]) / self.px_per_m
                        step_dy = (th.history[k][2] - th.history[k-1][2]) / self.px_per_m
                        if (step_dx * ux + step_dy * uy) < 0.0:
                            opposing_steps += 1

                    sustained_ratio = opposing_steps / max(1, len(th.history) - 1)
                    if sustained_ratio >= 0.70:
                        lane_name = lane.get("name", "Active Highway Lane")
                        lane_idx = lane.get("_index", 1)
                        vt = VehicleTelemetry(
                            trackId=th.track_id,
                            cls=th.label.lower(),
                            speedKmh=round(th.current_speed_kmh, 1),
                            lane=lane_name,
                            laneIndex=lane_idx,
                            x=round(float(cx / frame_w), 2),
                            dir=-1,
                            plate=None,
                            box=[float(cx - w/2), float(cy - h/2), float(w), float(h)],
                            ground_pos=[round(gx, 2), round(gy, 2)],
                        )
                        cand = IncidentCandidate(
                            incident_type=IncidentType.WRONG_WAY_DRIVER,
                            severity=IncidentSeverity.P0,
                            camera_id=self.camera_id,
                            km_marker=self.km_marker,
                            gps=self.gps,
                            timestamp=current_time,
                            primary_track_id=th.track_id,
                            lane_id=lane_name,
                            rule_score=0.98,
                            rule_reason=f"CRITICAL: Vehicle #{th.track_id} ({th.label}) moving AGAINST authorized traffic flow at {round(th.current_speed_kmh, 1)} km/h in {lane_name} (net displacement: {round(disp_norm, 1)}m).",
                            involved_vehicles=[vt],
                            evidence_details={
                                "track_age_s": round(th.duration_seconds, 2),
                                "measured_speed_kmh": round(th.current_speed_kmh, 1),
                                "net_displacement_m": round(disp_norm, 2),
                                "opposing_displacement_m": round(-dot, 2),
                                "angle_deg": round(math.degrees(math.acos(max(-1.0, min(1.0, cos_angle)))), 1),
                                "lane_name": lane_name,
                            },
                        )
                        candidates.append(cand)

        # -----------------------------------------------------------------
        # 3. Tailgating & Time-To-Collision (TTC) Risk
        # -----------------------------------------------------------------
        ttc_cfg = self.rules_cfg.get("tailgating_ttc", {})
        if ttc_cfg.get("enabled", True) and len(track_list) >= 2:
            crit_ttc = float(ttc_cfg.get("critical_ttc_seconds", 1.2))
            min_spd = float(ttc_cfg.get("min_speed_kmh", 20.0))
            min_sustained_s = float(ttc_cfg.get("min_sustained_seconds", 1.0))
            active_tailgate_pairs = set()

            for i in range(len(track_list)):
                th_a = track_list[i]
                if th_a.current_speed_kmh < min_spd:
                    continue

                _, ax, ay, aw, ah, agx, agy = th_a.history[-1]
                lane_a = self._resolve_lane(ax, ay, frame_w, frame_h)
                if lane_a.get("type") != "travel":
                    continue

                ldir = lane_a.get("direction", [1.0, 0.0])
                mag = max(1e-4, math.hypot(ldir[0], ldir[1]))
                ux = ldir[0] / mag
                uy = ldir[1] / mag

                for j in range(len(track_list)):
                    if i == j:
                        continue
                    th_b = track_list[j]
                    if th_b.current_speed_kmh < min_spd:
                        continue

                    _, bx, by, bw, bh, bgx, bgy = th_b.history[-1]
                    lane_b = self._resolve_lane(bx, by, frame_w, frame_h)

                    # Must be in the exact same lane
                    if lane_a.get("id") != lane_b.get("id"):
                        continue

                    # Vector from Vehicle A to Vehicle B
                    v_ab_x = (bx - ax) / self.px_per_m
                    v_ab_y = (by - ay) / self.px_per_m

                    # Longitudinal headway: projection along lane travel direction
                    headway_m = v_ab_x * ux + v_ab_y * uy

                    # Bounding box physical overlap check (IoU > 0.05 indicates split boxes on the same vehicle)
                    from app.tracker import calculate_iou_matrix
                    box_a = [ax - aw / 2.0, ay - ah / 2.0, aw, ah]
                    box_b = [bx - bw / 2.0, by - bh / 2.0, bw, bh]
                    iou_ab = calculate_iou_matrix([box_a], [box_b])[0, 0]
                    if iou_ab > 0.05:
                        continue

                    # A is behind B if headway_m > 0 (minimum 1.0m headway)
                    if headway_m < 1.0 or headway_m > 40.0:
                        continue

                    # Closing speed in m/s: Vehicle A speed minus Vehicle B speed
                    v_close_ms = (th_a.current_speed_kmh - th_b.current_speed_kmh) / 3.6

                    # Strictly require closing speed > 0 (follower is actively closing in)
                    if v_close_ms <= 0.5:
                        continue

                    ttc = headway_m / v_close_ms

                    # Mixed traffic risk multiplier (Truck/Bus following Car/Bike)
                    is_mixed = (th_a.label in ["Truck", "Bus"] and th_b.label in ["Motorbike", "Car"])
                    threshold = crit_ttc * 1.3 if is_mixed else crit_ttc

                    if ttc < threshold:
                        pair_key = (th_a.track_id, th_b.track_id)
                        active_tailgate_pairs.add(pair_key)
                        if pair_key not in self._tailgate_pairs:
                            common_start_ts = max(th_a.first_seen_ts, th_b.first_seen_ts)
                            self._tailgate_pairs[pair_key] = common_start_ts

                        sustained_duration = current_time - self._tailgate_pairs[pair_key]

                        # Must be sustained >= min_sustained_s
                        if sustained_duration >= min_sustained_s:
                            lane_name = lane_a.get("name", "Active Highway Lane")
                            lane_idx = lane_a.get("_index", 1)
                            vt_a = VehicleTelemetry(
                                trackId=th_a.track_id,
                                cls=th_a.label.lower(),
                                speedKmh=round(th_a.current_speed_kmh, 1),
                                lane=lane_name,
                                laneIndex=lane_idx,
                                x=round(float(ax / frame_w), 2),
                                dir=1,
                                plate=None,
                                box=[float(ax - aw/2), float(ay - ah/2), float(aw), float(ah)],
                                ground_pos=[round(agx, 2), round(agy, 2)],
                            )
                            vt_b = VehicleTelemetry(
                                trackId=th_b.track_id,
                                cls=th_b.label.lower(),
                                speedKmh=round(th_b.current_speed_kmh, 1),
                                lane=lane_name,
                                laneIndex=lane_idx,
                                x=round(float(bx / frame_w), 2),
                                dir=1,
                                plate=None,
                                box=[float(bx - bw/2), float(by - bh/2), float(bw), float(bh)],
                                ground_pos=[round(bgx, 2), round(bgy, 2)],
                            )
                            cand = IncidentCandidate(
                                incident_type=IncidentType.TAILGATING_COLLISION_RISK,
                                severity=IncidentSeverity.P1 if not is_mixed else IncidentSeverity.P0,
                                camera_id=self.camera_id,
                                km_marker=self.km_marker,
                                gps=self.gps,
                                timestamp=current_time,
                                primary_track_id=th_a.track_id,
                                secondary_track_id=th_b.track_id,
                                lane_id=lane_name,
                                rule_score=0.92,
                                rule_reason=f"Severe collision hazard: {th_a.label} #{th_a.track_id} tailgating {th_b.label} #{th_b.track_id} (headway: {round(headway_m, 1)}m, TTC: {round(ttc, 2)}s, closing speed: {round(v_close_ms * 3.6, 1)} km/h).",
                                involved_vehicles=[vt_a, vt_b],
                                evidence_details={
                                    "follower_track_age_s": round(th_a.duration_seconds, 2),
                                    "leader_track_age_s": round(th_b.duration_seconds, 2),
                                    "follower_speed_kmh": round(th_a.current_speed_kmh, 1),
                                    "leader_speed_kmh": round(th_b.current_speed_kmh, 1),
                                    "headway_m": round(headway_m, 2),
                                    "closing_speed_kmh": round(v_close_ms * 3.6, 1),
                                    "ttc_s": round(ttc, 2),
                                    "sustained_duration_s": round(sustained_duration, 2),
                                    "lane_name": lane_name,
                                },
                            )
                            candidates.append(cand)

            # Drop tailgate pairs that are no longer active
            self._tailgate_pairs = {
                pair: ts for pair, ts in self._tailgate_pairs.items()
                if pair in active_tailgate_pairs
            }

        return candidates
