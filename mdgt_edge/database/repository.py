"""
MDGT Edge Fingerprint Verification System - Repositories.

Each repository encapsulates data-access logic for one aggregate root.
All mutations return *new* model instances (immutable pattern).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .database import DatabaseManager
from .models import (
    Device,
    DeviceStatus,
    Fingerprint,
    SystemConfig,
    User,
    UserRole,
    VerificationDecision,
    VerificationLog,
    VerificationMode,
)

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# UserRepository
# ============================================================================

class UserRepository:
    """CRUD and query operations for the ``users`` table."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # -- Create --------------------------------------------------------------

    def create(self, user: User) -> User:
        """Insert a new user and return it with the generated ``id``.

        Raises:
            sqlite3.IntegrityError: If ``employee_id`` already exists.
        """
        now = _utcnow()
        cursor = self._db.execute(
            """
            INSERT INTO users (employee_id, full_name, department, role, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user.employee_id,
                user.full_name,
                user.department,
                user.role.value,
                int(user.is_active),
                now,
                now,
            ),
        )
        from dataclasses import replace
        return replace(user, id=cursor.lastrowid, created_at=now, updated_at=now)

    # -- Read ----------------------------------------------------------------

    def get_by_id(self, user_id: int) -> Optional[User]:
        row = self._db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        return User.from_row(row) if row else None

    def get_by_employee_id(self, employee_id: str) -> Optional[User]:
        row = self._db.fetch_one(
            "SELECT * FROM users WHERE employee_id = ?", (employee_id,)
        )
        return User.from_row(row) if row else None

    def get_all(self, active_only: bool = False) -> list[User]:
        if active_only:
            rows = self._db.fetch_all(
                "SELECT * FROM users WHERE is_active = 1 ORDER BY id"
            )
        else:
            rows = self._db.fetch_all("SELECT * FROM users ORDER BY id")
        return [User.from_row(r) for r in rows]

    def filter_by_department(self, department: str) -> list[User]:
        rows = self._db.fetch_all(
            "SELECT * FROM users WHERE department = ? ORDER BY id",
            (department,),
        )
        return [User.from_row(r) for r in rows]

    def filter_by_role(self, role: UserRole) -> list[User]:
        rows = self._db.fetch_all(
            "SELECT * FROM users WHERE role = ? ORDER BY id",
            (role.value,),
        )
        return [User.from_row(r) for r in rows]

    def search(
        self,
        query: str,
        active_only: bool = True,
    ) -> list[User]:
        """Search users by employee_id or full_name (case-insensitive LIKE)."""
        pattern = f"%{query}%"
        sql = """
            SELECT * FROM users
            WHERE (employee_id LIKE ? OR full_name LIKE ?)
        """
        params: list[Any] = [pattern, pattern]
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY id"
        rows = self._db.fetch_all(sql, tuple(params))
        return [User.from_row(r) for r in rows]

    # -- Update --------------------------------------------------------------

    def update(self, user: User) -> User:
        """Update an existing user. Returns the updated (new) User instance.

        Raises:
            ValueError: If ``user.id`` is None.
        """
        if user.id is None:
            raise ValueError("Cannot update a user without an id")
        now = _utcnow()
        self._db.execute(
            """
            UPDATE users
            SET employee_id = ?, full_name = ?, department = ?,
                role = ?, is_active = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                user.employee_id,
                user.full_name,
                user.department,
                user.role.value,
                int(user.is_active),
                now,
                user.id,
            ),
        )
        from dataclasses import replace
        return replace(user, updated_at=now)

    def deactivate(self, user_id: int) -> bool:
        """Soft-delete a user. Returns True if a row was affected."""
        cursor = self._db.execute(
            "UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?",
            (_utcnow(), user_id),
        )
        return cursor.rowcount > 0

    # -- Delete --------------------------------------------------------------

    def delete(self, user_id: int) -> bool:
        """Hard-delete a user. Returns True if a row was deleted."""
        cursor = self._db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cursor.rowcount > 0

    # -- Count ---------------------------------------------------------------

    def count(self, active_only: bool = False) -> int:
        sql = "SELECT COUNT(*) FROM users"
        if active_only:
            sql += " WHERE is_active = 1"
        row = self._db.fetch_one(sql)
        return row[0] if row else 0


# ============================================================================
# FingerprintRepository
# ============================================================================

class FingerprintRepository:
    """CRUD and query operations for the ``fingerprints`` table."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # -- Create --------------------------------------------------------------

    def create(self, fp: Fingerprint) -> Fingerprint:
        """Insert a fingerprint record and return it with generated ``id``."""
        now = _utcnow()
        cursor = self._db.execute(
            """
            INSERT INTO fingerprints
                (user_id, finger_index, embedding_enc, minutiae_enc,
                 quality_score, image_hash, enrolled_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fp.user_id,
                fp.finger_index,
                fp.embedding_enc,
                fp.minutiae_enc,
                fp.quality_score,
                fp.image_hash,
                now,
                int(fp.is_active),
            ),
        )
        from dataclasses import replace
        return replace(fp, id=cursor.lastrowid, enrolled_at=now)

    # -- Read ----------------------------------------------------------------

    def get_by_id(self, fp_id: int) -> Optional[Fingerprint]:
        row = self._db.fetch_one(
            "SELECT * FROM fingerprints WHERE id = ?", (fp_id,)
        )
        return Fingerprint.from_row(row) if row else None

    def get_by_user_id(
        self, user_id: int, active_only: bool = True
    ) -> list[Fingerprint]:
        sql = "SELECT * FROM fingerprints WHERE user_id = ?"
        params: list[Any] = [user_id]
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY finger_index"
        rows = self._db.fetch_all(sql, tuple(params))
        return [Fingerprint.from_row(r) for r in rows]

    def get_active_embeddings(self) -> list[tuple[int, int, bytes]]:
        """Return (fp_id, user_id, embedding_enc) for all active fingerprints.

        This is the primary method used to build the FAISS index at startup.
        Only fingerprints that have a non-NULL embedding are returned.
        """
        rows = self._db.fetch_all(
            """
            SELECT id, user_id, embedding_enc
            FROM fingerprints
            WHERE is_active = 1 AND embedding_enc IS NOT NULL
            ORDER BY id
            """
        )
        return [(r[0], r[1], r[2]) for r in rows]

    def get_by_user_and_finger(
        self, user_id: int, finger_index: int
    ) -> Optional[Fingerprint]:
        row = self._db.fetch_one(
            """
            SELECT * FROM fingerprints
            WHERE user_id = ? AND finger_index = ? AND is_active = 1
            """,
            (user_id, finger_index),
        )
        return Fingerprint.from_row(row) if row else None

    def get_all_active(self) -> list[Fingerprint]:
        rows = self._db.fetch_all(
            "SELECT * FROM fingerprints WHERE is_active = 1 ORDER BY id"
        )
        return [Fingerprint.from_row(r) for r in rows]

    # -- Update --------------------------------------------------------------

    def update(self, fp: Fingerprint) -> Fingerprint:
        """Update an existing fingerprint record."""
        if fp.id is None:
            raise ValueError("Cannot update a fingerprint without an id")
        self._db.execute(
            """
            UPDATE fingerprints
            SET user_id = ?, finger_index = ?, embedding_enc = ?,
                minutiae_enc = ?, quality_score = ?, image_hash = ?,
                is_active = ?
            WHERE id = ?
            """,
            (
                fp.user_id,
                fp.finger_index,
                fp.embedding_enc,
                fp.minutiae_enc,
                fp.quality_score,
                fp.image_hash,
                int(fp.is_active),
                fp.id,
            ),
        )
        return fp

    def deactivate(self, fp_id: int) -> bool:
        cursor = self._db.execute(
            "UPDATE fingerprints SET is_active = 0 WHERE id = ?", (fp_id,)
        )
        return cursor.rowcount > 0

    def deactivate_by_user(self, user_id: int) -> int:
        """Deactivate all fingerprints for a user. Returns affected count."""
        cursor = self._db.execute(
            "UPDATE fingerprints SET is_active = 0 WHERE user_id = ?",
            (user_id,),
        )
        return cursor.rowcount

    # -- Delete --------------------------------------------------------------

    def delete(self, fp_id: int) -> bool:
        cursor = self._db.execute(
            "DELETE FROM fingerprints WHERE id = ?", (fp_id,)
        )
        return cursor.rowcount > 0

    # -- Count ---------------------------------------------------------------

    def count(self, active_only: bool = False) -> int:
        sql = "SELECT COUNT(*) FROM fingerprints"
        if active_only:
            sql += " WHERE is_active = 1"
        row = self._db.fetch_one(sql)
        return row[0] if row else 0

    def count_by_user(self, user_id: int, active_only: bool = True) -> int:
        sql = "SELECT COUNT(*) FROM fingerprints WHERE user_id = ?"
        params: list[Any] = [user_id]
        if active_only:
            sql += " AND is_active = 1"
        row = self._db.fetch_one(sql, tuple(params))
        return row[0] if row else 0


# ============================================================================
# LogRepository
# ============================================================================

class LogRepository:
    """Create and query verification / identification audit logs."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # -- Create --------------------------------------------------------------

    def create(self, log: VerificationLog) -> VerificationLog:
        """Insert a verification log record."""
        now = _utcnow()
        cursor = self._db.execute(
            """
            INSERT INTO verification_logs
                (matched_user_id, matched_fp_id, mode, score,
                 decision, latency_ms, device_id, timestamp, probe_quality)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log.matched_user_id,
                log.matched_fp_id,
                log.mode.value,
                log.score,
                log.decision.value,
                log.latency_ms,
                log.device_id,
                now,
                log.probe_quality,
            ),
        )
        from dataclasses import replace
        return replace(log, id=cursor.lastrowid, timestamp=now)

    # -- Query ---------------------------------------------------------------

    def get_by_id(self, log_id: int) -> Optional[VerificationLog]:
        row = self._db.fetch_one(
            "SELECT * FROM verification_logs WHERE id = ?", (log_id,)
        )
        return VerificationLog.from_row(row) if row else None

    def query(
        self,
        *,
        user_id: Optional[int] = None,
        device_id: Optional[str] = None,
        decision: Optional[VerificationDecision] = None,
        mode: Optional[VerificationMode] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[VerificationLog]:
        """Flexible query with optional filters.

        All date parameters are ISO-8601 strings.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if user_id is not None:
            clauses.append("matched_user_id = ?")
            params.append(user_id)
        if device_id is not None:
            clauses.append("device_id = ?")
            params.append(device_id)
        if decision is not None:
            clauses.append("decision = ?")
            params.append(decision.value)
        if mode is not None:
            clauses.append("mode = ?")
            params.append(mode.value)
        if start_date is not None:
            clauses.append("timestamp >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("timestamp <= ?")
            params.append(end_date)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM verification_logs{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._db.fetch_all(sql, tuple(params))
        return [VerificationLog.from_row(r) for r in rows]

    def get_recent(self, limit: int = 20) -> list[VerificationLog]:
        rows = self._db.fetch_all(
            "SELECT * FROM verification_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [VerificationLog.from_row(r) for r in rows]

    # -- Statistics ----------------------------------------------------------

    def get_stats(
        self,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return aggregate statistics for the given time range / device.

        Returns dict with keys: total, accept_count, reject_count,
        uncertain_count, avg_latency_ms, avg_score, accept_rate.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if start_date is not None:
            clauses.append("timestamp >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("timestamp <= ?")
            params.append(end_date)
        if device_id is not None:
            clauses.append("device_id = ?")
            params.append(device_id)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        row = self._db.fetch_one(
            f"""
            SELECT
                COUNT(*)                                          AS total,
                SUM(CASE WHEN decision = 'ACCEPT'    THEN 1 ELSE 0 END) AS accept_count,
                SUM(CASE WHEN decision = 'REJECT'    THEN 1 ELSE 0 END) AS reject_count,
                SUM(CASE WHEN decision = 'UNCERTAIN' THEN 1 ELSE 0 END) AS uncertain_count,
                AVG(latency_ms)                                   AS avg_latency_ms,
                AVG(score)                                        AS avg_score
            FROM verification_logs{where}
            """,
            tuple(params),
        )

        if row is None or row[0] == 0:
            return {
                "total": 0,
                "accept_count": 0,
                "reject_count": 0,
                "uncertain_count": 0,
                "avg_latency_ms": 0.0,
                "avg_score": 0.0,
                "accept_rate": 0.0,
            }

        total = row[0]
        accept_count = row[1] or 0
        return {
            "total": total,
            "accept_count": accept_count,
            "reject_count": row[2] or 0,
            "uncertain_count": row[3] or 0,
            "avg_latency_ms": round(row[4] or 0.0, 2),
            "avg_score": round(row[5] or 0.0, 4),
            "accept_rate": round(accept_count / total, 4) if total > 0 else 0.0,
        }

    def count(self) -> int:
        row = self._db.fetch_one("SELECT COUNT(*) FROM verification_logs")
        return row[0] if row else 0


# ============================================================================
# DeviceRepository
# ============================================================================

class DeviceRepository:
    """CRUD operations for the ``devices`` table."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # -- Create --------------------------------------------------------------

    def create(self, device: Device) -> Device:
        """Insert a device record.

        Raises:
            sqlite3.IntegrityError: If ``id`` already exists.
        """
        self._db.execute(
            """
            INSERT INTO devices (id, name, location, firmware_ver, last_sync, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                device.id,
                device.name,
                device.location,
                device.firmware_ver,
                device.last_sync,
                device.status.value,
            ),
        )
        return device

    # -- Read ----------------------------------------------------------------

    def get_by_id(self, device_id: str) -> Optional[Device]:
        row = self._db.fetch_one(
            "SELECT * FROM devices WHERE id = ?", (device_id,)
        )
        return Device.from_row(row) if row else None

    def get_all(self) -> list[Device]:
        rows = self._db.fetch_all("SELECT * FROM devices ORDER BY id")
        return [Device.from_row(r) for r in rows]

    def get_by_status(self, status: DeviceStatus) -> list[Device]:
        rows = self._db.fetch_all(
            "SELECT * FROM devices WHERE status = ? ORDER BY id",
            (status.value,),
        )
        return [Device.from_row(r) for r in rows]

    # -- Update --------------------------------------------------------------

    def update(self, device: Device) -> Device:
        """Update an existing device."""
        self._db.execute(
            """
            UPDATE devices
            SET name = ?, location = ?, firmware_ver = ?,
                last_sync = ?, status = ?
            WHERE id = ?
            """,
            (
                device.name,
                device.location,
                device.firmware_ver,
                device.last_sync,
                device.status.value,
                device.id,
            ),
        )
        return device

    def update_sync(self, device_id: str) -> bool:
        """Touch the ``last_sync`` timestamp. Returns True if row existed."""
        cursor = self._db.execute(
            "UPDATE devices SET last_sync = ? WHERE id = ?",
            (_utcnow(), device_id),
        )
        return cursor.rowcount > 0

    def set_status(self, device_id: str, status: DeviceStatus) -> bool:
        cursor = self._db.execute(
            "UPDATE devices SET status = ? WHERE id = ?",
            (status.value, device_id),
        )
        return cursor.rowcount > 0

    # -- Delete --------------------------------------------------------------

    def delete(self, device_id: str) -> bool:
        cursor = self._db.execute(
            "DELETE FROM devices WHERE id = ?", (device_id,)
        )
        return cursor.rowcount > 0

    # -- Count ---------------------------------------------------------------

    def count(self) -> int:
        row = self._db.fetch_one("SELECT COUNT(*) FROM devices")
        return row[0] if row else 0


# ============================================================================
# ConfigRepository
# ============================================================================

class ConfigRepository:
    """Get / set operations for the ``system_config`` key-value table."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # -- Get -----------------------------------------------------------------

    def get(self, key: str) -> Optional[SystemConfig]:
        row = self._db.fetch_one(
            "SELECT * FROM system_config WHERE key = ?", (key,)
        )
        return SystemConfig.from_row(row) if row else None

    def get_value(self, key: str, default: Any = None) -> Any:
        """Return the parsed JSON value for *key*, or *default*."""
        cfg = self.get(key)
        if cfg is None:
            return default
        try:
            return json.loads(cfg.value)
        except (json.JSONDecodeError, TypeError):
            return cfg.value

    def get_all(self) -> list[SystemConfig]:
        rows = self._db.fetch_all(
            "SELECT * FROM system_config ORDER BY key"
        )
        return [SystemConfig.from_row(r) for r in rows]

    def get_all_as_dict(self) -> dict[str, Any]:
        """Return all config entries as a flat ``{key: parsed_value}`` dict."""
        configs = self.get_all()
        result: dict[str, Any] = {}
        for cfg in configs:
            try:
                result[cfg.key] = json.loads(cfg.value)
            except (json.JSONDecodeError, TypeError):
                result[cfg.key] = cfg.value
        return result

    # -- Set -----------------------------------------------------------------

    def set(self, key: str, value: Any) -> SystemConfig:
        """Insert or update a config entry. *value* is JSON-serialised."""
        now = _utcnow()
        json_value = json.dumps(value) if not isinstance(value, str) else value
        self._db.execute(
            """
            INSERT INTO system_config (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, json_value, now),
        )
        return SystemConfig(key=key, value=json_value, updated_at=now)

    def set_many(self, entries: dict[str, Any]) -> list[SystemConfig]:
        """Bulk upsert multiple config entries."""
        results: list[SystemConfig] = []
        for key, value in entries.items():
            results.append(self.set(key, value))
        return results

    # -- Delete --------------------------------------------------------------

    def delete(self, key: str) -> bool:
        cursor = self._db.execute(
            "DELETE FROM system_config WHERE key = ?", (key,)
        )
        return cursor.rowcount > 0

    # -- Count ---------------------------------------------------------------

    def count(self) -> int:
        row = self._db.fetch_one("SELECT COUNT(*) FROM system_config")
        return row[0] if row else 0
