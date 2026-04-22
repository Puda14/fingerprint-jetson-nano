"""Centralized configuration for the Jetson worker."""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Configuration for Jetson Nano Worker."""

    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    device_id: str = "JETSON-001"

    worker_home: str = Field(
        default_factory=lambda: str(Path.cwd()),
        description="Base directory used to resolve relative worker paths.",
    )
    model_dir: str = "models"
    data_dir: str = "data"
    backup_dir: str = "data/backups"

    backend: str = Field(
        default="tensorrt",
        description="Inference backend: 'tensorrt' | 'onnx'",
    )
    model_path: str = Field(
        default="models/embedding",
        description=(
            "Optional path to a model file or a directory containing embedding "
            "models (.engine, .trt, .onnx)"
        ),
    )

    image_width: int = 192
    image_height: int = 192
    knn_k: int = 16
    embedding_dim: int = 256
    extractor: str = "cn"
    fingernet_model_path: str = ""
    clahe_clip: float = 2.5
    clahe_grid: int = 8

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
    sensor_min_quality: float = Field(
        default=20.0,
        description="Minimum capture quality required for enroll/verify/identify",
    )
    sensor_settle_ms: int = Field(
        default=250,
        description="Wait time after finger detection before final capture",
    )
    sensor_capture_timeout_sec: float = Field(
        default=5.0,
        description="Max time to wait for a stable finger capture",
    )
    duplicate_identify_threshold: float = Field(
        default=0.72,
        description="Stricter threshold used to reject duplicate enrollment",
    )

    sensor_vid: int = Field(default=0x0483, description="USB Vendor ID of the sensor")
    sensor_pid: int = Field(default=0x5720, description="USB Product ID of the sensor")
    sensor_sdk_path: str = Field(
        default="/home/binhan1/SDK-Fingerprint-sensor",
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

    cors_origins: list = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ]

    database_url: str = "sqlite+aiosqlite:///data/fingerprint.db"

    mqtt_enabled: bool = Field(default=True, description="Enable MQTT connection to orchestrator")
    mqtt_broker_host: str = Field(default="localhost", description="MQTT broker hostname/IP")
    mqtt_broker_port: int = Field(default=1883, description="MQTT broker port")
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_client_id: str = ""
    mqtt_keepalive: int = 60
    mqtt_reconnect_delay: int = 5
    heartbeat_interval: int = Field(default=10, description="Heartbeat interval in seconds")

    encryption_key: str = Field(
        default="",
        description=(
            "Fernet key for encrypting embeddings. Generate with: "
            "python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'"
        ),
    )

    class Config:
        env_prefix = "WORKER_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @validator("worker_home", pre=True, always=True)
    def _normalize_worker_home(cls, value):
        if value in (None, ""):
            return str(Path.cwd())
        return str(Path(value).expanduser().resolve())

    @validator("sensor_vid", "sensor_pid", pre=True)
    def _parse_hex_int(cls, value):
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            value = value.strip()
            if value.startswith(("0x", "0X")):
                return int(value, 16)
            return int(value)
        return value

    @validator("model_dir", "data_dir", "backup_dir", "sample_dir", pre=True, always=True)
    def _resolve_directory(cls, value, values):
        return cls._resolve_path_value(value, values)

    @validator("model_path", "fingernet_model_path", pre=True, always=True)
    def _resolve_file_path(cls, value, values):
        return cls._resolve_path_value(value, values)

    @staticmethod
    def _resolve_path_value(value, values):
        if value in (None, ""):
            return ""

        raw_path = Path(str(value)).expanduser()
        if raw_path.is_absolute():
            return str(raw_path)

        base_dir = Path(values.get("worker_home", Path.cwd()))
        return str((base_dir / raw_path).resolve())

    def as_pipeline_config(self):
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
def get_settings():
    """Return the cached settings instance."""
    return Settings()
