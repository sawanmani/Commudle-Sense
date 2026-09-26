"""
demo/streamlit_app.py — Streamlit demo UI.

Search box, clickable suggestion chips, interpreted-intent panel,
blocked banner, ranked results, and web-enrichment expander.

Run: streamlit run demo/streamlit_app.py
"""

from __future__ import annotations

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from app.extraction import extract_intent
from app.validation import validate_intent
from app.ranking import embed_text, rank_results
from app.autocomplete import suggest
from app.external_search import safe_web_search
from app.logging_utils import log_blocked_attempt
from app.permissions import MODEL_MAP
from app.query_builder import build_and_run, BlockedQueryError
from app.schemas import EntityType, RequesterContext
from app.models import engine

from sqlalchemy.orm import sessionmaker

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Commudle Safe Search",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 Commudle Safe Natural-Language Search")
st.caption("PS-01: Permission-aware search with injection defenses")

# ── Sidebar: auth context ──────────────────────────────────────────────────────
with st.sidebar:
    st.header("Auth Context")
    auth_state = st.selectbox("Role", ["logged_out", "member", "organiser"])
    user_city = st.selectbox("Your City", [None] + [
        "lucknow", "delhi", "bangalore", "mumbai", "pune",
        "hyderabad", "chennai", "kolkata",
    ])

ctx = RequesterContext(auth_state=auth_state, city=user_city)

# ── Search input ───────────────────────────────────────────────────────────────
query = st.text_input("Search Commudle", placeholder="e.g. Flutter developers in Lucknow")

# ── Autocomplete suggestions ──────────────────────────────────────────────────
if query and len(query) >= 2:
    suggestions = suggest(query, city=user_city)
    if suggestions:
        st.caption("Suggestions:")
        cols = st.columns(min(len(suggestions), 6))
        for i, s in enumerate(suggestions[:6]):
            with cols[i]:
                if st.button(s, key=f"sug_{i}"):
                    query = s

# ── Run search ─────────────────────────────────────────────────────────────────
if query and st.button("Search", type="primary"):
    # Stage 1 — Extraction
    intent = extract_intent(query)

    # Stage 2 — Validation
    intent, dropped = validate_intent(intent)

    if dropped:
        log_blocked_attempt(query, "fields_dropped", auth_state, dropped)

    # ── Interpreted Intent Panel ───────────────────────────────────────────
    with st.expander("📋 Interpreted Intent", expanded=True):
        st.json(intent.model_dump())
        if dropped:
            st.warning(f"Dropped fields: {dropped}")

    # ── Blocked check ─────────────────────────────────────────────────────
    if intent.entity_type == EntityType.unknown:
        log_blocked_attempt(query, "could_not_determine_entity_type", auth_state)
        st.error("⛔ **Blocked**: Could not determine what you are searching for. Try a more specific query.")
    else:
        # Compute embedding
        query_embedding = None
        model = MODEL_MAP.get(intent.entity_type.value)
        if model and hasattr(model, "embedding"):
            try:
                embed_input = intent.free_text_remainder or query[:300]
                qe = embed_text(embed_input)
                if not all(v == 0.0 for v in qe):
                    query_embedding = qe
            except Exception:
                pass

        # Stage 4 — Query
        db = SessionLocal()
        try:
            rows, data_cols = build_and_run(db, intent, ctx, query_embedding)
        except BlockedQueryError as e:
            log_blocked_attempt(query, e.reason, auth_state)
            st.error(f"⛔ **Blocked**: {e.reason}")
            rows = []
            data_cols = []
        finally:
            db.close()

        if rows:
            # Stage 5 — Ranking
            rows = rank_results(rows, query_embedding)

            st.subheader(f"Results ({len(rows)})")
            for r in rows:
                title = r.get("title") or r.get("name") or f"#{r.get('id', '?')}"
                snippet = r.get("description") or r.get("bio") or ""
                score = r.get("score", 0.0)

                with st.container():
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(f"**{title}**")
                        st.caption(snippet[:300])
                    with col2:
                        st.metric("Score", f"{score:.4f}")
                    st.divider()
        elif data_cols:
            st.info("No results found for your query.")

    # ── Web enrichment ─────────────────────────────────────────────────────
    with st.expander("🌐 Web Enrichment (External — Unverified)"):
        st.warning("⚠️ These results are from the public web and are **unverified**. URLs shown as text only.")
        web_results = safe_web_search(query)
        if web_results:
            for wr in web_results:
                st.markdown(f"**{wr['title']}**")
                st.caption(wr["snippet"])
                st.code(wr["url"], language=None)
                st.divider()
        else:
            st.info("No web results available.")
