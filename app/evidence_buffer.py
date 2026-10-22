"""
Evidence ring buffer, deduplication engine, and asset generator.
Maintains a sliding 10-second window of frames and telemetry in RAM.
When a hazard triggers, generates snapshot evidence, MP4 clips, and crop quality gates.
"""

import collections
import cv2
import numpy as np
import os
import time
from typing import Dict, List, Optional, Tuple


class EvidenceBuffer:
    def __init__(
        self,
        max_seconds: float = 10.0,
        fps: float = 15.0,
        evidence_dir: str = "evidence",
        cooldown_seconds: float = 30.0,
    ):
        self.max_frames = int(max_seconds * fps)
        self.fps = fps
        self.cooldown_seconds = cooldown_seconds
        self.evidence_dir = evidence_dir
        
        self.snapshots_dir = os.path.join(evidence_dir, "snapshots")
        self.clips_dir = os.path.join(evidence_dir, "clips")
        self.crops_dir = os.path.join(evidence_dir, "crops")
        
        os.makedirs(self.snapshots_dir, exist_ok=True)
        os.makedirs(self.clips_dir, exist_ok=True)
        os.makedirs(self.crops_dir, exist_ok=True)
        
        # Sliding buffer of (timestamp, raw_frame)
        self.frame_buffer = collections.deque(maxlen=self.max_frames)
        
        # Deduplication tracker: (camera_id, incident_type, primary_track_id) -> last_fired_ts
        self._cooldown_map: Dict[Tuple[str, str, int], float] = {}

    def push_frame(self, frame: np.ndarray, timestamp: Optional[float] = None):
        """Push a frame into the sliding ring buffer."""
        ts = timestamp or time.time()
        # Keep a copy so video writer doesn't suffer mutation
        self.frame_buffer.append((ts, frame.copy()))

    def should_suppress_dedupe(self, camera_id: str, incident_type: str, track_id: int, now: Optional[float] = None) -> bool:
        """
        Deduplication gate: Returns True if this exact (camera, incident_type, track_id)
        has already fired within the cooldown period.
        """
        current_time = now or time.time()
        key = (camera_id, str(incident_type), int(track_id))
        last_fired = self._cooldown_map.get(key, 0.0)
        
        if current_time - last_fired < self.cooldown_seconds:
            return True  # Suppress duplicate alert
        
        self._cooldown_map[key] = current_time
        return False

    def save_snapshot(
        self,
        incident_id: str,
        frame: np.ndarray,
        involved_boxes: Optional[List[Tuple[int, int, int, int, str]]] = None,
    ) -> str:
        """
        Saves a marked snapshot showing the incident scene with tactical brackets.
        """
        annotated = frame.copy()
        if involved_boxes:
            for (x, y, w, h, label) in involved_boxes:
                # Tactical red/amber incident box
                cv2.rectangle(annotated, (int(x), int(y)), (int(x + w), int(y + h)), (0, 0, 255), 2)
                tag = f"HAZARD: {label}"
                cv2.rectangle(annotated, (int(x), max(0, int(y) - 20)), (int(x + 140), int(y)), (0, 0, 255), -1)
                cv2.putText(annotated, tag, (int(x) + 4, max(14, int(y) - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        filename = f"{incident_id}.jpg"
        filepath = os.path.join(self.snapshots_dir, filename)
        cv2.imwrite(filepath, annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return filepath

    def save_clip(self, incident_id: str) -> Optional[str]:
        """
        Compiles the last 5-10s of buffered frames into an evidence MP4 clip.
        Essential for police, insurance, and court validation.
        """
        if not self.frame_buffer:
            return None

        filename = f"{incident_id}.mp4"
        filepath = os.path.join(self.clips_dir, filename)
        
        sample_frame = self.frame_buffer[0][1]
        h, w = sample_frame.shape[:2]
        
        # Use mp4v or avc1 codec
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(filepath, fourcc, self.fps, (w, h))
        
        for _, frame in list(self.frame_buffer):
            writer.write(frame)
        writer.release()
        
        return filepath

    def extract_quality_crop(self, frame: np.ndarray, box: Tuple[int, int, int, int], track_id: int) -> Tuple[str, float]:
        """
        Extracts vehicle crop and scores its quality using Laplacian variance.
        High Laplacian variance (> 100) indicates sharp, in-focus vehicle/plate.
        """
        h_img, w_img = frame.shape[:2]
        x, y, w, h = [int(v) for v in box]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w_img, x + w)
        y2 = min(h_img, y + h)

        if x2 <= x1 or y2 <= y1:
            return "", 0.0

        crop = frame[y1:y2, x1:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        crop_path = os.path.join(self.crops_dir, f"track_{track_id}_{int(time.time()*1000)}.jpg")
        cv2.imwrite(crop_path, crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return crop_path, sharpness
