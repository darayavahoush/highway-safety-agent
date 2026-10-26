"""Integration guard; exercised after scripts/apply_pr10_integration.py is applied."""
from pathlib import Path

import pytest


evaluator = pytest.importorskip("tools.eval_detector", reason="must run inside highway-safety-agent checkout")


def test_benchmark_refuses_to_overwrite_committed_baseline():
    repo_root = Path(evaluator.__file__).resolve().parents[1]
    baseline = repo_root / "reports" / "detector_baseline.json"
    with pytest.raises(ValueError, match="immutable historical reference|is immutable"):
        evaluator.run(
            model_path=str(repo_root / "missing-model.onnx"),
            split_path=str(repo_root / "missing-split.json"),
            out_path=str(baseline),
        )


def test_attribution_runner_refuses_to_overwrite_baseline_in_temporary_root(tmp_path, monkeypatch):
    driver = pytest.importorskip("tools.eval_detector_attribution", reason="must run inside highway-safety-agent checkout")
    reports = tmp_path / "reports"
    reports.mkdir()
    baseline = reports / "detector_baseline.json"
    baseline.write_text('{"marker":"historical baseline"}', encoding="utf-8")
    monkeypatch.setattr(driver, "ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="immutable; refusing to overwrite"):
        driver.run("missing-model.onnx", "missing-split.json", str(baseline), baseline_report_path=str(baseline))
    assert baseline.read_text(encoding="utf-8") == '{"marker":"historical baseline"}'


def test_missing_model_writes_blocked_report_without_changing_baseline(tmp_path, monkeypatch):
    driver = pytest.importorskip("tools.eval_detector_attribution", reason="must run inside highway-safety-agent checkout")
    reports = tmp_path / "reports"
    reports.mkdir()
    baseline = reports / "detector_baseline.json"
    baseline_bytes = b'{"marker":"historical baseline"}\n'
    baseline.write_bytes(baseline_bytes)
    output = reports / "detector_attribution.json"
    monkeypatch.setattr(driver, "ROOT", str(tmp_path))

    report = driver.run(
        model_path=str(tmp_path / "missing-model.onnx"),
        split_path=str(tmp_path / "missing-split.json"),
        out_path=str(output),
        baseline_report_path=str(baseline),
    )

    import json
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "BLOCKED"
    assert saved["status"] == "BLOCKED"
    assert saved["blocker"]["type"] == "FileNotFoundError"
    assert "Model file not found" in saved["blocker"]["message"]
    assert "attribution" not in saved or saved["attribution"] == {}
    assert baseline.read_bytes() == baseline_bytes


def test_missing_pycocotools_fails_closed_in_metric_helper(monkeypatch):
    import builtins

    original_import = builtins.__import__
    def deny_pycocotools(name, *args, **kwargs):
        if name.startswith("pycocotools"):
            raise ImportError("forced missing pycocotools for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny_pycocotools)
    with pytest.raises(RuntimeError, match="pycocotools is required"):
        evaluator._coco_metrics(None, None)
