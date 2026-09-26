"""
app/models_extra.py — Additive tables that are not part of the protected core schema.

SpeakerTalk links a speaker to an event they spoke at. It powers "speakers who have spoken in
<city>". It is NOT a searchable entity (not in MODEL_MAP): it is only ever used inside a
sub-select by the query builder and never projected to the client.
"""

from sqlalchemy import Column, Integer, String, UniqueConstraint

from app.models import PUBLIC, Base


class SpeakerTalk(Base):
    __tablename__ = "speaker_talks"
    id = Column(Integer, primary_key=True, autoincrement=True, info=PUBLIC)
    speaker_id = Column(Integer, nullable=False, index=True, info=PUBLIC)
    event_id = Column(Integer, nullable=False, index=True, info=PUBLIC)


class RecordAudience(Base):
    """Row-level audience for a listing. A record with no row here is public.

    audience = "members"    → hidden from logged-out visitors
               "organisers" → only organisers see it (e.g. an organiser planning meetup)
    This decides WHICH RECORDS a role can list; private FIELDS (emails, RSVPs, …) stay unselectable for
    every role regardless. Never projected to clients except as the audience label.
    """
    __tablename__ = "record_audience"
    __table_args__ = (UniqueConstraint("entity", "record_id", name="uq_record_audience"),)
    id = Column(Integer, primary_key=True, autoincrement=True, info=PUBLIC)
    entity = Column(String(32), nullable=False, index=True, info=PUBLIC)
    record_id = Column(Integer, nullable=False, index=True, info=PUBLIC)
    audience = Column(String(16), nullable=False, info=PUBLIC)
