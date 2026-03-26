"""
MDGT Edge CLI - Command-line interface for fingerprint system management.
"""
import sys
import json
import asyncio
from pathlib import Path
from typing import Optional

try:
    import click
except ImportError:
    print("Error: 'click' package required. Install: pip install click")
    sys.exit(1)


# Resolve project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_async(coro):
    """Run async coroutine from sync click context."""
    return asyncio.get_event_loop().run_until_complete(coro)


def load_config() -> dict:
    """Load configuration from default.yaml."""
    config_path = PROJECT_ROOT / "config" / "default.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            pass
    return {}


@click.group()
@click.version_option(version="1.0.0", prog_name="mdgt-edge")
@click.pass_context
def cli(ctx):
    """MDGT Edge Fingerprint Verification System CLI."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config()


# ==================== User Commands ====================

@cli.group()
def users():
    """User management commands."""
    pass


@users.command("list")
@click.option("--department", "-d", default=None, help="Filter by department")
@click.option("--role", "-r", default=None, help="Filter by role")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
def users_list(department, role, fmt):
    """List all enrolled users."""
    from mdgt_edge.database import DatabaseManager, UserRepository

    db = DatabaseManager()
    repo = UserRepository(db)
    all_users = repo.get_all()

    if department:
        all_users = [u for u in all_users if u.department == department]
    if role:
        all_users = [u for u in all_users if u.role == role]

    if fmt == "json":
        click.echo(json.dumps([u.to_dict() for u in all_users], indent=2, default=str))
        return

    if not all_users:
        click.echo("No users found.")
        return

    # Table format
    header = f"{'ID':>4} {'Employee ID':<15} {'Name':<25} {'Department':<15} {'Role':<12} {'Active':<6}"
    click.echo(header)
    click.echo("-" * len(header))
    for u in all_users:
        active = "Yes" if u.is_active else "No"
        click.echo(
            f"{u.id:>4} {u.employee_id:<15} {u.full_name:<25} "
            f"{(u.department or '-'):<15} {u.role.value:<12} {active:<6}"
        )
    click.echo(f"\nTotal: {len(all_users)} users")


@users.command("add")
@click.option("--employee-id", "-e", required=True, help="Employee ID")
@click.option("--name", "-n", required=True, help="Full name")
@click.option("--department", "-d", default=None, help="Department")
@click.option("--role", "-r", type=click.Choice(["user", "admin", "superadmin"]), default="user")
def users_add(employee_id, name, department, role):
    """Add a new user (without fingerprint enrollment)."""
    from mdgt_edge.database import DatabaseManager, UserRepository
    from mdgt_edge.database.models import User, UserRole

    db = DatabaseManager()
    repo = UserRepository(db)

    existing = repo.get_by_employee_id(employee_id)
    if existing:
        click.echo(f"Error: Employee ID '{employee_id}' already exists.", err=True)
        sys.exit(1)

    user = repo.create(User(
        employee_id=employee_id,
        full_name=name,
        department=department or "",
        role=UserRole(role),
    ))
    click.echo(f"User created: ID={user.id}, Employee={user.employee_id}, Name={user.full_name}")


@users.command("delete")
@click.argument("user_id", type=int)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def users_delete(user_id, force):
    """Delete a user and all associated fingerprints."""
    from mdgt_edge.database import DatabaseManager, UserRepository

    db = DatabaseManager()
    repo = UserRepository(db)
    user = repo.get_by_id(user_id)

    if not user:
        click.echo(f"Error: User ID {user_id} not found.", err=True)
        sys.exit(1)

    if not force:
        click.confirm(
            f"Delete user '{user.full_name}' (ID={user_id})? This will remove all fingerprints.",
            abort=True,
        )

    success = repo.delete(user_id)
    if success:
        click.echo(f"User {user_id} deleted successfully.")
    else:
        click.echo("Error: Failed to delete user.", err=True)
        sys.exit(1)


@users.command("info")
@click.argument("user_id", type=int)
def users_info(user_id):
    """Show detailed user information."""
    from mdgt_edge.database import DatabaseManager, UserRepository, FingerprintRepository

    db = DatabaseManager()
    user_repo = UserRepository(db)
    fp_repo = FingerprintRepository(db)

    user = user_repo.get_by_id(user_id)
    if not user:
        click.echo(f"Error: User ID {user_id} not found.", err=True)
        sys.exit(1)

    fingerprints = fp_repo.get_by_user_id(user_id)

    click.echo(f"User ID:     {user.id}")
    click.echo(f"Employee ID: {user.employee_id}")
    click.echo(f"Full Name:   {user.full_name}")
    click.echo(f"Department:  {user.department or '-'}")
    click.echo(f"Role:        {user.role.value}")
    click.echo(f"Active:      {'Yes' if user.is_active else 'No'}")
    click.echo(f"Created:     {user.created_at}")
    click.echo(f"Updated:     {user.updated_at}")
    click.echo(f"\nEnrolled Fingers: {len(fingerprints)}")

    finger_names = [
        "R-Thumb", "R-Index", "R-Middle", "R-Ring", "R-Pinky",
        "L-Thumb", "L-Index", "L-Middle", "L-Ring", "L-Pinky",
    ]
    for fp in fingerprints:
        fname = finger_names[fp.finger_index] if 0 <= fp.finger_index < 10 else f"Finger-{fp.finger_index}"
        active = "Active" if fp.is_active else "Inactive"
        click.echo(f"  [{fp.finger_index}] {fname}: quality={fp.quality_score:.1f}, {active}")


# ==================== Verification Commands ====================

@cli.command()
@click.option("--user-id", "-u", type=int, required=True, help="User ID for 1:1 verification")
@click.option("--threshold", "-t", type=float, default=None, help="Override verify threshold")
def verify(user_id, threshold):
    """Verify fingerprint against a specific user (1:1)."""
    click.echo(f"Starting 1:1 verification for user {user_id}...")
    click.echo("Place finger on sensor...")

    config = load_config()
    thresh = threshold or config.get("verify_threshold", 0.55)

    try:
        from mdgt_edge.pipeline import VerificationPipeline

        pipeline = VerificationPipeline(config)
        # In real usage, this would capture from sensor
        click.echo(f"Verification threshold: {thresh}")
        click.echo("Note: Sensor capture not available in CLI demo mode.")
        click.echo("Use the web UI or connect a sensor for live verification.")
    except ImportError as e:
        click.echo(f"Pipeline not available: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--top-k", "-k", type=int, default=None, help="Number of candidates")
@click.option("--threshold", "-t", type=float, default=None, help="Override identify threshold")
def identify(top_k, threshold):
    """Identify fingerprint against all enrolled users (1:N)."""
    config = load_config()
    k = top_k or config.get("identify_top_k", 5)
    thresh = threshold or config.get("identify_threshold", 0.50)

    click.echo(f"Starting 1:N identification (top-{k}, threshold={thresh})...")
    click.echo("Place finger on sensor...")
    click.echo("Note: Sensor capture not available in CLI demo mode.")
    click.echo("Use the web UI or connect a sensor for live identification.")


# ==================== Model Commands ====================

@cli.group()
def model():
    """Model management commands."""
    pass


@model.command("list")
def model_list():
    """List available models."""
    models_dir = PROJECT_ROOT / "models"
    if not models_dir.exists():
        click.echo("No models directory found.")
        return

    extensions = {".onnx", ".engine", ".trt", ".pth", ".pt"}
    models = []

    for f in sorted(models_dir.iterdir()):
        if f.suffix.lower() in extensions:
            size_mb = f.stat().st_size / (1024 * 1024)
            models.append((f.name, f.suffix.upper()[1:], size_mb))

    if not models:
        click.echo("No models found in models/ directory.")
        return

    click.echo(f"{'Name':<35} {'Format':<10} {'Size (MB)':>10}")
    click.echo("-" * 57)
    for name, fmt, size in models:
        click.echo(f"{name:<35} {fmt:<10} {size:>10.1f}")


@model.command("activate")
@click.argument("model_path", type=click.Path(exists=True))
def model_activate(model_path):
    """Set a model as the active inference model."""
    path = Path(model_path)
    click.echo(f"Activating model: {path.name}")

    from mdgt_edge.database import DatabaseManager, ConfigRepository

    db = DatabaseManager()
    config_repo = ConfigRepository(db)
    config_repo.set("model_path", str(path))
    click.echo(f"Active model set to: {path}")


@model.command("convert")
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output path for TensorRT engine")
@click.option("--fp16", is_flag=True, default=True, help="Use FP16 precision (default)")
def model_convert(input_path, output, fp16):
    """Convert ONNX model to TensorRT engine."""
    input_file = Path(input_path)
    if input_file.suffix.lower() != ".onnx":
        click.echo("Error: Input must be an ONNX file.", err=True)
        sys.exit(1)

    output_path = output or str(input_file.with_suffix(".engine"))
    precision = "FP16" if fp16 else "FP32"

    click.echo(f"Converting: {input_file.name}")
    click.echo(f"Output:     {output_path}")
    click.echo(f"Precision:  {precision}")

    try:
        from mdgt_edge.pipeline.inference_engine import TensorRTBackend

        backend = TensorRTBackend()
        click.echo("Starting conversion... (this may take several minutes)")
        # Conversion would happen here
        click.echo("Note: TensorRT conversion requires running on Jetson Nano.")
    except ImportError:
        click.echo("Error: TensorRT not available on this platform.", err=True)
        click.echo("Run this command on the Jetson Nano device.")
        sys.exit(1)


@model.command("profile")
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--iterations", "-n", type=int, default=100, help="Number of iterations")
def model_profile(model_path, iterations):
    """Benchmark model inference latency."""
    path = Path(model_path)
    click.echo(f"Profiling: {path.name} ({iterations} iterations)")

    try:
        import numpy as np
        from mdgt_edge.pipeline.inference_engine import ONNXBackend, TensorRTBackend
        import time

        if path.suffix.lower() == ".onnx":
            backend = ONNXBackend()
        elif path.suffix.lower() in (".engine", ".trt"):
            backend = TensorRTBackend()
        else:
            click.echo(f"Error: Unsupported format: {path.suffix}", err=True)
            sys.exit(1)

        if not backend.load(str(path)):
            click.echo("Error: Failed to load model.", err=True)
            sys.exit(1)

        click.echo("Model loaded. Running warmup...")
        click.echo(f"Running {iterations} iterations...")
        click.echo("Note: Full profiling requires sensor input or test data.")

    except ImportError as e:
        click.echo(f"Error: Missing dependency: {e}", err=True)
        sys.exit(1)


# ==================== System Commands ====================

@cli.command()
def status():
    """Show system health status."""
    click.echo("=== MDGT Edge System Status ===\n")

    # Database stats
    try:
        from mdgt_edge.database import DatabaseManager, UserRepository, FingerprintRepository

        db = DatabaseManager()
        user_repo = UserRepository(db)
        fp_repo = FingerprintRepository(db)

        user_count = user_repo.count()
        fp_count = fp_repo.count()

        click.echo(f"Database:")
        click.echo(f"  Users:        {user_count}")
        click.echo(f"  Fingerprints: {fp_count}")
    except Exception as e:
        click.echo(f"Database: Error - {e}")

    # Models
    models_dir = PROJECT_ROOT / "models"
    if models_dir.exists():
        model_files = [f for f in models_dir.iterdir() if f.suffix in {".onnx", ".engine", ".trt", ".pth"}]
        click.echo(f"\nModels: {len(model_files)} available")
        for m in model_files:
            click.echo(f"  {m.name} ({m.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        click.echo("\nModels: Directory not found")

    # System info
    try:
        import platform

        click.echo(f"\nSystem:")
        click.echo(f"  Platform: {platform.machine()}")
        click.echo(f"  Python:   {platform.python_version()}")

        try:
            import psutil

            mem = psutil.virtual_memory()
            click.echo(f"  Memory:   {mem.used / 1024 / 1024:.0f} MB / {mem.total / 1024 / 1024:.0f} MB ({mem.percent}%)")
            click.echo(f"  CPU:      {psutil.cpu_percent()}%")
        except ImportError:
            pass

    except Exception as e:
        click.echo(f"System: Error - {e}")


@cli.group()
def db():
    """Database management commands."""
    pass


@db.command("backup")
@click.option("--output", "-o", default=None, help="Output path for backup")
def db_backup(output):
    """Create database backup."""
    import shutil
    from datetime import datetime

    data_dir = PROJECT_ROOT / "data"
    db_path = data_dir / "mdgt_edge.db"

    if not db_path.exists():
        click.echo("Error: Database not found.", err=True)
        sys.exit(1)

    backup_dir = PROJECT_ROOT / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(output) if output else backup_dir / f"mdgt_edge_{timestamp}.db"

    shutil.copy2(db_path, backup_path)
    click.echo(f"Backup created: {backup_path}")


@db.command("restore")
@click.argument("backup_path", type=click.Path(exists=True))
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def db_restore(backup_path, force):
    """Restore database from backup."""
    import shutil

    data_dir = PROJECT_ROOT / "data"
    db_path = data_dir / "mdgt_edge.db"

    if not force:
        click.confirm(
            "This will overwrite the current database. Continue?",
            abort=True,
        )

    shutil.copy2(backup_path, db_path)
    click.echo(f"Database restored from: {backup_path}")


@db.command("init")
@click.option("--device-id", default="JETSON-001", help="Device identifier")
def db_init(device_id):
    """Initialize a fresh database."""
    from mdgt_edge.database import DatabaseManager, ConfigRepository, DeviceRepository
    from mdgt_edge.database.models import Device

    db = DatabaseManager()
    config_repo = ConfigRepository(db)
    device_repo = DeviceRepository(db)

    # Set default config values
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

    # Register this device
    device_repo.create(Device(
        id=device_id,
        name=f"Jetson Nano ({device_id})",
        location="Default",
    ))

    click.echo(f"Database initialized with device ID: {device_id}")
    click.echo(f"Default configuration values set: {len(defaults)} entries")


# ==================== Server Command ====================

@cli.command()
@click.option("--host", "-h", default="0.0.0.0", help="Bind host")
@click.option("--port", "-p", type=int, default=8000, help="Bind port")
@click.option("--reload", is_flag=True, help="Auto-reload on code changes")
def serve(host, port, reload):
    """Start the web server."""
    click.echo(f"Starting MDGT Edge server on {host}:{port}...")

    try:
        import uvicorn

        uvicorn.run(
            "web.backend.main:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info",
        )
    except ImportError:
        click.echo("Error: uvicorn not installed. Install: pip install uvicorn[standard]", err=True)
        sys.exit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
