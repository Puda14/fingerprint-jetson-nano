"""
Fernet-based encryption for fingerprint embeddings.

Ported from jetson-fingerverify-app/mdgt_edge/database/crypto.py.
Encrypts/decrypts embedding vectors and minutiae data at rest.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from app.database.models import EMBEDDING_DIM

logger = logging.getLogger(__name__)

_KEY_FILE_NAME = ".fingerprint_key"
_PBKDF2_ITERATIONS = 480_000
_PBKDF2_SALT = b"fingerprint-jetson-nano-v1"


def _derive_key_from_string(secret):
    # type: (str) -> bytes
    """Derive a Fernet key from a string using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_PBKDF2_SALT,
        iterations=_PBKDF2_ITERATIONS,
    )
    raw = kdf.derive(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def resolve_encryption_key(key_string="", key_dir=None):
    # type: (str, Optional[str]) -> bytes
    """Resolve the encryption key.

    Priority:
      1. Explicit key_string (from WORKER_ENCRYPTION_KEY env var)
      2. WORKER_DEVICE_ID env var (derive via PBKDF2)
      3. Key file on disk (generated if absent)
    """
    # 1. Explicit key
    if key_string:
        logger.info("Using provided encryption key")
        return key_string.encode("utf-8") if isinstance(key_string, str) else key_string

    # 2. Derive from device ID
    device_id = os.environ.get("WORKER_DEVICE_ID", "")
    if device_id:
        logger.info("Deriving encryption key from WORKER_DEVICE_ID")
        return _derive_key_from_string(device_id)

    # 3. File-based key
    base = Path(key_dir) if key_dir else Path.cwd()
    key_path = base / _KEY_FILE_NAME
    if key_path.is_file():
        key = key_path.read_bytes().strip()
        logger.info("Loaded encryption key from %s", key_path)
        return key

    key = Fernet.generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    logger.warning("Generated NEW encryption key at %s", key_path)
    return key


class CryptoService:
    """Fernet encryption/decryption for fingerprint data.

    Instantiate once and reuse — the Fernet cipher is thread-safe.
    """

    def __init__(self, key=None, key_dir=None):
        # type: (Optional[bytes], Optional[str]) -> None
        if key is None:
            from app.core.config import get_settings
            settings = get_settings()
            key = resolve_encryption_key(
                key_string=settings.encryption_key,
                key_dir=str(Path.cwd() / settings.data_dir),
            )
        self._key = key
        self._fernet = Fernet(self._key)
        logger.info("CryptoService initialised")

    def encrypt_embedding(self, vector):
        # type: (list) -> bytes
        """Encrypt a float32 embedding vector."""
        if len(vector) != EMBEDDING_DIM:
            raise ValueError(
                "Expected {}-dim vector, got {}".format(EMBEDDING_DIM, len(vector))
            )
        raw = struct.pack("<{}f".format(EMBEDDING_DIM), *vector)
        return self._fernet.encrypt(raw)

    def decrypt_embedding(self, data):
        # type: (bytes) -> list
        """Decrypt ciphertext bytes back to a float32 vector."""
        raw = self._fernet.decrypt(data)
        expected_bytes = EMBEDDING_DIM * 4
        if len(raw) == expected_bytes:
            return list(struct.unpack("<{}f".format(EMBEDDING_DIM), raw))

        # Backward compatibility for pre-migration records (256-d vectors).
        if len(raw) == 256 * 4 and EMBEDDING_DIM == 512:
            legacy = list(struct.unpack("<256f", raw))
            return legacy + [0.0] * 256

        raise ValueError(
            "Unexpected embedding bytes: expected {} bytes, got {}".format(
                expected_bytes, len(raw)
            )
        )

    def encrypt_minutiae(self, minutiae):
        # type: (list) -> bytes
        """Encrypt a list of minutiae dicts."""
        payload = json.dumps(minutiae, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return self._fernet.encrypt(payload)

    def decrypt_minutiae(self, data):
        # type: (bytes) -> list
        """Decrypt ciphertext bytes back to minutiae dicts."""
        payload = self._fernet.decrypt(data)
        return json.loads(payload)

    def encrypt_bytes(self, plaintext):
        # type: (bytes) -> bytes
        return self._fernet.encrypt(plaintext)

    def decrypt_bytes(self, ciphertext):
        # type: (bytes) -> bytes
        return self._fernet.decrypt(ciphertext)
