"""Audit logging for agent actions, API requests, and approvals."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AuditLogger:
    """Append-only SQLite audit log.

    Stores action type, actor/session, a SHA-256 hash of the payload, and a redacted
    summary. Never writes raw secrets, API keys, or tokens.
    """

    SENSITIVE_KEYS = {"api_key", "token", "access_token", "authorization", "password"}

    def __init__(self, db_path: str | Path = "audit.db"):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT,
                    session_id TEXT,
                    payload_hash TEXT,
                    summary TEXT,
                    details TEXT
                )
                """
            )

    def _redact(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            return {
                k: "[REDACTED]" if k.lower() in self.SENSITIVE_KEYS else self._redact(v)
                for k, v in payload.items()
            }
        if isinstance(payload, list):
            return [self._redact(v) for v in payload]
        return payload

    def _hash(self, payload: Any) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def log(
        self,
        action: str,
        actor: str | None = None,
        session_id: str | None = None,
        payload: Dict[str, Any] | None = None,
    ) -> None:
        payload = payload or {}
        redacted = self._redact(payload)
        summary = redacted.get("tool_name") or redacted.get("message") or redacted.get("action") or action
        details = json.dumps(redacted, default=str)
        payload_hash = self._hash(payload)
        timestamp = datetime.now(timezone.utc).isoformat()

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO audit_log (timestamp, action, actor, session_id, payload_hash, summary, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (timestamp, action, actor, session_id, payload_hash, str(summary), details),
                )
        logger.info("Audit: %s actor=%s session=%s", action, actor, session_id)

    def query(
        self,
        action: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            where = []
            params: list[Any] = []
            if action:
                where.append("action = ?")
                params.append(action)
            if session_id:
                where.append("session_id = ?")
                params.append(session_id)
            query = "SELECT * FROM audit_log"
            if where:
                query += " WHERE " + " AND ".join(where)
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]


_AUDIT_LOGGER: AuditLogger | None = None


def get_audit_logger(db_path: str | Path = "audit.db") -> AuditLogger:
    global _AUDIT_LOGGER
    if _AUDIT_LOGGER is None:
        _AUDIT_LOGGER = AuditLogger(db_path)
    return _AUDIT_LOGGER
