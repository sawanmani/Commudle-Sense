"""
app/config.py — Environment config + allow-list vocabulary.

All runtime vocabulary is defined here and is NEVER LLM/user-extensible.
"""

import os
from dotenv import load_dotenv

# override=True so .env wins over any stale OS/shell vars (see blueprint §15.2)
# An explicitly exported DATABASE_URL (Docker, the launcher, CI) beats .env; everything else follows .env.
_explicit_db = os.environ.get("DATABASE_URL")
load_dotenv(override=True)
if _explicit_db:
    os.environ["DATABASE_URL"] = _explicit_db

# ── Environment variables ──────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
_RAW_DB_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/commudle_safe_search",
)
# SQLAlchemy 2.1 defaults "postgresql://" to psycopg3; this project ships psycopg2.
DATABASE_URL: str = (
    _RAW_DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    if _RAW_DB_URL.startswith("postgresql://") else _RAW_DB_URL
)
# Demo-only: return a step-by-step pipeline trace (incl. generated SQL). Off by default because it
# reveals schema details; scripts/launch.py and docker-compose switch it on for demos.
ENABLE_TRACE: bool = os.getenv("ENABLE_TRACE", "false").lower() == "true"
# Semantic search with a local multilingual embedding model (needs sentence-transformers + torch).
ENABLE_EMBEDDINGS: bool = os.getenv("ENABLE_EMBEDDINGS", "true").lower() == "true"
LLM_EXTRACTION_ENABLED: bool = os.getenv("LLM_EXTRACTION_ENABLED", "true").lower() == "true"
LLM_COOLDOWN_SECONDS: int = int(os.getenv("LLM_COOLDOWN_SECONDS", "60"))
LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "6"))
# Comma-separated list of allowed browser origins (never "*").
CORS_ORIGINS: list = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8501,http://localhost:3000").split(",") if o.strip()
]
# Optional regex for origins that change per deploy, e.g. Vercel previews: https://.*\.vercel\.app
CORS_ORIGIN_REGEX: str | None = os.getenv("CORS_ORIGIN_REGEX") or None
# "<calls>/<window seconds>" per client IP.
RATE_LIMIT_SEARCH: str = os.getenv("RATE_LIMIT_SEARCH", "30/60")
RATE_LIMIT_WEB_ENRICH: str = os.getenv("RATE_LIMIT_WEB_ENRICH", "10/60")
ENABLE_WEB_SEARCH: bool = os.getenv("ENABLE_WEB_SEARCH", "true").lower() == "true"
WEB_SEARCH_MAX_RESULTS: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
WEB_SEARCH_TIMEOUT_SECONDS: int = int(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "5"))
LOG_BLOCKED_ATTEMPTS_PATH: str = os.getenv(
    "LOG_BLOCKED_ATTEMPTS_PATH", "./logs/blocked_attempts.log"
)

# ── Allow-list vocabulary (ONLY runtime vocab; never LLM/user-extensible) ─────
KNOWN_TECHNOLOGIES = [
    "android", "kotlin", "flutter", "react", "react-native", "vue",
    "angular", "nodejs", "python", "django", "fastapi", "rust", "go",
    "devops", "kubernetes", "docker", "aws", "gcp", "ml", "genai",
    "blockchain", "web3", "ios", "swift", "java", "spring",
    "graphql", "frontend", "backend", "full stack", "fullstack",
]

KNOWN_CITIES = [
    "lucknow", "delhi", "bangalore", "mumbai", "pune", "hyderabad",
    "chennai", "kolkata", "noida", "gurgaon", "ahmedabad", "jaipur",
    "indore", "chandigarh", "remote",
]

KNOWN_ROLES = ["speaker", "organiser", "developer", "mentor", "volunteer"]

KNOWN_ENTITY_TYPES = [
    "community", "event", "speaker", "hackathon", "build", "lab", "job",
]

KNOWN_CONTENT_TYPES = ["talk", "workshop", "meetup", "conference", "project"]
