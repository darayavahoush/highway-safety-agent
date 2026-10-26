"""
Vehicle detectors. Both expose the same interface:

    detect(frame) -> list of (x, y, w, h, label, confidence)

so tracker.py and main.py don't care which one is in use.

YoloOnnxDetector (default): YOLOv8n exported to ONNX, run through OpenCV's
built-in cv2.dnn module. This is the one that actually labels vehicle type
(Car / Truck / Bus / Motorbike) via COCO class IDs. No PyTorch or other ML
runtime needed on the inference device — opencv-python(-headless) already
ships cv2.dnn. The ONNX export step happens once, on a normal machine (see
scripts/export_yolo_onnx.py); only the small resulting .onnx file needs to
reach a Raspberry Pi.

BackgroundSubtractionDetector: the original zero-model fallback. Cheaper
than any DL detector, but can't tell you vehicle type — everything comes
back labeled "Vehicle". Useful if a specific Pi is too weak even for
YOLOv8n at a small input size, or as a sanity check when tuning a new
camera's tripwire line.
"""

import os
import cv2
import numpy as np

# COCO class indices YOLOv8 was trained on, restricted to vehicle types.
COCO_VEHICLE_CLASSES = {
    2: "Car",
    3: "Motorbike",
    5: "Bus",
    7: "Truck",
}

# VisDrone vehicle class indices from fine-tuned VisDroneVehicles dataset.
VISDRONE_VEHICLE_CLASSES = {
    0: "Car",
    1: "Van",
    2: "Truck",
    3: "Bus",
    4: "Motorbike",
}


def _postprocess_yolo_output(output, frame_w, frame_h, input_size, conf_threshold, nms_threshold):
    """Pure function (no cv2.dnn network needed) so it's independently testable.

    output: raw YOLOv8 ONNX output, shape (1, C, N) — 4 box coords + (C-4)
    class scores per candidate detection. C=84 for standard COCO, C=9 for
    5-class VisDrone fine-tuned models.
    """
    preds = output[0].T  # -> (N, C)
    x_scale, y_scale = frame_w / input_size, frame_h / input_size

    num_classes = output.shape[1] - 4
    if num_classes == 5:
        vehicle_classes = VISDRONE_VEHICLE_CLASSES
    else:
        vehicle_classes = COCO_VEHICLE_CLASSES

    boxes, confidences, class_ids = [], [], []
    for row in preds:
        class_scores = row[4:]
        class_id = int(np.argmax(class_scores))
        confidence = float(class_scores[class_id])
        if confidence < conf_threshold or class_id not in vehicle_classes:
            continue
        cx, cy, bw, bh = row[0:4]
        x = (cx - bw / 2) * x_scale
        y = (cy - bh / 2) * y_scale
        boxes.append([int(x), int(y), int(bw * x_scale), int(bh * y_scale)])
        confidences.append(confidence)
        class_ids.append(class_id)

    results = []
    if boxes:
        indices = cv2.dnn.NMSBoxes(boxes, confidences, conf_threshold, nms_threshold)
        for i in np.array(indices).flatten():
            x, y, bw, bh = boxes[i]
            results.append((x, y, bw, bh, vehicle_classes[class_ids[i]], confidences[i]))
    return results


DNN_NUM_THREADS = int(os.getenv("DNN_NUM_THREADS", "0"))
if DNN_NUM_THREADS > 0:
    cv2.setNumThreads(DNN_NUM_THREADS)


class YoloOnnxDetector:
    def __init__(self, model_path, input_size=320, conf_threshold=0.4, nms_threshold=0.45):
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        self.input_size = input_size
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold

    def detect(self, frame):
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame, scalefactor=1 / 255.0, size=(self.input_size, self.input_size),
            swapRB=True, crop=False,
        )
        self.net.setInput(blob)
        output = self.net.forward()
        return _postprocess_yolo_output(
            output, w, h, self.input_size, self.conf_threshold, self.nms_threshold
        )


class OrtYoloDetector:
    """ONNX Runtime detector with explicit CPU settings and optional I/O Binding.

    I/O Binding is opt-in (ORT_USE_IO_BINDING=1) so the original execution path
    remains the default. The reusable output buffer is only intended for one
    inference call at a time per detector instance.
    """

    @staticmethod
    def _env_bool(name, default):
        value = os.getenv(name)
        if value is None:
            return default
        value = value.strip().lower()
        if value in ("1", "true", "yes", "on"):
            return True
        if value in ("0", "false", "no", "off"):
            return False
        raise ValueError(f"{name} must be a boolean (0/1/true/false), got {value!r}")

    @staticmethod
    def _positive_int_env(name, default):
        raw = os.getenv(name)
        if raw is None:
            return int(default)
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be a positive integer, got {raw!r}") from exc
        if value < 1:
            raise ValueError(f"{name} must be >= 1, got {value}")
        return value

    @staticmethod
    def _default_intra_op_threads():
        # Prefer a physical-core count when psutil is installed. If not, use a
        # conservative half of logical CPUs; this is a heuristic, not a hardware claim.
        try:
            import psutil
            physical = psutil.cpu_count(logical=False)
        except ImportError:
            physical = None
        if not physical:
            physical = max(1, (os.cpu_count() or 2) // 2)
        return max(1, min(4, int(physical)))

    def __init__(self, model_path, input_size=320, conf_threshold=0.4, nms_threshold=0.45):
        try:
            import onnxruntime as ort
        except ImportError:
            raise RuntimeError(
                "onnxruntime is not installed. Run 'pip install onnxruntime' "
                "or use OpenCV DNN backend with an unquantized FP32 model."
            )
        opts = ort.SessionOptions()
        # ORT_NUM_THREADS remains supported for backwards compatibility.
        legacy_threads = os.getenv("ORT_NUM_THREADS")
        default_threads = int(legacy_threads) if legacy_threads else self._default_intra_op_threads()
        opts.intra_op_num_threads = self._positive_int_env("ORT_INTRA_OP_THREADS", default_threads)
        opts.inter_op_num_threads = self._positive_int_env("ORT_INTER_OP_THREADS", 1)
        opts.enable_cpu_mem_arena = self._env_bool("ORT_ENABLE_CPU_MEM_ARENA", True)
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.ort_intra_op_threads = opts.intra_op_num_threads
        self.ort_inter_op_threads = opts.inter_op_num_threads
        self.ort_enable_cpu_mem_arena = opts.enable_cpu_mem_arena
        self.input_name = self.session.get_inputs()[0].name
        outputs = self.session.get_outputs()
        if not outputs:
            raise RuntimeError("ONNX model exposes no outputs")
        self.output_name = outputs[0].name
        self._io_binding = None
        self._output_buffer = None
        self.input_size = input_size
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold

    def infer_raw(self, blob, use_iobinding=None):
        """Run the model. Optional CPU output binding reuses one fixed-shape buffer."""
        if use_iobinding is None:
            use_iobinding = self._env_bool("ORT_USE_IO_BINDING", False)
        if not use_iobinding:
            return self.session.run(None, {self.input_name: blob})[0]

        # First pass discovers the actual output shape and creates the reusable
        # buffer. This pass is ordinary session.run; benchmark warm-up must exclude it.
        if self._io_binding is None:
            outputs = self.session.run(None, {self.input_name: blob})
            if len(outputs) != 1:
                raise RuntimeError("ORT_USE_IO_BINDING currently requires exactly one model output")
            first_output = np.asarray(outputs[0])
            self._output_buffer = np.empty(first_output.shape, dtype=first_output.dtype, order="C")
            try:
                binding = self.session.io_binding()
                binding.bind_output(
                    self.output_name,
                    "cpu",
                    0,
                    self._output_buffer.dtype.type,
                    self._output_buffer.shape,
                    self._output_buffer.ctypes.data,
                )
            except Exception as exc:
                self._output_buffer = None
                raise RuntimeError(f"Could not initialize ORT reusable output binding: {exc}") from exc
            self._io_binding = binding
            return first_output

        try:
            # Input memory changes frame-to-frame, so rebind the input pointer.
            # The bound output pointer remains the same reusable NumPy allocation.
            self._io_binding.clear_binding_inputs()
            self._io_binding.bind_cpu_input(self.input_name, blob)
            self.session.run_with_iobinding(self._io_binding)
            self._io_binding.synchronize_outputs()
        except Exception as exc:
            raise RuntimeError(f"ORT I/O Binding inference failed: {exc}") from exc
        return self._output_buffer

    def detect(self, frame):
        h, w = frame.shape[:2]
        img = cv2.resize(frame, (self.input_size, self.input_size))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        blob = np.transpose(img, (2, 0, 1))[np.newaxis, ...]
        output = self.infer_raw(blob)
        return _postprocess_yolo_output(
            output, w, h, self.input_size, self.conf_threshold, self.nms_threshold
        )

def create_yolo_detector(model_path, input_size=320, conf_threshold=0.4, nms_threshold=0.45, engine="auto"):
    """Factory selecting OpenCV DNN or ONNX Runtime based on model file and configuration."""
    is_int8 = "int8" in os.path.basename(model_path).lower()
    if engine == "ort" or (engine == "auto" and is_int8):
        return OrtYoloDetector(
            model_path, input_size=input_size, conf_threshold=conf_threshold, nms_threshold=nms_threshold
        )
    return YoloOnnxDetector(
        model_path, input_size=input_size, conf_threshold=conf_threshold, nms_threshold=nms_threshold
    )


class TiledYoloDetector:
    """
    Same detect(frame) -> boxes interface as YoloOnnxDetector, but slices
    the frame into overlapping tiles (sized to match the ONNX model's
    fixed input) before running detection, instead of squashing the whole
    frame down to input_size in one shot.

    Use this instead of YoloOnnxDetector when the camera is far overhead
    (drone/aerial) and/or the scene is dense with many small vehicles —
    a full-frame resize to 320x320 makes each vehicle a handful of pixels
    and the plain detector misses almost everything. Costs roughly
    (frame_area / tile_area) times as many forward passes per detection,
    so throttle how often you call it (see STATIC_DETECT_INTERVAL_SEC in
    main.py) rather than running it every frame.
    """

    def __init__(self, model_path, tile=320, overlap=80, conf_threshold=0.25, nms_threshold=0.4, engine="auto"):
        self._inner = create_yolo_detector(
            model_path, input_size=tile, conf_threshold=conf_threshold, nms_threshold=nms_threshold, engine=engine
        )
        self.tile = tile
        self.overlap = overlap
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold

    def detect(self, frame):
        h, w = frame.shape[:2]
        tile, stride = self.tile, self.tile - self.overlap

        boxes, confidences, labels = [], [], []
        ys = list(range(0, max(h - tile, 0) + 1, stride)) or [0]
        if ys[-1] + tile < h:
            ys.append(max(h - tile, 0))
        xs = list(range(0, max(w - tile, 0) + 1, stride)) or [0]
        if xs[-1] + tile < w:
            xs.append(max(w - tile, 0))

        for ty in ys:
            for tx in xs:
                crop = frame[ty:ty + tile, tx:tx + tile]
                ch, cw = crop.shape[:2]
                if ch < tile or cw < tile:
                    padded = np.zeros((tile, tile, 3), dtype=frame.dtype)
                    padded[:ch, :cw] = crop
                    crop = padded
                for (bx, by, bw, bh, label, conf) in self._inner.detect(crop):
                    boxes.append([bx + tx, by + ty, bw, bh])
                    confidences.append(conf)
                    labels.append(label)

        if not boxes:
            return []
        keep = cv2.dnn.NMSBoxes(boxes, confidences, self.conf_threshold, self.nms_threshold)
        keep = np.array(keep).flatten() if len(keep) else []
        return [(boxes[i][0], boxes[i][1], boxes[i][2], boxes[i][3], labels[i], confidences[i]) for i in keep]


class BackgroundSubtractionDetector:
    def __init__(
        self,
        min_area=900,
        max_area=60000,
        min_aspect=0.3,
        max_aspect=3.5,
        history=500,
        var_threshold=40,
        detect_shadows=True,
    ):
        self.min_area = min_area
        self.max_area = max_area
        self.min_aspect = min_aspect
        self.max_aspect = max_aspect

        self._bg = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=var_threshold,
            detectShadows=detect_shadows,
        )
        self._kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        self._kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

    def detect(self, frame):
        fg_mask = self._bg.apply(frame)
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self._kernel_open)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, self._kernel_close, iterations=2)

        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < self.min_area or area > self.max_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            aspect = w / float(h)
            if aspect < self.min_aspect or aspect > self.max_aspect:
                continue
            # No classifier here, so label is generic — this detector can
            # tell you *something* is there, not *what*.
            results.append((x, y, w, h, "Vehicle", 1.0))

        return results
