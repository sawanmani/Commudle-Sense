"""
app/audience.py — Who may LIST which records (row-level), by requester role.

    logged_out → public records only
    member     → public + members-only
    organiser  → public + members-only + organisers-only

Records without a record_audience row are public. An unrecognised role gets the logged-out view
(fail closed). This is independent of — and never relaxes — the column rules in permissions.py:
private fields stay unselectable for every role.

Note: in this demo the role comes from the request body. In production it must come from the
authenticated session, never from something the client can type.
"""

from __future__ import annotations

from typing import List

from sqlalchemy import select

from app.models_extra import RecordAudience

AUDIENCE_LEVEL = {"members": 1, "organisers": 2}
ROLE_LEVEL = {"logged_out": 0, "member": 1, "organiser": 2}


def hidden_audiences(auth_state: str) -> List[str]:
    """Audiences this role may NOT see."""
    level = ROLE_LEVEL.get(auth_state, 0)
    return [a for a, need in AUDIENCE_LEVEL.items() if need > level]


def restrict(stmt, model, entity: str, auth_state: str):
    """Add `id NOT IN (records whose audience is above this role)` — a bound-parameter subquery."""
    hidden = hidden_audiences(auth_state)
    if not hidden:
        return stmt
    blocked = select(RecordAudience.record_id).where(
        RecordAudience.entity == entity, RecordAudience.audience.in_(hidden)
    )
    return stmt.where(model.id.not_in(blocked))


def audience_label(model, entity: str):
    """Correlated subquery: the record's audience label (None = public), for the result badge."""
    return (
        select(RecordAudience.audience)
        .where(RecordAudience.entity == entity, RecordAudience.record_id == model.id)
        .scalar_subquery()
        .label("audience")
    )
