"""Run the detector preprocessing/decoder 2x2 attribution experiment.

Requires the repository's existing `eval_detector.py`, `visdrone_loader.py`, the
model artifact and the locally prepared VisDrone dataset. Does not overwrite the
committed as-deployed baseline report.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tempfile
import traceback
import hashlib
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

import eval_detector as evaluator  # noqa: E402
import visdrone_loader as vl  # noqa: E402
from comparison_harness import factorial_attribution  # noqa: E402

CONFIGS = (
    ("deployed_argmax", "deployed", "argmax"),
    ("deployed_fused", "deployed", "fused"),
    ("letterbox_argmax", "letterbox", "argmax"),
    ("letterbox_fused", "letterbox", "fused"),
)


def _write_report(path, report):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _metric_values(report):
    values = {
        "AP50": report["overall"].get("AP50"),
        "AP50_95": report["overall"].get("AP50_95"),
    }
    for name, metrics in report.get("per_class", {}).items():
        values[f"{name}.AP50"] = metrics.get("AP50")
        values[f"{name}.AP50_95"] = metrics.get("AP50_95")
    if any(v is None for v in values.values()):
        raise ValueError("one or more COCO AP metrics are unavailable")
    return values



def _write_migration_section(path, report, baseline_report_path, result_path=None):
    """Atomically append/replace an idempotent result section, including blockers."""
    status = report.get("status", "BLOCKED")
    begin = "<!-- BEGIN detector comparison attribution -->"
    end = "<!-- END detector comparison attribution -->"

    if status not in ("COMPLETE", "SMOKE_ONLY"):
        blocker = report.get("blocker", {})
        lines = [
            begin,
            "## Preprocessing & Decoding Attribution",
            "",
            f"**Status: {status}.** No four-way metric table was produced; no metrics have been fabricated.",
            "",
            f"**Blocker type:** `{blocker.get('type', 'Unknown')}`",
            "",
            f"**Exact blocker:** {blocker.get('message', 'No details were returned.')}",
            "",
            "**Domain gap: NOT ESTIMATED.** This experiment cannot estimate aerial-to-fixed-camera domain shift.",
            "",
            "Government-pilot verdict remains **BLOCKED**.",
            "",
            f"See `{os.path.relpath(os.path.abspath(result_path or os.path.join(ROOT, 'reports', 'detector_attribution.json')), ROOT)}` for structured details, including traceback where available.",
            end,
        ]
    else:
        configurations = report["configurations"]
        keys = ("deployed_argmax", "deployed_fused", "letterbox_argmax", "letterbox_fused")
        lines = [
            begin,
            "## Preprocessing & Decoding Attribution",
            "",
            ("**Status: COMPLETE.**" if status == "COMPLETE" else "**Status: SMOKE_ONLY.** These results are limited-sample diagnostics, not a full evaluation."),
            "",
            "Measured on the same model artifact and held-out VisDrone split. This is a fixed-model 2×2 configuration experiment, not a measure of domain gap or target highway performance.",
            "",
            "| Configuration | Preprocessing | Decoder | AP50 | AP50:95 | Inference p50 (ms) | Inference p95 (ms) | Pipeline p50 (ms) | Model size (bytes) |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for key in keys:
            item = configurations[key]
            latency = item.get("latency_benchmark", {})
            infer = latency.get("inference_latency_ms", {})
            pipe = latency.get("full_pipeline_latency_ms", {})
            overall = item.get("overall", {})
            def fmt(value):
                return "—" if value is None else f"{value:.4f}" if isinstance(value, (int, float)) else str(value)
            lines.append(
                f"| `{key}` | {item['preprocess']} | {item['decode']} | {fmt(overall.get('AP50'))} | {fmt(overall.get('AP50_95'))} | {fmt(infer.get('p50'))} | {fmt(infer.get('p95'))} | {fmt(pipe.get('p50'))} | {item.get('model_size_bytes', '—')} |"
            )
        lines += ["", "### Per-class AP50", "", "| Configuration | Car | Motorcycle | Truck | Bus |", "|---|---:|---:|---:|---:|"]
        for key in keys:
            per_class = configurations[key].get("per_class", {})
            vals = [per_class.get(name, {}).get("AP50") for name in ("car", "motorcycle", "truck", "bus")]
            lines.append("| `" + key + "` | " + " | ".join("—" if value is None else f"{value:.4f}" for value in vals) + " |")
        lines += ["", "### Factor attribution", "", "| Metric | Total delta (D−A) | Preprocessing average marginal effect | Decoder average marginal effect | Interaction diagnostic |", "|---|---:|---:|---:|---:|"]
        for metric in ("AP50", "AP50_95"):
            attrib = report.get("attribution", {}).get(metric, {})
            if attrib:
                lines.append(f"| {metric} | {attrib.get('total_delta', 0.0):+.4f} | {attrib.get('preprocessing_average_marginal_effect', 0.0):+.4f} | {attrib.get('decoding_average_marginal_effect', 0.0):+.4f} | {attrib.get('interaction_diagnostic', 0.0):+.4f} |")
        lines += [
            "",
            "**Domain gap: NOT ESTIMATED.** All four runs use the same data domain, so aerial-to-fixed-camera domain shift is not identifiable. The two average marginal effects sum to D−A by construction; each receives half of the preprocessing×decoder interaction.",
            "",
            "### Latency-tail comparison",
            "",
        ]
        baseline = {}
        if baseline_report_path and os.path.isfile(baseline_report_path):
            try:
                with open(baseline_report_path, encoding="utf-8") as stream:
                    baseline = json.load(stream).get("latency_benchmark", {})
            except (OSError, ValueError):
                baseline = {}
        before = baseline.get("inference_latency_ms", {})
        after = configurations["deployed_argmax"].get("latency_benchmark", {}).get("inference_latency_ms", {})
        baseline_ratio = (round(before["p99"] / before["p50"], 3)
                          if before.get("p50") and before.get("p99") else "—")
        lines += [
            "| Measurement | Historical committed baseline | Current deployed/argmax run |",
            "|---|---:|---:|",
            f"| Inference p50 (ms) | {before.get('p50', '—')} | {after.get('p50', '—')} |",
            f"| Inference p99 (ms) | {before.get('p99', '—')} | {after.get('p99', '—')} |",
            f"| p99/p50 tail ratio | {baseline_ratio} | {after.get('tail_ratio_p99_over_p50', '—')} |",
            "",
            "The historical/current comparison is valid as a same-host before/after only when host, model hash, runtime and thread settings match. Output-buffer reuse is opt-in; the JSON report records whether ORT I/O Binding was used.",
            "",
            "Government-pilot verdict remains **BLOCKED**. VisDrone results do not establish fixed-camera highway performance.",
            end,
        ]

    section = "\n".join(lines)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as stream:
            old_text = stream.read()
    else:
        old_text = "# Model Migration Report\n\nThis report is evidence-led. Measurements are generated by the benchmark scripts; no result is inferred from literature alone.\n"
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if begin in old_text and end in old_text:
        start = old_text.index(begin)
        finish = old_text.index(end, start) + len(end)
        new_text = old_text[:start] + section + old_text[finish:]
    else:
        new_text = old_text.rstrip() + "\n\n" + section + "\n"
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        stream.write(new_text)
    os.replace(temporary, path)

def run(model_path, split_path, out_path, conf=0.001, limit=0, warmup=20,
        min_bench_iters=200, expected_images=1554, nms_mode="class-agnostic",
        baseline_report_path=None):
    immutable_baseline = os.path.realpath(os.path.join(ROOT, "reports", "detector_baseline.json"))
    if os.path.realpath(os.path.abspath(out_path)) == immutable_baseline:
        raise ValueError("reports/detector_baseline.json is immutable; refusing to overwrite it")
    if limit < 0:
        raise ValueError("--limit must be zero (full run) or a positive number of images")
    if not limit and expected_images < 1:
        raise ValueError("--expected-images must be positive for a full evaluation")
    report = {
        "schema_version": "detector-attribution-v1",
        "status": "BLOCKED",
        "model": model_path,
        "split": split_path,
        "configuration_order": [],
        "configurations": {},
        "attribution": {},
        "domain_gap": {
            "status": "NOT_ESTIMATED",
            "reason": "All four comparisons use the same model and VisDrone split; domain shift is not identifiable from this experiment.",
        },
        "nms_mode": nms_mode,
        "conf_threshold": conf,
    }
    try:
        if nms_mode != "class-agnostic":
            raise ValueError("The four-way attribution experiment fixes class-agnostic NMS to match the deployed global NMS policy; run class-aware NMS as a separate sensitivity study")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")
        if not os.path.isfile(split_path):
            raise FileNotFoundError(f"Dataset split file not found: {split_path}")
        model_hash = hashlib.sha256()
        with open(model_path, "rb") as model_stream:
            for chunk in iter(lambda: model_stream.read(1 << 20), b""):
                model_hash.update(chunk)
        report["model_sha256"] = model_hash.hexdigest()
        if baseline_report_path:
            if not os.path.isfile(baseline_report_path):
                raise FileNotFoundError(f"Committed baseline report not found: {baseline_report_path}")
            with open(baseline_report_path, encoding="utf-8") as baseline_stream:
                baseline = json.load(baseline_stream)
            baseline_hash = baseline.get("model_sha256")
            report["baseline_model_sha256"] = baseline_hash
            if not baseline_hash:
                raise RuntimeError("Committed baseline report has no model_sha256; cannot verify model parity")
            if report["model_sha256"] != baseline_hash:
                raise RuntimeError(
                    f"Model checksum differs from committed baseline ({report['model_sha256']} != {baseline_hash}); use the same artifact for attribution"
                )
        try:
            from pycocotools.coco import COCO as _COCO  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("pycocotools is required for AP evaluation; refusing to emit zero-valued placeholder metrics") from exc

        with open(split_path, encoding="utf-8") as stream:
            split = json.load(stream)
        samples = vl.fetch_samples(tag=None)
        _, holdout = vl.partition(samples, split)
        if limit:
            holdout = holdout[:limit]
        if not limit and expected_images and len(holdout) != expected_images:
            raise RuntimeError(
                f"Holdout count mismatch: expected {expected_images} images, resolved {len(holdout)}; refusing full-evaluation claim"
            )
        if not holdout:
            raise RuntimeError("Resolved evaluation split contains zero images")

        def _holdout_digest(items):
            # Bind the report to both selected paths and the annotation metadata that
            # drives COCO evaluation. This is a manifest digest, not a digest of image
            # pixel bytes; image asset revision/content hashes remain a separate dataset
            # provenance requirement.
            manifest = []
            for sample in items:
                manifest.append({
                    "filepath": sample["filepath"],
                    "metadata": sample.get("metadata", {}),
                    "ground_truth": sample.get("ground_truth", {}),
                })
            encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

        holdout_digest = _holdout_digest(holdout)
        report["holdout_manifest_sha256"] = holdout_digest

        # Fixed seed makes order reproducible while reducing systematic thermal/order bias.
        order = list(CONFIGS)
        random.Random(20261026).shuffle(order)
        report["configuration_order"] = [entry[0] for entry in order]
        with tempfile.TemporaryDirectory(prefix="highway-attribution-") as tmpdir:
            for key, preprocess_mode, decode_mode in order:
                # Pass the same in-memory sample manifest to every evaluator run.
                # The repository loader can otherwise re-download a large samples.json
                # manifest four times when its cache is absent. The ordered path digest
                # recorded above makes the evaluated set identifiable in the report.
                one_out = os.path.join(tmpdir, f"{key}.json")
                kwargs = {
                    "warmup_count": warmup,
                    "min_bench_iters": min_bench_iters,
                    "preprocess_mode": preprocess_mode,
                    "decode_mode": decode_mode,
                    "nms_mode": nms_mode,
                    "bootstrap_count": 0,
                    "samples_override": samples,
                }
                # Keep output readable: pycocotools prints a long summary per run;
                # the structured JSON report is the source of truth.
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    one = evaluator.run(model_path, split_path, conf, limit, one_out, **kwargs)
                if one.get("images") != len(holdout):
                    raise RuntimeError(
                        f"{key}: evaluator scored {one.get('images')} images, expected {len(holdout)}"
                    )
                report["configurations"][key] = {
                    "preprocess": preprocess_mode,
                    "decode": decode_mode,
                    "nms_mode": nms_mode,
                    "images": one["images"],
                    "predictions": one.get("predictions"),
                    "model_sha256": one.get("model_sha256"),
                    "model_size_bytes": one.get("model_size_bytes"),
                    "system_metadata": one.get("system_metadata"),
                    "latency_benchmark": one.get("latency_benchmark"),
                    "overall": one.get("overall"),
                    "per_class": one.get("per_class"),
                }

        metric_sets = {key: _metric_values(report["configurations"][key]) for key, _, _ in CONFIGS}
        report["attribution"] = factorial_attribution(metric_sets)
        report["status"] = "SMOKE_ONLY" if limit else "COMPLETE"
        split_digest = hashlib.sha256()
        with open(split_path, "rb") as split_stream:
            for chunk in iter(lambda: split_stream.read(1 << 20), b""):
                split_digest.update(chunk)
        report["evaluation"] = {
            "split_sha256": split_digest.hexdigest(),
            "split_version": split.get("version"),
            "taxonomy_version": split.get("taxonomy_version", vl.TAXONOMY_VERSION),
            "expected_images": expected_images if not limit else None,
            "resolved_images": len(holdout),
            "holdout_manifest_sha256": holdout_digest,
            "full_evaluation": not bool(limit),
            "note": "COMPLETE refers only to this fixed-model VisDrone experiment; it is not evidence of target-domain highway readiness.",
        }
    except Exception as exc:
        report["status"] = "BLOCKED"
        report["blocker"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(limit=8),
        }
    _write_report(out_path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.path.join(ROOT, "models", "yolov8n_coco_320.onnx"))
    parser.add_argument("--split", default=os.path.join(ROOT, "configs", "visdrone_det_split_v1.json"))
    parser.add_argument("--conf", type=float, default=0.001)
    parser.add_argument("--limit", type=int, default=0, help="Smoke-test image limit; never a full-evaluation result")
    parser.add_argument("--expected-images", type=int, default=1554)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--min-bench-iters", type=int, default=200)
    parser.add_argument("--nms-mode", choices=("class-aware", "class-agnostic"), default="class-agnostic")
    parser.add_argument("--baseline-report", default=os.path.join(ROOT, "reports", "detector_baseline.json"))
    parser.add_argument("--migration-report", default=os.path.join(ROOT, "docs", "MODEL_MIGRATION_REPORT.md"))
    parser.add_argument("--io-binding", choices=("auto", "on", "off"), default="off",
                        help="Use reusable ORT output binding; default off preserves the historical session.run path")
    parser.add_argument("--out", default=os.path.join(ROOT, "reports", "detector_attribution.json"))
    args = parser.parse_args(argv)
    if args.io_binding != "auto":
        os.environ["ORT_USE_IO_BINDING"] = "1" if args.io_binding == "on" else "0"
    report = run(args.model, args.split, args.out, args.conf, args.limit, args.warmup,
                 args.min_bench_iters, args.expected_images, args.nms_mode, args.baseline_report)
    _write_migration_section(args.migration_report, report, args.baseline_report, args.out)
    print(json.dumps({"status": report["status"], "out": args.out, "blocker": report.get("blocker")}, indent=2))
    return 0 if report["status"] in ("COMPLETE", "SMOKE_ONLY") else 2


if __name__ == "__main__":
    raise SystemExit(main())
