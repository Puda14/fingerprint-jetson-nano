"""
MDGT Edge Fingerprint Verification System - Encryption Service.

Provides Fernet-based symmetric encryption for fingerprint embeddings
and minutiae data at rest.  The encryption key is derived from:
  1. The MDGT_ENCRYPTION_KEY environment variable (base64-encoded 32 bytes), or
  2. A device serial number (stretched with PBKDF2), or
  3. A freshly generated key (development / first-run only).

All public functions are stateless and operate on immutable data.
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

from .models import EMBEDDING_DIM

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KEY_ENV_VAR = "MDGT_ENCRYPTION_KEY"
_SERIAL_ENV_VAR = "MDGT_DEVICE_SERIAL"
_KEY_FILE_NAME = ".mdgt_key"
_PBKDF2_ITERATIONS = 480_000
_PBKDF2_SALT = b"mdgt-edge-fingerprint-v1"  # fixed salt (device-specific serial provides entropy)


# ---------------------------------------------------------------------------
# Key management (pure functions + thin IO layer)
# ---------------------------------------------------------------------------

def _derive_key_from_serial(serial: str) -> bytes:
    """Derive a Fernet-compatible key from a device serial string using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_PBKDF2_SALT,
        iterations=_PBKDF2_ITERATIONS,
    )
    raw = kdf.derive(serial.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def _generate_key() -> bytes:
    """Generate a fresh Fernet key."""
    return Fernet.generate_key()


def _load_or_create_key_file(path: Path) -> bytes:
    """Load key from *path*; create the file if it does not exist."""
    if path.is_file():
        key = path.read_bytes().strip()
        logger.info("Loaded encryption key from %s", path)
        return key
    key = _generate_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    path.chmod(0o600)
    logger.warning("Generated NEW encryption key and saved to %s", path)
    return key


def resolve_encryption_key(key_dir: Optional[str] = None) -> bytes:
    """Resolve the encryption key using the priority chain.

    Priority:
      1. ``MDGT_ENCRYPTION_KEY`` env var (raw base64 key)
      2. ``MDGT_DEVICE_SERIAL`` env var  (derive via PBKDF2)
      3. Key file on disk (``<key_dir>/.mdgt_key``); generated if absent.
    """
    # 1. Explicit key
    env_key = os.environ.get(_KEY_ENV_VAR)
    if env_key:
        logger.info("Using encryption key from %s env var", _KEY_ENV_VAR)
        return env_key.encode("utf-8") if isinstance(env_key, str) else env_key

    # 2. Derive from device serial
    serial = os.environ.get(_SERIAL_ENV_VAR)
    if serial:
        logger.info("Deriving encryption key from device serial")
        return _derive_key_from_serial(serial)

    # 3. File-based key
    base = Path(key_dir) if key_dir else Path.cwd()
    return _load_or_create_key_file(base / _KEY_FILE_NAME)


# ---------------------------------------------------------------------------
# Encryption service
# ---------------------------------------------------------------------------

class CryptoService:
    """Fernet encryption/decryption for fingerprint data.

    Instantiate once and reuse -- the Fernet cipher is thread-safe.
    """

    def __init__(self, key: Optional[bytes] = None, key_dir: Optional[str] = None) -> None:
        self._key = key if key is not None else resolve_encryption_key(key_dir)
        self._fernet = Fernet(self._key)
        logger.info("CryptoService initialised")

    # -- Embedding -----------------------------------------------------------

    def encrypt_embedding(self, vector: list[float]) -> bytes:
        """Encrypt a float32 embedding vector and return ciphertext bytes.

        Args:
            vector: List of floats with exactly ``EMBEDDING_DIM`` elements.

        Returns:
            Fernet-encrypted bytes of the packed float32 buffer.

        Raises:
            ValueError: If the vector length does not match ``EMBEDDING_DIM``.
        """
        if len(vector) != EMBEDDING_DIM:
            raise ValueError(
                f"Expected {EMBEDDING_DIM}-dim vector, got {len(vector)}"
            )
        raw = struct.pack(f"<{EMBEDDING_DIM}f", *vector)
        return self._fernet.encrypt(raw)

    def decrypt_embedding(self, data: bytes) -> list[float]:
        """Decrypt ciphertext bytes back to a float32 vector.

        Args:
            data: Fernet-encrypted bytes produced by ``encrypt_embedding``.

        Returns:
            A list of ``EMBEDDING_DIM`` floats.
        """
        raw = self._fernet.decrypt(data)
        return list(struct.unpack(f"<{EMBEDDING_DIM}f", raw))

    # -- Minutiae ------------------------------------------------------------

    def encrypt_minutiae(self, minutiae: list[dict]) -> bytes:
        """Encrypt a list of minutiae dicts (JSON-serialised, then Fernet-encrypted).

        Args:
            minutiae: List of dicts, each typically containing keys like
                      ``x``, ``y``, ``angle``, ``type``, ``quality``.

        Returns:
            Fernet-encrypted bytes.
        """
        payload = json.dumps(minutiae, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return self._fernet.encrypt(payload)

    def decrypt_minutiae(self, data: bytes) -> list[dict]:
        """Decrypt ciphertext bytes back to a list of minutiae dicts.

        Args:
            data: Fernet-encrypted bytes produced by ``encrypt_minutiae``.

        Returns:
            The original list of minutiae dicts.
        """
        payload = self._fernet.decrypt(data)
        result = json.loads(payload)
        if not isinstance(result, list):
            raise ValueError("Decrypted minutiae payload is not a list")
        return result

    # -- Utility -------------------------------------------------------------

    def encrypt_bytes(self, plaintext: bytes) -> bytes:
        """Generic Fernet encrypt."""
        return self._fernet.encrypt(plaintext)

    def decrypt_bytes(self, ciphertext: bytes) -> bytes:
        """Generic Fernet decrypt."""
        return self._fernet.decrypt(ciphertext)

    @property
    def key(self) -> bytes:
        """Return a copy of the raw key (handle with care)."""
        return self._key
