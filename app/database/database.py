"""
Thread-safe SQLite database manager.

Ported from jetson-fingerverify-app/mdgt_edge/database/database.py.
Provides DDL, thread-local connections, transaction management.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL statements
# ---------------------------------------------------------------------------

_DDL_STATEMENTS = (
    # -- users ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id TEXT    NOT NULL UNIQUE,
        full_name   TEXT    NOT NULL,
        department  TEXT    NOT NULL DEFAULT '',
        role        TEXT    NOT NULL DEFAULT 'user'
                        CHECK (role IN ('user', 'admin', 'superadmin')),
        is_active   INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )
    """,
    # -- fingerprints --------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS fingerprints (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        finger_index   INTEGER NOT NULL CHECK (finger_index BETWEEN 0 AND 9),
        embedding_enc  BLOB,
        minutiae_enc   BLOB,
        quality_score  REAL    NOT NULL DEFAULT 0 CHECK (quality_score BETWEEN 0 AND 100),
        image_hash     TEXT    NOT NULL DEFAULT '',
        enrolled_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        is_active      INTEGER NOT NULL DEFAULT 1
    )
    """,
    # -- verification_logs ---------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS verification_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        matched_user_id INTEGER REFERENCES users(id),
        matched_fp_id   INTEGER REFERENCES fingerprints(id),
        mode            TEXT    NOT NULL DEFAULT 'verify'
                            CHECK (mode IN ('verify', 'identify')),
        score           REAL    NOT NULL DEFAULT 0,
        decision        TEXT    NOT NULL DEFAULT 'REJECT'
                            CHECK (decision IN ('ACCEPT', 'REJECT', 'UNCERTAIN')),
        latency_ms      REAL    NOT NULL DEFAULT 0,
        device_id       TEXT    NOT NULL DEFAULT '',
        timestamp       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        probe_quality   REAL    NOT NULL DEFAULT 0
    )
    """,
    # -- system_config -------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS system_config (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_users_employee_id   ON users(employee_id)",
    "CREATE INDEX IF NOT EXISTS idx_users_is_active      ON users(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_fp_user_id           ON fingerprints(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_fp_user_finger       ON fingerprints(user_id, finger_index)",
    "CREATE INDEX IF NOT EXISTS idx_fp_is_active         ON fingerprints(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_logs_timestamp       ON verification_logs(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_logs_matched_user    ON verification_logs(matched_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_logs_decision        ON verification_logs(decision)",
)


# ---------------------------------------------------------------------------
# Database manager (singleton, thread-safe)
# ---------------------------------------------------------------------------


class DatabaseManager:
    """Thread-safe SQLite database manager (singleton per db path)."""

    _instances = {}   # type: dict[str, DatabaseManager]
    _instance_lock = threading.Lock()

    def __new__(cls, db_path="data/fingerprint.db"):
        # type: (str) -> DatabaseManager
        resolved = str(Path(db_path).resolve())
        with cls._instance_lock:
            if resolved not in cls._instances:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instances[resolved] = instance
        return cls._instances[resolved]

    def __init__(self, db_path="data/fingerprint.db"):
        # type: (str) -> None
        if self._initialized:
            return
        self._db_path = str(Path(db_path).resolve())
        self._local = threading.local()
        self._lock = threading.Lock()
        self._initialized = True

        # Ensure parent directory exists
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        # Bootstrap schema
        self._init_schema()
        logger.info("DatabaseManager initialised: %s", self._db_path)

    # -- Connection management -----------------------------------------------

    @property
    def _conn(self):
        # type: () -> sqlite3.Connection
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = None
            self._local.conn = conn
        return conn

    @contextmanager
    def connection(self):
        # type: () -> Generator[sqlite3.Connection, None, None]
        yield self._conn

    @contextmanager
    def transaction(self):
        # type: () -> Generator[sqlite3.Connection, None, None]
        conn = self._conn
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self):
        # type: () -> None
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -- Schema management ---------------------------------------------------

    def _init_schema(self):
        # type: () -> None
        conn = self._conn
        try:
            for ddl in _DDL_STATEMENTS:
                conn.execute(ddl)
            for idx in _INDEX_STATEMENTS:
                conn.execute(idx)
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("Failed to initialise database schema")
            raise

    # -- Query helpers -------------------------------------------------------

    def execute(self, sql, params=()):
        # type: (str, Any) -> sqlite3.Cursor
        with self.transaction() as conn:
            return conn.execute(sql, params)

    def fetch_one(self, sql, params=()):
        # type: (str, Any) -> Optional[tuple]
        with self.connection() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchone()

    def fetch_all(self, sql, params=()):
        # type: (str, Any) -> list
        with self.connection() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()

    # -- Utility -------------------------------------------------------------

    @property
    def db_path(self):
        # type: () -> str
        return self._db_path

    def row_count(self, table):
        # type: (str) -> int
        row = self.fetch_one("SELECT COUNT(*) FROM {}".format(table))
        return row[0] if row else 0

    @classmethod
    def reset_instances(cls):
        # type: () -> None
        with cls._instance_lock:
            for instance in cls._instances.values():
                instance.close()
            cls._instances.clear()
