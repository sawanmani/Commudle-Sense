# Architecture — Commudle Safe Natural-Language Search

## Overview

The system converts natural-language search queries (English, Hindi, Hinglish) into
permission-checked, ranked results while structurally preventing prompt injection,
SQL injection, and private data leakage.

## Pipeline (5 stages — every stage may block)

```
NL query
 → [1] extraction.py   LLM fills SearchIntent (schema-locked; extra fields rejected)
 → [2] validation.py   fuzzy-match each field to allow-list; suspicious/unmatched → DROPPED
 → [3] permissions.py  which columns may this role see (single source of truth)
 → [4] query_builder.py parameterized SELECT of ONLY allowed cols (+ cosine similarity);
                        hard-block entity_type == "unknown"
 → [5] ranking.py      score = 0.6*semantic + 0.4*recency; sort desc
 → results (+ optional DuckDuckGo enrichment, labeled external/unverified)
```

## Security Model

### Defense-in-depth (code-enforced, not prompt-enforced)

1. **Schema lock**: LLM output must conform to `SearchIntent` Pydantic model with `extra="forbid"`.
   Any invented field is rejected outright.

2. **Allow-list validation**: Every extracted field (entity_type, technologies, location, role,
   content_type) is fuzzy-matched against a closed vocabulary. Unmatched values are DROPPED.

3. **Suspicious pattern detection**: ~48 regex patterns catch SQLi, prompt injection, role
   escalation, data exfiltration, and XSS attempts. Flagged values are dropped.

4. **Permission-checked columns**: `models.py` tags every column with `PUBLIC`, `PRIVATE`, or
   `ORGANISER_ONLY`. `permissions.py` returns ONLY `PUBLIC` columns. PRIVATE/ORGANISER_ONLY
   are NEVER returned, even to organisers (search is not the analytics dashboard).

5. **Parameterized queries only**: `query_builder.py` uses SQLAlchemy Core with bound parameters.
   SQL is NEVER built via string formatting or concatenation.

6. **Fail-closed everywhere**: On any error, the system returns `unknown` / `[]` / blocked.
   Never widens access on failure.

### What the LLM can and cannot do

| Can | Cannot |
|---|---|
| Fill SearchIntent fields from allow-list values | Invent new fields (rejected by `extra="forbid"`) |
| Return entity_type from the enum | Access the database directly |
| Be treated as untrusted data | Have its output become SQL |
| Fail (→ returns `unknown`) | Cause data leakage on failure |

## Embedding Model

- **Model**: `paraphrase-multilingual-MiniLM-L12-v2` (384-dim)
- **Applied to**: Event and Speaker entities only
- **Usage**: Cosine similarity for semantic ranking (never projected to client)
- **Fallback**: If model unavailable, semantic search degrades gracefully (NULL embeddings, score=0)

## Hybrid Ranking

```
score = 0.6 * semantic_similarity + 0.4 * recency_score
```

- `semantic_similarity`: cosine similarity between query embedding and row embedding
- `recency_score`: exponential decay with 90-day half-life; future dates clamped to 1.0
