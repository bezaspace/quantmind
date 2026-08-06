"""Content-addressed Tier-1 storage for OHLCV and factor panels."""

from __future__ import annotations

import hashlib
import json
import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

import polars as pl

logger = logging.getLogger(__name__)


class Tier1Store:
    """Content-addressed Parquet store for DataFrames.

    Items are stored by SHA-256 of their deterministic JSON descriptor
    (kind, key params, content hash). This makes retrieval idempotent
    across runs and strategies.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root or Path.home() / ".quantmind" / "tier1")
        self.root.mkdir(parents=True, exist_ok=True)

    def _descriptor_hash(self, kind: str, key: str, meta: Dict[str, Any]) -> str:
        payload = json.dumps({"kind": kind, "key": key, "meta": meta}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def _blob_path(self, digest: str) -> Path:
        prefix = digest[:2]
        return self.root / prefix / f"{digest}.parquet"

    def put(
        self,
        df: pl.DataFrame,
        kind: str,
        key: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store ``df`` and return its content-addressed digest."""
        buf = BytesIO()
        df.write_parquet(buf)
        content_hash = hashlib.sha256(buf.getvalue()).hexdigest()
        descriptor = self._descriptor_hash(kind, key, meta or {})
        # Include content hash in path so same descriptor with different data
        # creates a new blob rather than silently overwriting.
        digest = hashlib.sha256(f"{descriptor}:{content_hash}".encode()).hexdigest()
        blob_path = self._blob_path(digest)
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(buf.getvalue())
        logger.debug("Tier1 stored %s/%s -> %s", kind, key, digest)
        return digest

    def get(self, digest: str) -> Optional[pl.DataFrame]:
        """Load a DataFrame by digest, or ``None`` if missing."""
        blob_path = self._blob_path(digest)
        if not blob_path.exists():
            return None
        return pl.read_parquet(blob_path)

    def exists(self, digest: str) -> bool:
        return self._blob_path(digest).exists()
