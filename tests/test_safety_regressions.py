"""Regression tests for safety-critical honesty rules.

1. A vehicle that has only just stopped is not a stalled vehicle yet, and incident evidence
   reports the real stopped time, not the track's age.
2. ANPR never invents a plate. Unreadable means NO READ.
"""
import os
import shutil
import sys

import cv2
import numpy as np
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.incident_schema import IncidentType
from app.incident_rules import EdgeTriggerEngine, TrackHistory
import app.anpr as anpr
from app.anpr import ANPRPipeline


def _engine():
    return EdgeTriggerEngine(camera_config_path="config/camera_config.json",
                             rules_config_path="config/safety_rules.json")


def _stalled(cands):
    return [c for c in cands if c.incident_type == IncidentType.STALLED_VEHICLE]


def _drive(engine, base, moving_steps, stopped_steps, y=250.0, tid=901):
    """Moves ~15 km/h for moving_steps (0.2 s each), then stands still for stopped_steps."""
    fired_at = None
    x = 50.0
    for i in range(moving_steps + stopped_steps):
        t = base + i * 0.2
        if i < moving_steps:
            x += 18.0
        engine.update_tracks([(x, y, 60.0, 35.0, "Car", tid, True)], now=t)
        if _stalled(engine.evaluate_rules(640, 480, now=t)) and fired_at is None:
            fired_at = i - moving_steps  # steps after stopping
    return fired_at


# ---------- stalled timing ----------

def test_long_tracked_vehicle_that_just_stopped_does_not_fire_at_once():
    # Tracked for 5 s, stopped for only ~1.4 s: old code fired here because track age >= 3 s.
    engine = _engine()
    fired_at = _drive(engine, 5000.0, moving_steps=25, stopped_steps=8)
    assert fired_at is None, f"fired {fired_at} steps after stopping, before the 3 s stop was reached"


def test_fires_after_the_required_continuous_stop_and_reports_real_stopped_time():
    engine = _engine()
    base = 6000.0
    fired = None
    x = 50.0
    for i in range(25 + 30):
        t = base + i * 0.2
        if i < 25:
            x += 18.0
        engine.update_tracks([(x, 250.0, 60.0, 35.0, "Car", 902, True)], now=t)
        c = _stalled(engine.evaluate_rules(640, 480, now=t))
        if c and fired is None:
            fired = (i - 25, c[0])
    assert fired is not None, "a vehicle stopped for 6 s must be reported"
    steps_after_stop, cand = fired
    assert steps_after_stop * 0.2 >= 2.8, "must wait for ~3 s of continuous stop"
    ev = cand.evidence_details
    assert ev["stationary_duration_s"] < ev["track_age_s"], "stopped time must not equal track age"
    assert ev["stationary_duration_s"] >= 3.0


def test_stopped_timer_resets_when_the_vehicle_moves_again():
    th = TrackHistory(1, "Car", is_confirmed=True)
    t = 100.0
    for i in range(10):  # stopped
        th.update((100.0, 100.0, 60.0, 35.0), t + i * 0.2)
    assert th.stationary_duration_seconds > 1.5
    for i in range(10, 16):  # moves ~15 km/h
        th.update((100.0 + (i - 9) * 18.0, 100.0, 60.0, 35.0), t + i * 0.2)
    assert th.stationary_since is None and th.stationary_duration_seconds == 0.0


def test_a_speed_spike_does_not_start_the_stopped_timer():
    th = TrackHistory(2, "Car", is_confirmed=True)
    for i in range(10):
        th.update((50.0 + i * 18.0, 100.0, 60.0, 35.0), 200.0 + i * 0.2)
    assert th.stationary_since is None
    th.update((9000.0, 100.0, 60.0, 35.0), 202.2)  # impossible jump, e.g. an ID switch
    assert th.is_speed_valid is False
    assert th.stationary_since is None, "unknown speed must not count as stopped"


# ---------- ANPR ----------

def _crop_with_plate(text):
    crop = np.full((300, 520, 3), 90, np.uint8)
    cv2.rectangle(crop, (30, 200), (490, 270), (255, 255, 255), -1)
    cv2.putText(crop, text, (45, 253), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 4, cv2.LINE_AA)
    return crop


def test_blank_crop_is_no_read_never_a_generated_plate():
    p = ANPRPipeline()
    for _ in range(5):
        r = p.process_vehicle_crop(np.full((200, 300, 3), 120, np.uint8), track_id=7)
    assert r["readable"] is False and r["text"] == "NO READ"
    assert r["confidence"] == 0.0 and r["votes"] == 0 and r["frames"] == 5
    assert r["hotlist"] is None and r["state"] is None and r["district"] is None


def test_ocr_failure_is_no_read_not_a_made_up_plate(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("tesseract not installed")
    monkeypatch.setattr(anpr.pytesseract, "image_to_data", boom)
    r = ANPRPipeline().process_vehicle_crop(_crop_with_plate("AP16TX4921"), track_id=8)
    assert r["readable"] is False and r["text"] == "NO READ"


def test_no_synthetic_plate_function_exists():
    assert not hasattr(ANPRPipeline, "_get_seeded_fallback_plate")


def test_hotlist_is_empty_by_default_and_demo_entries_are_marked_simulated(monkeypatch):
    monkeypatch.delenv("ANPR_DEMO_HOTLIST", raising=False)
    monkeypatch.delenv("ANPR_HOTLIST_PATH", raising=False)
    assert anpr.load_hotlist() == {}
    monkeypatch.setenv("ANPR_DEMO_HOTLIST", "1")
    assert all(v.get("simulated") for v in anpr.load_hotlist().values())


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_a_clearly_readable_plate_is_read_with_measured_confidence():
    r = ANPRPipeline().process_vehicle_crop(_crop_with_plate("AP16TX4921"), track_id=9)
    assert r["readable"] is True
    assert r["text"].replace(" ", "") == "AP16TX4921"
    assert 0.0 < r["confidence"] <= 1.0


def test_confidence_falls_when_reads_disagree(monkeypatch):
    p = ANPRPipeline()
    seq = iter([("AP 16 TX 4921", 0.9), ("AP 16 TX 4927", 0.9), ("AP 16 TX 4921", 0.9), ("AP 16 TX 4927", 0.9)])
    monkeypatch.setattr(p, "_read_candidate",
                        lambda cand, cfg: (lambda t, c: (p.parse_plate_text(t), c))(*next(seq)))
    out = [p.process_vehicle_crop(np.full((200, 300, 3), 120, np.uint8), track_id=3) for _ in range(4)]
    assert out[-1]["confidence"] <= 0.5 and out[-1]["frames"] == 4


# ---------- camera health ----------

def test_camera_health_starts_unknown_not_healthy():
    from app.camera_health import CameraHealthAnalyzer
    snap = CameraHealthAnalyzer().snapshot()
    assert snap["camera_stability"] is None and snap["lighting_condition"] is None
    assert snap["visibility_score"] is None and snap["frames_analysed"] == 0
    assert snap["frame_age_s"] is None, "no frame yet means no proof of life"


def test_frame_age_grows_when_frames_stop():
    from app.camera_health import CameraHealthAnalyzer
    a = CameraHealthAnalyzer()
    frame = np.full((360, 640, 3), 120, np.uint8)
    a.analyze_frame(frame, now=1000.0)
    assert a.snapshot(now=1000.5)["frame_age_s"] == 0.5
    snap = a.snapshot(now=1030.0)  # 30 s with no frames, health message still being sent
    assert snap["frame_age_s"] == 30.0 and snap["frames_analysed"] == 1
    assert snap["camera_stability"] is not None  # real data after a real frame


def test_confidence_responds_to_image_quality():
    """Confidence is measured from the image, so a blurred crop of the same
    plate must score lower than the sharp crop."""
    import cv2
    clean = _crop_with_plate("AP16TX4921")
    blurred = cv2.GaussianBlur(clean, (0, 0), 4)
    sharp = ANPRPipeline().process_vehicle_crop(clean, track_id=9)
    blur = ANPRPipeline().process_vehicle_crop(blurred, track_id=9)
    assert sharp["readable"] is True
    assert sharp["confidence"] > blur["confidence"]
