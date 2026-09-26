"""
app/logging_utils.py — Bonus: blocked-attempt audit log.

Appends a JSON line per blocked/dropped attempt for audit trail (required by PS-01).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import LOG_BLOCKED_ATTEMPTS_PATH


def log_blocked_attempt(
    raw_query: str,
    reason: str,
    auth_state: str,
    dropped_fields: Optional[List[str]] = None,
) -> None:
    """Append a JSON-line audit entry for a blocked or partially-dropped query."""
    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "raw_query": raw_query[:500],
        "reason": reason,
        "auth_state": auth_state,
        "dropped_fields": dropped_fields or [],
    }

    try:
        parent = os.path.dirname(LOG_BLOCKED_ATTEMPTS_PATH)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(LOG_BLOCKED_ATTEMPTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Logging must never crash the pipeline
