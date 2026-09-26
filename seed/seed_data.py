"""
seed/seed_data.py — Synthetic data for all 7 searchable entities + embeddings.

Uses Faker(en_IN) for fictitious-only data.
Private/organiser columns get sentinel strings so tests can prove they never leak.
Embeddings are set on Event & Speaker rows (try/except: graceful if model missing).

Run: python -m seed.seed_data
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, date

from faker import Faker
from sqlalchemy.orm import Session, sessionmaker

from app.config import KNOWN_TECHNOLOGIES, KNOWN_CITIES, KNOWN_CONTENT_TYPES
from app.models import (
    Base, engine,
    Community, Event, Speaker, Hackathon, Build, Lab, Job,
)

fake = Faker("en_IN")
Faker.seed(42)
random.seed(42)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# ── Safe embedding helper ─────────────────────────────────────────────────────
_embed_fn = None

def _safe_embed(text: str):
    """Embed text; returns None if sentence-transformers/torch unavailable."""
    global _embed_fn
    if _embed_fn is False:
        return None
    if _embed_fn is None:
        try:
            from app.ranking import embed_text
            _embed_fn = embed_text
        except Exception:
            _embed_fn = False
            return None
    try:
        vec = _embed_fn(text)
        # Check for zero vector (model unavailable)
        if all(v == 0.0 for v in vec):
            return None
        return vec
    except Exception:
        return None


def _pick_techs(n=None):
    """Pick 1-3 random techs."""
    if n is None:
        n = random.randint(1, 3)
    return random.sample(KNOWN_TECHNOLOGIES, min(n, len(KNOWN_TECHNOLOGIES)))


def _pick_city():
    return random.choice(KNOWN_CITIES)


def _pick_content_type():
    return random.choice(KNOWN_CONTENT_TYPES)


PRIVATE_SENTINEL = "PRIVATE -- never expose via search"
ORGANISER_SENTINEL = "ORGANISER_ONLY -- never expose via search"


def seed_communities(db: Session, count: int = 20):
    print(f"  Seeding {count} communities...")
    for i in range(count):
        techs = _pick_techs()
        city = _pick_city()
        db.add(Community(
            name=f"{' & '.join(t.title() for t in techs)} Community {city.title()} #{i+1}",
            city=city,
            tags=", ".join(techs),
            description=f"A vibrant community for {', '.join(techs)} enthusiasts in {city.title()}. {fake.sentence()}",
            member_count=random.randint(50, 5000),
            created_at=datetime.now() - timedelta(days=random.randint(30, 1000)),
            internal_notes=ORGANISER_SENTINEL,
        ))
    db.flush()


def seed_speakers(db: Session, count: int = 60):
    print(f"  Seeding {count} speakers...")
    for i in range(count):
        techs = _pick_techs()
        city = _pick_city()
        bio = f"Expert in {', '.join(techs)}. {fake.sentence()}"
        embed_text = f"{' '.join(techs)} {bio} {city}"
        db.add(Speaker(
            name=fake.name(),
            city=city,
            bio=bio,
            tags=", ".join(techs),
            talks_given=random.randint(0, 50),
            embedding=_safe_embed(embed_text),
            email=PRIVATE_SENTINEL,
            phone=PRIVATE_SENTINEL,
        ))
    db.flush()


def seed_events(db: Session, count: int = 80):
    print(f"  Seeding {count} events...")
    for i in range(count):
        techs = _pick_techs()
        city = _pick_city()
        ct = _pick_content_type()
        title = f"{techs[0].title()} {ct.title()} #{i+1}"
        desc = f"A {ct} about {', '.join(techs)} in {city.title()}. {fake.sentence()}"
        embed_text = f"{title} {desc} {city}"
        db.add(Event(
            community_id=random.randint(1, 20),
            title=title,
            city=city,
            tags=", ".join(techs),
            event_date=date.today() + timedelta(days=random.randint(-180, 180)),
            description=desc,
            embedding=_safe_embed(embed_text),
            rsvp_list=PRIVATE_SENTINEL,
            attendance_log=PRIVATE_SENTINEL,
            form_responses=PRIVATE_SENTINEL,
            organiser_analytics=ORGANISER_SENTINEL,
        ))
    db.flush()


def seed_hackathons(db: Session, count: int = 15):
    print(f"  Seeding {count} hackathons...")
    for i in range(count):
        techs = _pick_techs()
        city = _pick_city()
        db.add(Hackathon(
            title=f"{techs[0].title()} Hackathon {city.title()} #{i+1}",
            city=city,
            tags=", ".join(techs),
            start_date=date.today() + timedelta(days=random.randint(-60, 120)),
            description=f"A hackathon focused on {', '.join(techs)} in {city.title()}. {fake.sentence()}",
            registrations=PRIVATE_SENTINEL,
            judging_notes=ORGANISER_SENTINEL,
        ))
    db.flush()


def seed_builds(db: Session, count: int = 40):
    print(f"  Seeding {count} builds...")
    for i in range(count):
        techs = _pick_techs()
        db.add(Build(
            title=f"{techs[0].title()} Build Project #{i+1}",
            tags=", ".join(techs),
            description=f"An open-source project using {', '.join(techs)}. {fake.sentence()}",
            author_name=fake.name(),
            created_at=datetime.now() - timedelta(days=random.randint(1, 365)),
        ))
    db.flush()


def seed_labs(db: Session, count: int = 15):
    print(f"  Seeding {count} labs...")
    for i in range(count):
        techs = _pick_techs()
        city = _pick_city()
        db.add(Lab(
            title=f"{techs[0].title()} Lab #{i+1}",
            tags=", ".join(techs),
            city=city,
            description=f"Hands-on lab for {', '.join(techs)} in {city.title()}. {fake.sentence()}",
            draft_content=PRIVATE_SENTINEL,
        ))
    db.flush()


def seed_jobs(db: Session, count: int = 25):
    print(f"  Seeding {count} jobs...")
    for i in range(count):
        techs = _pick_techs()
        city = _pick_city()
        db.add(Job(
            title=f"{techs[0].title()} Developer - {fake.company()}",
            company=fake.company(),
            city=city,
            tags=", ".join(techs),
            description=f"We are hiring {', '.join(techs)} developers in {city.title()}. {fake.sentence()}",
            applicant_list=PRIVATE_SENTINEL,
        ))
    db.flush()


def main():
    print("Creating tables...")
    Base.metadata.create_all(engine)

    print("Seeding data...")
    db = SessionLocal()
    try:
        # Clear existing data
        for model in [Job, Lab, Build, Hackathon, Event, Speaker, Community]:
            db.query(model).delete()
        db.commit()

        seed_communities(db)
        seed_speakers(db)
        seed_events(db)
        seed_hackathons(db)
        seed_builds(db)
        seed_labs(db)
        seed_jobs(db)

        db.commit()
        print("Seeding complete!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
