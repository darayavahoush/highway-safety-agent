# Model Migration & Benchmark Report: Stock COCO YOLOv8n Baseline

## 1. Executive Summary & Verdict

- **Model Under Evaluation**: Stock Ultralytics YOLOv8n exported to ONNX (320x320 FP32, 80 COCO classes).
- **Benchmark Split**: Held-out test split of VisDrone-DET (`configs/visdrone_det_split_v1.json`, 1,554 images across 64 held-out sequences).
- **Deployment Runtime**: `OrtYoloDetector` (ONNX Runtime CPU Execution Provider).
- **Government Pilot Readiness Verdict**: **`BLOCKED`**
  - **Reason**: VisDrone consists of aerial/drone imagery rather than fixed Indian highway sentry CCTV. Furthermore, the dataset is released under CC BY-NC-SA 3.0 (non-commercial), preventing commercial pilot certification without legal clearance. Production highway deployment requires validation against calibrated, labelled Indian highway corridors (e.g. NH-16 / NH-65 in Andhra Pradesh) under varying lighting, weather, and mixed-traffic density.

---

## 2. Model Provenance & Verification

| Parameter | Baseline Candidate (`yolov8n_coco_320.onnx`) | Legacy Deployed (`yolov8n.onnx`) |
| :--- | :--- | :--- |
| **Source Weights** | Ultralytics YOLOv8n (stock COCO, 80 classes) | Unknown 5-class fine-tune ("VisDroneVehicles") |
| **Export Method** | `export(format="onnx", imgsz=320, opset=12, dynamic=False, simplify=True)` | Unknown (no export script or training config in repo) |
| **Software Versions** | Ultralytics 8.4.187, ONNX 1.23.2, onnxslim 0.1.98 | Unknown |
| **Input Shape** | `[1, 3, 320, 320]` (RGB FP32 normalized 0..1) | `[1, 3, 320, 320]` |
| **Output Shape** | `[1, 84, 2100]` (4 coords + 80 COCO class logits) | `[1, 9, 2100]` (4 coords + 5 class logits) |
| **File Size** | 12,725,062 bytes (~12.13 MiB) | 12,398,592 bytes (~11.82 MiB) |
| **SHA-256 Checksum** | `2d4c483a11e10a8685ff65a126dd202da02674651d6a80a5e991288ae097f78c` | `59b353c...` (Initial repository commit) |
| **Provenance Status** | **Fully Audited & Reproducible** (`models/PROVENANCE_coco_320.md`) | **Unverified / Legacy** (not certified for benchmarking) |

---

## 3. Evaluation Setup & Methodology

### 3.1 Taxonomy & Ground Truth Mapping
Ground truth is extracted from VisDrone2019-DET using the sequence-level holdout split:
- **Scored Classes**:
  - `car` (VisDrone `car` + proposed `van`)
  - `motorcycle` (VisDrone `motor`)
  - `truck` (VisDrone `truck`)
  - `bus` (VisDrone `bus`)
- **Ignore Regions & Crowd Handling**:
  - Unmapped categories (`pedestrian`, `people`, `bicycle`, `tricycle`, `awning-tricycle`, `others`) and annotated `ignore_regions` are converted to `iscrowd=1` annotations across all evaluated categories.
  - False positives landing on ignored objects do not penalise detector precision.

### 3.2 Preprocessing & Deployment Divergence
- **Stretch-to-320x320**: The deployed `OrtYoloDetector` resizes the input frame directly to `(320, 320)` via `cv2.resize` without preserving aspect ratio. Standard YOLOv8 was trained with letterbox padding (aspect-ratio preservation with gray margins). This distortion degrades small and distant object detection, noted as a known architectural divergence to be addressed in subsequent optimization PRs.
- **Argmax Class Selection**: `_postprocess_yolo_output` selects the global `argmax` across all 80 classes. If the top-scoring class is not a highway vehicle class, the candidate bounding box is discarded.

### 3.3 Latency Measurement Isolation
- Dataset I/O and network fetching (`urllib` / Hugging Face) are strictly isolated and excluded from latency benchmarks.
- Latency is divided into:
  - **Raw Model Inference**: Time spent exclusively inside `ort.InferenceSession.run()`.
  - **Full Edge Pipeline**: Preprocessing (`cv2.resize` + normalization + transpose) + Inference + Postprocessing (`_postprocess_yolo_output` + NMS).
- Benchmark timings are recorded over at least 200 post-warmup iterations.

---

## 4. Hardware & Benchmark Environment

- **Host Machine**: Apple Mac (Apple M2 CPU, 8 logical cores)
- **Host Memory**: 8.0 GiB RAM
- **Operating System**: Darwin 24.3.0 (macOS, arm64)
- **Python Runtime**: Python 3.14.8 (`~/venvs/highway`)
- **Inference Engine**: ONNX Runtime 1.31.0 (`CPUExecutionProvider`)
- **Engine Configuration**: `ORT_NUM_THREADS=4`, `ExecutionMode.ORT_SEQUENTIAL`, `GraphOptimizationLevel.ORT_ENABLE_ALL`

---

## 5. Measured Baseline Results

*(Extracted directly from `reports/detector_baseline.json`)*

### 5.1 Detection Accuracy (COCOeval mAP)
- **Total Evaluated Test Images**: 1,554
- **Scored Ground Truth Boxes**: 43,190
- **Total Predictions (conf >= 0.001)**: 53,296
- **Overall mAP@0.5:0.95**: **0.0215 (2.15%)**
- **Overall mAP@0.5**: **0.0398 (3.98%)**
- **Bootstrap 95% Confidence Intervals (50 iterations, 85% sample subset)**:
  - **mAP@0.5:0.95 (95% CI)**: `[0.0208, 0.0226]`, $\sigma = 0.0005$
  - **mAP@0.5 (95% CI)**: `[0.0385, 0.0412]`, $\sigma = 0.0008$

### 5.2 Per-Class Breakdown
| Category | GT Boxes | mAP@0.5:0.95 | mAP@0.5 | Reliability Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Car** | 33,624 | **0.0592 (5.92%)** | **0.1235 (12.35%)** | High statistical power ($>33\text{k}$ boxes) |
| **Motorcycle** | 5,842 | **0.0022 (0.22%)** | **0.0028 (0.28%)** | Severe degradation due to small aerial pixel scale |
| **Truck** | 1,967 | **0.0121 (1.21%)** | **0.0186 (1.86%)** | Low representation, non-Indian truck body types |
| **Bus** | 1,757 | **0.0125 (1.25%)** | **0.0143 (1.43%)** | Low representation |

### 5.3 Latency & Throughput Profile
- **Warmup Iterations**: 20
- **Measured Iterations**: 1,534 post-warmup iterations
- **Model Inference Latency (ms)**:
  - Median (p50): **52.03 ms**
  - 95th Percentile (p95): **174.70 ms**
  - 99th Percentile (p99): **576.08 ms**
  - Mean: **80.28 ms** ($\sigma = 136.66\text{ ms}$)
- **Full Pipeline Latency (ms)**:
  - Median (p50): **65.54 ms**
  - 95th Percentile (p95): **203.30 ms**
  - 99th Percentile (p99): **632.41 ms**
  - Mean: **96.98 ms** ($\sigma = 155.48\text{ ms}$)
- **Component Breakdown**:
  - Preprocessing: mean **3.18 ms** (p50: 2.14 ms)
  - Postprocessing + NMS: mean **13.51 ms** (p50: 9.90 ms)
- **Steady-State Inference FPS**: **12.46 FPS** ($1000 / 80.28\text{ ms}$)
- **Steady-State Full Pipeline FPS**: **10.31 FPS** ($1000 / 96.98\text{ ms}$)

---

## 6. Exact Reproduction Command

```bash
# 1. Activate verified virtual environment
source ~/venvs/highway/bin/activate
cd ~/Downloads/highway-safety-agent

# 2. Run full 1,554-image evaluation on held-out split
python tools/eval_detector.py \
  --model models/yolov8n_coco_320.onnx \
  --split configs/visdrone_det_split_v1.json \
  --conf 0.001 \
  --out reports/detector_baseline.json
```

---

## 7. Next Optimization Steps (One PR per variable)

1. **Letterbox vs Stretch Preprocessing**: Benchmark letterboxed input against stretch-to-320x320 to evaluate mAP recovery from aspect-ratio preservation.
2. **Per-Vehicle-Class Thresholding**: Evaluate per-vehicle sigmoid scoring vs argmax over all 84 outputs to avoid dropping vehicles masked by background classes.
3. **INT8 Quantization & Edge SBC Profiling**: Quantize the verified model to INT8 and benchmark on target ARM edge devices (Raspberry Pi 4B / 5).
