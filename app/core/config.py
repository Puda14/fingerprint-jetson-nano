"""Centralized configuration for the Jetson worker."""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Configuration for Jetson Nano Worker."""

    api_prefix = "/api/v1"
    host = "0.0.0.0"
    port = 8000
    debug = False

    device_id = "JETSON-001"

    worker_home = Field(
        default_factory=lambda: str(Path.cwd()),
        description="Base directory used to resolve relative worker paths.",
    )
    model_dir = "models"
    data_dir = "data"
    backup_dir = "data/backups"

    backend = Field(
        default="tensorrt",
        description="Inference backend: 'tensorrt' | 'onnx'",
    )
    model_path = Field(
        default="models/mdgtv2_fp16.engine",
        description="Path to model file (.engine or .onnx)",
    )

    image_width = 192
    image_height = 192
    knn_k = 16
    embedding_dim = 256
    extractor = "cn"
    fingernet_model_path = ""
    clahe_clip = 2.5
    clahe_grid = 8

    verify_threshold = Field(
        default=0.55,
        description="Cosine similarity threshold for 1:1 verification",
    )
    verify_margin = Field(
        default=0.02,
        description="Minimum margin between target score and best non-target score",
    )
    identify_threshold = Field(
        default=0.50,
        description="Cosine similarity threshold for 1:N identification",
    )
    identify_top_k = Field(
        default=5,
        description="Max number of results returned in 1:N identification",
    )

    sensor_vid = Field(default=0x0483, description="USB Vendor ID of the sensor")
    sensor_pid = Field(default=0x5720, description="USB Product ID of the sensor")
    sensor_sdk_path = Field(
        default="/home/binhan1/SDK-Fingerprint-sensor",
        description="Path to sensor SDK",
    )
    mock_mode = Field(
        default=False,
        description="Use mock sensor instead of real hardware (loads data/sample/*.tif)",
    )
    sample_dir = Field(
        default="data/sample",
        description="Directory containing sample fingerprint images for mock mode",
    )

    cors_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ]

    database_url = "sqlite+aiosqlite:///data/fingerprint.db"

    mqtt_enabled = Field(default=True, description="Enable MQTT connection to orchestrator")
    mqtt_broker_host = Field(default="localhost", description="MQTT broker hostname/IP")
    mqtt_broker_port = Field(default=1883, description="MQTT broker port")
    mqtt_username = ""
    mqtt_password = ""
    mqtt_client_id = ""
    mqtt_keepalive = 60
    mqtt_reconnect_delay = 5
    heartbeat_interval = Field(default=10, description="Heartbeat interval in seconds")

    encryption_key = Field(
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
