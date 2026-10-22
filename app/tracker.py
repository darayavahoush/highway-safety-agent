"""
Multi-Object Tracker with ByteTrack-style Two-Stage Association & Kalman Filtering.

Features:
- Kalman filter estimation of 2D bounding boxes [cx, cy, w, h, vcx, vcy, vw, vh].
- Two-stage association using scipy.optimize.linear_sum_assignment:
    Stage 1: High-confidence detections matched against predicted tracks via IoU.
    Stage 2: Low-confidence detections matched against remaining tracks via IoU.
- Track confirmation: A track is only 'confirmed' after N consecutive hits (default 5).
- Lost track persistence: Maintained in video seconds (default 1.0s) rather than raw frames.
- Label stability: Majority voting across observation history prevents class flipping (Car vs Truck).
- LineCrossingCounter: Virtual tripwire vehicle counting for highway traffic telemetry.
"""

from collections import Counter, deque
import math
import time
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
from scipy.optimize import linear_sum_assignment


def _centroid(box: Tuple[float, float, float, float]) -> Tuple[float, float]:
    x, y, w, h = box
    return (float(x + w / 2.0), float(y + h / 2.0))


def _side_of_line(point: Tuple[float, float], line: Tuple[Tuple[float, float], Tuple[float, float]]) -> int:
    """Sign of the cross product; tells us which side of the line a point is on."""
    (x1, y1), (x2, y2) = line
    px, py = point
    cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
    if cross > 0:
        return 1
    if cross < 0:
        return -1
    return 0


def calculate_iou_matrix(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    """
    Computes pairwise IoU matrix between boxes_a (M, 4) and boxes_b (N, 4).
    Each box is in format [x, y, w, h].
    Returns (M, N) matrix with IoU values in [0.0, 1.0].
    """
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float32)

    a = np.atleast_2d(np.asarray(boxes_a, dtype=np.float32))
    b = np.atleast_2d(np.asarray(boxes_b, dtype=np.float32))

    ax1 = a[:, 0]
    ay1 = a[:, 1]
    ax2 = a[:, 0] + np.maximum(0.0, a[:, 2])
    ay2 = a[:, 1] + np.maximum(0.0, a[:, 3])

    bx1 = b[:, 0]
    by1 = b[:, 1]
    bx2 = b[:, 0] + np.maximum(0.0, b[:, 2])
    by2 = b[:, 1] + np.maximum(0.0, b[:, 3])

    inter_x1 = np.maximum(ax1[:, None], bx1[None, :])
    inter_y1 = np.maximum(ay1[:, None], by1[None, :])
    inter_x2 = np.minimum(ax2[:, None], bx2[None, :])
    inter_y2 = np.minimum(ay2[:, None], by2[None, :])

    inter_w = np.maximum(0.0, inter_x2 - inter_x1)
    inter_h = np.maximum(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = np.maximum(0.0, a[:, 2]) * np.maximum(0.0, a[:, 3])
    area_b = np.maximum(0.0, b[:, 2]) * np.maximum(0.0, b[:, 3])
    union_area = area_a[:, None] + area_b[None, :] - inter_area

    iou = np.where(union_area > 1e-6, inter_area / union_area, 0.0)
    return iou.astype(np.float32)


class KalmanBoxTracker:
    """
    Constant velocity Kalman filter for 2D bounding boxes:
    State: [cx, cy, w, h, vcx, vcy, vw, vh]^T
    Measurement: [cx, cy, w, h]^T
    """
    def __init__(self, box: Tuple[float, float, float, float]):
        x, y, w, h = box
        cx = x + w / 2.0
        cy = y + h / 2.0

        # State vector [8, 1]
        self.x = np.array([[cx], [cy], [w], [h], [0.0], [0.0], [0.0], [0.0]], dtype=np.float32)

        # State covariance P [8, 8]
        self.P = np.diag([10.0, 10.0, 10.0, 10.0, 1000.0, 1000.0, 1000.0, 1000.0]).astype(np.float32)

        # Measurement matrix H [4, 8]
        self.H = np.zeros((4, 8), dtype=np.float32)
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0
        self.H[2, 2] = 1.0
        self.H[3, 3] = 1.0

        # Measurement noise R [4, 4]
        self.R = np.diag([1.0, 1.0, 2.0, 2.0]).astype(np.float32)

    def predict(self, dt: float = 0.02) -> Tuple[float, float, float, float]:
        """Predicts state ahead by dt seconds."""
        dt = float(max(1e-4, min(1.0, dt)))

        # Transition matrix F [8, 8]
        F = np.eye(8, dtype=np.float32)
        F[0, 4] = dt
        F[1, 5] = dt
        F[2, 6] = dt
        F[3, 7] = dt

        # Process noise covariance Q [8, 8]
        Q = np.diag([1.0, 1.0, 1.0, 1.0, 100.0, 100.0, 25.0, 25.0]).astype(np.float32)

        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

        return self.get_box()

    def update(self, box: Tuple[float, float, float, float]):
        """Kalman update step with new detection measurement [x, y, w, h]."""
        x, y, w, h = box
        cx = x + w / 2.0
        cy = y + h / 2.0
        z = np.array([[cx], [cy], [w], [h]], dtype=np.float32)

        y_res = z - (self.H @ self.x)
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)

        self.x = self.x + K @ y_res
        I = np.eye(8, dtype=np.float32)
        self.P = (I - K @ self.H) @ self.P

    def get_box(self) -> Tuple[float, float, float, float]:
        cx = float(self.x[0, 0])
        cy = float(self.x[1, 0])
        w = max(2.0, float(self.x[2, 0]))
        h = max(2.0, float(self.x[3, 0]))
        x = cx - w / 2.0
        y = cy - h / 2.0
        return (x, y, w, h)

    def get_velocity(self) -> Tuple[float, float]:
        vcx = float(self.x[4, 0])
        vcy = float(self.x[5, 0])
        return (vcx, vcy)


class Track:
    """Stateful representation of a tracked vehicle."""
    def __init__(
        self,
        track_id: int,
        box: Tuple[float, float, float, float],
        label: str,
        confidence: float,
        side: int = 0,
        timestamp: float = 0.0,
        min_hits: int = 5,
    ):
        self.id = track_id
        self.kf = KalmanBoxTracker(box)
        self.box = box
        self.centroid = _centroid(box)
        self.confidence = float(confidence)
        self.side = side
        self.min_hits = min_hits

        self.hits = 1
        self.age = 1
        self.first_seen_ts = timestamp
        self.last_seen_ts = timestamp
        self.time_since_update = 0.0
        self.counted = False

        self.labels_history = deque(maxlen=40)
        self.labels_history.append(label)

    @property
    def label(self) -> str:
        """Majority voting over history prevents class flip (e.g. Car <-> Truck)."""
        if not self.labels_history:
            return "Car"
        return Counter(self.labels_history).most_common(1)[0][0]

    @property
    def is_confirmed(self) -> bool:
        """A track is confirmed only after reaching min_hits consecutive associations."""
        return self.hits >= self.min_hits

    @property
    def disappeared(self) -> int:
        """Legacy compatibility: returns frame-based disappearance proxy."""
        return int(round(self.time_since_update * 50.0))

    def predict(self, dt: float) -> Tuple[float, float, float, float]:
        self.age += 1
        self.time_since_update += dt
        self.box = self.kf.predict(dt)
        self.centroid = _centroid(self.box)
        return self.box

    def update_matched(self, box: Tuple[float, float, float, float], label: str, confidence: float, timestamp: float):
        self.kf.update(box)
        self.box = self.kf.get_box()
        self.centroid = _centroid(self.box)
        self.confidence = float(confidence)
        self.labels_history.append(label)
        self.hits += 1
        self.time_since_update = 0.0
        self.last_seen_ts = timestamp


class LineCrossingCounter:
    """
    ByteTrack-style IoU + Kalman multi-object tracker and tripwire counting barrier.
    """
    def __init__(
        self,
        line: Tuple[Tuple[float, float], Tuple[float, float]],
        min_hits: int = 5,
        max_lost_time_s: float = 1.0,
        conf_high: float = 0.35,
        conf_low: float = 0.15,
        iou_threshold: float = 0.20,
        max_disappeared: int = 15,
        max_match_distance: float = 80.0,
    ):
        self.line = line
        self.min_hits = min_hits
        self.max_lost_time_s = max_lost_time_s
        self.conf_high = conf_high
        self.conf_low = conf_low
        self.iou_threshold = iou_threshold

        self._tracks: Dict[int, Track] = {}
        self._next_id = 1
        self._prev_ts: Optional[float] = None

        self.count_in = 0
        self.count_out = 0
        self.count_by_label: Dict[str, Dict[str, int]] = {}

    @property
    def total(self) -> int:
        return self.count_in + self.count_out

    def _record_crossing(self, direction: str, label: str):
        if direction == "in":
            self.count_in += 1
        else:
            self.count_out += 1
        bucket = self.count_by_label.setdefault(label, {"in": 0, "out": 0})
        bucket[direction] += 1

    def update(self, detections: List[Any], now: Optional[float] = None) -> Tuple[List[Track], List[dict]]:
        """
        detections: list of (x, y, w, h, label, confidence)
        now: current video or clock timestamp in seconds
        Returns (tracks, events).
        """
        current_time = float(time.time() if now is None else now)
        if self._prev_ts is None:
            dt = 0.02
        else:
            dt = max(1e-4, min(1.0, current_time - self._prev_ts))
        self._prev_ts = current_time

        # 1. Kalman prediction for all existing tracks
        for track in self._tracks.values():
            track.predict(dt)

        # 2. Partition detections into high and low confidence pools (ByteTrack)
        high_dets = []
        low_dets = []
        for det in detections:
            x, y, w, h, label, conf = det[:6]
            box = (float(x), float(y), float(w), float(h))
            item = (box, str(label), float(conf))
            if conf >= self.conf_high:
                high_dets.append(item)
            elif conf >= self.conf_low:
                low_dets.append(item)

        active_track_ids = list(self._tracks.keys())
        track_boxes = np.array([self._tracks[tid].box for tid in active_track_ids], dtype=np.float32) if active_track_ids else np.empty((0, 4), dtype=np.float32)

        matched_track_ids = set()
        matched_high_det_indices = set()
        events = []

        # 3. Stage 1: Match existing tracks with high-confidence detections
        if len(active_track_ids) > 0 and len(high_dets) > 0:
            high_det_boxes = np.array([d[0] for d in high_dets], dtype=np.float32)
            iou_matrix = calculate_iou_matrix(track_boxes, high_det_boxes)
            cost_matrix = 1.0 - iou_matrix

            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            for r, c in zip(row_ind, col_ind):
                if iou_matrix[r, c] >= self.iou_threshold:
                    tid = active_track_ids[r]
                    box, label, conf = high_dets[c]
                    track = self._tracks[tid]
                    track.update_matched(box, label, conf, current_time)
                    matched_track_ids.add(tid)
                    matched_high_det_indices.add(c)

        # 4. Stage 2: Match remaining tracks with low-confidence detections
        unmatched_track_ids = [tid for tid in active_track_ids if tid not in matched_track_ids]
        if len(unmatched_track_ids) > 0 and len(low_dets) > 0:
            unmatched_track_boxes = np.array([self._tracks[tid].box for tid in unmatched_track_ids], dtype=np.float32)
            low_det_boxes = np.array([d[0] for d in low_dets], dtype=np.float32)
            iou_matrix_low = calculate_iou_matrix(unmatched_track_boxes, low_det_boxes)
            cost_matrix_low = 1.0 - iou_matrix_low

            row_ind, col_ind = linear_sum_assignment(cost_matrix_low)
            for r, c in zip(row_ind, col_ind):
                if iou_matrix_low[r, c] >= self.iou_threshold:
                    tid = unmatched_track_ids[r]
                    box, label, conf = low_dets[c]
                    track = self._tracks[tid]
                    track.update_matched(box, label, conf, current_time)
                    matched_track_ids.add(tid)

        # 5. Initialize new tentative tracks for unmatched high-confidence detections
        # Suppress duplicate/split bounding boxes on already tracked vehicles
        new_boxes_this_frame = []
        for idx, (box, label, conf) in enumerate(high_dets):
            if idx not in matched_high_det_indices:
                bcx, bcy = _centroid(box)
                is_duplicate = False
                for existing_track in self._tracks.values():
                    ecx, ecy = existing_track.centroid
                    dist = float(np.hypot(bcx - ecx, bcy - ecy))
                    iou_ex = calculate_iou_matrix([box], [existing_track.box])[0, 0]
                    if iou_ex >= 0.15 or dist < 28.0:
                        is_duplicate = True
                        break

                if not is_duplicate:
                    for nbox in new_boxes_this_frame:
                        ncx, ncy = _centroid(nbox)
                        dist = float(np.hypot(bcx - ncx, bcy - ncy))
                        iou_n = calculate_iou_matrix([box], [nbox])[0, 0]
                        if iou_n >= 0.15 or dist < 28.0:
                            is_duplicate = True
                            break

                if not is_duplicate:
                    new_boxes_this_frame.append(box)
                    side = _side_of_line(_centroid(box), self.line)
                    new_track = Track(
                        track_id=self._next_id,
                        box=box,
                        label=label,
                        confidence=conf,
                        side=side,
                        timestamp=current_time,
                        min_hits=self.min_hits,
                    )
                    self._tracks[self._next_id] = new_track
                    self._next_id += 1

        # 6. Evaluate line crossing for confirmed tracks & update line side
        for track in list(self._tracks.values()):
            new_side = _side_of_line(track.centroid, self.line)
            if track.is_confirmed and track.side != 0 and new_side != 0 and new_side != track.side and not track.counted:
                direction = "in" if new_side > track.side else "out"
                self._record_crossing(direction, track.label)
                track.counted = True
                events.append({
                    "direction": direction,
                    "label": track.label,
                    "track_id": track.id,
                    "confidence": round(track.confidence, 2),
                    "timestamp": current_time,
                })
            track.side = new_side if new_side != 0 else track.side

        # 7. Evict dead tracks based on video time (max_lost_time_s)
        surviving_tracks = {}
        for tid, track in self._tracks.items():
            if track.time_since_update <= self.max_lost_time_s:
                surviving_tracks[tid] = track

        self._tracks = surviving_tracks
        return list(self._tracks.values()), events
