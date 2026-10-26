"""
Threaded video capture that always exposes the LATEST frame.

Why this exists: cv2.VideoCapture buffers frames internally. If your
processing loop is slower than the camera's FPS (common on CPU), the
buffer fills up and you start processing frames that are seconds old,
with the lag growing over time. This class runs capture in its own
thread, continuously grabbing frames and discarding all but the most
recent one, so processing always sees "now", not a growing backlog.
"""

import os
import threading
import time
import cv2


VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")


class LatestFrameReader:
    def __init__(self, source, reconnect_delay=2.0):
        """
        source: RTSP URL (str), video file path (str), directory of video
                 files (str), or webcam index (int).

        Passing a directory plays every video file inside it back to back,
        looping the whole set — for a batch of drone clips instead of one
        fixed camera file.
        """
        self.reconnect_delay = reconnect_delay
        self._playlist = None
        self._playlist_idx = 0

        if isinstance(source, str) and os.path.isdir(source):
            self._playlist = sorted(
                os.path.join(source, f) for f in os.listdir(source)
                if f.lower().endswith(VIDEO_EXTENSIONS)
            )
            if not self._playlist:
                raise RuntimeError(f"No video files found in directory {source!r}")
            source = self._playlist[0]
            print(f"[capture] playing {len(self._playlist)} clip(s) from {source!r}'s directory: "
                  + ", ".join(os.path.basename(p) for p in self._playlist))

        self.source = source
        # A local video file "disconnecting" just means it hit EOF — loop it
        # (or advance to the next clip in the playlist) instantly instead of
        # treating it like a dropped camera connection.
        self._is_synthetic_demo = isinstance(source, str) and source.lower() in ("synthetic_demo", "demo")
        self._is_local_file = isinstance(source, str) and os.path.isfile(source)
        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._connected = bool(self._is_synthetic_demo)
        self._pending_source = None
        self._frames_captured = 0
        self._last_frame_ts: Optional[float] = None
        self._last_error: Optional[str] = None
        self._frame_delay = 0.033
        if not self._is_local_file and not self._is_synthetic_demo and isinstance(source, str) and not source.startswith(("rtsp://", "rtsps://", "http://", "https://")):
            self._last_error = f"Video file not found at path: {source}"

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _diagnose_failure(self) -> str:
        s = str(self.source)
        if isinstance(self.source, str):
            if s.startswith(("rtsp://", "rtsps://")):
                return f"Unable to connect to RTSP stream: {s}"
            if s.startswith(("http://", "https://")):
                return f"Unable to connect to HTTP video stream: {s}"
            if not os.path.exists(s):
                return f"Video file not found at path: {s}"
        elif isinstance(self.source, int):
            return f"Cannot access webcam device index {self.source}"
        return f"Unable to open video source: {s}"

    def _open(self):
        cap = cv2.VideoCapture(self.source)
        # Keep OpenCV's own buffer as small as possible; we do our own
        # "latest frame" buffering above this layer.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        fps = cap.get(cv2.CAP_PROP_FPS)
        self._frame_delay = (1.0 / fps) if (fps and 1.0 < fps < 120.0) else 0.033
        return cap

    def _run(self):
        if getattr(self, "_is_synthetic_demo", False):
            import numpy as np
            self._connected = True
            self._last_error = None
            step = 0
            while self._running:
                step += 1
                cur_time = time.time()
                frame = np.zeros((360, 640, 3), dtype=np.uint8)
                frame[:] = (55, 55, 55)
                # Lane divider lines
                cv2.line(frame, (213, 0), (213, 360), (255, 255, 255), 2)
                cv2.line(frame, (426, 0), (426, 360), (255, 255, 255), 2)
                # Moving simulated vehicle
                car_y = int((step * 6) % 360)
                cv2.rectangle(frame, (270, car_y), (370, min(360, car_y + 50)), (180, 110, 40), -1)
                # Watermark
                cv2.putText(frame, "DEMO SIMULATION FEED", (20, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                with self._lock:
                    self._frame = frame
                    self._last_frame_ts = cur_time
                    self._frames_captured += 1
                    self._connected = True
                    self._last_error = None
                time.sleep(self._frame_delay)
            return

        self._cap = self._open()
        self._connected = bool(self._cap and self._cap.isOpened())
        if not self._connected:
            self._last_error = self._diagnose_failure()

        while self._running:
            if self._pending_source:
                with self._lock:
                    new_src = self._pending_source
                    self._pending_source = None
                    self._frame = None
                self.source = new_src
                self._is_local_file = isinstance(new_src, str) and os.path.isfile(new_src)
                if self._cap:
                    self._cap.release()
                self._cap = self._open()
                self._connected = bool(self._cap and self._cap.isOpened())
                if not self._connected:
                    self._last_error = self._diagnose_failure()
                else:
                    self._last_error = None
                continue

            if not self._cap or not self._cap.isOpened():
                self._connected = False
                self._last_error = self._diagnose_failure()
                time.sleep(self.reconnect_delay)
                self._cap = self._open()
                self._connected = bool(self._cap and self._cap.isOpened())
                if self._connected:
                    self._last_error = None
                continue

            ok, frame = self._cap.read()
            if not ok:
                if self._playlist:
                    # End of this clip — advance to the next one in the
                    # playlist (wrapping around), not just restart the same file.
                    self._playlist_idx = (self._playlist_idx + 1) % len(self._playlist)
                    self.source = self._playlist[self._playlist_idx]
                    print(f"[capture] next clip: {os.path.basename(self.source)}")
                    self._cap.release()
                    self._cap = self._open()
                    continue
                if self._is_local_file:
                    # End of file, not a dropped connection — loop instantly.
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                self._connected = False
                self._last_error = f"Stream interrupted: failed to read frame from {self.source}"
                time.sleep(self.reconnect_delay)
                self._cap.release()
                self._cap = self._open()
                continue

            cur_time = time.time()
            with self._lock:
                self._connected = True
                self._frame = frame
                self._last_frame_ts = cur_time
                self._frames_captured += 1
                self._last_error = None

            if self._is_local_file or self._playlist:
                time.sleep(self._frame_delay)

    def read(self):
        """Returns the most recent frame (or None if nothing yet)."""
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    @property
    def connected(self):
        return self._connected

    @property
    def last_frame_ts(self) -> Optional[float]:
        with self._lock:
            return self._last_frame_ts

    @property
    def frames_captured(self) -> int:
        with self._lock:
            return self._frames_captured

    @property
    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def get_status(self, now: Optional[float] = None) -> Dict[str, Any]:
        cur = time.time() if now is None else now
        with self._lock:
            last_ts = self._last_frame_ts
            frames = self._frames_captured
            connected = self._connected
            last_err = self._last_error
            src = self.source

        s = str(src)
        if getattr(self, "_is_synthetic_demo", False):
            source_type = "synthetic_demo"
        elif isinstance(src, int):
            source_type = "webcam"
        elif isinstance(src, str):
            if s.startswith(("rtsp://", "rtsps://", "http://", "https://")):
                source_type = "rtsp"
            elif self._playlist:
                source_type = "directory"
            else:
                source_type = "file"
        else:
            source_type = "unknown"

        frame_age_s = (cur - last_ts) if last_ts is not None else None
        is_stale = (frame_age_s is not None and frame_age_s > 5.0)

        if not connected:
            if source_type == "file" and not os.path.exists(s):
                state = "file_not_found"
                reason = last_err or f"Video file not found at path: {s}"
            else:
                state = "disconnected"
                reason = last_err or f"Video source unavailable or disconnected: {s}"
        elif is_stale:
            state = "stale"
            reason = f"Video stream stalled: no frame received for {frame_age_s:.1f}s"
        else:
            state = "connected"
            reason = None

        return {
            "source": s,
            "source_type": source_type,
            "connected": connected and not is_stale,
            "state": state,
            "frames_captured": frames,
            "last_frame_captured_at": last_ts,
            "frame_age_s": round(frame_age_s, 2) if frame_age_s is not None else None,
            "is_stale": is_stale,
            "reason": reason,
        }

    def get_playlist_info(self):
        with self._lock:
            if not self._playlist:
                current = os.path.basename(str(self.source))
                return {"playlist": [current], "current": current, "index": 0, "has_playlist": False}
            return {
                "playlist": [os.path.basename(p) for p in self._playlist],
                "current": os.path.basename(self._playlist[self._playlist_idx]),
                "index": self._playlist_idx,
                "has_playlist": True,
            }

    def switch_clip(self, idx: int):
        with self._lock:
            if not self._playlist or idx < 0 or idx >= len(self._playlist):
                return False
            self._playlist_idx = idx
            self.source = self._playlist[self._playlist_idx]
            self._is_local_file = True
            if self._cap:
                self._cap.release()
            self._cap = self._open()
            return True

    def set_source(self, source: str) -> bool:
        if not (isinstance(source, str) and os.path.isfile(source)):
            return False
        with self._lock:
            self._pending_source = source
        return True

    def next_clip(self):
        with self._lock:
            if not self._playlist:
                return False
            self._playlist_idx = (self._playlist_idx + 1) % len(self._playlist)
            self.source = self._playlist[self._playlist_idx]
            self._is_local_file = True
            if self._cap:
                self._cap.release()
            self._cap = self._open()
            return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()

