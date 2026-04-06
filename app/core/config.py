"""
Centralized configuration for Fingerprint Jetson Nano Worker.

All configurations are loaded from:
  1. .env file (highest priority)
  2. Environment variables (overrides .env)
  3. Default values defined in this class

See .env.example for all configurable variables.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Configuration for Jetson Nano Worker.

    Environment prefix: WORKER_
    Example: WORKER_DEBUG=true, WORKER_PORT=8000
    """

    # -------------------------------------------------------------------------
    # API Server
    # -------------------------------------------------------------------------
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # -------------------------------------------------------------------------
    # Device Identification
    # -------------------------------------------------------------------------
    device_id: str = "JETSON-001"

    # -------------------------------------------------------------------------
    # Directory Paths (relative to runtime dir)
    # -------------------------------------------------------------------------
    model_dir: str = "models/"
    data_dir: str = "data/"
    backup_dir: str = "data/backups/"

    # -------------------------------------------------------------------------
    # Inference Backend
    # Choose "tensorrt" for optimized speed on Jetson Nano (FP16).
    # Choose "onnx" to fallback if TensorRT is unavailable.
    # -------------------------------------------------------------------------
    backend: str = Field(
        default="tensorrt",
        description="Inference backend: 'tensorrt' | 'onnx'",
    )
    model_path: str = Field(
        default="models/mdgtv2_fp16.engine",
        description="Path to model file (.engine or .onnx)",
    )

    # -------------------------------------------------------------------------
    # Pipeline — Feature extraction parameters
    # -------------------------------------------------------------------------
    image_width: int = 192
    image_height: int = 192
    knn_k: int = 16                # number of neighbors in graph builder
    embedding_dim: int = 512       # embedding vector dimension
    extractor: str = "cn"          # minutiae extraction method: "cn" | "fingernet"
    fingernet_model_path: str = "" # ONNX path if using FingerNet
    clahe_clip: float = 2.5        # CLAHE clip level for preprocessing (0–8)
    clahe_grid: int = 8            # CLAHE grid size

    # -------------------------------------------------------------------------
    # Matching Thresholds
    # -------------------------------------------------------------------------
    verify_threshold: float = Field(
        default=0.55,
        description="Cosine similarity threshold for 1:1 verification",
    )
    verify_margin: float = Field(
        default=0.02,
        description="Minimum margin between target score and best non-target score",
    )
    identify_threshold: float = Field(
        default=0.50,
        description="Cosine similarity threshold for 1:N identification",
    )
    identify_top_k: int = Field(
        default=5,
        description="Max number of results returned in 1:N identification",
    )

    # -------------------------------------------------------------------------
    # Fingerprint Sensor (USB)
    # -------------------------------------------------------------------------
    sensor_vid: int = Field(default=0x0483, description="USB Vendor ID of the sensor")
    sensor_pid: int = Field(default=0x5720, description="USB Product ID of the sensor")

    @field_validator("sensor_vid", "sensor_pid", mode="before")
    @classmethod
    def _parse_hex_int(cls, v):
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v.startswith(("0x", "0X")):
                return int(v, 16)
            return int(v)
        return v

    sensor_sdk_path: str = Field(
        default="/home/yen/SDK-Fingerprint-sensor",
        description="Path to sensor SDK",
    )
    mock_mode: bool = Field(
        default=False,
        description="Use mock sensor instead of real hardware (loads data/sample/*.tif)",
    )
    sample_dir: str = Field(
        default="data/sample",
        description="Directory containing sample fingerprint images for mock mode",
    )

    # -------------------------------------------------------------------------
    # CORS — allowed origins to access API
    # -------------------------------------------------------------------------
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ]

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///data/fingerprint.db"

    # -------------------------------------------------------------------------
    # MQTT — Connection to Orchestrator
    # -------------------------------------------------------------------------
    mqtt_enabled: bool = Field(default=True, description="Enable MQTT connection to orchestrator")
    mqtt_broker_host: str = Field(default="localhost", description="MQTT broker hostname/IP")
    mqtt_broker_port: int = Field(default=1883, description="MQTT broker port")
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_client_id: str = ""
    mqtt_keepalive: int = 60
    mqtt_reconnect_delay: int = 5
    heartbeat_interval: int = Field(default=10, description="Heartbeat interval in seconds")

    # -------------------------------------------------------------------------
    # Encryption — for fingerprint embedding storage
    # -------------------------------------------------------------------------
    encryption_key: str = Field(
        default="",
        description="Fernet key for encrypting embeddings. Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'",
    )

    model_config = {
        "env_prefix": "WORKER_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def as_pipeline_config(self) -> dict:
        """
        Returns config dict to initialize VerificationPipeline.
        Separated so pipeline does not depend directly on Settings.
        """
        return {
            "backend": self.backend,
            "model_path": self.model_path,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "image_size": max(self.image_width, self.image_height),
            "knn_k": self.knn_k,
            "embedding_dim": self.embedding_dim,
            "extractor": self.extractor,
            "fingernet_model_path": self.fingernet_model_path,
            "clahe_clip": self.clahe_clip,
            "clahe_grid": self.clahe_grid,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns Settings instance (singleton - created only once).
    Uses lru_cache to ensure the same object is reused throughout the app.
    """
    return Settings()
