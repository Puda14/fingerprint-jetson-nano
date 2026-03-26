#!/usr/bin/env python3
"""
Extract Embeddings for FVC-imported fingerprints.

Reads fingerprint images from data/fvc_images/, runs them through the
MDGTv2 pipeline (preprocessing → minutiae → graph → inference), and
writes the resulting 256-dim embeddings back into the database.

Usage:
    python tools/extract_embeddings.py
    python tools/extract_embeddings.py --db data/fvc_benchmark.db --model models/mdgtv2.onnx
    python tools/extract_embeddings.py --build-faiss
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def extract(
    db_path: str = "data/fvc_benchmark.db",
    images_dir: str = "data/fvc_images",
    model_path: str | None = None,
    build_faiss: bool = False,
) -> None:
    """Extract embeddings for fingerprints with NULL embedding_enc."""
    from mdgt_edge.database import DatabaseManager, FingerprintRepository

    full_db = PROJECT_ROOT / db_path
    if not full_db.exists():
        print(f"Database not found: {full_db}")
        sys.exit(1)

    db = DatabaseManager(str(full_db))
    fp_repo = FingerprintRepository(db)

    # Find fingerprints missing embeddings
    rows = db.fetch_all(
        "SELECT id, user_id, finger_index, image_hash FROM fingerprints "
        "WHERE embedding_enc IS NULL AND is_active = 1"
    )

    if not rows:
        print("All fingerprints already have embeddings.")
        return

    print(f"Found {len(rows)} fingerprints without embeddings.")

    # Try loading pipeline
    try:
        from mdgt_edge.pipeline import VerificationPipeline
        config = {}
        if model_path:
            config["model"] = {"path": model_path}
        pipeline = VerificationPipeline(config)
        print(f"Pipeline loaded (model: {model_path or 'default'})")
    except ImportError as e:
        print(f"Pipeline not available: {e}")
        print("Run this on the Jetson Nano with all dependencies installed.")
        sys.exit(1)

    # Scan image files
    img_dir = PROJECT_ROOT / images_dir
    image_files = {}
    if img_dir.exists():
        for d in img_dir.iterdir():
            if d.is_dir():
                for f in d.iterdir():
                    image_files[f.stem] = f

    updated = 0
    errors = 0
    for fp_id, user_id, finger_index, image_hash in rows:
        # Find matching image file
        # Try patterns: s{user_id}_sample{finger_index+1}, or by hash
        img_path = None
        for pattern in [
            f"s{user_id:03d}_sample{finger_index + 1}",
        ]:
            if pattern in image_files:
                img_path = image_files[pattern]
                break

        if img_path is None:
            errors += 1
            continue

        try:
            import numpy as np
            from PIL import Image

            img = Image.open(img_path).convert("L")
            img = img.resize((192, 192), Image.LANCZOS)
            image_bytes = np.array(img, dtype=np.uint8).tobytes()

            # Extract embedding via pipeline
            import asyncio
            embedding = asyncio.run(pipeline.extract_embedding(image_bytes))
            if embedding is not None:
                # Store as raw bytes (encryption would be via CryptoService in production)
                import struct
                emb_bytes = struct.pack(f"<{len(embedding)}f", *embedding)
                db.execute(
                    "UPDATE fingerprints SET embedding_enc = ? WHERE id = ?",
                    (emb_bytes, fp_id),
                )
                updated += 1
                if updated % 20 == 0:
                    print(f"  Extracted {updated}/{len(rows)} ...")
            else:
                errors += 1
        except Exception as e:
            print(f"  Error on fp_id={fp_id}: {e}")
            errors += 1

    print(f"\nExtraction complete: {updated} updated, {errors} errors")

    if build_faiss and updated > 0:
        print("Building FAISS index...")
        try:
            from mdgt_edge.pipeline import FAISSIndexManager
            import struct
            import numpy as np

            index_mgr = FAISSIndexManager(dim=256)
            active = fp_repo.get_active_embeddings()
            ids = []
            vectors = []
            for fp_id, user_id, emb_enc in active:
                if emb_enc:
                    n = len(emb_enc) // 4
                    vec = np.array(struct.unpack(f"<{n}f", emb_enc), dtype=np.float32)
                    vectors.append(vec)
                    ids.append(fp_id)

            if vectors:
                matrix = np.stack(vectors)
                index_mgr.build_index(matrix, ids)
                index_path = PROJECT_ROOT / "data" / "fvc_faiss.index"
                index_mgr.save(str(index_path))
                print(f"FAISS index saved: {index_path} ({len(ids)} vectors)")
        except Exception as e:
            print(f"FAISS build error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Extract embeddings for FVC fingerprints")
    parser.add_argument("--db", default="data/fvc_benchmark.db", help="Database path")
    parser.add_argument("--images", default="data/fvc_images", help="Images directory")
    parser.add_argument("--model", default=None, help="Model path (ONNX or TRT)")
    parser.add_argument("--build-faiss", action="store_true", help="Build FAISS index after extraction")
    args = parser.parse_args()

    extract(
        db_path=args.db,
        images_dir=args.images,
        model_path=args.model,
        build_faiss=args.build_faiss,
    )


if __name__ == "__main__":
    main()
