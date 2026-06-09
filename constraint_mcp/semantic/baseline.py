"""SQLite store for per-file baseline embeddings (drift detection only)."""

from __future__ import annotations

import hashlib
import io
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def _default_db_path() -> Path:
    return Path(os.environ.get("CONSTRAINT_MCP_BASELINE_DB", ".constraint-mcp/baselines.db"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(embedding: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.save(buf, embedding.astype(np.float32), allow_pickle=False)
    return buf.getvalue()


def _deserialize(blob: bytes) -> np.ndarray:
    return np.load(io.BytesIO(blob), allow_pickle=False)


class BaselineStore:
    """Persists per-file baseline embeddings for drift detection.

    Baseline update policy:
      - ``auto``: baseline is updated every time a file passes all checks, so it
        tracks the file's semantic evolution; drift is a sudden large jump.
      - ``locked``: baseline is set once (first successful write) and never
        updated, so writes must stay close to the first-ever version.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS baselines (
                    filepath      TEXT PRIMARY KEY,
                    content_hash  TEXT NOT NULL,
                    embedding     BLOB NOT NULL,
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL,
                    mode          TEXT NOT NULL
                )
                """
            )

    def content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get(self, filepath: str) -> np.ndarray | None:
        """Return the stored baseline embedding, or None if none exists."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT embedding FROM baselines WHERE filepath = ?", (filepath,)
            ).fetchone()
        if row is None:
            return None
        return _deserialize(row[0])

    def get_mode(self, filepath: str) -> str | None:
        """Return the stored mode ("auto"/"locked") for a file, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT mode FROM baselines WHERE filepath = ?", (filepath,)
            ).fetchone()
        return row[0] if row else None

    def set(self, filepath: str, content: str, embedding: np.ndarray, mode: str) -> None:
        """Upsert a baseline. A ``locked`` baseline is never overwritten once set."""
        now = _now()
        chash = self.content_hash(content)
        blob = _serialize(embedding)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at, mode FROM baselines WHERE filepath = ?", (filepath,)
            ).fetchone()
            if existing is not None and existing[1] == "locked":
                # Locked baselines are immutable once established.
                return
            created_at = existing[0] if existing is not None else now
            conn.execute(
                """
                INSERT INTO baselines (filepath, content_hash, embedding, created_at, updated_at, mode)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(filepath) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    embedding    = excluded.embedding,
                    updated_at   = excluded.updated_at,
                    mode         = excluded.mode
                """,
                (filepath, chash, blob, created_at, now, mode),
            )

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM baselines").fetchone()[0]

    def files(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT filepath FROM baselines ORDER BY filepath").fetchall()
        return [r[0] for r in rows]
