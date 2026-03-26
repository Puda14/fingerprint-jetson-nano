"""
MDGT Edge - Database package.

Exports all public classes for convenient single-line imports::

    from mdgt_edge.database import (
        DatabaseManager,
        CryptoService,
        User, Fingerprint, VerificationLog, Device, SystemConfig, Embedding,
        UserRepository, FingerprintRepository, LogRepository,
        DeviceRepository, ConfigRepository,
    )
"""

from .models import (
    EMBEDDING_DIM,
    Device,
    DeviceStatus,
    Embedding,
    Fingerprint,
    SystemConfig,
    User,
    UserRole,
    VerificationDecision,
    VerificationLog,
    VerificationMode,
)
from .database import DatabaseManager
from .crypto import CryptoService, resolve_encryption_key
from .repository import (
    ConfigRepository,
    DeviceRepository,
    FingerprintRepository,
    LogRepository,
    UserRepository,
)

__all__ = [
    # Models & enums
    "EMBEDDING_DIM",
    "Device",
    "DeviceStatus",
    "Embedding",
    "Fingerprint",
    "SystemConfig",
    "User",
    "UserRole",
    "VerificationDecision",
    "VerificationLog",
    "VerificationMode",
    # Database
    "DatabaseManager",
    # Crypto
    "CryptoService",
    "resolve_encryption_key",
    # Repositories
    "ConfigRepository",
    "DeviceRepository",
    "FingerprintRepository",
    "LogRepository",
    "UserRepository",
]
