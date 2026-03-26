#!/usr/bin/env python3
"""
Pipeline Benchmark Tool.

Profiles each stage of the verification pipeline.

Usage:
    python tools/benchmark.py --model models/mdgtv2.onnx --iterations 50
"""
import argparse
import sys
import time
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def generate_test_image(width: int = 192, height: int = 192) -> bytes:
    """Generate synthetic fingerprint-like test image."""
    import numpy as np

    # Create a synthetic pattern with ridges
    x = np.linspace(0, 4 * np.pi, width)
    y = np.linspace(0, 4 * np.pi, height)
    xx, yy = np.meshgrid(x, y)

    # Simulated ridge pattern
    pattern = np.sin(xx * 2 + yy * 0.5) * 50 + 128
    noise = np.random.normal(0, 10, (height, width))
    image = np.clip(pattern + noise, 0, 255).astype(np.uint8)

    return image.tobytes()


def benchmark_preprocessing(image_bytes: bytes, iterations: int) -> dict:
    """Benchmark preprocessing stage."""
    try:
        from mdgt_edge.pipeline.preprocessing import FingerprintPreprocessor

        preprocessor = FingerprintPreprocessor()
        latencies = []

        for _ in range(iterations):
            start = time.perf_counter()
            preprocessor.process(image_bytes)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        latencies.sort()
        return {
            "stage": "preprocessing",
            "iterations": iterations,
            "avg_ms": sum(latencies) / len(latencies),
            "min_ms": latencies[0],
            "max_ms": latencies[-1],
            "p50_ms": latencies[len(latencies) // 2],
            "p95_ms": latencies[int(0.95 * len(latencies))],
        }
    except ImportError as e:
        return {"stage": "preprocessing", "error": str(e)}


def benchmark_minutiae(image_bytes: bytes, iterations: int) -> dict:
    """Benchmark minutiae extraction stage."""
    try:
        from mdgt_edge.pipeline.minutiae_extractor import SimpleCNExtractor
        import numpy as np

        image = np.frombuffer(image_bytes, dtype=np.uint8).reshape(192, 192)
        extractor = SimpleCNExtractor()
        latencies = []

        for _ in range(iterations):
            start = time.perf_counter()
            extractor.extract(image)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        latencies.sort()
        return {
            "stage": "minutiae_extraction",
            "iterations": iterations,
            "avg_ms": sum(latencies) / len(latencies),
            "min_ms": latencies[0],
            "max_ms": latencies[-1],
            "p50_ms": latencies[len(latencies) // 2],
            "p95_ms": latencies[int(0.95 * len(latencies))],
        }
    except ImportError as e:
        return {"stage": "minutiae_extraction", "error": str(e)}


def benchmark_graph(iterations: int) -> dict:
    """Benchmark graph construction stage."""
    try:
        from mdgt_edge.pipeline.graph_builder import DynamicGraphBuilder
        from mdgt_edge.pipeline.minutiae_extractor import Minutia
        import numpy as np

        builder = DynamicGraphBuilder()

        # Generate synthetic minutiae
        minutiae = [
            Minutia(
                x=float(np.random.uniform(10, 180)),
                y=float(np.random.uniform(10, 180)),
                theta=float(np.random.uniform(0, 2 * np.pi)),
                minutia_type="ridge_ending" if i % 2 == 0 else "bifurcation",
                quality=float(np.random.uniform(0.5, 1.0)),
            )
            for i in range(40)
        ]

        latencies = []
        for _ in range(iterations):
            start = time.perf_counter()
            builder.build(minutiae, k=16)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        latencies.sort()
        return {
            "stage": "graph_construction",
            "iterations": iterations,
            "minutiae_count": len(minutiae),
            "avg_ms": sum(latencies) / len(latencies),
            "min_ms": latencies[0],
            "max_ms": latencies[-1],
            "p50_ms": latencies[len(latencies) // 2],
            "p95_ms": latencies[int(0.95 * len(latencies))],
        }
    except ImportError as e:
        return {"stage": "graph_construction", "error": str(e)}


def benchmark_inference(model_path: str, iterations: int) -> dict:
    """Benchmark model inference stage."""
    path = Path(model_path)
    if not path.exists():
        return {"stage": "inference", "error": f"Model not found: {model_path}"}

    try:
        if path.suffix == ".onnx":
            from mdgt_edge.pipeline.inference_engine import ONNXBackend
            backend = ONNXBackend()
        else:
            from mdgt_edge.pipeline.inference_engine import TensorRTBackend
            backend = TensorRTBackend()

        if not backend.load(str(path)):
            return {"stage": "inference", "error": "Failed to load model"}

        info = backend.get_info()
        return {
            "stage": "inference",
            "model": path.name,
            "backend": info.get("backend", "unknown"),
            "note": "Full benchmark requires graph data input",
        }
    except ImportError as e:
        return {"stage": "inference", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Pipeline Benchmark Tool")
    parser.add_argument("--model", "-m", default=None, help="Model path for inference benchmark")
    parser.add_argument("--iterations", "-n", type=int, default=50, help="Iterations per stage")
    parser.add_argument("--output", "-o", default=None, help="Output JSON file")
    parser.add_argument("--stage", choices=["all", "preprocess", "minutiae", "graph", "inference"],
                        default="all", help="Which stage to benchmark")
    args = parser.parse_args()

    print(f"=== MDGT Edge Pipeline Benchmark ===")
    print(f"Iterations: {args.iterations}")
    print()

    image_bytes = generate_test_image()
    results = []

    stages = {
        "preprocess": lambda: benchmark_preprocessing(image_bytes, args.iterations),
        "minutiae": lambda: benchmark_minutiae(image_bytes, args.iterations),
        "graph": lambda: benchmark_graph(args.iterations),
        "inference": lambda: benchmark_inference(args.model or "", args.iterations),
    }

    for name, bench_fn in stages.items():
        if args.stage != "all" and args.stage != name:
            continue

        print(f"--- {name.upper()} ---")
        result = bench_fn()
        results.append(result)

        if "error" in result:
            print(f"  Error: {result['error']}")
        else:
            for key, val in result.items():
                if key not in ("stage", "iterations"):
                    if isinstance(val, float):
                        print(f"  {key}: {val:.3f}")
                    else:
                        print(f"  {key}: {val}")
        print()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {args.output}")


if __name__ == "__main__":
    main()
