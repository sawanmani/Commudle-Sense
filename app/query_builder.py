"""
app/query_builder.py — Stage 4: Permission-checked parameterized query + cosine sim.

SQL is NEVER built via string formatting. All filters use bound parameters
through SQLAlchemy Core expressions. entity_type == "unknown" is hard-blocked.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.audience import audience_label, hidden_audiences, restrict
from app.models import Event
from app.models_extra import SpeakerTalk
from app.permissions import get_allowed_columns, entity_allowed_for, MODEL_MAP
from app.schemas import SearchIntent


class BlockedQueryError(Exception):
    """Raised when a query must be blocked (unknown entity, disallowed role, etc.)."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


# Entities whose date is when it HAPPENS (rank upcoming first) rather than when it was created.
TIME_BOUND = {"event", "hackathon"}

# Entity → date column name (others have no public date → neutral recency)
DATE_COLUMN = {
    "event": "event_date",
    "hackathon": "start_date",
    "community": "created_at",
    "build": "created_at",
}


_TECH_EQUIV = {"fullstack": ("fullstack", "full stack"), "full stack": ("fullstack", "full stack")}


def _tag_regex(tech: str) -> str:
    """POSIX regex matching `tech` as a complete comma-separated tag (allow-listed value, escaped)."""
    names = "|".join(re.escape(n) for n in _TECH_EQUIV.get(tech, (tech,)))
    return rf"(^|,\s*)({names})(\s*,|$)"


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
    trace: Optional[Dict[str, Any]] = None,
    limit: int = 50,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Build and execute the permission-checked, parameterized query.

    If `trace` (a dict) is given it is filled with the generated SQL, its bound parameters and
    which columns were allowed / hidden — for the demo's "how it worked" panel.

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

    # Audience label for the result badge; for speakers also their most recent PAST talk ("recent activity").
    extras = [audience_label(model, entity)]
    last_talk = None
    if entity == "speaker":
        last_talk = (
            select(func.max(Event.event_date))
            .join(SpeakerTalk, SpeakerTalk.event_id == Event.id)
            .where(SpeakerTalk.speaker_id == model.id, Event.event_date <= date.today())
            .scalar_subquery()
            .label("last_talk")
        )
        extras.append(last_talk)

    stmt = select(*columns, *extras)

    # ── Row-level audience: records above this role's level never leave the database ──
    stmt = restrict(stmt, model, entity, auth_state)

    # ── Filters (all bound params) ─────────────────────────────────────────
    if intent.location and hasattr(model, "city"):
        stmt = stmt.where(model.city == intent.location)

    # "speakers who have SPOKEN in <city>": sub-select over speaker_talks -> events (bound parameter)
    if intent.spoken_in and entity == "speaker":
        spoke_there = (
            select(SpeakerTalk.speaker_id)
            .join(Event, Event.id == SpeakerTalk.event_id)
            .where(Event.city == intent.spoken_in)
        )
        stmt = stmt.where(model.id.in_(spoke_there))

    if intent.technologies and hasattr(model, "tags"):
        # Whole-tag match on the comma-separated `tags` column (bound regex parameter). A substring
        # ILIKE would make "go" match "django" and "react" match "react-native".
        tag_filters = [model.tags.op("~*")(_tag_regex(t)) for t in intent.technologies]
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
                if entity in TIME_BOUND:
                    # Things you attend: upcoming first (soonest first), then past (most recent first).
                    today = date.today()
                    is_past = case((date_col >= today, 0), else_=1)
                    stmt = stmt.order_by(is_past, case((date_col >= today, date_col)).asc(), date_col.desc().nulls_last())
                else:
                    stmt = stmt.order_by(date_col.desc().nulls_last())
        elif last_talk is not None:
            stmt = stmt.order_by(last_talk.desc().nulls_last())  # recently active speakers first

    stmt = stmt.limit(max(1, min(int(limit), 50)))

    if trace is not None:
        from sqlalchemy.dialects import postgresql
        compiled = stmt.compile(dialect=postgresql.dialect())
        trace["sql"] = str(compiled)
        trace["params"] = {k: (f"<{len(v)}-dim vector>" if isinstance(v, (list, tuple)) and len(v) > 8 else v)
                           for k, v in compiled.params.items()}
        trace["allowed_columns"] = data_cols
        hidden = hidden_audiences(auth_state)
        trace["audience_rule"] = (f"{auth_state}: records for {' / '.join(hidden)} are excluded inside the query"
                                  if hidden else f"{auth_state}: may see every audience level")
        trace["hidden_columns"] = [{"column": c.name, "visibility": c.info.get("visibility", "unspecified")}
                                   for c in model.__table__.columns if c.info.get("visibility") != "public"]

    # ── Execute ────────────────────────────────────────────────────────────
    result = db.execute(stmt)
    rows = []
    for row in result:
        m = row._mapping
        row_dict: Dict[str, Any] = {}
        for col_name in data_cols:
            val = m[col_name]
            # Convert dates/datetimes to string for JSON
            if isinstance(val, (date, datetime)):
                val = val.isoformat()
            row_dict[col_name] = val
        sim = m.get("similarity") if sim_expr is not None else None
        row_dict["similarity"] = float(sim) if sim is not None else None
        row_dict["_audience"] = m.get("audience")
        # Date used for ranking: when it happens / was created; for speakers, their most recent talk
        date_col_name = DATE_COLUMN.get(entity)
        if date_col_name and date_col_name in row_dict:
            row_dict["_date_value"] = row_dict[date_col_name]
        elif last_talk is not None and m.get("last_talk") is not None:
            row_dict["_date_value"] = m["last_talk"].isoformat()
        else:
            row_dict["_date_value"] = None
        # Popularity signal for ranking: talks given / community size
        act = row_dict.get("talks_given") if "talks_given" in row_dict else row_dict.get("member_count")
        row_dict["_activity"] = act
        rows.append(row_dict)

    return rows, data_cols
