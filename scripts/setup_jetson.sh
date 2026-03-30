#!/usr/bin/env bash
# ===========================================================================
# Fingerprint Jetson Nano Worker — Quick Setup Script
# ===========================================================================
# Run this script on a fresh Jetson Nano to install all dependencies
# and prepare the environment for running the worker + GUI.
#
# Usage:
#   chmod +x scripts/setup_jetson.sh
#   sudo ./scripts/setup_jetson.sh
# ===========================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "============================================="
echo "  Fingerprint Jetson Nano Worker Setup"
echo "============================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo ""

# ---------------------------------------------------------------------------
# 1. System dependencies
# ---------------------------------------------------------------------------
echo "[1/6] Installing system dependencies..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    python3-pyqt5 \
    python3-numpy \
    libopencv-dev \
    python3-opencv \
    libhdf5-dev \
    libatlas-base-dev \
    libjpeg-dev \
    zlib1g-dev \
    curl

echo "  ✓ System dependencies installed"

# ---------------------------------------------------------------------------
# 2. Python dependencies
# ---------------------------------------------------------------------------
echo ""
echo "[2/6] Installing Python dependencies..."
cd "$PROJECT_ROOT"
pip3 install --upgrade pip setuptools wheel
pip3 install -r requirements.txt

echo "  ✓ Python dependencies installed"

# ---------------------------------------------------------------------------
# 3. Create directories
# ---------------------------------------------------------------------------
echo ""
echo "[3/6] Creating data directories..."
mkdir -p "$PROJECT_ROOT/models"
mkdir -p "$PROJECT_ROOT/data"
mkdir -p "$PROJECT_ROOT/data/backups"
echo "  ✓ Directories created"

# ---------------------------------------------------------------------------
# 4. Environment file
# ---------------------------------------------------------------------------
echo ""
echo "[4/6] Setting up environment file..."
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    echo "  ✓ .env created from .env.example"
    echo "  ⚠ Please edit .env to configure your device settings"
else
    echo "  ✓ .env already exists, skipping"
fi

# ---------------------------------------------------------------------------
# 5. Make scripts executable
# ---------------------------------------------------------------------------
echo ""
echo "[5/6] Setting script permissions..."
chmod +x "$SCRIPT_DIR"/*.sh
echo "  ✓ Scripts are executable"

# ---------------------------------------------------------------------------
# 6. Quick test
# ---------------------------------------------------------------------------
echo ""
echo "[6/6] Running quick import test..."
cd "$PROJECT_ROOT"
python3 -c "
import sys
print('Python:', sys.version)
try:
    from PyQt5 import QtWidgets
    print('  ✓ PyQt5 OK')
except ImportError:
    print('  ✗ PyQt5 not found')
try:
    import numpy
    print('  ✓ NumPy OK')
except ImportError:
    print('  ✗ NumPy not found')
try:
    import requests
    print('  ✓ Requests OK')
except ImportError:
    print('  ✗ Requests not found')
try:
    import fastapi
    print('  ✓ FastAPI OK')
except ImportError:
    print('  ✗ FastAPI not found')
"

echo ""
echo "============================================="
echo "  Setup Complete!"
echo "============================================="
echo ""
echo "Next steps:"
echo "  1. Copy your model files (.onnx or .engine) to: $PROJECT_ROOT/models/"
echo "  2. Edit .env if needed: nano $PROJECT_ROOT/.env"
echo "  3. Start the system:"
echo "     ./scripts/run_gui.sh"
echo ""
echo "  Or manually:"
echo "     # Terminal 1: Start backend"
echo "     cd $PROJECT_ROOT && uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "     # Terminal 2: Start GUI"
echo "     cd $PROJECT_ROOT && python3 -m gui"
echo ""
