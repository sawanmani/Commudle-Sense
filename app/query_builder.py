"""
app/query_builder.py — Stage 4: Permission-checked parameterized query + cosine sim.

SQL is NEVER built via string formatting. All filters use bound parameters
through SQLAlchemy Core expressions. entity_type == "unknown" is hard-blocked.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app.permissions import get_allowed_columns, entity_allowed_for, MODEL_MAP
from app.schemas import SearchIntent


class BlockedQueryError(Exception):
    """Raised when a query must be blocked (unknown entity, disallowed role, etc.)."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


# Entity → date column name (others have no public date → neutral recency)
DATE_COLUMN = {
    "event": "event_date",
    "hackathon": "start_date",
    "community": "created_at",
    "build": "created_at",
}


def _parse_iso(value: Optional[str]):
    """Parse an ISO date string to a date/datetime. Returns None on failure (fail-closed)."""
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        pass
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def build_and_run(
    db: Session,
    intent: SearchIntent,
    ctx: Any,
    query_embedding: Optional[List[float]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Build and execute the permission-checked, parameterized query.

    Returns (rows_as_dicts, data_column_names).
    Raises BlockedQueryError if the query must be blocked.
    """
    entity = intent.entity_type.value

    # ── Hard-block unknown entity type ─────────────────────────────────────
    if entity == "unknown":
        raise BlockedQueryError("could_not_determine_entity_type")

    # ── Check entity permission ────────────────────────────────────────────
    auth_state = getattr(ctx, "auth_state", "logged_out")
    if not entity_allowed_for(entity, auth_state):
        raise BlockedQueryError(f"entity_not_allowed_for_role:{entity}:{auth_state}")

    model = MODEL_MAP[entity]
    allowed = get_allowed_columns(entity, auth_state)
    # Data columns exclude embedding (never projected to client)
    data_cols = [c for c in allowed if c != "embedding"]

    # ── Check for semantic search capability ───────────────────────────────
    semantic = bool(query_embedding) and hasattr(model, "embedding")
    sim_expr = None
    if semantic:
        sim_expr = (1 - model.embedding.cosine_distance(query_embedding)).label("similarity")

    # ── Build column selections ────────────────────────────────────────────
    columns = [getattr(model, c) for c in data_cols]
    if sim_expr is not None:
        columns.append(sim_expr)

    stmt = select(*columns)

    # ── Filters (all bound params) ─────────────────────────────────────────
    if intent.location and hasattr(model, "city"):
        stmt = stmt.where(model.city == intent.location)

    if intent.technologies and hasattr(model, "tags"):
        tag_filters = [model.tags.ilike(f"%{t}%") for t in intent.technologies]
        stmt = stmt.where(or_(*tag_filters))

    if intent.date_range:
        date_col_name = DATE_COLUMN.get(entity)
        if date_col_name:
            date_col = getattr(model, date_col_name, None)
            if date_col is not None:
                start = _parse_iso(intent.date_range.from_date)
                end = _parse_iso(intent.date_range.to_date)
                if start:
                    stmt = stmt.where(date_col >= start)
                if end:
                    stmt = stmt.where(date_col <= end)

    # ── content_type filter: ONLY for event entity (title ILIKE) ───────────
    if intent.content_type and entity == "event" and hasattr(model, "title"):
        stmt = stmt.where(model.title.ilike(f"%{intent.content_type}%"))

    # ── role: intentionally NOT a hard filter (no queryable column) ────────
    # Stays a classification signal shown in interpreted_intent (documented no-op).

    # ── Ordering ───────────────────────────────────────────────────────────
    if semantic:
        stmt = stmt.order_by(model.embedding.cosine_distance(query_embedding).asc())
    else:
        date_col_name = DATE_COLUMN.get(entity)
        if date_col_name:
            date_col = getattr(model, date_col_name, None)
            if date_col is not None:
                stmt = stmt.order_by(date_col.desc().nulls_last())

    stmt = stmt.limit(50)

    # ── Execute ────────────────────────────────────────────────────────────
    result = db.execute(stmt)
    rows = []
    for row in result:
        row_dict: Dict[str, Any] = {}
        for i, col_name in enumerate(data_cols):
            val = row[i]
            # Convert dates/datetimes to string for JSON
            if isinstance(val, (date, datetime)):
                val = val.isoformat()
            row_dict[col_name] = val
        # Add similarity if semantic
        if sim_expr is not None:
            row_dict["similarity"] = float(row[len(data_cols)]) if row[len(data_cols)] is not None else None
        else:
            row_dict["similarity"] = None
        # Add created_at / date value for recency scoring
        date_col_name = DATE_COLUMN.get(entity)
        if date_col_name and date_col_name in row_dict:
            row_dict["_date_value"] = row_dict[date_col_name]
        else:
            row_dict["_date_value"] = None
        rows.append(row_dict)

    return rows, data_cols
