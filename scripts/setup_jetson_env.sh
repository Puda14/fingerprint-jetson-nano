#!/bin/bash
# ============================================================================
# Jetson Nano worker environment setup for Python 3.6 + TensorRT
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/venv"
SKIP_APT="${SKIP_APT:-0}"


log_step() {
    echo
    echo "================================================================="
    echo "$1"
    echo "================================================================="
}


read_backend() {
    local backend="tensorrt"

    if [ -f "$PROJECT_ROOT/.env" ]; then
        local env_value
        env_value="$(grep -E '^WORKER_BACKEND=' "$PROJECT_ROOT/.env" | tail -n 1 | cut -d'=' -f2- || true)"
        env_value="${env_value//\"/}"
        env_value="${env_value// /}"
        if [ -n "$env_value" ]; then
            backend="$env_value"
        fi
    elif [ -f "$PROJECT_ROOT/.env.example" ]; then
        local example_value
        example_value="$(grep -E '^WORKER_BACKEND=' "$PROJECT_ROOT/.env.example" | tail -n 1 | cut -d'=' -f2- || true)"
        example_value="${example_value//\"/}"
        example_value="${example_value// /}"
        if [ -n "$example_value" ]; then
            backend="$example_value"
        fi
    fi

    echo "$backend"
}


detect_cuda_root() {
    local candidate

    for candidate in /usr/local/cuda /usr/local/cuda-10.2 /usr/local/cuda-11.4; do
        if [ -f "$candidate/include/cuda.h" ]; then
            echo "$candidate"
            return 0
        fi
    done

    candidate="$(find /usr -path '*/include/cuda.h' 2>/dev/null | head -n 1 || true)"
    if [ -n "$candidate" ]; then
        dirname "$(dirname "$candidate")"
        return 0
    fi

    return 1
}


install_system_deps() {
    log_step "1. Installing system dependencies"
    sudo apt-get update
    sudo apt-get install -y \
        build-essential \
        cmake \
        curl \
        git \
        libatlas-base-dev \
        libboost-python-dev \
        libboost-thread-dev \
        libhdf5-dev \
        libjpeg-dev \
        libopenblas-dev \
        python3-appdirs \
        python3-cryptography \
        python3-decorator \
        python3-dev \
        python3-mako \
        python3-numpy \
        python3-opencv \
        python3-pip \
        python3-pyqt5 \
        python3-venv \
        swig \
        wget \
        zlib1g-dev
}


create_project_env() {
    log_step "2. Creating project venv with system packages"

    if [ -d "$VENV_DIR" ]; then
        echo "Removing old venv at $VENV_DIR"
        rm -rf "$VENV_DIR"
    fi

    python3 -m venv --system-site-packages "$VENV_DIR"
    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"

    python3 -m pip install --upgrade \
        "pip<22" \
        "setuptools<60" \
        "wheel<0.38"
}


prepare_project_files() {
    log_step "3. Preparing project directories and env file"

    mkdir -p "$PROJECT_ROOT/models"
    mkdir -p "$PROJECT_ROOT/data"
    mkdir -p "$PROJECT_ROOT/data/backups"

    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
        echo "Created .env from .env.example"
    fi
}


install_python_deps() {
    log_step "4. Installing Python dependencies"

    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"
    pip install -r "$PROJECT_ROOT/requirements.txt"

    local backend
    backend="$(read_backend)"
    if [ "$backend" = "onnx" ]; then
        echo "WORKER_BACKEND=onnx detected -> installing optional ONNX deps"
        pip install -r "$PROJECT_ROOT/requirements-onnx.txt"
    else
        echo "WORKER_BACKEND=$backend -> skipping pip onnxruntime in default TensorRT setup"
    fi
}


install_pycuda_for_tensorrt() {
    local backend
    backend="$(read_backend)"
    if [ "$backend" != "tensorrt" ]; then
        echo "WORKER_BACKEND=$backend -> skipping pycuda install"
        return 0
    fi

    log_step "5. Ensuring TensorRT runtime dependencies"

    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"

    if ! python3 -c "import tensorrt as trt; print(trt.__version__)" >/dev/null 2>&1; then
        echo "ERROR: TensorRT Python package is not importable. Install JetPack/TensorRT first."
        return 1
    fi

    if python3 -c "import pycuda.driver as cuda; import pycuda.autoinit" >/dev/null 2>&1; then
        echo "pycuda already available"
        return 0
    fi

    local cuda_root
    cuda_root="$(detect_cuda_root || true)"
    if [ -z "$cuda_root" ]; then
        echo "ERROR: Could not detect CUDA root (cuda.h not found)."
        return 1
    fi

    export CUDA_ROOT="$cuda_root"
    export PATH="$CUDA_ROOT/bin:$PATH"
    export LD_LIBRARY_PATH="$CUDA_ROOT/lib64:${LD_LIBRARY_PATH:-}"

    local build_dir
    build_dir="$(mktemp -d /tmp/pycuda-build.XXXXXX)"
    trap 'rm -rf "$build_dir"' EXIT

    echo "Downloading pycuda source into $build_dir"
    cd "$build_dir"
    curl -L --retry 20 --retry-delay 5 --connect-timeout 30 \
        -o pycuda-2021.1.tar.gz \
        https://files.pythonhosted.org/packages/source/p/pycuda/pycuda-2021.1.tar.gz

    tar -xzf pycuda-2021.1.tar.gz
    cd pycuda-2021.1

    python3 configure.py --cuda-root="$CUDA_ROOT" --no-use-shipped-boost
    python3 setup.py build
    python3 setup.py install

    cd "$PROJECT_ROOT"
    trap - EXIT
    rm -rf "$build_dir"
}


compile_faiss_cpu() {
    log_step "6. Compiling FAISS CPU fallback"

    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"

    local faiss_dir="/tmp/faiss_build"
    if python3 -c "import faiss" >/dev/null 2>&1; then
        echo "FAISS already available, skipping build"
        return 0
    fi

    rm -rf "$faiss_dir"
    git clone --branch v1.7.4 --depth 1 https://github.com/facebookresearch/faiss.git "$faiss_dir"
    cd "$faiss_dir"

    wget -q https://github.com/Kitware/CMake/releases/download/v3.24.3/cmake-3.24.3-linux-aarch64.sh -O /tmp/cmake.sh
    chmod +x /tmp/cmake.sh
    mkdir -p /tmp/cmake_bin
    /tmp/cmake.sh --skip-license --prefix=/tmp/cmake_bin
    export PATH=/tmp/cmake_bin/bin:$PATH

    local py_inc
    local numpy_inc
    py_inc="$(python3 -c "import sysconfig; print(sysconfig.get_path('include'))")"
    numpy_inc="$(python3 -c "import numpy as np; print(np.get_include())")"

    cmake -B build \
        -DFAISS_ENABLE_GPU=OFF \
        -DFAISS_ENABLE_PYTHON=ON \
        -DFAISS_OPT_LEVEL=generic \
        -DPython_EXECUTABLE="$(which python3)" \
        -DPython_INCLUDE_DIR="$py_inc" \
        -DPython_NumPy_INCLUDE_DIRS="$numpy_inc" \
        .

    make -C build -j"$(nproc)" faiss swigfaiss
    cd build/faiss/python
    python3 setup.py install
    cd "$PROJECT_ROOT"
    rm -rf "$faiss_dir"
}


run_sanity_checks() {
    log_step "7. Running runtime sanity checks"

    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"

    python3 - <<'PY'
import importlib
import os
import shutil
import sys

checks = [
    ("PyQt5.QtWidgets", "PyQt5 GUI"),
    ("numpy", "NumPy"),
    ("cv2", "OpenCV"),
    ("cryptography", "cryptography"),
    ("fastapi", "FastAPI"),
    ("requests", "requests"),
    ("tensorrt", "TensorRT"),
    ("pycuda.driver", "PyCUDA"),
]

failed = []
for module_name, label in checks:
    try:
        mod = importlib.import_module(module_name)
        version = getattr(mod, "__version__", "")
        location = getattr(mod, "__file__", "")
        extra = f" version={version}" if version else ""
        print(f"  OK  {label:<14} {module_name}{extra} {location}")
    except Exception as exc:
        failed.append((label, module_name, exc))
        print(f"  FAIL {label:<14} {module_name}: {exc}")

engine_candidates = []
for root, _, files in os.walk("models"):
    for name in files:
        if name.endswith((".engine", ".trt")):
            engine_candidates.append(os.path.join(root, name))

if engine_candidates:
    print("  OK  TensorRT engine files found:")
    for path in sorted(engine_candidates):
        print(f"      - {path}")
else:
    print("  WARN No TensorRT engine found under models/")

trtexec = shutil.which("trtexec") or "/usr/src/tensorrt/bin/trtexec"
print(f"  INFO trtexec path: {trtexec if os.path.exists(trtexec) else 'not found'}")

if failed:
    print("")
    print("Sanity check failed. Fix the missing imports above before running the worker.")
    sys.exit(1)
PY
}


main() {
    cd "$PROJECT_ROOT"

    if [ "$SKIP_APT" != "1" ]; then
        install_system_deps
    else
        log_step "1. Skipping apt dependencies (SKIP_APT=1)"
    fi

    create_project_env
    prepare_project_files
    install_python_deps
    install_pycuda_for_tensorrt
    compile_faiss_cpu
    run_sanity_checks

    echo
    echo "================================================================="
    echo "Setup complete"
    echo "================================================================="
    echo "Activate with: source $VENV_DIR/bin/activate"
    echo "Run backend:   python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    echo "Run GUI:       python3 -m gui"
}


main "$@"
