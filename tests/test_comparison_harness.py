import numpy as np
import pytest

from tools.comparison_harness import (
    decode_yolo_output,
    factorial_attribution,
    latency_summary,
    preprocess_frame,
)


def test_letterbox_preserves_aspect_ratio_and_pads_non_square_image():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    blob, transform, _ = preprocess_frame(frame, 320, "letterbox")
    assert blob.shape == (1, 3, 320, 320)
    assert transform["resized_width"] == 320
    assert transform["resized_height"] == 160
    assert transform["pad_x"] == 0
    assert transform["pad_y"] == 80
    assert np.allclose(transform["scale"], 1.6)
    # The top padding is RGB 114 after normalization.
    assert np.allclose(blob[0, :, 0, 0], 114 / 255.0)


def test_deployed_preprocess_retains_stretch_transform():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    blob, transform, _ = preprocess_frame(frame, 320, "deployed")
    assert blob.shape == (1, 3, 320, 320)
    assert transform["scale_x"] == 1.6
    assert transform["scale_y"] == 3.2


def test_fused_decoder_recovers_vehicle_when_nonvehicle_class_is_argmax():
    # Candidate 0: person score wins global argmax, but the car score is still high.
    output = np.zeros((1, 84, 1), dtype=np.float32)
    output[0, :4, 0] = [160, 160, 80, 40]
    output[0, 4 + 0, 0] = 0.95  # person
    output[0, 4 + 2, 0] = 0.80  # car
    _, transform, _ = preprocess_frame(np.zeros((320, 320, 3), np.uint8), 320, "deployed")
    argmax = decode_yolo_output(output, transform, 0.25, 0.45, mode="argmax")
    fused = decode_yolo_output(output, transform, 0.25, 0.45, mode="fused")
    assert argmax == []
    assert len(fused) == 1
    assert fused[0][4] == "Car"
    assert fused[0][5] == pytest.approx(0.8)


def test_fused_decoder_class_aware_nms_keeps_overlapping_different_vehicle_classes():
    output = np.zeros((1, 84, 2), dtype=np.float32)
    output[0, :4, 0] = [100, 100, 80, 80]
    output[0, :4, 1] = [101, 101, 80, 80]
    output[0, 4 + 2, 0] = 0.9
    output[0, 4 + 3, 1] = 0.85
    _, transform, _ = preprocess_frame(np.zeros((320, 320, 3), np.uint8), 320, "deployed")
    result = decode_yolo_output(output, transform, 0.25, 0.45, mode="fused", nms_mode="class-aware")
    assert {row[4] for row in result} == {"Car", "Motorbike"}


def test_latency_summary_includes_tail_ratio_and_outlier_count():
    summary = latency_summary([10, 10, 10, 10, 100])
    assert summary["count"] == 5
    assert summary["max"] == 100
    assert summary["p99"] is not None
    assert summary["tail_ratio_p99_over_p50"] > 1
    assert summary["count_over_3x_p50"] == 1
    assert summary["p99_9"] is not None


def test_latency_summary_rejects_invalid_samples():
    with pytest.raises(ValueError):
        latency_summary([1.0, float("nan")])
    with pytest.raises(ValueError):
        latency_summary([-1])


def test_factorial_effects_sum_to_total_delta_and_domain_gap_is_not_claimed():
    metrics = {
        "deployed_argmax": {"AP50": 0.10},
        "deployed_fused": {"AP50": 0.20},
        "letterbox_argmax": {"AP50": 0.30},
        "letterbox_fused": {"AP50": 0.50},
    }
    result = factorial_attribution(metrics)["AP50"]
    assert result["total_delta"] == pytest.approx(0.40)
    assert result["preprocessing_average_marginal_effect"] == pytest.approx(0.25)
    assert result["decoding_average_marginal_effect"] == pytest.approx(0.15)
    assert result["decomposition_sum_check"] == pytest.approx(result["total_delta"])
    assert result["domain_gap"] is None
    assert result["domain_gap_status"] == "NOT_ESTIMATED"


def test_factorial_attribution_requires_all_four_configs():
    with pytest.raises(ValueError):
        factorial_attribution({"deployed_argmax": {"AP50": 0.1}})


def test_deployed_argmax_uses_legacy_coordinate_scaling_and_int_truncation():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    _, transform, _ = preprocess_frame(frame, 320, "deployed")
    output = np.zeros((1, 84, 1), dtype=np.float32)
    output[0, :4, 0] = [160.0, 160.0, 64.0, 32.0]
    output[0, 4 + 2, 0] = 0.9
    decoded = decode_yolo_output(output, transform, 0.25, 0.45, mode="argmax", nms_mode="class-agnostic")
    assert decoded == [(80, 45, 40, 10, "Car", pytest.approx(0.9))]


def test_deployed_preprocessing_is_pixel_equal_to_legacy_recipe():
    import cv2
    frame = np.random.RandomState(4).randint(0, 256, (73, 151, 3), dtype=np.uint8)
    old = cv2.resize(frame, (320, 320))
    old = cv2.cvtColor(old, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    old = np.transpose(old, (2, 0, 1))[np.newaxis, ...]
    new, _, _ = preprocess_frame(frame, 320, "deployed")
    assert np.array_equal(new, old)


def test_deployed_argmax_decoder_matches_production_postprocessor_exactly():
    """Integration regression: skip in the standalone patch bundle, run in the repo."""
    try:
        from app.detector import _postprocess_yolo_output
    except ImportError:
        pytest.skip("requires the repository app.detector module")

    rng = np.random.RandomState(37)
    frame = rng.randint(0, 256, (271, 483, 3), dtype=np.uint8)
    _, transform, _ = preprocess_frame(frame, 320, "deployed")
    output = np.zeros((1, 84, 96), dtype=np.float32)
    output[0, 0, :] = rng.uniform(0, 320, 96)
    output[0, 1, :] = rng.uniform(0, 320, 96)
    output[0, 2, :] = rng.uniform(5, 110, 96)
    output[0, 3, :] = rng.uniform(5, 90, 96)
    output[0, 4:, :] = rng.uniform(0, 0.95, (80, 96))
    threshold, nms_threshold = 0.35, 0.45
    expected = _postprocess_yolo_output(output, frame.shape[1], frame.shape[0], 320,
                                        threshold, nms_threshold)
    observed = decode_yolo_output(output, transform, threshold, nms_threshold,
                                  mode="argmax", nms_mode="class-agnostic")
    assert observed == expected
