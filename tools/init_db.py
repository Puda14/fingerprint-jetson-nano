#!/usr/bin/env python3
"""
Database Initialization Tool.

Creates a fresh database with schema and default configuration.

Usage:
    python tools/init_db.py --device-id JETSON-001
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def init_database(device_id: str, db_path: str = "data/mdgt_edge.db") -> None:
    """Initialize database with schema and default values."""
    from mdgt_edge.database import DatabaseManager, ConfigRepository, DeviceRepository
    from mdgt_edge.database.models import Device

    full_path = PROJECT_ROOT / db_path
    full_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Initializing database at: {full_path}")

    db = DatabaseManager(str(full_path))

    # Set default configuration
    config_repo = ConfigRepository(db)
    defaults = {
        "verify_threshold": "0.55",
        "identify_threshold": "0.50",
        "identify_top_k": "5",
        "min_quality_enroll": "40",
        "min_minutiae_count": "12",
        "max_failed_attempts": "3",
        "cooldown_seconds": "30",
        "knn_k": "16",
        "faiss_nprobe": "8",
        "model_path": "models/mdgtv2_fp16.engine",
    }

    for key, value in defaults.items():
        config_repo.set(key, value)
        print(f"  Config: {key} = {value}")

    # Register device
    device_repo = DeviceRepository(db)
    device_repo.create(Device(
        id=device_id,
        name=f"Jetson Nano ({device_id})",
        location="Default",
    ))
    print(f"  Device registered: {device_id}")

    print(f"\nDatabase initialized successfully!")
    print(f"  Tables created: users, fingerprints, verification_logs, devices, system_config")
    print(f"  Config entries: {len(defaults)}")
    print(f"  Device ID: {device_id}")


def main():
    parser = argparse.ArgumentParser(description="Initialize MDGT Edge Database")
    parser.add_argument("--device-id", default="JETSON-001", help="Device identifier")
    parser.add_argument("--db-path", default="data/mdgt_edge.db", help="Database file path")
    args = parser.parse_args()

    init_database(args.device_id, args.db_path)


if __name__ == "__main__":
    main()
