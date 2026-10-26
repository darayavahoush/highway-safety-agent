# Comparison harness methodology notes

This PR must keep `reports/detector_baseline.json` unchanged as the original
as-deployed reference. The fair-comparison run writes a separate attribution
report. Do not overwrite or regenerate the baseline automatically.

## The four-way design

Evaluate the same model on the same ordered holdout using the four configurations:

| Key | Preprocessing | Decoder |
|---|---|---|
| `deployed_argmax` | Existing stretch-to-square | Existing global argmax + NMS |
| `deployed_fused` | Existing stretch-to-square | Vehicle-only class-wise thresholding + NMS |
| `letterbox_argmax` | Aspect-preserving letterbox | Single argmax among all classes |
| `letterbox_fused` | Aspect-preserving letterbox | Vehicle-only class-wise thresholding + NMS |

The deployed/argmax cell must call the current legacy postprocessor, not a newly
implemented imitation. That makes it the parity control.

The primary four-way experiment uses class-agnostic NMS in every non-legacy decoder path to match the existing global NMS policy as closely as possible. The legacy `deployed_argmax` cell calls the production postprocessor verbatim. Since class-agnostic NMS can suppress a motorcycle merely because its box overlaps a car or bus, a follow-up class-aware NMS sensitivity run should be reported separately; do not silently mix NMS policy changes into the preprocessing/decoding attribution.

## Attribution: what can be inferred

Let A = deployed/argmax, B = deployed/fused, C = letterbox/argmax, D = letterbox/fused.
For a reported AP metric:

- Total observed change: D - A.
- Preprocessing average marginal effect: ((C - A) + (D - B)) / 2.
- Decoder average marginal effect: ((B - A) + (D - C)) / 2.
- Interaction diagnostic: (D - C) - (B - A).

The two average marginal effects sum to D-A (each receives half the interaction).
This is an attribution of this 2x2 configuration experiment, not a causal proof
that one code change alone explains a result under every domain.

**Domain gap is not identifiable from these four runs.** The dataset is held
constant, so the result must say `NOT_ESTIMATED`; do not invent an additive
equation that attributes part of the measured change to domain gap. VisDrone is
an aerial dataset and does not establish fixed-camera Andhra Pradesh highway
performance.

## Latency

Report model execution and full detector pipeline separately. Exclude image
loading and COCO metric calculation from these timings. Publish p50/p90/p95/p99/
p99.9/max, sample count, samples over 3x p50 and p99/p50 tail ratio. Keep the
old committed latency values as the before comparison and benchmark any output
binding optimization on the same host, model, input and runtime configuration.

ONNX Runtime's `session.run()` does not accept an output buffer. If output-memory
reuse is tested, implement it via ONNX Runtime I/O Binding with a fixed-shape
output, and report the path actually used. Never silently label a `session.run`
fallback as a preallocated-output benchmark.

## Claims and blockers

- No model artifact or VisDrone dataset is bundled in this patch.
- Metrics from a run are valid only if the model hash, full split count and
  environment are recorded.
- If the model or dataset is absent, write `BLOCKED` with the exact exception;
  do not write fake zero-valued metrics.
- Government-pilot readiness remains `BLOCKED` until representative fixed-camera
  highway footage, edge hardware and operational integrations have been validated.
