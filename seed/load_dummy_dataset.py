"""
seed/load_dummy_dataset.py — Load seed/dummy_dataset.json into Postgres.

Run: python -m seed.load_dummy_dataset [--if-empty]   (respects DATABASE_URL)
  --if-empty  skip loading when the speakers table already has rows (safe for container restarts)
Embeddings are computed for events/speakers if sentence-transformers is installed.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.models import (
    Base, engine, get_engine, Community, Event, Speaker, Hackathon, Build, Lab, Job, User,
)
from app.models_extra import RecordAudience, SpeakerTalk
from seed.seed_data import _safe_embed

TABLES = [
    ("communities", Community), ("events", Event), ("speakers", Speaker),
    ("hackathons", Hackathon), ("builds", Build), ("labs", Lab),
    ("jobs", Job), ("users", User), ("speaker_talks", SpeakerTalk),
    ("record_audience", RecordAudience),
]
DATE_COLS = {"event_date", "start_date"}
DT_COLS = {"created_at"}


def main():
    with engine.connect() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        c.commit()
    only = None  # None = load every table
    if "--if-empty" in sys.argv:
        Base.metadata.create_all(engine)
        with engine.connect() as c:
            if c.execute(text("SELECT count(*) FROM speakers")).scalar():
                # older database: backfill just the newer (additive) tables that are still empty
                only = {t for t in ("speaker_talks", "record_audience")
                        if not c.execute(text(f"SELECT count(*) FROM {t}")).scalar()}
                if not only:
                    print("database already seeded; skipping")
                    return
                print("backfilling", ", ".join(sorted(only)))
    else:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with open(os.path.join(os.path.dirname(__file__), "dummy_dataset.json"), encoding="utf-8") as f:
        data = json.load(f)

    db = sessionmaker(bind=get_engine())()  # real engine: one connection per session
    for key, model in TABLES:
        if only is not None and key not in only:
            continue
        for row in data[key]:
            row = dict(row)
            for k in row:
                if k in DATE_COLS:
                    row[k] = date.fromisoformat(row[k])
                elif k in DT_COLS:
                    row[k] = datetime.fromisoformat(row[k])
            if hasattr(model, "embedding"):
                txt = " ".join(str(row.get(k, "")) for k in ("title", "name", "bio", "description", "tags", "city"))
                row["embedding"] = _safe_embed(txt)
            db.add(model(**row))
        db.commit()
        print(f"loaded {len(data[key])} {key}")
    db.close()


if __name__ == "__main__":
    main()
