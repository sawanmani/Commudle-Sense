"""
app/main.py — FastAPI app + endpoints.

POST /search: full pipeline (extract → validate → embed → query → rank → respond).
GET  /autocomplete: safe pool suggestions.
GET  /web-enrich: DuckDuckGo enrichment (labeled external/unverified).
GET  /health: readiness check.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL
from app.models import engine
from app.schemas import (
    RequesterContext,
    SearchIntent,
    SearchResponse,
    SearchResultItem,
    EntityType,
)
from app.extraction import extract_intent
from app.validation import validate_intent
from app.query_builder import build_and_run, BlockedQueryError
from app.ranking import rank_results, embed_text
from app.autocomplete import suggest, record_successful_query
from app.external_search import safe_web_search
from app.logging_utils import log_blocked_attempt
from app.permissions import MODEL_MAP

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Commudle Safe Natural-Language Search",
    version="1.0.0",
    description="PS-01: Permission-aware NL search with injection defenses.",
)

# CORS — allow demo/frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB session dependency ──────────────────────────────────────────────────────
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/search", response_model=SearchResponse)
def search(
    query: str,
    ctx: Optional[RequesterContext] = None,
    db: Session = Depends(get_db),
):
    """Full search pipeline: extract → validate → embed → query → rank."""
    if ctx is None:
        ctx = RequesterContext()

    # Stage 1 — Extraction
    intent = extract_intent(query)

    # Stage 2 — Validation
    intent, dropped = validate_intent(intent)

    # Log dropped fields
    if dropped:
        log_blocked_attempt(
            raw_query=query,
            reason="fields_dropped",
            auth_state=ctx.auth_state,
            dropped_fields=dropped,
        )

    # Check if entity is unknown after validation (hard block)
    if intent.entity_type == EntityType.unknown:
        log_blocked_attempt(
            raw_query=query,
            reason="could_not_determine_entity_type",
            auth_state=ctx.auth_state,
        )
        return SearchResponse(
            results=[],
            blocked=True,
            block_reason="Could not determine what you are searching for. Please try a more specific query.",
            interpreted_intent=intent,
        )

    # Lazily compute embedding ONLY if entity has an embedding column
    query_embedding = None
    model = MODEL_MAP.get(intent.entity_type.value)
    if model and hasattr(model, "embedding"):
        try:
            embed_input = intent.free_text_remainder or query[:300]
            query_embedding = embed_text(embed_input)
            # Check if it's all zeros (model unavailable)
            if all(v == 0.0 for v in query_embedding):
                query_embedding = None
        except Exception:
            query_embedding = None

    # Stage 4 — Query builder
    try:
        rows, data_cols = build_and_run(db, intent, ctx, query_embedding)
    except BlockedQueryError as e:
        log_blocked_attempt(
            raw_query=query,
            reason=e.reason,
            auth_state=ctx.auth_state,
        )
        return SearchResponse(
            results=[],
            blocked=True,
            block_reason=str(e.reason),
            interpreted_intent=intent,
        )

    # Stage 5 — Ranking
    rows = rank_results(rows, query_embedding)

    # Map to response items
    results = []
    for r in rows:
        title = r.get("title") or r.get("name") or f"{intent.entity_type.value}#{r.get('id', '?')}"
        snippet = r.get("description") or r.get("bio") or ""
        results.append(
            SearchResultItem(
                entity_type=intent.entity_type.value,
                id=r.get("id", 0),
                title=str(title),
                snippet=str(snippet)[:500],
                score=r.get("score", 0.0),
            )
        )

    # Record successful query for autocomplete popularity
    clean_query = " ".join(
        filter(None, [
            intent.entity_type.value if intent.entity_type != EntityType.unknown else None,
            " ".join(intent.technologies),
            intent.location,
        ])
    ).strip()
    if clean_query:
        record_successful_query(clean_query)

    return SearchResponse(
        results=results,
        blocked=False,
        interpreted_intent=intent,
    )


@app.get("/autocomplete")
def autocomplete(
    q: str = Query("", min_length=0),
    city: Optional[str] = None,
):
    """Return safe pool suggestions for the given prefix."""
    return {"suggestions": suggest(q, city=city)}


@app.get("/web-enrich")
def web_enrich(q: str = Query("", min_length=1)):
    """DuckDuckGo web enrichment. Results labeled external/unverified."""
    return {"results": safe_web_search(q)}


@app.get("/health")
def health():
    """Readiness check."""
    return {"status": "ok"}
