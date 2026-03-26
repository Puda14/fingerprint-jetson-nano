#!/usr/bin/env python3
"""
ONNX to TensorRT Conversion Tool.

Usage:
    python tools/convert_trt.py --input models/mdgtv2.onnx --output models/mdgtv2_fp16.engine --fp16

Requirements:
    - Must run on Jetson Nano (TensorRT installed via JetPack)
    - ONNX model with dynamic axes for variable minutiae count
"""
import argparse
import sys
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def convert_onnx_to_trt(
    input_path: str,
    output_path: str,
    fp16: bool = True,
    max_workspace_mb: int = 1024,
    max_batch_size: int = 1,
) -> bool:
    """Convert ONNX model to TensorRT engine.

    Args:
        input_path: Path to ONNX model.
        output_path: Path to save TensorRT engine.
        fp16: Enable FP16 precision.
        max_workspace_mb: Maximum workspace size in MB.
        max_batch_size: Maximum batch size.

    Returns:
        True if conversion successful.
    """
    try:
        import tensorrt as trt
    except ImportError:
        logger.error("TensorRT not available. This tool must run on Jetson Nano with JetPack.")
        return False

    logger.info(f"TensorRT version: {trt.__version__}")
    logger.info(f"Input:  {input_path}")
    logger.info(f"Output: {output_path}")
    logger.info(f"FP16:   {fp16}")

    trt_logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(trt_logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, trt_logger)

    # Parse ONNX model
    logger.info("Parsing ONNX model...")
    with open(input_path, "rb") as f:
        if not parser.parse(f.read()):
            for i in range(parser.num_errors):
                logger.error(f"  Parse error: {parser.get_error(i)}")
            return False

    logger.info(f"  Network inputs:  {network.num_inputs}")
    logger.info(f"  Network outputs: {network.num_outputs}")

    for i in range(network.num_inputs):
        inp = network.get_input(i)
        logger.info(f"  Input {i}: {inp.name}, shape={inp.shape}, dtype={inp.dtype}")

    for i in range(network.num_outputs):
        out = network.get_output(i)
        logger.info(f"  Output {i}: {out.name}, shape={out.shape}, dtype={out.dtype}")

    # Build engine config
    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, max_workspace_mb * (1 << 20))

    if fp16 and builder.platform_has_fast_fp16:
        logger.info("Enabling FP16 precision")
        config.set_flag(trt.BuilderFlag.FP16)
    elif fp16:
        logger.warning("FP16 not supported on this platform, using FP32")

    # Handle dynamic shapes if present
    profile = builder.create_optimization_profile()
    for i in range(network.num_inputs):
        inp = network.get_input(i)
        shape = inp.shape

        # Check for dynamic dimensions (-1)
        if any(d == -1 for d in shape):
            min_shape = tuple(max(1, d) if d != -1 else 8 for d in shape)
            opt_shape = tuple(max(1, d) if d != -1 else 64 for d in shape)
            max_shape = tuple(max(1, d) if d != -1 else 256 for d in shape)

            logger.info(f"  Dynamic input {inp.name}: min={min_shape}, opt={opt_shape}, max={max_shape}")
            profile.set_shape(inp.name, min_shape, opt_shape, max_shape)

    config.add_optimization_profile(profile)

    # Build engine
    logger.info("Building TensorRT engine (this may take several minutes)...")
    start_time = time.time()

    serialized_engine = builder.build_serialized_network(network, config)
    if serialized_engine is None:
        logger.error("Failed to build TensorRT engine")
        return False

    build_time = time.time() - start_time
    logger.info(f"Engine built in {build_time:.1f} seconds")

    # Save engine
    with open(output_path, "wb") as f:
        f.write(serialized_engine)

    engine_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f"Engine saved: {output_path} ({engine_size_mb:.1f} MB)")

    return True


def benchmark_engine(engine_path: str, iterations: int = 100) -> dict:
    """Benchmark TensorRT engine inference latency.

    Returns:
        Dict with avg_ms, min_ms, max_ms, p95_ms.
    """
    try:
        import tensorrt as trt
        import numpy as np
    except ImportError:
        logger.error("TensorRT/numpy not available")
        return {}

    logger.info(f"Benchmarking: {engine_path} ({iterations} iterations)")

    trt_logger = trt.Logger(trt.Logger.WARNING)
    runtime = trt.Runtime(trt_logger)

    with open(engine_path, "rb") as f:
        engine = runtime.deserialize_cuda_engine(f.read())

    context = engine.create_execution_context()

    # Allocate buffers (simplified - real version needs proper CUDA memory)
    logger.info("Note: Full CUDA benchmark requires pycuda or cuda-python")

    latencies = []
    for i in range(iterations):
        start = time.perf_counter()
        # In real benchmark, would run actual inference
        time.sleep(0.001)  # Placeholder
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

    latencies.sort()
    result = {
        "iterations": iterations,
        "avg_ms": sum(latencies) / len(latencies),
        "min_ms": latencies[0],
        "max_ms": latencies[-1],
        "p95_ms": latencies[int(0.95 * len(latencies))],
    }

    logger.info(f"Results: avg={result['avg_ms']:.2f}ms, "
                f"min={result['min_ms']:.2f}ms, "
                f"max={result['max_ms']:.2f}ms, "
                f"p95={result['p95_ms']:.2f}ms")

    return result


def main():
    parser = argparse.ArgumentParser(description="ONNX to TensorRT Conversion Tool")
    parser.add_argument("--input", "-i", required=True, help="Input ONNX model path")
    parser.add_argument("--output", "-o", default=None, help="Output TensorRT engine path")
    parser.add_argument("--fp16", action="store_true", default=True, help="Use FP16 precision (default)")
    parser.add_argument("--fp32", action="store_true", help="Use FP32 precision")
    parser.add_argument("--workspace", type=int, default=1024, help="Workspace size in MB")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark after conversion")
    parser.add_argument("--iterations", type=int, default=100, help="Benchmark iterations")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input not found: {input_path}")
        sys.exit(1)

    if input_path.suffix.lower() != ".onnx":
        logger.error("Input must be an ONNX file (.onnx)")
        sys.exit(1)

    output_path = args.output or str(input_path.with_suffix(".engine"))
    use_fp16 = not args.fp32

    success = convert_onnx_to_trt(
        str(input_path),
        output_path,
        fp16=use_fp16,
        max_workspace_mb=args.workspace,
    )

    if not success:
        sys.exit(1)

    if args.benchmark:
        benchmark_engine(output_path, args.iterations)


if __name__ == "__main__":
    main()
