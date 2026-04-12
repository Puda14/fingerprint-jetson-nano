#!/usr/bin/env bash
# ============================================================================
# Root wrapper for Jetson setup
# ============================================================================
# Run this script with sudo on a fresh Jetson Nano. It installs system
# dependencies as root, then hands off to setup_jetson_env.sh as the normal
# project user so the venv is created in the right home/workspace.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TARGET_USER="${SUDO_USER:-$USER}"

echo "============================================="
echo "  Fingerprint Jetson Nano Worker Setup"
echo "============================================="
echo "Project root: $PROJECT_ROOT"
echo "Target user : $TARGET_USER"

if [ "$EUID" -ne 0 ]; then
    echo
    echo "Please run this wrapper with sudo:"
    echo "  sudo ./scripts/setup_jetson.sh"
    exit 1
fi

cd "$PROJECT_ROOT"

echo
echo "[root] Installing system packages..."
apt-get update
apt-get install -y \
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

echo
echo "[root] Handing off to user-space environment setup..."
sudo -u "$TARGET_USER" -H bash -lc "cd '$PROJECT_ROOT' && SKIP_APT=1 ./scripts/setup_jetson_env.sh"
