"""MDGT Edge AI inference pipeline for fingerprint verification.

Public API
----------
Preprocessing:
    FingerprintPreprocessor

Minutiae extraction:
    Minutia, MinutiaeType, MinutiaeExtractor,
    FingerNetExtractor, SimpleCNExtractor

Graph construction:
    GraphData, DynamicGraphBuilder

Inference:
    InferenceBackend, ONNXBackend, TensorRTBackend

Vector search:
    FAISSIndexManager

Orchestration:
    VerificationPipeline, profile_stage

Profiling:
    PipelineProfiler
"""

from mdgt_edge.pipeline.profiler import PipelineProfiler

# Lazy imports: pipeline modules require optional deps (cv2, numpy, faiss)
# Import them only when accessed to avoid ImportError on systems without these.
try:
    from mdgt_edge.pipeline.faiss_index import FAISSIndexManager
    from mdgt_edge.pipeline.graph_builder import DynamicGraphBuilder, GraphData
    from mdgt_edge.pipeline.inference_engine import (
        InferenceBackend,
        ONNXBackend,
        TensorRTBackend,
    )
    from mdgt_edge.pipeline.minutiae_extractor import (
        FingerNetExtractor,
        Minutia,
        MinutiaeExtractor,
        MinutiaeType,
        SimpleCNExtractor,
    )
    from mdgt_edge.pipeline.pipeline import VerificationPipeline, profile_stage
    from mdgt_edge.pipeline.preprocessing import FingerprintPreprocessor
except ImportError:
    pass  # Optional deps not installed; individual modules importable directly

__all__ = [
    # Preprocessing
    "FingerprintPreprocessor",
    # Minutiae
    "Minutia",
    "MinutiaeType",
    "MinutiaeExtractor",
    "FingerNetExtractor",
    "SimpleCNExtractor",
    # Graph
    "GraphData",
    "DynamicGraphBuilder",
    # Inference
    "InferenceBackend",
    "ONNXBackend",
    "TensorRTBackend",
    # FAISS
    "FAISSIndexManager",
    # Pipeline
    "VerificationPipeline",
    "profile_stage",
    # Profiler
    "PipelineProfiler",
]
