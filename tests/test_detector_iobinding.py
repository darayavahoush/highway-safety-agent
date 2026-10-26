"""Tests for the optional ONNX Runtime output-buffer path after integration."""
from types import ModuleType, SimpleNamespace
import ctypes
import sys

import numpy as np
import pytest


def _fake_onnxruntime(monkeypatch):
    try:
        import app.detector as detector_module
    except ImportError:
        pytest.skip("requires highway-safety-agent app.detector")
    if not hasattr(detector_module.OrtYoloDetector, "infer_raw"):
        pytest.skip("apply the PR #10 integration before running I/O-binding tests")

    class FakeOptions:
        def __init__(self):
            self.intra_op_num_threads = None
            self.inter_op_num_threads = None
            self.enable_cpu_mem_arena = None
            self.execution_mode = None
            self.graph_optimization_level = None

    class FakeBinding:
        def __init__(self):
            self.output_spec = None
            self.input_blob = None

        def bind_output(self, *args):
            self.output_spec = args

        def clear_binding_inputs(self):
            self.input_blob = None

        def bind_cpu_input(self, name, blob):
            self.input_blob = blob

        def synchronize_outputs(self):
            pass

    class FakeSession:
        def __init__(self, options):
            self.options = options
            self.binding = FakeBinding()
            self.run_count = 0
            self.binding_run_count = 0

        def get_inputs(self):
            return [SimpleNamespace(name="images")]

        def get_outputs(self):
            return [SimpleNamespace(name="output")]

        def get_providers(self):
            return ["CPUExecutionProvider"]

        def run(self, output_names, feed):
            self.run_count += 1
            value = float(feed["images"][0, 0, 0, 0])
            return [np.full((1, 12, 2), value, dtype=np.float32)]

        def io_binding(self):
            return self.binding

        def run_with_iobinding(self, binding):
            self.binding_run_count += 1
            _, device, _device_id, dtype, shape, ptr = binding.output_spec
            assert device == "cpu"
            c_type = ctypes.c_float if dtype is np.float32 else ctypes.c_double
            view = np.ctypeslib.as_array((c_type * int(np.prod(shape))).from_address(ptr)).reshape(shape)
            value = float(binding.input_blob[0, 0, 0, 0])
            np.copyto(view, np.full(shape, value, dtype=np.dtype(dtype)))

    fake_session = None
    def make_session(model_path, options, providers):
        nonlocal fake_session
        assert providers == ["CPUExecutionProvider"]
        fake_session = FakeSession(options)
        return fake_session

    ort = ModuleType("onnxruntime")
    ort.__version__ = "fake-test-runtime"
    ort.SessionOptions = FakeOptions
    ort.ExecutionMode = SimpleNamespace(ORT_SEQUENTIAL="sequential")
    ort.GraphOptimizationLevel = SimpleNamespace(ORT_ENABLE_ALL="all")
    ort.InferenceSession = make_session
    monkeypatch.setitem(sys.modules, "onnxruntime", ort)
    return detector_module, lambda: fake_session


def test_ort_detector_iobinding_reuses_fixed_output_buffer(monkeypatch):
    detector_module, get_session = _fake_onnxruntime(monkeypatch)
    monkeypatch.setenv("ORT_NUM_THREADS", "2")
    monkeypatch.setenv("ORT_INTRA_OP_THREADS", "2")
    monkeypatch.setenv("ORT_INTER_OP_THREADS", "1")
    monkeypatch.setenv("ORT_ENABLE_CPU_MEM_ARENA", "1")
    detector = detector_module.OrtYoloDetector("fake-model.onnx", input_size=320)
    session = get_session()

    first = detector.infer_raw(np.full((1, 3, 320, 320), 1, dtype=np.float32), use_iobinding=True)
    assert np.all(first == 1)
    buffer = detector._output_buffer
    assert buffer is not None

    second = detector.infer_raw(np.full((1, 3, 320, 320), 2, dtype=np.float32), use_iobinding=True)
    assert second is buffer
    assert np.all(second == 2)
    third = detector.infer_raw(np.full((1, 3, 320, 320), 3, dtype=np.float32), use_iobinding=True)
    assert third is buffer
    assert np.all(third == 3)
    assert session.run_count == 1
    assert session.binding_run_count == 2
    assert session.options.intra_op_num_threads == 2
    assert session.options.inter_op_num_threads == 1
    assert session.options.enable_cpu_mem_arena is True


def test_ort_detector_default_path_keeps_session_run(monkeypatch):
    detector_module, get_session = _fake_onnxruntime(monkeypatch)
    monkeypatch.setenv("ORT_NUM_THREADS", "2")
    detector = detector_module.OrtYoloDetector("fake-model.onnx", input_size=320)
    session = get_session()
    output = detector.infer_raw(np.full((1, 3, 320, 320), 7, dtype=np.float32), use_iobinding=False)
    assert np.all(output == 7)
    assert session.run_count == 1
    assert session.binding_run_count == 0


def test_invalid_thread_setting_is_rejected(monkeypatch):
    detector_module, _ = _fake_onnxruntime(monkeypatch)
    monkeypatch.setenv("ORT_INTRA_OP_THREADS", "0")
    with pytest.raises(ValueError, match="must be >= 1"):
        detector_module.OrtYoloDetector("fake-model.onnx", input_size=320)
