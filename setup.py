"""MDGT Edge Verification System - Setup."""
from setuptools import setup, find_packages

setup(
    name="mdgt-edge",
    version="1.0.0",
    description="MDGT Edge Fingerprint Verification System for Jetson Nano",
    author="Binh An",
    python_requires=">=3.8",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "cryptography>=41.0.0",
        "numpy>=1.24.0",
        "pillow>=10.0.0",
        "pyyaml>=6.0",
        "click>=8.1.0",
        "aiofiles>=23.0.0",
    ],
    extras_require={
        "ai": [
            "onnxruntime>=1.16.0",
            "faiss-cpu>=1.7.4",
            "opencv-python>=4.8.0",
        ],
        "jetson": [
            "onnxruntime>=1.16.0",
            "faiss-cpu>=1.7.4",
            "opencv-python>=4.8.0",
            # tensorrt installed via JetPack
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "httpx>=0.25.0",
            "psutil>=5.9.0",
        ],
        "ssh": [
            "asyncssh>=2.14.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "mdgt=cli.main:main",
        ],
    },
)
