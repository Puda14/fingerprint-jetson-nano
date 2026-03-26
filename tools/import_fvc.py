#!/usr/bin/env python3
"""
Import FVC Fingerprint Dataset into MDGT Edge Database.

Supports FVC2000 / FVC2002 / FVC2004 naming convention:
    XXX_Y.{tif,bmp,png}
    XXX = subject ID (1-110), Y = sample number (1-8)

Usage:
    # Preview what will be imported (dry-run)
    python tools/import_fvc.py /path/to/FVC2004/DB1_A --dry-run

    # Import into database
    python tools/import_fvc.py /path/to/FVC2004/DB1_A

    # Import specific sub-database with custom label
    python tools/import_fvc.py /path/to/FVC2002/DB2_A --dataset-name FVC2002-DB2

    # Also save images to data/fvc_images/ for later viewing
    python tools/import_fvc.py /path/to/FVC2004/DB1_A --save-images

    # Resize all images to 192x192 to match sensor resolution
    python tools/import_fvc.py /path/to/FVC2004/DB1_A --resize 192
"""
import argparse
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Image extensions to scan
IMAGE_EXTS = {".tif", ".tiff", ".bmp", ".png", ".jpg", ".jpeg", ".wsq"}

# FVC filename pattern: XXX_Y.ext  (subject_sample)
FVC_PATTERN = re.compile(r"^(\d+)_(\d+)\.\w+$")


def scan_fvc_dir(fvc_dir: Path) -> list[dict]:
    """Scan directory for FVC images. Returns sorted list of records."""
    records = []
    for f in sorted(fvc_dir.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in IMAGE_EXTS:
            continue
        m = FVC_PATTERN.match(f.name)
        if not m:
            print(f"  SKIP (no match): {f.name}")
            continue
        subject_id = int(m.group(1))
        sample_num = int(m.group(2))
        records.append({
            "path": f,
            "subject_id": subject_id,
            "sample_num": sample_num,
            "filename": f.name,
        })
    records.sort(key=lambda r: (r["subject_id"], r["sample_num"]))
    return records


def load_image_bytes(path: Path, target_size: int | None = None) -> tuple[bytes, int, int]:
    """Load image as grayscale bytes. Returns (raw_bytes, width, height)."""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        # Fallback: read raw file bytes (no resize)
        data = path.read_bytes()
        return data, 0, 0

    img = Image.open(path).convert("L")  # grayscale

    if target_size:
        img = img.resize((target_size, target_size), Image.LANCZOS)

    arr = np.array(img, dtype=np.uint8)
    return arr.tobytes(), img.width, img.height


def calculate_quality(image_bytes: bytes) -> float:
    """Quality score = standard deviation of pixel values."""
    if not image_bytes or len(image_bytes) < 100:
        return 0.0
    avg = sum(image_bytes) / len(image_bytes)
    variance = sum((x - avg) ** 2 for x in image_bytes) / len(image_bytes)
    return min(variance ** 0.5, 100.0)


def import_fvc(
    fvc_dir: Path,
    db_path: str = "data/fvc_benchmark.db",
    dataset_name: str = "FVC",
    dry_run: bool = False,
    save_images: bool = False,
    resize: int | None = None,
) -> None:
    """Import FVC dataset into MDGT Edge database."""

    records = scan_fvc_dir(fvc_dir)
    if not records:
        print(f"No FVC images found in {fvc_dir}")
        return

    # Stats
    subjects = sorted(set(r["subject_id"] for r in records))
    samples_per_subject = {}
    for r in records:
        samples_per_subject.setdefault(r["subject_id"], []).append(r["sample_num"])

    print(f"=== FVC Dataset Import ===")
    print(f"Source:     {fvc_dir}")
    print(f"Dataset:    {dataset_name}")
    print(f"Subjects:   {len(subjects)} ({min(subjects)}-{max(subjects)})")
    print(f"Images:     {len(records)}")
    print(f"Samples:    {min(len(v) for v in samples_per_subject.values())}-"
          f"{max(len(v) for v in samples_per_subject.values())} per subject")
    print(f"Resize:     {resize}x{resize}" if resize else f"Resize:     original")
    print(f"DB path:    {PROJECT_ROOT / db_path}")
    print()

    if dry_run:
        print("[DRY RUN] Would import:")
        for sid in subjects[:5]:
            samps = samples_per_subject[sid]
            print(f"  Subject {sid:>3}: {len(samps)} samples ({samps})")
        if len(subjects) > 5:
            print(f"  ... and {len(subjects) - 5} more subjects")
        print(f"\nTotal: {len(subjects)} users, {len(records)} fingerprint records")
        return

    # --- Create database ---
    from mdgt_edge.database import DatabaseManager, UserRepository, FingerprintRepository
    from mdgt_edge.database.models import User, Fingerprint, UserRole

    full_db_path = PROJECT_ROOT / db_path
    full_db_path.parent.mkdir(parents=True, exist_ok=True)

    db = DatabaseManager(str(full_db_path))
    user_repo = UserRepository(db)
    fp_repo = FingerprintRepository(db)

    # Optional: save image copies
    images_dir = None
    if save_images:
        images_dir = PROJECT_ROOT / "data" / "fvc_images" / dataset_name
        images_dir.mkdir(parents=True, exist_ok=True)

    # --- Import ---
    user_count = 0
    fp_count = 0
    subject_to_user_id: dict[int, int] = {}

    for sid in subjects:
        # Create user per subject
        employee_id = f"{dataset_name}-S{sid:03d}"
        existing = user_repo.get_by_employee_id(employee_id)
        if existing:
            subject_to_user_id[sid] = existing.id
            print(f"  Subject {sid:>3}: already exists (user_id={existing.id}), skipping user creation")
        else:
            user = user_repo.create(User(
                employee_id=employee_id,
                full_name=f"FVC Subject {sid}",
                department=dataset_name,
                role=UserRole.USER,
            ))
            subject_to_user_id[sid] = user.id
            user_count += 1

    print(f"Users created: {user_count}")

    for rec in records:
        sid = rec["subject_id"]
        sample = rec["sample_num"]
        user_id = subject_to_user_id[sid]

        # Load image
        image_bytes, w, h = load_image_bytes(rec["path"], target_size=resize)
        quality = calculate_quality(image_bytes)
        img_hash = hashlib.sha256(image_bytes).hexdigest()[:16]

        # finger_index: use sample_num modulo 10 (FVC samples are same finger, different impressions)
        # We use 0 for all since FVC typically captures the same finger
        finger_idx = min(sample - 1, 9)  # sample 1-8 → finger_index 0-7

        fp = fp_repo.create(Fingerprint(
            user_id=user_id,
            finger_index=finger_idx,
            embedding_enc=None,  # will be filled when pipeline extracts embeddings
            minutiae_enc=None,
            quality_score=min(quality, 100.0),
            image_hash=img_hash,
        ))
        fp_count += 1

        # Save image copy
        if images_dir:
            dest = images_dir / f"s{sid:03d}_sample{sample}.png"
            try:
                from PIL import Image
                import numpy as np
                if w > 0 and h > 0:
                    arr = np.frombuffer(image_bytes, dtype=np.uint8).reshape((h, w))
                    Image.fromarray(arr, mode="L").save(str(dest))
                else:
                    shutil.copy2(rec["path"], dest)
            except Exception:
                shutil.copy2(rec["path"], dest)

        if fp_count % 50 == 0:
            print(f"  Imported {fp_count}/{len(records)} ...")

    print(f"\n=== Import Complete ===")
    print(f"Database:     {full_db_path}")
    print(f"Users:        {user_count} created")
    print(f"Fingerprints: {fp_count} imported")
    print(f"Note: embedding_enc is NULL — run pipeline to extract embeddings:")
    print(f"  python tools/extract_embeddings.py --db {db_path}")
    if images_dir:
        print(f"Images saved: {images_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Import FVC fingerprint dataset into MDGT Edge database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/import_fvc.py /data/FVC2004/DB1_A --dry-run
  python tools/import_fvc.py /data/FVC2004/DB1_A --dataset-name FVC2004-DB1
  python tools/import_fvc.py /data/FVC2004/DB1_A --resize 192 --save-images
        """,
    )
    parser.add_argument("fvc_dir", type=str, help="Path to FVC dataset directory")
    parser.add_argument("--db-path", default="data/fvc_benchmark.db",
                        help="Database file path (default: data/fvc_benchmark.db)")
    parser.add_argument("--dataset-name", default=None,
                        help="Dataset label (default: auto-detect from dir name)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview import without writing to database")
    parser.add_argument("--save-images", action="store_true",
                        help="Save grayscale copies to data/fvc_images/")
    parser.add_argument("--resize", type=int, default=None,
                        help="Resize images to NxN (e.g., 192 to match sensor)")
    args = parser.parse_args()

    fvc_dir = Path(args.fvc_dir)
    if not fvc_dir.is_dir():
        print(f"Error: {fvc_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    dataset_name = args.dataset_name or fvc_dir.name
    import_fvc(
        fvc_dir=fvc_dir,
        db_path=args.db_path,
        dataset_name=dataset_name,
        dry_run=args.dry_run,
        save_images=args.save_images,
        resize=args.resize,
    )


if __name__ == "__main__":
    main()
