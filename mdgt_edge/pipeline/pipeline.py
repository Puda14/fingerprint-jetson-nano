"""End-to-end verification / identification pipeline orchestrating all stages."""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import Any, Callable, TypeVar

import numpy as np

from mdgt_edge.pipeline.faiss_index import FAISSIndexManager
from mdgt_edge.pipeline.graph_builder import DynamicGraphBuilder, GraphData
from mdgt_edge.pipeline.inference_engine import (
    InferenceBackend,
    ONNXBackend,
    TensorRTBackend,
)
from mdgt_edge.pipeline.minutiae_extractor import (
    FingerNetExtractor,
    MinutiaeExtractor,
    SimpleCNExtractor,
)
from mdgt_edge.pipeline.preprocessing import FingerprintPreprocessor
from mdgt_edge.pipeline.profiler import PipelineProfiler

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ------------------------------------------------------------------
# Profiling decorator
# ------------------------------------------------------------------


def profile_stage(stage_name: str) -> Callable[[F], F]:
    """Decorator that measures execution time and records it in the profiler.

    Works for both sync and async callables.  The decorated object must be
    a method on ``VerificationPipeline`` (i.e. ``self._profiler`` must exist).
    """

    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
                profiler: PipelineProfiler = self._profiler
                profiler.start(stage_name)
                try:
                    result = await func(self, *args, **kwargs)
                finally:
                    profiler.stop(stage_name)
                return result

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            profiler: PipelineProfiler = self._profiler
            profiler.start(stage_name)
            try:
                result = func(self, *args, **kwargs)
            finally:
                profiler.stop(stage_name)
            return result

        return sync_wrapper  # type: ignore[return-value]

    return decorator


# ------------------------------------------------------------------
# Pipeline
# ------------------------------------------------------------------


class VerificationPipeline:
    """Orchestrates preprocessing -> minutiae extraction -> graph build
    -> model inference -> FAISS search.

    Config dict keys (all optional -- sensible defaults are used):
        ``image_width``          int   (192)
        ``image_height``         int   (192)
        ``image_size``           int   (192)  for graph builder normalisation
        ``knn_k``                int   (16)
        ``embedding_dim``        int   (256)
        ``backend``              str   ``"onnx"`` | ``"tensorrt"``
        ``model_path``           str   path to model file
        ``extractor``            str   ``"fingernet"`` | ``"cn"``
        ``fingernet_model_path`` str   path to FingerNet ONNX
        ``clahe_clip``           float (2.5)
        ``clahe_grid``           int   (8)
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}

        self._image_width: int = cfg.get("image_width", 192)
        self._image_height: int = cfg.get("image_height", 192)
        self._image_size: int = cfg.get("image_size", 192)
        self._knn_k: int = cfg.get("knn_k", 16)
        self._embedding_dim: int = cfg.get("embedding_dim", 256)

        # Profiler
        self._profiler = PipelineProfiler()

        # Preprocessor
        self._preprocessor = FingerprintPreprocessor(
            clahe_clip=cfg.get("clahe_clip", 2.5),
            clahe_grid=cfg.get("clahe_grid", 8),
        )

        # Minutiae extractor
        extractor_type = cfg.get("extractor", "cn")
        if extractor_type == "fingernet":
            fp_model = cfg.get("fingernet_model_path", "")
            self._extractor: MinutiaeExtractor = FingerNetExtractor(fp_model)
        else:
            self._extractor = SimpleCNExtractor()

        # Graph builder
        self._graph_builder = DynamicGraphBuilder(image_size=self._image_size)

        # Inference backend
        backend_name = cfg.get("backend", "onnx")
        if backend_name == "tensorrt":
            self._backend: InferenceBackend = TensorRTBackend()
        else:
            self._backend = ONNXBackend()

        model_path = cfg.get("model_path")
        if model_path:
            loaded = self._backend.load(model_path)
            if not loaded:
                logger.warning(
                    "Model failed to load from %s. "
                    "Inference calls will raise until a model is loaded.",
                    model_path,
                )

        # FAISS index
        self._faiss = FAISSIndexManager(dim=self._embedding_dim)

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    async def extract_embedding(
        self, image: bytes
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Run the full pipeline and return the embedding + profiling data.

        Args:
            image: Raw image bytes.

        Returns:
            Tuple of (256-dim embedding, profiling dict).
        """
        loop = asyncio.get_event_loop()

        # Preprocessing
        self._profiler.start("preprocessing")
        preprocessed = await loop.run_in_executor(
            None,
            self._preprocessor.process,
            image,
            self._image_width,
            self._image_height,
        )
        self._profiler.stop("preprocessing")

        # Minutiae extraction
        self._profiler.start("minutiae_extraction")
        minutiae = await loop.run_in_executor(
            None, self._extractor.extract, preprocessed
        )
        self._profiler.stop("minutiae_extraction")

        if not minutiae:
            logger.warning("No minutiae detected; returning zero embedding.")
            zero = np.zeros(self._embedding_dim, dtype=np.float32)
            return zero, self._profiler.get_report()

        # Graph construction
        self._profiler.start("graph_construction")
        graph = await loop.run_in_executor(
            None, self._graph_builder.build, minutiae, self._knn_k
        )
        self._profiler.stop("graph_construction")

        # Model inference
        self._profiler.start("inference")
        embedding = await loop.run_in_executor(
            None, self._backend.infer, graph
        )
        self._profiler.stop("inference")

        return embedding, self._profiler.get_report()

    async def verify(
        self,
        probe_image: bytes,
        gallery_embedding: np.ndarray,
        threshold: float = 0.55,
    ) -> tuple[bool, float]:
        """1:1 verification -- compare a probe image against a stored embedding.

        Args:
            probe_image: Raw image bytes of the probe.
            gallery_embedding: Pre-computed gallery embedding (256-dim).
            threshold: Cosine-similarity threshold for a match.

        Returns:
            ``(is_match, score)``
        """
        probe_emb, _ = await self.extract_embedding(probe_image)
        score = float(np.dot(probe_emb, gallery_embedding))
        is_match = score >= threshold
        logger.debug("Verify score=%.4f threshold=%.4f match=%s", score, threshold, is_match)
        return is_match, score

    async def identify(
        self,
        probe_image: bytes,
        top_k: int = 5,
        threshold: float = 0.50,
    ) -> list[tuple[int, float]]:
        """1:N identification -- search the FAISS gallery for matches.

        Args:
            probe_image: Raw image bytes.
            top_k: Max candidates to return.
            threshold: Minimum score to include.

        Returns:
            List of ``(fp_id, score)`` above threshold, sorted descending.
        """
        probe_emb, _ = await self.extract_embedding(probe_image)

        self._profiler.start("faiss_search")
        results = self._faiss.search(probe_emb, top_k=top_k)
        self._profiler.stop("faiss_search")

        filtered = [(fp_id, score) for fp_id, score in results if score >= threshold]
        return filtered

    # ------------------------------------------------------------------
    # FAISS helpers (delegate)
    # ------------------------------------------------------------------

    def enroll(self, embedding: np.ndarray, fp_id: int) -> None:
        """Add an embedding to the gallery."""
        self._faiss.add(embedding, fp_id)

    def build_gallery(self, embeddings: np.ndarray, ids: np.ndarray) -> None:
        """Build the FAISS gallery from a batch of embeddings."""
        self._faiss.build_index(embeddings, ids)

    def save_gallery(self, path: str) -> None:
        self._faiss.save(path)

    def load_gallery(self, path: str) -> None:
        self._faiss.load(path)

    # ------------------------------------------------------------------
    # Profiling
    # ------------------------------------------------------------------

    def get_profiling(self) -> dict[str, Any]:
        """Return per-stage profiling statistics."""
        return self._profiler.get_report()

    def reset_profiling(self) -> None:
        self._profiler.reset()
