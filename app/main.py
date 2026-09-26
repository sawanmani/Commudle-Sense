"""
app/main.py — FastAPI app + endpoints.

POST /search: guard -> extract -> validate -> embed -> query -> rank -> respond
              (+ an "other platforms" section from the external catalog).
GET  /autocomplete: safe pool suggestions.
GET  /web-enrich: DuckDuckGo enrichment (labeled external/unverified).
GET  /health: readiness check.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import date
import time
import uuid
from typing import List, Optional

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app import config
from app.autocomplete import record_successful_query, suggest
from app.external_catalog import search_external
from app.external_search import safe_web_search
from app.insights import compute_insights
from app.extraction import extract_with_source, llm_available
from app.fallback_extraction import NEAR_ME_RE
from app.guard import BLOCK_MESSAGES, check_raw_query, classify_block, normalize_query
from app.logging_utils import log_blocked_attempt
from app.models import get_engine
from app.permissions import MODEL_MAP, entity_allowed_for
from app.query_builder import BlockedQueryError, build_and_run
from app.query_builder import TIME_BOUND
from app.ranking import effective_weights, embed_text, embedder_status, rank_results, warm_up
from app.ratelimit import SlidingWindowLimiter, parse_limit, rate_limit
from app.schemas import (
    EntityType,
    SearchIntent,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from app.validation import redact_suspicious, validate_intent

REDACTED_MARK = "[content removed by safety filter]"

# ── App ────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load the embedding model in the background at start-up so no user request waits for it.
    warm_up()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Commudle Safe Natural-Language Search",
    version="1.3.0",
    description="PS-01: permission-aware NL search with injection defenses, local + other-platform results.",
)

# CORS — explicit origins only (config.CORS_ORIGINS). No wildcard, no credentials: the API
# authenticates via the request body's context, not cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

log = logging.getLogger("commudle.api")


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Server-generated request id (never trusted from the client), timing and safe default headers."""
    rid, start = uuid.uuid4().hex[:12], time.perf_counter()
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Process-Time-ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(SQLAlchemyError)
async def database_unavailable(request: Request, exc: SQLAlchemyError):
    """A DB outage must not leak driver/SQL details: log it, answer with a clean 503."""
    rid = getattr(request.state, "request_id", "-")
    log.error("database error [%s]: %s", rid, type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Search backend temporarily unavailable.", "request_id": rid},
                        headers={"Retry-After": "5"})


search_limiter = SlidingWindowLimiter(*parse_limit(config.RATE_LIMIT_SEARCH))
web_limiter = SlidingWindowLimiter(*parse_limit(config.RATE_LIMIT_WEB_ENRICH))

# ── DB session dependency ──────────────────────────────────────────────────────
# Bind to the REAL engine: a session bound to models.engine (a lazy proxy object) checks out a new pool
# connection for every query and holds them all until close — 15 queries in one request exhausted the pool.
SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


ENTITY_OPTIONS: List[str] = ["events", "speakers", "communities", "hackathons", "jobs", "labs", "projects"]


def _unanswered(intent: SearchIntent, reason: str, *, blocked: bool, question: Optional[str] = None,
                options: Optional[List[str]] = None) -> SearchResponse:
    return SearchResponse(
        results=[], blocked=blocked, block_reason=reason, interpreted_intent=intent,
        clarifying_question=question, clarification_options=options or [],
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

def _status(when) -> Optional[str]:
    try:
        d = date.fromisoformat(str(when)[:10])
    except (TypeError, ValueError):
        return None
    today = date.today()
    return "today" if d == today else "upcoming" if d > today else "past"


def _relaxations(intent: SearchIntent):
    """Broader versions of the intent to try when the exact one finds nothing (most specific first)."""
    ent = intent.entity_type.value + ("s" if not intent.entity_type.value.endswith("s") else "")
    techs = ", ".join(intent.technologies)
    if intent.date_range:
        yield "the same search at any date", intent.model_copy(update={"date_range": None})
    if intent.location:
        yield f"{techs + ' ' if techs else ''}{ent} in other cities", intent.model_copy(update={"location": None})
    if intent.spoken_in:
        yield f"{techs + ' ' if techs else ''}speakers who spoke elsewhere", intent.model_copy(update={"spoken_in": None})
    if intent.technologies and (intent.location or intent.spoken_in):
        where = (intent.location or intent.spoken_in).title()
        yield f"other {ent} in {where}", intent.model_copy(update={"technologies": []})


def _reasons(intent: SearchIntent, row: dict) -> List[str]:
    """Plain-language 'why is this here' built only from the validated intent and public columns."""
    out = []
    tags = {t.strip() for t in (row.get("tags") or "").split(",")}
    hit = [t for t in intent.technologies if t in tags or (t in ("fullstack", "full stack") and tags & {"fullstack", "full stack"})]
    if hit:
        out.append("tech: " + ", ".join(hit))
    if intent.location and row.get("city") == intent.location:
        out.append(f"in {intent.location.title()}")
    if intent.spoken_in:
        out.append(f"has spoken in {intent.spoken_in.title()}")
    if intent.date_range:
        out.append("in your date range")
    if row.get("_audience"):
        out.append("members only" if row["_audience"] == "members" else "organisers only")
    if row.get("similarity") is not None:
        out.append(f"meaning match {row['similarity']:.2f}")
    return out


def _rank(rows, query_embedding, intent: SearchIntent, entity: str):
    """Rank rows of ONE entity type; returns (rows, human-readable formula)."""
    uses_activity = any(r.get("_activity") is not None for r in rows)
    time_bound = entity in TIME_BOUND
    w = dict(w_sem=0.5, w_recency=0.3, w_activity=0.2) if uses_activity else dict(w_sem=0.6, w_recency=0.4, w_activity=0.0)
    rows = rank_results(rows, query_embedding, sort=intent.sort.value, time_bound=time_bound, **w)
    ew_sem, ew_rec, ew_act = effective_weights(rows, **w)
    time_signal = ("nearness to today" if intent.sort.value == "upcoming"
                   else "timeliness (upcoming first, sooner is better; past events below)" if time_bound else "recency")
    parts = [f"{v:.2f} x {name}" for v, name in ((ew_sem, "meaning similarity"), (ew_rec, time_signal),
                                                  (ew_act, "activity (talks given / community size)")) if v > 0]
    return rows, " + ".join(parts)


def _to_item(r: dict, entity: str, intent: SearchIntent, broadened: Optional[str] = None) -> SearchResultItem:
    """Build a result card from PUBLIC columns only; stored text is untrusted, so it is redacted."""
    time_bound = entity in TIME_BOUND
    title = r.get("title") or r.get("name") or f"{entity}#{r.get('id', '?')}"
    snippet = r.get("description") or r.get("bio") or ""
    return SearchResultItem(
        entity_type=entity,
        id=r.get("id", 0),
        title=redact_suspicious(str(title), 200),
        snippet=redact_suspicious(str(snippet), 500),
        score=r.get("score", 0.0),
        city=r.get("city"),
        date=(r.get("_date_value") or None) and str(r["_date_value"])[:10],
        date_label=(("starts" if time_bound else "last talk" if entity == "speaker" else "created")
                    if r.get("_date_value") else None),
        status=_status(r.get("_date_value")) if time_bound else None,
        tags=[t.strip() for t in (r.get("tags") or "").split(",") if t.strip()][:6],
        match_reasons=_reasons(intent, r) + ([f"broader match: {broadened}"] if broadened else []),
        audience=r.get("_audience"),
    )


ENTITY_WORD = {"event": "events", "speaker": "speakers", "community": "communities", "hackathon": "hackathons",
               "job": "jobs", "lab": "labs", "build": "projects"}
EVERYTHING_ORDER = ["event", "hackathon", "speaker", "community", "job", "lab", "build"]


def _describe(intent: SearchIntent) -> str:
    bits = [", ".join(t.title() if len(t) > 3 else t.upper() for t in intent.technologies)]
    if intent.location:
        bits.append("in " + ("Online" if intent.location == "remote" else intent.location.title()))
    if intent.spoken_in:
        bits.append(f"who spoke in {intent.spoken_in.title()}")
    return " ".join(b for b in bits if b) or "your search"


def _search_everything(db, intent: SearchIntent, ctx, query: str, body: SearchRequest, trace, notes: List[str]) -> SearchResponse:
    """No type named ("frontend", "rust in pune"): don't ask, search every type the requester may see and
    interleave the best of each. Same permission-checked builder, ranking and redaction as a normal search."""
    has_signal = bool(intent.technologies or intent.location or intent.spoken_in or intent.date_range or intent.content_type)
    if not has_signal:
        trace.add("5. Choose what to search", "nothing recognised",
                  note="No technology, city, date or type was recognised, so there is nothing safe to filter on.")
        notes.append('Nothing recognisable in that search. Try a technology, a city or a type, e.g. "flutter events in Delhi".')
        return SearchResponse(results=[], blocked=False, interpreted_intent=intent, notes=notes,
                              clarification_options=list(ENTITY_WORD.values()), trace=trace.result())

    entities = [e for e in EVERYTHING_ORDER if entity_allowed_for(e, ctx.auth_state)]
    if intent.spoken_in:
        entities = [e for e in entities if e == "speaker"]  # "spoke in" only makes sense for speakers
    if intent.location:
        entities = [e for e in entities if hasattr(MODEL_MAP[e], "city")]  # a project has no city: "in Pune" can't apply
    trace.add("5. Choose what to search", "all types",
              note="No type named, so every type you may see is searched: " + ", ".join(ENTITY_WORD[e] for e in entities) + ".")
    embedding = None
    try:
        qe = embed_text(intent.free_text_remainder or query[:300], block=False)
        embedding = None if all(v == 0.0 for v in qe) else qe
    except Exception:
        embedding = None

    per_type, found, formulas = {}, {}, {}
    for e in entities:
        ie = intent.model_copy(update={"entity_type": EntityType(e)})
        emb = embedding if hasattr(MODEL_MAP[e], "embedding") else None
        rows, _ = build_and_run(db, ie, ctx, emb, limit=10)
        rows, formulas[e] = _rank(rows, emb, ie, e)
        per_type[e] = [_to_item(r, e, ie) for r in rows]
        found[e] = len(rows)
    trace.add("6. Permission-checked SQL", "ran", per_type_rows=found,
              note="One parameterized, public-columns-only query per type (same builder as a normal search).")

    # interleave by rank: best of each type first, then second-best of each ... -> variety, not 20 of one type
    results: List[SearchResultItem] = []
    depth = max((len(v) for v in per_type.values()), default=0)
    for i in range(depth):
        for e in entities:
            if i < len(per_type.get(e, [])) and len(results) < body.limit:
                results.append(per_type[e][i])
    trace.add("7. Rank", "ok", formula="each type ranked on its own signals, then interleaved by rank", per_type=formulas)
    trace.add("8. Clean stored text", "ok", redacted_results=sum(REDACTED_MARK in (r.title, r.snippet) for r in results))

    seen, external = set(), []
    for e in entities:
        for x in search_external(intent.model_copy(update={"entity_type": EntityType(e)}), limit=4):
            if x["id"] not in seen and x["match_level"] in ("exact", "online"):
                seen.add(x["id"])
                external.append(x)
    external = sorted(external, key=lambda x: x["score"], reverse=True)[:12]
    trace.add("9. Other platforms", "ok", hits=len(external))

    with_hits = [ENTITY_WORD[e] for e in entities if found.get(e)]
    notes.append(f"Showing everything about {_describe(intent)}: " +
                 ("narrow it down below." if with_hits else "nothing matched on Commudle yet."))
    return SearchResponse(results=results, external_results=external, blocked=False, interpreted_intent=intent,
                          notes=notes, clarification_options=with_hits, trace=trace.result())


class _Trace:
    """Collects the pipeline steps for the demo's "how it worked" view. No-op unless enabled."""

    def __init__(self, enabled: bool):
        self.enabled, self.steps = enabled, []

    def add(self, stage: str, status: str, **detail) -> None:
        if self.enabled:
            self.steps.append({"stage": stage, "status": status, **detail})

    def result(self):
        return self.steps if self.enabled else None


def _blocked(intent, reason, trace, **kw):
    r = _unanswered(intent, reason, **kw)
    r.trace = trace.result()
    return r


@app.post("/search", response_model=SearchResponse, dependencies=[Depends(rate_limit(search_limiter))])
def search(body: SearchRequest, db: Session = Depends(get_db)):
    """Full search pipeline: guard → extract → validate → embed → query → rank."""
    ctx = body.context
    query = normalize_query(body.query)
    trace = _Trace(config.ENABLE_TRACE and body.debug)
    trace.add("1. Input", "info", note="Query arrives in the JSON body (never the URL).", raw=body.query[:200],
              normalized=query, requester={"auth_state": ctx.auth_state, "city": ctx.city})

    # Stage 0 — raw-query guard: nothing suspicious ever reaches the LLM, DB or web.
    reason = check_raw_query(body.query)
    if reason == "empty_query":
        trace.add("2. Safety guard", "stopped", reason="empty query")
        return _blocked(SearchIntent(), "Please type what you are looking for.", trace, blocked=False,
                        question="What would you like to find?", options=ENTITY_OPTIONS)
    if reason:
        category = classify_block(body.query)
        log_blocked_attempt(raw_query=query, reason=reason, auth_state=ctx.auth_state)
        trace.add("2. Safety guard", "BLOCKED", reason=reason, category=category,
                  note="Matched an injection / exfiltration pattern. Stopped here: no LLM call, no database, no web request.")
        r = _blocked(SearchIntent(), BLOCK_MESSAGES[category], trace, blocked=True)
        r.block_category = category
        return r
    trace.add("2. Safety guard", "passed", note="No injection, SQL or private-data pattern found after Unicode normalisation.")

    # Stage 1 — Extraction (LLM with deterministic fallback)
    intent, source = extract_with_source(query)
    trace.add("3. Understand the query", "ok", produced_by=source, raw_intent=intent.model_dump(mode="json"),
              note="The model only fills a fixed JSON schema. It has no database access.")

    # Stage 2 — Validation
    intent, dropped = validate_intent(intent)
    if dropped:
        log_blocked_attempt(raw_query=query, reason="fields_dropped", auth_state=ctx.auth_state, dropped_fields=dropped)
    trace.add("4. Validate against allow-lists", "ok" if not dropped else "dropped some fields", dropped=dropped,
              validated_intent=intent.model_dump(mode="json"),
              note="Every value must be in a closed vocabulary; anything else is removed, never widened.")

    notes: List[str] = []
    question: Optional[str] = None

    # "near me" -> the requester's city (context comes from the caller; validated against the allow-list)
    if NEAR_ME_RE.search(query) and not intent.location:
        if ctx.city and ctx.city.lower() in config.KNOWN_CITIES:
            intent.location = ctx.city.lower()
            notes.append(f"'near me' interpreted as your city: {intent.location.title()}.")
            trace.add("4b. 'Near me'", "resolved", city=intent.location)
        else:
            question = "Which city should I search near? Set your city or add it to the query (e.g. 'in Lucknow')."
            trace.add("4b. 'Near me'", "needs city")

    # No type named -> search every type instead of asking (the user wants results, not a quiz)
    if intent.entity_type == EntityType.unknown:
        return _search_everything(db, intent, ctx, query, body, trace, notes)

    # Lazily compute embedding ONLY if entity has an embedding column
    query_embedding = None
    model = MODEL_MAP.get(intent.entity_type.value)
    if model is not None and hasattr(model, "embedding"):
        try:
            qe = embed_text(intent.free_text_remainder or query[:300], block=False)  # never wait for a loading model
            query_embedding = None if all(v == 0.0 for v in qe) else qe
        except Exception:
            query_embedding = None
    if query_embedding:
        sem_note = "Your words were turned into a 384-number meaning vector (multilingual model); results are ordered by closeness in meaning."
    elif model is None or not hasattr(model, "embedding"):
        sem_note = f"{intent.entity_type.value.title()} records have no meaning vectors, so structured filters + ranking only."
    else:
        sem_note = {"loading": "Embedding model is still loading (first minute after start-up); using filters + ranking meanwhile.",
                    "not loaded": "Embedding model is still loading (first minute after start-up); using filters + ranking meanwhile.",
                    "ready": "The query's meaning vector could not be computed this time; using filters + ranking.",
                    "unavailable": "Embedding model not installed; using filters + ranking only.",
                    "disabled": "Semantic search disabled (ENABLE_EMBEDDINGS=false)."}.get(embedder_status(), "Semantic vector unavailable.")
    trace.add("5. Semantic vector", "used" if query_embedding else "skipped", note=sem_note, model_status=embedder_status())

    if intent.location and model is not None and not hasattr(model, "city"):
        notes.append(f"{intent.entity_type.value.title()} entries have no city, so the location filter was not applied.")

    # Stage 4 — Query builder
    sql_trace: dict = {}
    try:
        rows, _data_cols = build_and_run(db, intent, ctx, query_embedding, trace=sql_trace if trace.enabled else None, limit=body.limit)
    except BlockedQueryError as e:
        log_blocked_attempt(raw_query=query, reason=e.reason, auth_state=ctx.auth_state)
        trace.add("6. Database query", "BLOCKED", reason=str(e.reason))
        return _blocked(intent, str(e.reason), trace, blocked=True)
    trace.add("6. Permission-checked SQL", "ran", rows_returned=len(rows), **sql_trace,
              note="Only PUBLIC columns are selected; PRIVATE / ORGANISER_ONLY columns cannot appear. "
                   "Values are bound parameters, never pasted into the SQL text.")

    # Nothing matched exactly -> broaden step by step (never beyond the validated intent's own values),
    # and label every broadened result so it can't be mistaken for an exact match.
    broadened: Optional[str] = None
    if not rows:
        for label, relaxed in _relaxations(intent):
            rows, _ = build_and_run(db, relaxed, ctx, query_embedding, limit=body.limit)
            if rows:
                broadened = label
                notes.append(f"No exact matches, so showing {label}.")
                trace.add("6b. Broaden", "ok", showing=label, rows_returned=len(rows),
                          note="Exact filters found nothing; the same query was re-run with one filter removed.")
                break

    # Stage 5 — Ranking
    rows, formula = _rank(rows, query_embedding, intent, intent.entity_type.value)
    trace.add("7. Rank", "ok", sort=intent.sort.value, formula=formula, top_scores=[r.get("score") for r in rows[:5]])

    # Stored content is untrusted too: redact anything that looks like an injection payload.
    results = [_to_item(r, intent.entity_type.value, intent, broadened) for r in rows]
    redacted = sum(REDACTED_MARK in (it.title, it.snippet) for it in results)
    trace.add("8. Clean stored text", "ok", redacted_results=redacted,
              note="Database text is untrusted too: anything that looks like an injection is replaced.")

    # Record successful query for autocomplete popularity
    clean_query = " ".join(filter(None, [intent.entity_type.value, " ".join(intent.technologies), intent.location])).strip()
    if clean_query:
        record_successful_query(clean_query)

    # Stage 6 — Other platforms (in-memory allow-listed catalog, sanitized)
    external = search_external(intent)
    trace.add("9. Other platforms", "ok", hits=len(external),
              by_match_level={lvl: sum(1 for x in external if x["match_level"] == lvl)
                              for lvl in ("exact", "online", "relaxed_city", "relaxed_tech")},
              note="Same validated filters applied to the external catalog; links must be https on an allow-listed platform host.")

    return SearchResponse(
        results=results,
        external_results=external,
        blocked=False,
        interpreted_intent=intent,
        clarifying_question=question,
        notes=notes,
        trace=trace.result(),
    )


@app.get("/autocomplete")
def autocomplete(q: str = Query("", max_length=100), city: Optional[str] = Query(None, max_length=50)):
    """Return safe pool suggestions for the given prefix."""
    return {"suggestions": suggest(q, city=city)}


@app.get("/web-enrich", dependencies=[Depends(rate_limit(web_limiter))])
def web_enrich(q: str = Query("", min_length=1, max_length=200)):
    """DuckDuckGo web enrichment. Results labeled external/unverified. Guarded like /search."""
    if check_raw_query(q):
        log_blocked_attempt(raw_query=q, reason="web_enrich_blocked", auth_state="unknown")
        return {"results": [], "blocked": True}
    return {"results": safe_web_search(q), "blocked": False}


@app.get("/insights", dependencies=[Depends(rate_limit(web_limiter))])
def insights(db: Session = Depends(get_db)):
    """Public aggregate numbers only (counts over public columns + blocked attempts by reason)."""
    runtime = {
        "llm_extraction": "available" if llm_available() else "fallback_rules",
        "semantic_search": embedder_status(),
        "rate_limit_search": config.RATE_LIMIT_SEARCH,
    }
    return compute_insights(db, runtime)


EXTERNAL_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed", "external_platforms_dataset.csv")


@app.get("/datasets/external-platforms.csv", dependencies=[Depends(rate_limit(web_limiter))])
def external_dataset_csv():
    """The synthetic other-platforms catalog (public by design). The local dataset is NOT downloadable:
    it deliberately contains fake private fields for leak testing."""
    return FileResponse(EXTERNAL_CSV, media_type="text/csv", filename="commudle-external-platforms.csv")


@app.get("/vocabulary")
def vocabulary():
    """The closed vocabularies the search understands (handy for dropdowns / autocomplete UIs)."""
    return {"technologies": config.KNOWN_TECHNOLOGIES, "cities": config.KNOWN_CITIES, "roles": config.KNOWN_ROLES,
            "entity_types": config.KNOWN_ENTITY_TYPES, "content_types": config.KNOWN_CONTENT_TYPES}


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness: the database answers. (/health only says the process is up.)"""
    db.execute(text("SELECT 1"))  # a failure becomes the clean 503 above
    return {"ready": True, "database": "ok"}


@app.get("/health")
def health():
    """Readiness check (also reports whether the LLM path is currently usable)."""
    return {"status": "ok", "llm_extraction": "available" if llm_available() else "fallback_rules",
            "semantic_search": embedder_status()}
