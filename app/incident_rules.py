"""
Edge Trigger & Incident Rule Engine.
Ultra-lightweight pure Python/NumPy logic running on live tracks.
Zero LLM in the perception loop — keeps FPS at 15-30 on CPU/Raspberry Pi.
"""

import collections
import json
import math
import numpy as np
import time
from typing import Dict, List, Optional, Tuple

from app.incident_schema import (
    IncidentCandidate,
    IncidentSeverity,
    IncidentType,
    VehicleTelemetry,
)


class TrackHistory:
    """Keeps rolling positional & velocity history for a single track."""
    def __init__(self, track_id: int, label: str, max_points: int = 45):
        self.track_id = track_id
        self.label = label
        # Deque of (timestamp, cx, cy, w, h, ground_x, ground_y)
        self.history = collections.deque(maxlen=max_points)
        self.first_seen_ts = time.time()
        self.last_seen_ts = time.time()
        self.current_speed_kmh = 0.0

    def update(self, box: Tuple[float, float, float, float], timestamp: float, px_per_meter: float = 22.0):
        x, y, w, h = box
        cx = x + w / 2.0
        cy = y + h / 2.0
        ground_x = cx / px_per_meter
        ground_y = (y + h) / px_per_meter

        if self.history:
            prev_ts, prev_cx, prev_cy, _, _, prev_gx, prev_gy = self.history[-1]
            dt = max(1e-3, timestamp - prev_ts)
            # Distance moved in meters
            dx_m = (cx - prev_cx) / px_per_meter
            dy_m = (cy - prev_cy) / px_per_meter
            dist_m = math.hypot(dx_m, dy_m)
            speed_ms = dist_m / dt
            instant_kmh = speed_ms * 3.6
            # Exponential moving average filter for smooth speed
            self.current_speed_kmh = 0.65 * instant_kmh + 0.35 * self.current_speed_kmh
        else:
            self.current_speed_kmh = 0.0

        self.history.append((timestamp, cx, cy, w, h, ground_x, ground_y))
        self.last_seen_ts = timestamp

    @property
    def displacement_vector(self) -> Tuple[float, float]:
        """Total displacement (dx, dy) over the rolling history."""
        if len(self.history) < 2:
            return 0.0, 0.0
        start = self.history[0]
        end = self.history[-1]
        return end[1] - start[1], end[2] - start[2]

    @property
    def duration_seconds(self) -> float:
        if len(self.history) < 2:
            return 0.0
        return self.history[-1][0] - self.history[0][0]


class EdgeTriggerEngine:
    def __init__(self, camera_config_path: str = "config/camera_config.json", rules_config_path: str = "config/safety_rules.json"):
        # Load configs
        with open(camera_config_path, "r") as f:
            self.camera_cfg = json.load(f)
        with open(rules_config_path, "r") as f:
            self.rules_cfg = json.load(f)

        self.camera_id = self.camera_cfg.get("camera_id", "CAM-01")
        self.km_marker = self.camera_cfg.get("km_marker", "KM 0.0")
        self.gps = self.camera_cfg.get("gps", {"lat": 16.5412, "lng": 80.6421})
        self.px_per_m = float(self.camera_cfg.get("pixels_per_meter", 22.0))
        self.flow_axis = self.camera_cfg.get("flow_direction", {}).get("primary_axis", "x")
        self.flow_sign = int(self.camera_cfg.get("flow_direction", {}).get("direction_sign", 1))

        # Track history store: track_id -> TrackHistory
        self.tracks: Dict[int, TrackHistory] = {}

    def update_tracks(self, active_detections: List[Tuple[float, float, float, float, str, int]], now: Optional[float] = None):
        """
        active_detections: list of (x, y, w, h, label, track_id)
        """
        current_time = now or time.time()
        active_ids = set()

        for (x, y, w, h, label, track_id) in active_detections:
            active_ids.add(track_id)
            if track_id not in self.tracks:
                self.tracks[track_id] = TrackHistory(track_id, label)
            self.tracks[track_id].update((x, y, w, h), current_time, self.px_per_m)

        # Evict tracks that haven't been seen in > 3 seconds
        to_evict = [tid for tid, th in self.tracks.items() if current_time - th.last_seen_ts > 3.0]
        for tid in to_evict:
            del self.tracks[tid]

    def evaluate_rules(self, frame_w: int, frame_h: int, now: Optional[float] = None) -> List[IncidentCandidate]:
        """
        Runs safety rules across all active tracks and pairs.
        Returns list of IncidentCandidates that fired on this frame.
        """
        current_time = now or time.time()
        candidates: List[IncidentCandidate] = []

        track_list = [th for th in self.tracks.values() if len(th.history) >= 4]

        # -----------------------------------------------------------------
        # 1. Stalled Vehicle Detection
        # -----------------------------------------------------------------
        stalled_cfg = self.rules_cfg.get("stalled_vehicle", {})
        if stalled_cfg.get("enabled", True):
            min_sec = float(stalled_cfg.get("min_stationary_seconds", 3.0))
            max_kmh = float(stalled_cfg.get("max_speed_kmh", 3.5))

            for th in track_list:
                if th.duration_seconds >= min_sec and th.current_speed_kmh <= max_kmh:
                    _, cx, cy, w, h, gx, gy = th.history[-1]
                    # Ensure it is in active roadway (not off the screen edges)
                    if 0.05 * frame_w < cx < 0.95 * frame_w and 0.1 * frame_h < cy < 0.9 * frame_h:
                        lane_name = self._resolve_lane_name(cy / float(frame_h))
                        lane_idx = self._resolve_lane_index(cy / float(frame_h))
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
                            severity=IncidentSeverity.CRITICAL,
                            camera_id=self.camera_id,
                            km_marker=self.km_marker,
                            gps=self.gps,
                            timestamp=current_time,
                            primary_track_id=th.track_id,
                            lane_id=lane_name,
                            rule_score=0.95,
                            rule_reason=f"Vehicle #{th.track_id} ({th.label}) stationary for {round(th.duration_seconds, 1)}s in {lane_name} (speed: {round(th.current_speed_kmh, 1)} km/h). Severe collision hazard.",
                            involved_vehicles=[vt],
                        )
                        candidates.append(cand)

        # -----------------------------------------------------------------
        # 2. Wrong-Way Driving Detection
        # -----------------------------------------------------------------
        wrong_cfg = self.rules_cfg.get("wrong_way", {})
        if wrong_cfg.get("enabled", True):
            min_speed = float(wrong_cfg.get("min_speed_kmh", 8.0))
            min_disp = float(wrong_cfg.get("min_displacement_px", 25.0))

            for th in track_list:
                dx, dy = th.displacement_vector
                axis_disp = dx if self.flow_axis == "x" else dy
                # Opposite sign indicates movement against the expected traffic flow
                is_wrong_direction = (axis_disp * self.flow_sign) < -min_disp

                if is_wrong_direction and th.current_speed_kmh >= min_speed:
                    _, cx, cy, w, h, gx, gy = th.history[-1]
                    lane_name = self._resolve_lane_name(cy / float(frame_h))
                    lane_idx = self._resolve_lane_index(cy / float(frame_h))
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
                        severity=IncidentSeverity.CRITICAL,
                        camera_id=self.camera_id,
                        km_marker=self.km_marker,
                        gps=self.gps,
                        timestamp=current_time,
                        primary_track_id=th.track_id,
                        lane_id=lane_name,
                        rule_score=0.98,
                        rule_reason=f"CRITICAL: Vehicle #{th.track_id} ({th.label}) moving AGAINST authorized traffic flow at {round(th.current_speed_kmh, 1)} km/h in {lane_name}.",
                        involved_vehicles=[vt],
                    )
                    candidates.append(cand)

        # -----------------------------------------------------------------
        # 3. Tailgating & Time-To-Collision (TTC) Risk
        # -----------------------------------------------------------------
        ttc_cfg = self.rules_cfg.get("tailgating_ttc", {})
        if ttc_cfg.get("enabled", True) and len(track_list) >= 2:
            crit_ttc = float(ttc_cfg.get("critical_ttc_seconds", 1.2))
            min_spd = float(ttc_cfg.get("min_speed_kmh", 15.0))

            for i in range(len(track_list)):
                th_a = track_list[i]
                if th_a.current_speed_kmh < min_spd:
                    continue

                for j in range(len(track_list)):
                    if i == j:
                        continue
                    th_b = track_list[j]

                    _, ax, ay, aw, ah, agx, agy = th_a.history[-1]
                    _, bx, by, bw, bh, bgx, bgy = th_b.history[-1]

                    # Check if they are in the same or adjacent vertical lane band
                    lane_diff = abs(ay - by)
                    if lane_diff > (ah + bh) * 0.9:
                        continue  # In totally different lanes

                    # Check longitudinal direction: Is Vehicle A approaching Vehicle B from behind?
                    # In +X flow, A is behind B if ax < bx
                    longitudinal_dist_px = (bx - ax) * self.flow_sign
                    if longitudinal_dist_px <= 0 or longitudinal_dist_px > (frame_w * 0.5):
                        continue

                    dist_meters = longitudinal_dist_px / self.px_per_m
                    rel_speed_kmh = th_a.current_speed_kmh - th_b.current_speed_kmh
                    rel_speed_ms = rel_speed_kmh / 3.6

                    if rel_speed_ms > 1.5:  # Vehicle A is closing in rapidly
                        ttc = dist_meters / rel_speed_ms
                        
                        # Mixed traffic danger multiplier (e.g. Truck tailgating Bike or Car)
                        is_mixed = (th_a.label in ["Truck", "Bus"] and th_b.label in ["Motorbike", "Car"])
                        threshold = crit_ttc * 1.3 if is_mixed else crit_ttc

                        if ttc < threshold:
                            lane_name_a = self._resolve_lane_name(ay / float(frame_h))
                            lane_idx_a = self._resolve_lane_index(ay / float(frame_h))
                            vt_a = VehicleTelemetry(
                                trackId=th_a.track_id,
                                cls=th_a.label.lower(),
                                speedKmh=round(th_a.current_speed_kmh, 1),
                                lane=lane_name_a,
                                laneIndex=lane_idx_a,
                                x=round(float(ax / frame_w), 2),
                                dir=1,
                                plate=None,
                                box=[float(ax - aw/2), float(ay - ah/2), float(aw), float(ah)],
                                ground_pos=[round(agx, 2), round(agy, 2)],
                            )
                            lane_name_b = self._resolve_lane_name(by / float(frame_h))
                            lane_idx_b = self._resolve_lane_index(by / float(frame_h))
                            vt_b = VehicleTelemetry(
                                trackId=th_b.track_id,
                                cls=th_b.label.lower(),
                                speedKmh=round(th_b.current_speed_kmh, 1),
                                lane=lane_name_b,
                                laneIndex=lane_idx_b,
                                x=round(float(bx / frame_w), 2),
                                dir=1,
                                plate=None,
                                box=[float(bx - bw/2), float(by - bh/2), float(bw), float(bh)],
                                ground_pos=[round(bgx, 2), round(bgy, 2)],
                            )
                            cand = IncidentCandidate(
                                incident_type=IncidentType.TAILGATING_COLLISION_RISK,
                                severity=IncidentSeverity.HIGH if not is_mixed else IncidentSeverity.CRITICAL,
                                camera_id=self.camera_id,
                                km_marker=self.km_marker,
                                gps=self.gps,
                                timestamp=current_time,
                                primary_track_id=th_a.track_id,
                                secondary_track_id=th_b.track_id,
                                lane_id=self._resolve_lane_name(ay / float(frame_h)),
                                rule_score=0.90,
                                rule_reason=f"Severe collision hazard: {th_a.label} #{th_a.track_id} tailgating {th_b.label} #{th_b.track_id} (headway: {round(dist_meters, 1)}m, TTC: {round(ttc, 2)}s, closing speed: {round(rel_speed_kmh, 1)} km/h).",
                                involved_vehicles=[vt_a, vt_b],
                            )
                            candidates.append(cand)

        return candidates

    def _resolve_lane_name(self, y_fraction: float) -> str:
        """Resolves lane identifier from camera configuration."""
        for lane in self.camera_cfg.get("lanes", []):
            poly = lane.get("polygon", [])
            if poly and len(poly) >= 3:
                y_min = min(p[1] for p in poly)
                y_max = max(p[1] for p in poly)
                if y_min <= y_fraction <= y_max:
                    return lane.get("name", lane.get("id"))
        return "Active Highway Lane"

    def _resolve_lane_index(self, y_fraction: float) -> int:
        for idx, lane in enumerate(self.camera_cfg.get("lanes", [])):
            poly = lane.get("polygon", [])
            if poly and len(poly) >= 3:
                y_min = min(p[1] for p in poly)
                y_max = max(p[1] for p in poly)
                if y_min <= y_fraction <= y_max:
                    return idx + 1
        return 1
