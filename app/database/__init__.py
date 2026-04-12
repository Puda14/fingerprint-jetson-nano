"""Database layer for local fingerprint storage.

Ported from jetson-fingerverify-app/mdgt_edge/database.
Provides SQLite persistence with Fernet-encrypted embeddings.
"""

from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator
from app.database.database import DatabaseManager  # noqa: F401
from app.database.crypto import CryptoService  # noqa: F401

__all__ = ["DatabaseManager", "CryptoService"]
