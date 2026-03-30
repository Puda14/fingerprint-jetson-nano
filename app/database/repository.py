"""
Repository layer for fingerprint database CRUD operations.

Ported from jetson-fingerverify-app/mdgt_edge/database/repository.py.
Provides UserRepository, FingerprintRepository, and VerificationLogRepository.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from app.database.database import DatabaseManager
from app.database.models import Fingerprint, User, VerificationLog

logger = logging.getLogger(__name__)


def _utcnow():
    # type: () -> str
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# UserRepository
# ============================================================================

class UserRepository:
    """CRUD operations for the users table."""

    def __init__(self, db):
        # type: (DatabaseManager) -> None
        self._db = db

    def create(self, user):
        # type: (User) -> User
        """Insert a new user and return it with generated id."""
        self._db.execute(
            """INSERT INTO users (employee_id, full_name, department, role, is_active)
               VALUES (?, ?, ?, ?, ?)""",
            (user.employee_id, user.full_name, user.department,
             user.role, int(user.is_active)),
        )
        row = self._db.fetch_one(
            "SELECT * FROM users WHERE employee_id = ?",
            (user.employee_id,),
        )
        return User.from_row(row) if row else user

    def get_by_id(self, user_id):
        # type: (int) -> Optional[User]
        row = self._db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        return User.from_row(row) if row else None

    def get_by_employee_id(self, employee_id):
        # type: (str) -> Optional[User]
        row = self._db.fetch_one(
            "SELECT * FROM users WHERE employee_id = ?", (employee_id,),
        )
        return User.from_row(row) if row else None

    def get_all(self, active_only=False):
        # type: (bool) -> List[User]
        if active_only:
            rows = self._db.fetch_all(
                "SELECT * FROM users WHERE is_active = 1 ORDER BY id",
            )
        else:
            rows = self._db.fetch_all("SELECT * FROM users ORDER BY id")
        return [User.from_row(r) for r in rows]

    def search(self, query, active_only=True):
        # type: (str, bool) -> List[User]
        pattern = "%{}%".format(query)
        sql = """SELECT * FROM users
                 WHERE (employee_id LIKE ? OR full_name LIKE ?)"""
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY id"
        rows = self._db.fetch_all(sql, (pattern, pattern))
        return [User.from_row(r) for r in rows]

    def update(self, user):
        # type: (User) -> User
        if user.id is None:
            raise ValueError("Cannot update user without id")
        self._db.execute(
            """UPDATE users SET employee_id=?, full_name=?, department=?,
               role=?, is_active=?, updated_at=? WHERE id=?""",
            (user.employee_id, user.full_name, user.department,
             user.role, int(user.is_active), _utcnow(), user.id),
        )
        return self.get_by_id(user.id) or user

    def deactivate(self, user_id):
        # type: (int) -> bool
        cur = self._db.execute(
            "UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?",
            (_utcnow(), user_id),
        )
        return cur.rowcount > 0

    def delete(self, user_id):
        # type: (int) -> bool
        cur = self._db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cur.rowcount > 0

    def count(self, active_only=False):
        # type: (bool) -> int
        if active_only:
            row = self._db.fetch_one(
                "SELECT COUNT(*) FROM users WHERE is_active = 1",
            )
        else:
            row = self._db.fetch_one("SELECT COUNT(*) FROM users")
        return row[0] if row else 0


# ============================================================================
# FingerprintRepository
# ============================================================================

class FingerprintRepository:
    """CRUD operations for the fingerprints table."""

    def __init__(self, db):
        # type: (DatabaseManager) -> None
        self._db = db

    def create(self, fp):
        # type: (Fingerprint) -> Fingerprint
        self._db.execute(
            """INSERT INTO fingerprints
               (user_id, finger_index, embedding_enc, minutiae_enc,
                quality_score, image_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (fp.user_id, fp.finger_index, fp.embedding_enc,
             fp.minutiae_enc, fp.quality_score, fp.image_hash),
        )
        row = self._db.fetch_one(
            """SELECT * FROM fingerprints
               WHERE user_id = ? AND finger_index = ?
               ORDER BY id DESC LIMIT 1""",
            (fp.user_id, fp.finger_index),
        )
        return Fingerprint.from_row(row) if row else fp

    def get_by_id(self, fp_id):
        # type: (int) -> Optional[Fingerprint]
        row = self._db.fetch_one(
            "SELECT * FROM fingerprints WHERE id = ?", (fp_id,),
        )
        return Fingerprint.from_row(row) if row else None

    def get_by_user_id(self, user_id, active_only=True):
        # type: (int, bool) -> List[Fingerprint]
        sql = "SELECT * FROM fingerprints WHERE user_id = ?"
        if active_only:
            sql += " AND is_active = 1"
        rows = self._db.fetch_all(sql, (user_id,))
        return [Fingerprint.from_row(r) for r in rows]

    def get_active_embeddings(self):
        # type: () -> List[Tuple[int, int, bytes]]
        """Return (fp_id, user_id, embedding_enc) for all active fingerprints.

        This is used to build the FAISS index at startup.
        """
        rows = self._db.fetch_all(
            """SELECT id, user_id, embedding_enc
               FROM fingerprints
               WHERE is_active = 1 AND embedding_enc IS NOT NULL""",
        )
        return [(r[0], r[1], r[2]) for r in rows]

    def update(self, fp):
        # type: (Fingerprint) -> Fingerprint
        if fp.id is None:
            raise ValueError("Cannot update fingerprint without id")
        self._db.execute(
            """UPDATE fingerprints
               SET user_id=?, finger_index=?, embedding_enc=?,
                   minutiae_enc=?, quality_score=?, image_hash=?, is_active=?
               WHERE id=?""",
            (fp.user_id, fp.finger_index, fp.embedding_enc,
             fp.minutiae_enc, fp.quality_score, fp.image_hash,
             int(fp.is_active), fp.id),
        )
        return self.get_by_id(fp.id) or fp

    def deactivate(self, fp_id):
        # type: (int) -> bool
        cur = self._db.execute(
            "UPDATE fingerprints SET is_active = 0 WHERE id = ?", (fp_id,),
        )
        return cur.rowcount > 0

    def deactivate_by_user(self, user_id):
        # type: (int) -> int
        cur = self._db.execute(
            "UPDATE fingerprints SET is_active = 0 WHERE user_id = ?",
            (user_id,),
        )
        return cur.rowcount

    def delete(self, fp_id):
        # type: (int) -> bool
        cur = self._db.execute(
            "DELETE FROM fingerprints WHERE id = ?", (fp_id,),
        )
        return cur.rowcount > 0

    def count(self, active_only=False):
        # type: (bool) -> int
        if active_only:
            row = self._db.fetch_one(
                "SELECT COUNT(*) FROM fingerprints WHERE is_active = 1",
            )
        else:
            row = self._db.fetch_one("SELECT COUNT(*) FROM fingerprints")
        return row[0] if row else 0

    def count_by_user(self, user_id, active_only=True):
        # type: (int, bool) -> int
        sql = "SELECT COUNT(*) FROM fingerprints WHERE user_id = ?"
        if active_only:
            sql += " AND is_active = 1"
        row = self._db.fetch_one(sql, (user_id,))
        return row[0] if row else 0


# ============================================================================
# VerificationLogRepository
# ============================================================================

class VerificationLogRepository:
    """CRUD operations for the verification_logs table."""

    def __init__(self, db):
        # type: (DatabaseManager) -> None
        self._db = db

    def create(self, log):
        # type: (VerificationLog) -> VerificationLog
        self._db.execute(
            """INSERT INTO verification_logs
               (matched_user_id, matched_fp_id, mode, score, decision,
                latency_ms, device_id, probe_quality)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (log.matched_user_id, log.matched_fp_id, log.mode,
             log.score, log.decision, log.latency_ms,
             log.device_id, log.probe_quality),
        )
        row = self._db.fetch_one(
            "SELECT * FROM verification_logs ORDER BY id DESC LIMIT 1",
        )
        return VerificationLog.from_row(row) if row else log

    def get_recent(self, limit=50):
        # type: (int) -> List[VerificationLog]
        rows = self._db.fetch_all(
            "SELECT * FROM verification_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [VerificationLog.from_row(r) for r in rows]

    def get_by_user(self, user_id, limit=50):
        # type: (int, int) -> List[VerificationLog]
        rows = self._db.fetch_all(
            """SELECT * FROM verification_logs
               WHERE matched_user_id = ? ORDER BY id DESC LIMIT ?""",
            (user_id, limit),
        )
        return [VerificationLog.from_row(r) for r in rows]

    def count(self):
        # type: () -> int
        row = self._db.fetch_one("SELECT COUNT(*) FROM verification_logs")
        return row[0] if row else 0
