"""
app/schemas.py — Pydantic models for the search pipeline.

SearchIntent is the LLM's ONLY allowed output shape.
extra = "forbid" rejects any invented field outright.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


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
    content_type: Optional[str] = None
    sort: SortOrder = SortOrder.relevance
    free_text_remainder: Optional[str] = None  # embedding input only; never a filter

    model_config = ConfigDict(extra="forbid")


class RequesterContext(BaseModel):
    auth_state: str = "logged_out"
    user_id: Optional[int] = None
    city: Optional[str] = None


class SearchResultItem(BaseModel):
    entity_type: str
    id: int
    title: str
    snippet: str
    score: float


class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    blocked: bool = False
    block_reason: Optional[str] = None
    interpreted_intent: SearchIntent
