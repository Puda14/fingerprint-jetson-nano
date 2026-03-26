"""Inference backends for the MDGTv2 fingerprint embedding model.

Supports ONNX Runtime and TensorRT with graceful fallback when either
dependency is unavailable.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from mdgt_edge.pipeline.graph_builder import GraphData

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
    def get_info(self) -> dict[str, Any]:
        """Return model / backend metadata."""

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

    def profile(self, graph_data: GraphData, iterations: int = 20) -> dict[str, float]:
        """Profile inference latency over *iterations* runs.

        Returns:
            Dict with ``avg_ms``, ``min_ms``, ``max_ms``, ``p95_ms``.
        """
        latencies: list[float] = []
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
        self._model_path: str | None = None
        self._ort = None

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
            logger.info("ONNX model loaded from %s (providers=%s)", model_path, providers)
            return True
        except Exception as exc:
            logger.error("Failed to load ONNX model %s: %s", model_path, exc)
            return False

    def infer(self, graph_data: GraphData) -> np.ndarray:
        if self._session is None:
            raise RuntimeError("ONNX model not loaded. Call load() first.")

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
        feed: dict[str, np.ndarray] = {}

        # Map positionally -- the ONNX export order is:
        #   node_features, edge_index, relational_features
        inputs_data = [node_feat, edge_idx, rel_feat]
        for name, data in zip(input_names, inputs_data):
            feed[name] = data

        outputs = self._session.run(None, feed)
        embedding = outputs[0].squeeze().astype(np.float32)

        return self._l2_normalize(embedding)

    def get_info(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "backend": "onnxruntime",
            "model_path": self._model_path,
            "loaded": self._session is not None,
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
        self._model_path: str | None = None
        self._trt = None
        self._cuda = None
        self._bindings: list[dict[str, Any]] = []
        self._stream = None

    def load(self, model_path: str) -> bool:
        try:
            import tensorrt as trt  # type: ignore[import-untyped]
            import pycuda.driver as cuda  # type: ignore[import-untyped]
            import pycuda.autoinit  # type: ignore[import-untyped]  # noqa: F401

            self._trt = trt
            self._cuda = cuda
        except ImportError as exc:
            logger.error(
                "TensorRT or PyCUDA not available: %s. "
                "Use ONNXBackend as a fallback.",
                exc,
            )
            return False

        trt_logger = self._trt.Logger(self._trt.Logger.WARNING)

        try:
            with open(model_path, "rb") as f:
                engine_data = f.read()

            runtime = self._trt.Runtime(trt_logger)
            self._engine = runtime.deserialize_cuda_engine(engine_data)
            if self._engine is None:
                logger.error("Failed to deserialise TensorRT engine from %s", model_path)
                return False

            self._context = self._engine.create_execution_context()
            self._stream = self._cuda.Stream()
            self._model_path = model_path

            # Pre-allocate bindings
            self._bindings = []
            for i in range(self._engine.num_bindings):
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

            logger.info(
                "TensorRT engine loaded from %s (%d bindings)",
                model_path,
                len(self._bindings),
            )
            return True
        except Exception as exc:
            logger.error("TensorRT load failed for %s: %s", model_path, exc)
            return False

    def infer(self, graph_data: GraphData) -> np.ndarray:
        if self._engine is None or self._context is None:
            raise RuntimeError("TensorRT engine not loaded. Call load() first.")

        cuda = self._cuda
        n = graph_data.num_nodes
        k = graph_data.edge_index.shape[1] if graph_data.edge_index.ndim == 2 else 0

        # Prepare host buffers and set dynamic shapes
        host_inputs: list[np.ndarray] = []
        host_outputs: list[np.ndarray] = []
        device_buffers: list[Any] = []
        buffer_ptrs: list[int] = []

        input_data_map = {
            0: graph_data.node_features.astype(np.float32),
            1: graph_data.edge_index.astype(np.int32),
            2: graph_data.relational_features.astype(np.float32),
        }

        input_idx = 0
        for binding in self._bindings:
            if binding["is_input"]:
                data = input_data_map.get(input_idx)
                if data is None:
                    raise RuntimeError(
                        f"No input data for binding index {input_idx}"
                    )
                # Add batch dim
                if data.ndim < len(binding["shape"]):
                    data = data[np.newaxis, ...]
                # Set dynamic shape
                self._context.set_binding_shape(binding["index"], data.shape)
                host_buf = np.ascontiguousarray(data)
                host_inputs.append(host_buf)
                dev_buf = cuda.mem_alloc(host_buf.nbytes)
                device_buffers.append(dev_buf)
                buffer_ptrs.append(int(dev_buf))
                input_idx += 1
            else:
                shape = tuple(
                    self._context.get_binding_shape(binding["index"])
                )
                host_buf = np.empty(shape, dtype=binding["dtype"])
                host_outputs.append(host_buf)
                dev_buf = cuda.mem_alloc(host_buf.nbytes)
                device_buffers.append(dev_buf)
                buffer_ptrs.append(int(dev_buf))

        # H2D transfer
        for h_in, d_buf in zip(host_inputs, device_buffers[: len(host_inputs)]):
            cuda.memcpy_htod_async(d_buf, h_in, self._stream)

        # Execute
        self._context.execute_async_v2(
            bindings=buffer_ptrs, stream_handle=self._stream.handle
        )

        # D2H transfer
        out_offset = len(host_inputs)
        for h_out, d_buf in zip(
            host_outputs, device_buffers[out_offset:]
        ):
            cuda.memcpy_dtoh_async(h_out, d_buf, self._stream)

        self._stream.synchronize()

        embedding = host_outputs[0].squeeze().astype(np.float32)
        return self._l2_normalize(embedding)

    def get_info(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "backend": "tensorrt",
            "model_path": self._model_path,
            "loaded": self._engine is not None,
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
