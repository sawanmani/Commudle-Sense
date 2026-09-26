"""
app/models.py — SQLAlchemy tables with visibility tags.  [SACRED]

Each column carries a visibility tag in its ``info`` dict:
  PUBLIC         → {"visibility": "public"}     — returned to all roles via search
  PRIVATE        → {"visibility": "private"}    — NEVER returned through search
  ORGANISER_ONLY → {"visibility": "organiser_only"} — NEVER returned through search

DO NOT change these tags without a line-by-line human review.
"""

from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, create_engine,
)
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

from app.config import DATABASE_URL

# ── Visibility shorthands ──────────────────────────────────────────────────────
PUBLIC = {"visibility": "public"}
PRIVATE = {"visibility": "private"}
ORGANISER_ONLY = {"visibility": "organiser_only"}

Base = declarative_base()

# ── Engine (lazy singleton; avoids import-time DB connection) ──────────────────
_engine = None


def get_engine():
    """Lazily create and cache the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    return _engine


# Backward-compatible property-like access
class _EngineProxy:
    """Proxy that defers engine creation until first attribute access."""
    def __getattr__(self, name):
        return getattr(get_engine(), name)
    def __bool__(self):
        return True


engine = _EngineProxy()


# ── Tables ─────────────────────────────────────────────────────────────────────

class Community(Base):
    __tablename__ = "communities"
    id = Column(Integer, primary_key=True, info=PUBLIC)
    name = Column(String(256), nullable=False, info=PUBLIC)
    city = Column(String(128), info=PUBLIC)
    tags = Column(Text, info=PUBLIC)
    description = Column(Text, info=PUBLIC)
    member_count = Column(Integer, default=0, info=PUBLIC)
    created_at = Column(DateTime, info=PUBLIC)
    internal_notes = Column(Text, info=ORGANISER_ONLY)


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, info=PUBLIC)
    community_id = Column(Integer, info=PUBLIC)
    title = Column(String(512), nullable=False, info=PUBLIC)
    city = Column(String(128), info=PUBLIC)
    tags = Column(Text, info=PUBLIC)
    event_date = Column(Date, info=PUBLIC)
    description = Column(Text, info=PUBLIC)
    embedding = Column(Vector(384), info=PUBLIC)
    # PRIVATE — never selectable through search
    rsvp_list = Column(Text, info=PRIVATE)
    attendance_log = Column(Text, info=PRIVATE)
    form_responses = Column(Text, info=PRIVATE)
    # ORGANISER_ONLY
    organiser_analytics = Column(Text, info=ORGANISER_ONLY)


class Speaker(Base):
    __tablename__ = "speakers"
    id = Column(Integer, primary_key=True, info=PUBLIC)
    name = Column(String(256), nullable=False, info=PUBLIC)
    city = Column(String(128), info=PUBLIC)
    bio = Column(Text, info=PUBLIC)
    tags = Column(Text, info=PUBLIC)
    talks_given = Column(Integer, default=0, info=PUBLIC)
    embedding = Column(Vector(384), info=PUBLIC)
    # PRIVATE
    email = Column(String(256), info=PRIVATE)
    phone = Column(String(32), info=PRIVATE)


class Hackathon(Base):
    __tablename__ = "hackathons"
    id = Column(Integer, primary_key=True, info=PUBLIC)
    title = Column(String(512), nullable=False, info=PUBLIC)
    city = Column(String(128), info=PUBLIC)
    tags = Column(Text, info=PUBLIC)
    start_date = Column(Date, info=PUBLIC)
    description = Column(Text, info=PUBLIC)
    # PRIVATE
    registrations = Column(Text, info=PRIVATE)
    # ORGANISER_ONLY
    judging_notes = Column(Text, info=ORGANISER_ONLY)


class Build(Base):
    __tablename__ = "builds"
    id = Column(Integer, primary_key=True, info=PUBLIC)
    title = Column(String(512), nullable=False, info=PUBLIC)
    tags = Column(Text, info=PUBLIC)
    description = Column(Text, info=PUBLIC)
    author_name = Column(String(256), info=PUBLIC)
    created_at = Column(DateTime, info=PUBLIC)


class Lab(Base):
    __tablename__ = "labs"
    id = Column(Integer, primary_key=True, info=PUBLIC)
    title = Column(String(512), nullable=False, info=PUBLIC)
    tags = Column(Text, info=PUBLIC)
    city = Column(String(128), info=PUBLIC)
    description = Column(Text, info=PUBLIC)
    # PRIVATE
    draft_content = Column(Text, info=PRIVATE)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, info=PUBLIC)
    title = Column(String(512), nullable=False, info=PUBLIC)
    company = Column(String(256), info=PUBLIC)
    city = Column(String(128), info=PUBLIC)
    tags = Column(Text, info=PUBLIC)
    description = Column(Text, info=PUBLIC)
    # PRIVATE
    applicant_list = Column(Text, info=PRIVATE)


class User(Base):
    """Users table — exists for auth-context realism.
    NOT in MODEL_MAP (not a searchable entity). Do not seed for search.
    """
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, info=PUBLIC)
    display_name = Column(String(256), info=PUBLIC)
    city = Column(String(128), info=PUBLIC)
    role = Column(String(64), info=PUBLIC)
    # PRIVATE
    email = Column(String(256), info=PRIVATE)
    phone = Column(String(32), info=PRIVATE)
    private_channel_ids = Column(Text, info=PRIVATE)
