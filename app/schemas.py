"""
app/schemas.py — Pydantic models for the search pipeline.

SearchIntent is the LLM's ONLY allowed output shape.
extra = "forbid" rejects any invented field outright.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EntityType(str, Enum):
    community = "community"
    event = "event"
    speaker = "speaker"
    hackathon = "hackathon"
    build = "build"
    lab = "lab"
    job = "job"
    unknown = "unknown"


class SortOrder(str, Enum):
    relevance = "relevance"
    recent = "recent"
    upcoming = "upcoming"


class DateRange(BaseModel):
    from_date: Optional[str] = None
    to_date: Optional[str] = None


class SearchIntent(BaseModel):
    """The LLM's ONLY allowed output. extra='forbid' rejects invented fields."""
    entity_type: EntityType = EntityType.unknown
    technologies: List[str] = []
    location: Optional[str] = None
    date_range: Optional[DateRange] = None
    role: Optional[str] = None
    spoken_in: Optional[str] = None  # speakers who have SPOKEN at an event in this city (not their home city)
    content_type: Optional[str] = None
    sort: SortOrder = SortOrder.relevance
    free_text_remainder: Optional[str] = None  # embedding input only; never a filter

    model_config = ConfigDict(extra="forbid")


class RequesterContext(BaseModel):
    auth_state: Literal["logged_out", "member", "organiser"] = "logged_out"
    user_id: Optional[int] = None
    city: Optional[str] = None


class SearchRequest(BaseModel):
    """POST /search body. The query travels in the body, never in the URL (logs, history, proxies)."""
    query: str = Field(..., max_length=2000)
    context: RequesterContext = Field(default_factory=RequesterContext)
    limit: int = Field(20, ge=1, le=50)  # max local results
    debug: bool = False  # ask for a pipeline trace (only honoured when ENABLE_TRACE=true)


class SearchResultItem(BaseModel):
    entity_type: str
    id: int
    title: str
    snippet: str
    score: float
    # Public metadata for display (only ever copied from PUBLIC columns)
    city: Optional[str] = None
    date: Optional[str] = None
    date_label: Optional[str] = None  # "starts" / "created"
    status: Optional[str] = None  # upcoming | today | past (events, hackathons)
    tags: List[str] = []
    match_reasons: List[str] = []
    audience: Optional[str] = None  # None = public; "members" / "organisers" = restricted listing the requester may see


class ExternalResultItem(BaseModel):
    """A hit from another platform (Devfolio, Devpost, ...). Untrusted content; link is allow-listed."""
    id: str
    source_platform: str
    entity_type: str
    title: str
    snippet: str
    city: Optional[str] = None
    mode: Optional[str] = None
    start_date: Optional[str] = None
    status: Optional[str] = None
    redirect_url: str
    match_level: str  # exact | online (joinable remotely) | relaxed_city | relaxed_tech
    is_synthetic: bool = True
    score: float


class SearchResponse(BaseModel):
    results: List[SearchResultItem]            # local: Commudle database
    external_results: List[ExternalResultItem] = []  # other platforms
    blocked: bool = False
    block_reason: Optional[str] = None
    block_category: Optional[str] = None  # prompt_injection | role_escalation | sql_injection | xss | private_data
    interpreted_intent: SearchIntent
    clarifying_question: Optional[str] = None
    clarification_options: List[str] = []
    notes: List[str] = []
    trace: Optional[List[dict]] = None  # step-by-step pipeline view (demo only)
