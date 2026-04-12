"""Inference backends for the MDGTv2 fingerprint embedding model.

Supports ONNX Runtime and TensorRT with graceful fallback when either
dependency is unavailable.
"""


from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator, TypeVar, Type, Awaitable, Sequence, Mapping
import logging
import threading
import time
from abc import ABC, abstractmethod

import numpy as np

# Updated import: from app.pipeline instead of mdgt_edge.pipeline
from app.pipeline.graph_builder import GraphData

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Abstract base
# ------------------------------------------------------------------


class InferenceBackend(ABC):
    """Interface for MDGTv2 model inference backends."""

    @abstractmethod
    def load(self, model_path: str) -> bool:
        """Load a serialised model.

        Args:
            model_path: Filesystem path to the model file.

        Returns:
            ``True`` if the model was loaded successfully.
        """

    @abstractmethod
    def infer(self, graph_data: GraphData) -> np.ndarray:
        """Run inference and return a 256-dim L2-normalised embedding.

        Args:
            graph_data: Graph representation of a minutiae set.

        Returns:
            1-D float32 ndarray of length 256.
        """

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Return model / backend metadata."""

    @property
    def expects_image_input(self) -> bool:
        return False

    def infer_image(self, image: np.ndarray) -> np.ndarray:
        raise RuntimeError(
            "%s does not support image-input inference" % self.__class__.__name__
        )

    # Shared helpers -----------------------------------------------

    @staticmethod
    def _l2_normalize(vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        if norm < 1e-12:
            return vec
        return vec / norm

    def warmup(self, graph_data: GraphData, iterations: int = 5) -> float:
        """Run *iterations* dummy inferences and return average latency (ms).

        Args:
            graph_data: A representative graph for warm-up.
            iterations: Number of warm-up passes.

        Returns:
            Average inference time in milliseconds.
        """
        total = 0.0
        for _ in range(iterations):
            t0 = time.perf_counter()
            self.infer(graph_data)
            total += (time.perf_counter() - t0) * 1000.0
        avg = total / max(iterations, 1)
        logger.info(
            "%s warmup: %d iters, avg %.2f ms",
            self.__class__.__name__,
            iterations,
            avg,
        )
        return avg

    def profile(self, graph_data: GraphData, iterations: int = 20) -> Dict[str, float]:
        """Profile inference latency over *iterations* runs.

        Returns:
            Dict with ``avg_ms``, ``min_ms``, ``max_ms``, ``p95_ms``.
        """
        latencies: List[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            self.infer(graph_data)
            latencies.append((time.perf_counter() - t0) * 1000.0)
        latencies.sort()
        count = len(latencies)
        p95_idx = min(int(count * 0.95), count - 1)
        return {
            "avg_ms": sum(latencies) / count,
            "min_ms": latencies[0],
            "max_ms": latencies[-1],
            "p95_ms": latencies[p95_idx],
        }


# ------------------------------------------------------------------
# ONNX Runtime backend
# ------------------------------------------------------------------


class ONNXBackend(InferenceBackend):
    """ONNX Runtime inference backend with dynamic-shape support."""

    def __init__(self) -> None:
        self._session = None
        self._model_path: Optional[str] = None
        self._ort = None
        self._input_mode: str = "graph"
        self._image_input_name: Optional[str] = None
        self._image_input_shape: Optional[List[Any]] = None
        self._image_layout: str = "nchw"

    def load(self, model_path: str) -> bool:
        try:
            import onnxruntime as ort

            self._ort = ort
        except ImportError:
            logger.error("onnxruntime is not installed.")
            return False

        try:
            sess_opts = ort.SessionOptions()
            sess_opts.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            providers = []
            available = ort.get_available_providers()
            if "CUDAExecutionProvider" in available:
                providers.append("CUDAExecutionProvider")
            providers.append("CPUExecutionProvider")

            self._session = ort.InferenceSession(
                model_path, sess_options=sess_opts, providers=providers
            )
            self._model_path = model_path

            # Detect whether the model expects graph tensors or image tensors.
            # Graph models typically take 3 inputs; image models usually take
            # one rank-4 input like NCHW (e.g. input_image).
            inputs = self._session.get_inputs()
            if len(inputs) == 1:
                shape = inputs[0].shape
                rank = len(shape) if isinstance(shape, (list, tuple)) else 0
                if rank == 4:
                    self._input_mode = "image"
                    self._image_input_name = inputs[0].name
                    self._image_input_shape = list(shape)

                    # Infer layout from fixed channel position where possible.
                    # Most models are NCHW; NHWC is handled if channel appears last.
                    c_first = shape[1] if len(shape) > 1 else None
                    c_last = shape[3] if len(shape) > 3 else None
                    if c_last in (1, 3) and c_first not in (1, 3):
                        self._image_layout = "nhwc"
                    else:
                        self._image_layout = "nchw"
                else:
                    self._input_mode = "graph"
            else:
                self._input_mode = "graph"

            logger.info("ONNX model loaded from %s (providers=%s)", model_path, providers)
            logger.info("ONNX input mode detected: %s", self._input_mode)
            if self._input_mode == "image":
                logger.info(
                    "ONNX image input: name=%s shape=%s layout=%s",
                    self._image_input_name,
                    self._image_input_shape,
                    self._image_layout,
                )
            return True
        except Exception as exc:
            logger.error("Failed to load ONNX model %s: %s", model_path, exc)
            return False

    @property
    def expects_image_input(self) -> bool:
        return self._input_mode == "image"

    def infer_image(self, image: np.ndarray) -> np.ndarray:
        """Run inference for ONNX models that consume image tensors.

        Args:
            image: Grayscale uint8/float image with shape (H, W).

        Returns:
            1-D float32 normalized embedding.
        """
        if self._session is None:
            raise RuntimeError("ONNX model not loaded. Call load() first.")

        if image.ndim != 2:
            raise ValueError("Expected grayscale image with shape (H, W)")

        if self._image_input_name is None:
            self._image_input_name = self._session.get_inputs()[0].name

        target_h = None
        target_w = None
        if self._image_input_shape is not None and len(self._image_input_shape) == 4:
            if self._image_layout == "nchw":
                h_val = self._image_input_shape[2]
                w_val = self._image_input_shape[3]
            else:
                h_val = self._image_input_shape[1]
                w_val = self._image_input_shape[2]

            if isinstance(h_val, int) and h_val > 0:
                target_h = h_val
            if isinstance(w_val, int) and w_val > 0:
                target_w = w_val

        if target_h is not None and target_w is not None and image.shape != (target_h, target_w):
            import cv2

            image = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

        # Normalize to [0, 1] and convert to NCHW: (1, 1, H, W)
        img = image.astype(np.float32)
        if img.max() > 1.0:
            img = img / 255.0
        if self._image_layout == "nhwc":
            img = img[np.newaxis, :, :, np.newaxis]
        else:
            img = img[np.newaxis, np.newaxis, :, :]

        outputs = self._session.run(None, {self._image_input_name: img})
        embedding = outputs[0].squeeze().astype(np.float32)
        return self._l2_normalize(embedding)

    def infer(self, graph_data: GraphData) -> np.ndarray:
        if self._session is None:
            raise RuntimeError("ONNX model not loaded. Call load() first.")

        if self._input_mode == "image":
            raise RuntimeError(
                "Loaded ONNX model expects image input; use infer_image() path."
            )

        # Build feed dict matching expected dynamic-axis inputs
        node_feat = graph_data.node_features.astype(np.float32)
        edge_idx = graph_data.edge_index.astype(np.int64)
        rel_feat = graph_data.relational_features.astype(np.float32)

        # Add batch dim if model expects it
        if node_feat.ndim == 2:
            node_feat = node_feat[np.newaxis, ...]  # (1, N, 5)
        if edge_idx.ndim == 2:
            edge_idx = edge_idx[np.newaxis, ...]  # (1, N, k)
        if rel_feat.ndim == 3:
            rel_feat = rel_feat[np.newaxis, ...]  # (1, N, N, 7)

        input_names = [inp.name for inp in self._session.get_inputs()]
        feed: Dict[str, np.ndarray] = {}

        # Map positionally -- the ONNX export order is:
        #   node_features, edge_index, relational_features
        inputs_data = [node_feat, edge_idx, rel_feat]
        for name, data in zip(input_names, inputs_data):
            feed[name] = data

        outputs = self._session.run(None, feed)
        embedding = outputs[0].squeeze().astype(np.float32)

        return self._l2_normalize(embedding)

    def get_info(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "backend": "onnxruntime",
            "model_path": self._model_path,
            "loaded": self._session is not None,
            "input_mode": self._input_mode,
        }
        if self._session is not None:
            info["inputs"] = [
                {"name": i.name, "shape": i.shape, "type": i.type}
                for i in self._session.get_inputs()
            ]
            info["outputs"] = [
                {"name": o.name, "shape": o.shape, "type": o.type}
                for o in self._session.get_outputs()
            ]
        return info


# ------------------------------------------------------------------
# TensorRT backend
# ------------------------------------------------------------------


class TensorRTBackend(InferenceBackend):
    """TensorRT inference backend optimised for Jetson Nano FP16.

    Falls back gracefully when ``tensorrt`` is not importable.
    """

    def __init__(self) -> None:
        self._engine = None
        self._context = None
        self._model_path: Optional[str] = None
        self._trt = None
        self._cuda = None
        self._cuda_context = None
        self._bindings: List[Dict[str, Any]] = []
        self._input_bindings: List[Dict[str, Any]] = []
        self._output_bindings: List[Dict[str, Any]] = []
        self._stream = None
        self._input_mode: str = "graph"
        self._image_input_shape: Optional[List[Any]] = None
        self._image_layout: str = "nchw"
        self._binding_lock = threading.Lock()

    def load(self, model_path: str) -> bool:
        try:
            import tensorrt as trt  # type: ignore[import-untyped]
            import pycuda.driver as cuda  # type: ignore[import-untyped]

            self._trt = trt
            self._cuda = cuda
            self._cuda.init()
        except ImportError as exc:
            logger.error(
                "TensorRT or PyCUDA not available: %s. "
                "Use ONNXBackend as a fallback.",
                exc,
            )
            return False

        trt_logger = self._trt.Logger(self._trt.Logger.WARNING)

        try:
            device = self._cuda.Device(0)
            self._cuda_context = device.make_context()

            with open(model_path, "rb") as f:
                engine_data = f.read()

            runtime = self._trt.Runtime(trt_logger)
            self._engine = runtime.deserialize_cuda_engine(engine_data)
            if self._engine is None:
                logger.error("Failed to deserialise TensorRT engine from %s", model_path)
                return False

            self._context = self._engine.create_execution_context()
            if hasattr(self._context, "active_optimization_profile"):
                self._context.active_optimization_profile = 0
            self._stream = self._cuda.Stream()
            self._model_path = model_path

            # Inspect active-profile bindings only. TensorRT reports bindings
            # for every optimization profile, but only profile 0 is used here.
            self._bindings = []
            num_profiles = max(
                int(getattr(self._engine, "num_optimization_profiles", 1) or 1), 1
            )
            bindings_per_profile = max(int(self._engine.num_bindings / num_profiles), 1)
            for i in range(bindings_per_profile):
                name = self._engine.get_binding_name(i)
                dtype = self._trt.nptype(self._engine.get_binding_dtype(i))
                shape = self._engine.get_binding_shape(i)
                is_input = self._engine.binding_is_input(i)
                self._bindings.append(
                    {
                        "name": name,
                        "dtype": dtype,
                        "shape": tuple(shape),
                        "is_input": is_input,
                        "index": i,
                    }
                )

            self._input_bindings = [b for b in self._bindings if b["is_input"]]
            self._output_bindings = [b for b in self._bindings if not b["is_input"]]

            if len(self._input_bindings) == 1 and len(self._input_bindings[0]["shape"]) == 4:
                self._input_mode = "image"
                self._image_input_shape = list(self._input_bindings[0]["shape"])
                c_first = (
                    self._image_input_shape[1]
                    if len(self._image_input_shape) > 1
                    else None
                )
                c_last = (
                    self._image_input_shape[3]
                    if len(self._image_input_shape) > 3
                    else None
                )
                if c_last in (1, 3) and c_first not in (1, 3):
                    self._image_layout = "nhwc"
                else:
                    self._image_layout = "nchw"
            else:
                self._input_mode = "graph"

            logger.info(
                "TensorRT engine loaded from %s (%d bindings)",
                model_path,
                len(self._bindings),
            )
            logger.info("TensorRT input mode detected: %s", self._input_mode)
            if self._input_mode == "image":
                logger.info(
                    "TensorRT image input: name=%s shape=%s layout=%s",
                    self._input_bindings[0]["name"],
                    self._image_input_shape,
                    self._image_layout,
                )
            return True
        except Exception as exc:
            logger.error("TensorRT load failed for %s: %s", model_path, exc)
            return False
        finally:
            if self._cuda_context is not None:
                try:
                    self._cuda_context.pop()
                except Exception:
                    pass

    @property
    def expects_image_input(self) -> bool:
        return self._input_mode == "image"

    def _prepare_image_input(self, image: np.ndarray) -> np.ndarray:
        if image.ndim != 2:
            raise ValueError("Expected grayscale image with shape (H, W)")

        target_h = None
        target_w = None
        if self._image_input_shape is not None and len(self._image_input_shape) == 4:
            if self._image_layout == "nchw":
                h_val = self._image_input_shape[2]
                w_val = self._image_input_shape[3]
            else:
                h_val = self._image_input_shape[1]
                w_val = self._image_input_shape[2]

            if isinstance(h_val, int) and h_val > 0:
                target_h = h_val
            if isinstance(w_val, int) and w_val > 0:
                target_w = w_val

        if target_h is not None and target_w is not None and image.shape != (target_h, target_w):
            import cv2

            image = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

        img = image.astype(np.float32)
        if img.max() > 1.0:
            img = img / 255.0

        if self._image_layout == "nhwc":
            return img[np.newaxis, :, :, np.newaxis]
        return img[np.newaxis, np.newaxis, :, :]

    def _run_inference(self, inputs: List[np.ndarray]) -> np.ndarray:
        if self._engine is None or self._context is None or self._cuda_context is None:
            raise RuntimeError("TensorRT engine not loaded. Call load() first.")

        if len(inputs) != len(self._input_bindings):
            raise RuntimeError(
                "TensorRT engine expects %d inputs but received %d"
                % (len(self._input_bindings), len(inputs))
            )

        cuda = self._cuda
        with self._binding_lock:
            self._cuda_context.push()
            try:
                binding_ptrs: List[int] = [0] * int(self._engine.num_bindings)
                device_buffers: List[Any] = []
                host_outputs: List[np.ndarray] = []
                output_device_buffers: List[Any] = []

                for binding, data in zip(self._input_bindings, inputs):
                    host_buf = np.ascontiguousarray(data, dtype=binding["dtype"])
                    if host_buf.ndim < len(binding["shape"]):
                        host_buf = host_buf[np.newaxis, ...]

                    self._context.set_binding_shape(binding["index"], tuple(host_buf.shape))
                    dev_buf = cuda.mem_alloc(host_buf.nbytes)
                    device_buffers.append(dev_buf)
                    binding_ptrs[binding["index"]] = int(dev_buf)
                    cuda.memcpy_htod_async(dev_buf, host_buf, self._stream)

                for binding in self._output_bindings:
                    shape = tuple(self._context.get_binding_shape(binding["index"]))
                    host_buf = np.empty(shape, dtype=binding["dtype"])
                    dev_buf = cuda.mem_alloc(host_buf.nbytes)
                    device_buffers.append(dev_buf)
                    output_device_buffers.append(dev_buf)
                    host_outputs.append(host_buf)
                    binding_ptrs[binding["index"]] = int(dev_buf)

                self._context.execute_async_v2(
                    bindings=binding_ptrs, stream_handle=self._stream.handle
                )

                for host_buf, dev_buf in zip(host_outputs, output_device_buffers):
                    cuda.memcpy_dtoh_async(host_buf, dev_buf, self._stream)

                self._stream.synchronize()
                embedding = host_outputs[0].squeeze().astype(np.float32)
                return self._l2_normalize(embedding)
            finally:
                try:
                    self._cuda_context.pop()
                except Exception:
                    pass

    def infer_image(self, image: np.ndarray) -> np.ndarray:
        if self._input_mode != "image":
            raise RuntimeError(
                "Loaded TensorRT engine expects graph input; use infer() path."
            )
        return self._run_inference([self._prepare_image_input(image)])

    def infer(self, graph_data: GraphData) -> np.ndarray:
        if self._input_mode == "image":
            raise RuntimeError(
                "Loaded TensorRT engine expects image input; use infer_image() path."
            )

        input_tensors = [
            graph_data.node_features.astype(np.float32),
            graph_data.edge_index.astype(np.int32),
            graph_data.relational_features.astype(np.float32),
        ]
        return self._run_inference(input_tensors)

    def get_info(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "backend": "tensorrt",
            "model_path": self._model_path,
            "loaded": self._engine is not None,
            "input_mode": self._input_mode,
        }
        if self._bindings:
            info["bindings"] = [
                {
                    "name": b["name"],
                    "shape": b["shape"],
                    "is_input": b["is_input"],
                }
                for b in self._bindings
            ]
        return info
