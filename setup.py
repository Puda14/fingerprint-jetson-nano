"""Setup for the Python 3.6 Jetson worker package."""

from __future__ import absolute_import

from io import open
from os import path

from setuptools import find_packages, setup


ROOT = path.abspath(path.dirname(__file__))

with open(path.join(ROOT, "README.md"), encoding="utf-8") as readme_file:
    README = readme_file.read()


INSTALL_REQUIRES = [
    "fastapi==0.83.0",
    "uvicorn[standard]==0.16.0",
    "aiofiles>=0.8.0,<1.0.0",
    "pydantic<2.0.0",
    "python-dateutil>=2.8.2,<3.0.0",
    "pillow>=8.0.0,<10.0",
    "click>=7.0,<8.1.0",
    "pyyaml>=5.4,<7.0",
    "paho-mqtt>=1.5.0,<2.0",
    "requests>=2.20.0,<2.28.0",
    "websocket-client>=0.59.0,<2.0",
    "websockets>=8.0,<10.0",
    "httpx>=0.18.0,<0.24.0",
    "python-multipart>=0.0.5,<0.0.6",
    "pyusb>=1.0.2,<2.0",
]


setup(
    name="fingerprint-jetson-worker",
    version="2.1.0",
    description="Installable fingerprint worker for Jetson Nano Python 3.6 nodes",
    long_description=README,
    long_description_content_type="text/markdown",
    author="MDGT",
    python_requires=">=3.6,<3.7",
    packages=find_packages(include=["app*", "gui*"]),
    py_modules=["cli"],
    install_requires=INSTALL_REQUIRES,
    extras_require={
        "jetson": [],
        "gui": [],
        "onnx": [
            "onnxruntime>=1.8.0,<2.0",
        ],
        "dev": [
            "pytest>=6.2,<7.0",
            "pytest-asyncio>=0.14,<0.17",
        ],
        "ssh": [
            "asyncssh>=2.5.0,<2.13.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "fingerprint-worker-api=app.main:main",
            "fingerprint-worker-cli=cli:run_cli",
            "fingerprint-worker-gui=gui.__main__:main",
        ],
    },
)
