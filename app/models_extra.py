"""
app/models_extra.py — Additive tables that are not part of the protected core schema.

SpeakerTalk links a speaker to an event they spoke at. It powers "speakers who have spoken in
<city>". It is NOT a searchable entity (not in MODEL_MAP): it is only ever used inside a
sub-select by the query builder and never projected to the client.
"""

from sqlalchemy import Column, Integer

from app.models import PUBLIC, Base


class SpeakerTalk(Base):
    __tablename__ = "speaker_talks"
    id = Column(Integer, primary_key=True, autoincrement=True, info=PUBLIC)
    speaker_id = Column(Integer, nullable=False, index=True, info=PUBLIC)
    event_id = Column(Integer, nullable=False, index=True, info=PUBLIC)
