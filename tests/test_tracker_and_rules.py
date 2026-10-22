"""
Comprehensive Synthetic Verification Suite for Edge Perception, Tracker, and Safety Rules.

Validates the 8 critical invariant properties required before real-world deployment:
1. Missing vehicle for 3 frames keeps its ID.
2. Two vehicles crossing paths keep their IDs.
3. ID switch does not produce a speed spike that reaches the rules.
4. Car stopped on the shoulder produces no P0 and zero dispatches.
5. Congestion (all vehicles slow in lane) suppresses stalled vehicle alert.
6. Opposite-direction traffic following its own lane direction does not fire wrong-way.
7. Genuine wrong-way vehicle fires exactly once (dedupe cooldown).
8. Tailgating fires for a real close follower and not for a faster leader pulling away.
"""

import math
import os
import sys
import tempfile
import time
import json
import numpy as np

# Ensure app is importable
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.incident_schema import IncidentType, IncidentSeverity
from app.incident_rules import EdgeTriggerEngine, TrackHistory
from app.tracker import LineCrossingCounter, Track
from app.evidence_buffer import EvidenceBuffer
from agent.reasoning import SafetyPolicyEngine


def test_1_vehicle_missing_for_3_frames_keeps_id():
    print("\n[TEST 1] Testing missing vehicle for 3 frames keeps its ID...")
    tracker = LineCrossingCounter(line=((0, 200), (640, 200)), min_hits=3, max_lost_time_s=1.0)
    
    # Send detections for 4 frames to confirm track (moving at 10 px / frame)
    for i in range(4):
        t = i * 0.02
        x = 100.0 + i * 10.0
        dets = [(x, 150.0, 50.0, 30.0, "Car", 0.90)]
        tracks, _ = tracker.update(dets, now=t)
        assert len(tracks) == 1
        orig_id = tracks[0].id

    assert orig_id == 1
    assert tracks[0].is_confirmed

    # Vehicle is occluded / missing for 3 frames (at 50 FPS = 0.06s << 1.0s)
    for i in range(4, 7):
        t = i * 0.02
        tracks, _ = tracker.update([], now=t)
        # Track is retained in lost/tentative state in memory
        assert 1 in tracker._tracks, "Track should be kept in memory during occlusion!"

    # Detection reappears at frame 7 at predicted position (~170px)
    t = 7 * 0.02
    reappear_x = 100.0 + 7 * 10.0
    dets = [(reappear_x, 150.0, 50.0, 30.0, "Car", 0.90)]
    tracks, _ = tracker.update(dets, now=t)

    assert len(tracks) >= 1
    matched_track = next((tr for tr in tracks if tr.id == orig_id), None)
    assert matched_track is not None, f"Failed: Track ID {orig_id} was lost after 3 missing frames!"
    print(f"  [PASS] Vehicle missing for 3 frames successfully retained ID #{orig_id}!")


def test_2_two_vehicles_crossing_paths_keep_ids():
    print("\n[TEST 2] Testing two vehicles crossing paths keep their IDs...")
    tracker = LineCrossingCounter(line=((0, 200), (640, 200)), min_hits=3, max_lost_time_s=1.0)

    # Vehicle A starts at x=100 moving East (+15 px/frame)
    # Vehicle B starts at x=340 moving West (-15 px/frame)
    # They will cross around x=220 at frame 8
    for i in range(16):
        t = i * 0.02
        xa = 100.0 + i * 15.0
        xb = 340.0 - i * 15.0

        dets = [
            (xa, 150.0, 40.0, 30.0, "Car", 0.90),
            (xb, 150.0, 40.0, 30.0, "Van", 0.90),
        ]
        tracks, _ = tracker.update(dets, now=t)

    # After crossing (frame 15):
    # Vehicle A is at x=100 + 15*15 = 325 (>220)
    # Vehicle B is at x=340 - 15*15 = 115 (<220)
    track_east = next((tr for tr in tracks if tr.box[0] > 250.0), None)
    track_west = next((tr for tr in tracks if tr.box[0] < 200.0), None)

    assert track_east is not None and track_west is not None, "Both tracks must be present after crossing!"
    assert track_east.id == 1, f"Expected Eastbound vehicle to keep ID #1, got ID #{track_east.id}"
    assert track_west.id == 2, f"Expected Westbound vehicle to keep ID #2, got ID #{track_west.id}"
    print(f"  [PASS] Crossing vehicles preserved identities: Eastbound=#1 (x={track_east.box[0]:.1f}), Westbound=#2 (x={track_west.box[0]:.1f})!")


def test_3_id_switch_speed_spike_isolated_from_rules():
    print("\n[TEST 3] Testing ID switch speed spike is marked invalid and isolated from rules...")
    engine = EdgeTriggerEngine(
        camera_config_path="config/camera_config.json",
        rules_config_path="config/safety_rules.json",
    )

    # Establish track 501 at normal speed (~60 km/h) for 8 frames
    for i in range(8):
        t = i * 0.1
        x = 100.0 + i * 8.0
        engine.update_tracks([(x, 200.0, 50.0, 30.0, "Car", 501, True)], now=t)

    th = engine.tracks[501]
    assert th.is_speed_valid, "Initial speed should be valid"
    assert th.current_speed_kmh < 100.0

    # Simulate catastrophic ID jump: vehicle jumps 400 pixels in 0.1s (~650 km/h)
    spike_t = 0.8
    engine.update_tracks([(550.0, 200.0, 50.0, 30.0, "Car", 501, True)], now=spike_t)

    assert th.is_speed_valid is False, "Speed spike > 200 km/h MUST be marked invalid!"
    assert th.invalid_speed_count >= 1, "Invalid speed sample must be counted in health metrics!"
    assert th.current_speed_kmh <= 200.0, f"Speed spike ({th.current_speed_kmh}) must not be passed to rules!"

    # Evaluate rules: track with invalid speed must be ignored
    candidates = engine.evaluate_rules(640, 480, now=spike_t)
    cand_501 = [c for c in candidates if c.primary_track_id == 501]
    assert len(cand_501) == 0, "No candidate must fire from an unphysical speed spike!"
    print("  [PASS] Speed spike (>200 km/h) cleanly rejected and blocked from rule engine!")


def test_4_car_stopped_on_shoulder_produces_no_p0_and_no_dispatch():
    print("\n[TEST 4] Testing car stopped on shoulder produces no P0 and no dispatch...")
    engine = EdgeTriggerEngine(
        camera_config_path="config/camera_config.json",
        rules_config_path="config/safety_rules.json",
    )
    policy = SafetyPolicyEngine(mock_base_url="http://127.0.0.1:8000/mock")

    # Emergency shoulder is defined at Y: 0.85 to 1.0 (in 480p: y > 408)
    base_ts = 1000.0
    for step in range(25):
        t = base_ts + step * 0.2
        # Stationary at y=430 (Emergency Shoulder)
        engine.update_tracks([(250.0, 420.0, 60.0, 35.0, "Car", 601, True)], now=t)

    candidates = engine.evaluate_rules(640, 480, now=base_ts + 5.0)
    assert len(candidates) >= 1, "Expected shoulder stop candidate to be generated!"

    cand = candidates[0]
    assert cand.severity == IncidentSeverity.P2, f"Shoulder stop must be P2, got: {cand.severity}"
    assert "live lane" not in cand.rule_reason.lower(), f"Shoulder stop must never say 'live lane'! Reason: {cand.rule_reason}"
    assert "shoulder" in cand.rule_reason.lower(), f"Shoulder stop must name shoulder! Reason: {cand.rule_reason}"

    briefing, trace, dispatches = policy.reason_and_triage(cand)
    assert len(dispatches) == 0, f"P2 shoulder stop must produce 0 dispatches, got: {len(dispatches)}"
    assert "live lane" not in briefing.lower(), f"Briefing must not say 'live lane': {briefing}"
    print(f"  [PASS] Shoulder vehicle produced P2 observation with ZERO dispatches! (Reason: '{cand.rule_reason}')")


def test_5_congestion_suppresses_stalled():
    print("\n[TEST 5] Testing heavy traffic congestion suppresses stalled vehicle alert...")
    engine = EdgeTriggerEngine(
        camera_config_path="config/camera_config.json",
        rules_config_path="config/safety_rules.json",
    )

    base_ts = 2000.0
    # 3 vehicles in heavy vehicle lane (y=250):
    # Track 701: stationary for 4.0s
    # Track 702: moving at 8.0 km/h
    # Track 703: moving at 10.0 km/h
    for step in range(25):
        t = base_ts + step * 0.2
        x_stalled = 200.0
        x_slow_1 = 300.0 + step * 1.0   # ~ 8 km/h
        x_slow_2 = 450.0 + step * 1.2   # ~ 10 km/h

        engine.update_tracks([
            (x_stalled, 250.0, 60.0, 35.0, "Truck", 701, True),
            (x_slow_1, 250.0, 50.0, 30.0, "Car", 702, True),
            (x_slow_2, 250.0, 55.0, 32.0, "Van", 703, True),
        ], now=t)

    candidates = engine.evaluate_rules(640, 480, now=base_ts + 5.0)
    stalled_701 = [c for c in candidates if c.primary_track_id == 701 and c.incident_type == IncidentType.STALLED_VEHICLE]

    assert len(stalled_701) == 0, "Congestion suppression failed: Stalled vehicle alert should not fire in slow queue!"
    print("  [PASS] Stalled alert successfully suppressed because surrounding lane traffic is < 15 km/h!")


def test_6_opposite_direction_traffic_follows_own_lane():
    print("\n[TEST 6] Testing dual-carriageway traffic following own lane direction does NOT fire wrong-way...")
    # Create temporary dual-carriageway camera config:
    # Lane 1 (Eastbound): direction: [1.0, 0.0]
    # Lane 2 (Westbound): direction: [-1.0, 0.0]
    dual_config = {
        "camera_id": "CAM-DUAL-TEST",
        "pixels_per_meter": 22.0,
        "lanes": [
            {
                "id": "lane_eastbound",
                "name": "Eastbound Carriageway",
                "type": "travel",
                "direction": [1.0, 0.0],
                "polygon": [[0.0, 0.1], [1.0, 0.1], [1.0, 0.5], [0.0, 0.5]],
            },
            {
                "id": "lane_westbound",
                "name": "Westbound Carriageway",
                "type": "travel",
                "direction": [-1.0, 0.0],
                "polygon": [[0.0, 0.5], [1.0, 0.5], [1.0, 0.9], [0.0, 0.9]],
            },
        ],
    }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(dual_config, f)
        temp_cfg = f.name

    try:
        engine = EdgeTriggerEngine(camera_config_path=temp_cfg, rules_config_path="config/safety_rules.json")
        base_ts = 3000.0

        # Vehicle 801 in Westbound carriageway (y=300 -> ny=0.625) moving West (-X) at 60 km/h (36 px / 0.1s)
        for step in range(25):
            t = base_ts + step * 0.1
            x = 550.0 - step * 16.0
            engine.update_tracks([(x, 300.0, 50.0, 30.0, "Car", 801, True)], now=t)

        candidates = engine.evaluate_rules(640, 480, now=base_ts + 2.5)
        wrong_way = [c for c in candidates if c.incident_type == IncidentType.WRONG_WAY_DRIVER]

        assert len(wrong_way) == 0, "Opposite direction vehicle matching its own lane vector must NOT fire wrong-way!"
        print("  [PASS] Dual-carriageway Westbound vehicle correctly honored its lane vector without wrong-way alert!")
    finally:
        os.remove(temp_cfg)


def test_7_genuine_wrong_way_vehicle_fires_once():
    print("\n[TEST 7] Testing genuine wrong-way vehicle fires exactly once under deduplication...")
    engine = EdgeTriggerEngine(
        camera_config_path="config/camera_config.json",
        rules_config_path="config/safety_rules.json",
    )
    buffer = EvidenceBuffer(cooldown_seconds=15.0)

    base_ts = 4000.0
    # Vehicle 901 moves West against Eastbound flow in Lane 2 (Left) for 3.0s at 35 km/h
    fired_count = 0
    for step in range(30):
        t = base_ts + step * 0.1
        x = 550.0 - step * 12.0
        engine.update_tracks([(x, 250.0, 50.0, 30.0, "Car", 901, True)], now=t)

        cands = engine.evaluate_rules(640, 480, now=t)
        for cand in cands:
            if cand.incident_type == IncidentType.WRONG_WAY_DRIVER and cand.primary_track_id == 901:
                suppressed = buffer.should_suppress_dedupe(cand.camera_id, cand.incident_type, cand.primary_track_id, now=t)
                if not suppressed:
                    fired_count += 1

    assert fired_count == 1, f"Expected genuine wrong-way vehicle to fire exactly 1 dispatch alert, got {fired_count}!"
    print(f"  [PASS] Genuine wrong-way vehicle fired exactly {fired_count} time with remaining alerts suppressed by dedupe!")


def test_8_tailgating_close_follower_vs_leader_pulling_away():
    print("\n[TEST 8] Testing tailgating fires for close follower but NOT when leader is pulling away...")
    engine = EdgeTriggerEngine(
        camera_config_path="config/camera_config.json",
        rules_config_path="config/safety_rules.json",
    )

    # --- Scenario A: Truck (1001) closing in fast on Car (1002) from behind ---
    base_ts = 5000.0
    cands_a = []
    for step in range(20):
        t = base_ts + step * 0.1
        # Leader Car 1002 at ~ 40 km/h (24 px / 0.1s)
        leader_x = 300.0 + step * 24.0
        # Follower Truck 1001 closing at ~ 60 km/h (36 px / 0.1s)
        follower_x = 120.0 + step * 36.0
        engine.update_tracks([
            (follower_x, 250.0, 60.0, 35.0, "Truck", 1001, True),
            (leader_x, 250.0, 50.0, 30.0, "Car", 1002, True),
        ], now=t)
        cands = engine.evaluate_rules(640, 480, now=t)
        cands_a.extend([c for c in cands if c.incident_type == IncidentType.TAILGATING_COLLISION_RISK])

    assert len(cands_a) >= 1, "Failed: Closing follower should trigger tailgating hazard!"
    print(f"  [PASS] Scenario A: Rapidly closing follower correctly fired Tailgating hazard!")

    # --- Scenario B: Leader (1004) pulling away from Follower (1003) ---
    engine_b = EdgeTriggerEngine(
        camera_config_path="config/camera_config.json",
        rules_config_path="config/safety_rules.json",
    )
    base_ts = 6000.0
    cands_b = []
    for step in range(20):
        t = base_ts + step * 0.1
        # Follower 1003 at ~ 40 km/h (24 px / 0.1s)
        follower_x = 100.0 + step * 24.0
        # Leader 1004 pulling away at ~ 70 km/h (42 px / 0.1s)
        leader_x = 150.0 + step * 42.0
        engine_b.update_tracks([
            (follower_x, 250.0, 50.0, 30.0, "Car", 1003, True),
            (leader_x, 250.0, 50.0, 30.0, "Car", 1004, True),
        ], now=t)
        cands = engine_b.evaluate_rules(640, 480, now=t)
        cands_b.extend([c for c in cands if c.incident_type == IncidentType.TAILGATING_COLLISION_RISK])

    assert len(cands_b) == 0, f"Failed: Faster leader pulling away must NOT trigger tailgating, got {len(cands_b)} alerts!"
    print("  [PASS] Scenario B: Faster leader pulling away correctly produced ZERO tailgating alerts!")


if __name__ == "__main__":
    print("\n=======================================================")
    print("STARTING SYNTHETIC EDGE TRACKER & RULES VERIFICATION")
    print("=======================================================")
    test_1_vehicle_missing_for_3_frames_keeps_id()
    test_2_two_vehicles_crossing_paths_keep_ids()
    test_3_id_switch_speed_spike_isolated_from_rules()
    test_4_car_stopped_on_shoulder_produces_no_p0_and_no_dispatch()
    test_5_congestion_suppresses_stalled()
    test_6_opposite_direction_traffic_follows_own_lane()
    test_7_genuine_wrong_way_vehicle_fires_once()
    test_8_tailgating_close_follower_vs_leader_pulling_away()
    print("\n=======================================================")
    print("ALL 8 SYNTHETIC TRACKER & RULE TESTS PASSED CLEANLY!")
    print("=======================================================\n")
