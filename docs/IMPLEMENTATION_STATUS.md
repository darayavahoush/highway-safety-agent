# PR #10 Comparison Harness — Implementation Status

**Prepared:** 2026-10-26
**Target branch:** `feat/comparison-harness`
**Target PR:** `Add comparison-grade evaluation harness with preprocessing attribution`

## Current status

**Implementation bundle: PARTIAL. GitHub PR: NOT OPENED. Full benchmark: BLOCKED.**

The environment used to prepare this bundle could read public GitHub source through web retrieval but could not resolve `github.com` from the shell (`git ls-remote` failed with `Could not resolve host: github.com`). It therefore could not clone the current repository, run the changes against the actual checkout, push a branch or open a pull request.

The bundle adds a comparison helper, a four-way evaluation driver, a fail-closed integration script for the existing detector/evaluator, and regression tests. The integration script should be run against a fresh checkout of the target `main` branch and the resulting diff reviewed before commit.

## Tests that ran

- Standalone bundle tests: **10 passed, 5 skipped**. The skipped tests require the repository's `app.detector` and `tools.eval_detector` modules.
- Isolated integration fixture tests after copying the bundle: **18 passed**. This checks the helper and an approximate fixture of the patched integration; it is not a full test run on the real repository.
- Fault injection: seven deliberate faults (four comparison/attribution faults and three detector I/O-binding/thread-configuration faults) each caused an intended regression test to fail. The original helper/detector were restored and tests rerun.
- Python compile check: `python -m compileall -q tools scripts tests` passed.

## Benchmark status: BLOCKED

No detector-attribution metrics were generated because the required runtime/data are unavailable in this environment:

- `onnxruntime` is not installed.
- `pycocotools` is not installed.
- The expected model artifact `models/yolov8n_coco_320.onnx` is not bundled here.
- The VisDrone dataset and split are not bundled here.

The existing baseline report expects SHA-256:

`2d4c483a11e10a8685ff65a126dd202da02674651d6a80a5e991288ae097f78c`

The full experiment must be run on the same verified model artifact and the intended 1,554-image split. The script should write `reports/detector_attribution.json` with `BLOCKED` plus the exact exception if prerequisites are missing. No model binaries or dataset files belong in the bundle.

## Interpretation safeguards

- `reports/detector_baseline.json` is an immutable historical reference. The integration adds guards against overwriting it.
- `deployed_argmax` uses the existing production postprocessor as the parity control.
- Domain gap remains `NOT_ESTIMATED`; a four-way experiment on the same VisDrone split cannot identify aerial-to-fixed-CCTV domain shift.
- Literature numbers are not substituted for measurements.
- Government-pilot verdict remains `BLOCKED` until target-domain highway footage, edge hardware and operational acceptance criteria are evaluated.

## Next local steps

1. Unzip the bundle outside the repository and merge `tools/`, `tests/`, and `docs/`; copy the patcher into the repository's `scripts/` directory.
2. Run `python scripts/apply_pr10_integration.py` on a fresh checkout. If a source anchor changed, stop and update the patch instead of forcing it.
3. Review the entire diff, especially `app/detector.py`, `tools/eval_detector.py`, baseline overwrite guards, and runtime defaults.
4. Run existing backend and frontend tests plus `npm run build`.
5. Install the benchmark dependencies, obtain the verified model and prepare the dataset under their existing provenance/licence instructions.
6. Run the documented four-way evaluation. Commit only the measured report and code; do not commit model weights or dataset files.
7. Remove `scripts/apply_pr10_integration.py` before committing the final PR; it is a one-shot migration tool.
