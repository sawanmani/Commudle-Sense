"""
tests/test_permissions.py — Deterministic permission proof (no DB/LLM).

For every entity × every auth_state, asserts that no private column is ever
returned by get_allowed_columns(). This is the leakage-impossible proof.
"""

from app.permissions import get_allowed_columns, MODEL_MAP

# Columns that must NEVER appear in search results (all visibility=private or organiser_only)
FORBIDDEN_COLUMNS = {
    "email", "phone", "rsvp_list", "attendance_log", "form_responses",
    "private_channel_ids", "internal_notes", "organiser_analytics",
    "draft_content", "applicant_list", "judging_notes", "registrations",
}

AUTH_STATES = ["logged_out", "member", "organiser"]


def test_no_private_columns_for_any_role():
    """Prove: no private/organiser column is ever returned for any entity × role."""
    for entity_type in MODEL_MAP:
        for auth_state in AUTH_STATES:
            allowed = get_allowed_columns(entity_type, auth_state)
            leaked = set(allowed) & FORBIDDEN_COLUMNS
            assert not leaked, (
                f"LEAKAGE: entity={entity_type}, auth_state={auth_state}, "
                f"leaked columns={leaked}"
            )


def test_allowed_columns_are_public():
    """Every returned column must have visibility='public' in its info."""
    for entity_type, model in MODEL_MAP.items():
        for auth_state in AUTH_STATES:
            allowed = get_allowed_columns(entity_type, auth_state)
            for col_name in allowed:
                col = model.__table__.columns[col_name]
                assert col.info.get("visibility") == "public", (
                    f"Column {col_name} on {entity_type} returned for "
                    f"{auth_state} but visibility={col.info.get('visibility')}"
                )


def test_unknown_entity_returns_empty():
    """Unknown entity type must return an empty column list."""
    for auth_state in AUTH_STATES:
        assert get_allowed_columns("unknown", auth_state) == []
        assert get_allowed_columns("nonexistent", auth_state) == []


def test_all_entities_have_id():
    """Every entity must expose 'id' as a public column."""
    for entity_type in MODEL_MAP:
        for auth_state in AUTH_STATES:
            allowed = get_allowed_columns(entity_type, auth_state)
            assert "id" in allowed, (
                f"Entity {entity_type} missing 'id' for {auth_state}"
            )
