"""
app/config.py — Environment config + allow-list vocabulary.

All runtime vocabulary is defined here and is NEVER LLM/user-extensible.
"""

import os
from dotenv import load_dotenv

# override=True so .env wins over any stale OS/shell vars (see blueprint §15.2)
load_dotenv(override=True)

# ── Environment variables ──────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/commudle_safe_search",
)
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
