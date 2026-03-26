"""
Application configuration using Pydantic Settings.
Loads from environment variables with sensible defaults for Jetson Nano deployment.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Central configuration for the MDGT Edge Fingerprint Verification System."""

    # --- API ---
    api_prefix: str = "/api/v1"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Paths ---
    model_dir: str = "models/"
    data_dir: str = "data/"

    # --- Device ---
    device_id: str = "JETSON-001"

    # --- Verification thresholds ---
    verify_threshold: float = 0.55
    identify_threshold: float = 0.50
    identify_top_k: int = 5

    # --- Sensor ---
    sensor_vid: int = Field(default=0x0483, description="Sensor USB Vendor ID")
    sensor_pid: int = Field(default=0x5720, description="Sensor USB Product ID")
    sensor_sdk_path: str = "/home/binhan3/SDK-Fingerprint-sensor"

    # --- CORS ---
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///data/fingerprint.db"
    backup_dir: str = "data/backups/"

    model_config = {
        "env_prefix": "MDGT_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


def get_settings() -> Settings:
    """Return a cached Settings instance (constructed once per process)."""
    return _settings


_settings = Settings()
