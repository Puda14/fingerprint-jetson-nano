"""
MDGT Edge Application Entry Point.

Initializes all services and runs the system.
"""
import sys
import logging
from pathlib import Path
from typing import Optional

import yaml


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent


def load_config(config_path: Optional[str] = None) -> dict:
    """Load configuration from YAML file."""
    path = Path(config_path) if config_path else PROJECT_ROOT / "config" / "default.yaml"

    # Override with device-specific config if exists
    device_config_path = PROJECT_ROOT / "config" / "device.yaml"

    config = {}

    if path.exists():
        with open(path) as f:
            config = yaml.safe_load(f) or {}

    if device_config_path.exists():
        with open(device_config_path) as f:
            device_config = yaml.safe_load(f) or {}
            _deep_merge(config, device_config)

    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base dict (modifies base in place)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def setup_logging(config: dict) -> None:
    """Configure logging from config."""
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
    fmt = log_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    logging.basicConfig(level=level, format=fmt)

    # Create log directory if specified
    log_dir = log_config.get("log_dir")
    if log_dir:
        Path(PROJECT_ROOT / log_dir).mkdir(parents=True, exist_ok=True)


def init_database(config: dict) -> None:
    """Initialize database with schema and default config."""
    from mdgt_edge.database import DatabaseManager

    db_path = config.get("database", {}).get("path", "data/mdgt_edge.db")
    full_path = PROJECT_ROOT / db_path

    # Ensure data directory exists
    full_path.parent.mkdir(parents=True, exist_ok=True)

    db = DatabaseManager(str(full_path))
    logger.info(f"Database initialized at {full_path}")
    return db


def init_pipeline(config: dict):
    """Initialize the verification pipeline."""
    try:
        from mdgt_edge.pipeline import VerificationPipeline

        pipeline = VerificationPipeline(config)
        logger.info("Verification pipeline initialized")
        return pipeline
    except Exception as e:
        logger.warning(f"Pipeline initialization failed: {e}. Running in limited mode.")
        return None


def run_server(config: dict) -> None:
    """Run the FastAPI web server."""
    import uvicorn

    server_config = config.get("server", {})
    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 8000)
    debug = server_config.get("debug", False)

    logger.info(f"Starting MDGT Edge server on {host}:{port}")

    uvicorn.run(
        "web.backend.main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="debug" if debug else "info",
    )


def main(config_path: Optional[str] = None, mode: str = "server") -> None:
    """Main application entry point.

    Args:
        config_path: Path to config file (default: config/default.yaml)
        mode: Run mode - 'server' (web), 'gui' (PyQt6), or 'cli'
    """
    config = load_config(config_path)
    setup_logging(config)

    logger.info("MDGT Edge Verification System starting...")
    logger.info(f"Mode: {mode}")

    # Initialize database
    init_database(config)

    if mode == "server":
        run_server(config)
    elif mode == "gui":
        logger.info("GUI mode not yet implemented in new architecture")
        logger.info("Use: python -m cli.main serve")
    elif mode == "cli":
        from cli.main import main as cli_main
        cli_main()
    else:
        logger.error(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
