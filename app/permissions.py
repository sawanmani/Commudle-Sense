"""
app/permissions.py — Single source of truth for visible columns.  [SACRED]

Search NEVER exposes PRIVATE or ORGANISER_ONLY columns to ANY role.
The three role sets (logged_out, member, organiser) are intentionally identical
for search — organiser analytics is a separate authenticated endpoint, not search.
"""

from __future__ import annotations
from typing import List

from app.models import Community, Event, Speaker, Hackathon, Build, Lab, Job

# ── Entity model map (searchable entities only; User is excluded) ──────────────
MODEL_MAP = {
    "community": Community,
    "event": Event,
    "speaker": Speaker,
    "hackathon": Hackathon,
    "build": Build,
    "lab": Lab,
    "job": Job,
}

# All roles see the same set of entities through search
LOGGED_OUT_ALLOWED_ENTITIES = {
    "community", "event", "speaker", "hackathon", "build", "lab", "job",
}
MEMBER_ALLOWED_ENTITIES = LOGGED_OUT_ALLOWED_ENTITIES
ORGANISER_ALLOWED_ENTITIES = LOGGED_OUT_ALLOWED_ENTITIES


def get_allowed_columns(entity_type: str, auth_state: str = "logged_out") -> List[str]:
    """Return the list of column names whose visibility is 'public'.

    PRIVATE and ORGANISER_ONLY columns are NEVER returned, regardless of role.
    """
    model = MODEL_MAP.get(entity_type)
    if model is None:
        return []

    allowed: List[str] = []
    for col in model.__table__.columns:
        vis = col.info.get("visibility")
        if vis == "public":
            allowed.append(col.name)
    return allowed


def entity_allowed_for(entity_type: str, auth_state: str = "logged_out") -> bool:
    """Check whether the given entity type is searchable for the given role."""
    if auth_state == "organiser":
        return entity_type in ORGANISER_ALLOWED_ENTITIES
    if auth_state == "member":
        return entity_type in MEMBER_ALLOWED_ENTITIES
    return entity_type in LOGGED_OUT_ALLOWED_ENTITIES
