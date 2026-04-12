#!/bin/bash
# =========================================================================================
# Tự động hóa cài đặt môi trường Python 3.6 cho Jetson Nano (TensorRT + PyQt5 + FAISS)
# =========================================================================================

set -e

echo "================================================================="
echo "1. Cài đặt các thư viện lõi của hệ thống (C++ & GUI)..."
echo "================================================================="
sudo apt-get update
sudo apt-get install -y \
    cmake swig libopenblas-dev \
    python3-venv python3-dev \
    python3-pyqt5 python3-opencv python3-cryptography \
    build-essential

echo "================================================================="
echo "2. Khởi tạo môi trường ảo Python 3.6 (--system-site-packages)..."
echo "================================================================="
if [ -d "venv" ]; then
    echo "Xóa venv cũ..."
    rm -rf venv
fi

python3 -m venv --system-site-packages venv
source venv/bin/activate

# Cập nhật pip
python3 -m pip install --upgrade pip

echo "================================================================="
echo "3. Cài đặt các thư viện Python chuẩn từ requirements.txt..."
echo "================================================================="
pip install -r requirements.txt

echo "================================================================="
echo "4. Biên dịch FAISS-CPU từ mã nguồn C++ (Mất khoảng 10-15 phút)..."
echo "================================================================="
FAISS_DIR="/tmp/faiss_build"

if python3 -c "import faiss" &> /dev/null; then
    echo "FAISS đã được cài đặt! Bỏ qua bước compile."
else
    echo "Bắt đầu tải và biên dịch FAISS..."
    rm -rf $FAISS_DIR
    git clone https://github.com/facebookresearch/faiss.git $FAISS_DIR
    cd $FAISS_DIR

    # Chỉ định CMake dùng Python3 của VENV
    cmake -B build \
          -DFAISS_ENABLE_GPU=OFF \
          -DFAISS_ENABLE_PYTHON=ON \
          -DPython_EXECUTABLE=$(which python3) .

    make -C build -j$(nproc) faiss swigfaiss
    cd build/faiss/python
    python3 setup.py install

    # Quay lại thư mục gốc dự án
    cd - > /dev/null
    rm -rf $FAISS_DIR
fi

echo "================================================================="
echo "✅ HOÀN TẤT! Môi trường đã sẵn sàng."
echo "Bạn có thể chạy lệnh: source venv/bin/activate && ./scripts/run_gui.sh"
echo "================================================================="
