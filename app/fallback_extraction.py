"""
app/fallback_extraction.py — Deterministic rule-based NL -> SearchIntent (no network, no LLM).

Used when the LLM is disabled, rate-limited, down, or returns "unknown". Understands English,
Hinglish and Hindi (Devanagari) keywords. Only ever emits values from the allow-lists in
app/config.py, so it can't widen access. Also resolves simple relative dates ("upcoming",
"this month", "next month", "in March") against an injected `today`.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import List, Optional, Tuple

from app.config import KNOWN_CITIES, KNOWN_CONTENT_TYPES
from app.schemas import DateRange, EntityType, SearchIntent, SortOrder

# (regex, canonical technology). Multi-word / specific patterns first.
_TECH_RULES: List[Tuple[str, str]] = [
    (r"react[\s\-]?native", "react-native"),
    (r"full[\s\-]?stack", "full stack"),
    (r"front[\s\-]?end", "frontend"),
    (r"back[\s\-]?end", "backend"),
    (r"spring(\s?boot)?", "spring"),
    (r"node(\.?js)?", "nodejs"),
    (r"vue(\.?js)?", "vue"),
    (r"react(\.?js)?", "react"),
    (r"angular(js)?", "angular"),
    (r"android", "android"),
    (r"kotlin", "kotlin"),
    (r"flutter|dart", "flutter"),
    (r"ios|iphone", "ios"),
    (r"swift(ui)?", "swift"),
    (r"django", "django"),
    (r"fastapi", "fastapi"),
    (r"python", "python"),
    (r"rust", "rust"),
    (r"golang|go\s?lang|go(?=\s+(meetups?|events?|developers?|speakers?|communit|jobs?|labs?|workshops?|hackathons?|builds?|projects?))", "go"),
    (r"devops|ci/?cd", "devops"),
    (r"kubernetes|k8s", "kubernetes"),
    (r"docker|containers?", "docker"),
    (r"aws|amazon web services", "aws"),
    (r"gcp|google cloud", "gcp"),
    (r"gen\s?ai|generative ai|llms?|chatgpt", "genai"),
    (r"machine learning|deep learning|artificial intelligence|ml|ai|मशीन\s*लर्निंग|एआई", "ml"),
    (r"blockchain|ब्लॉकचेन", "blockchain"),
    (r"web\s?3|crypto|defi|nft", "web3"),
    (r"java(?!\s?script)", "java"),
    (r"graphql", "graphql"),
]

_CITY_ALIASES = {
    "bengaluru": "bangalore", "bengalore": "bangalore", "blr": "bangalore", "बेंगलुरु": "bangalore", "बैंगलोर": "bangalore",
    "gurugram": "gurgaon", "bombay": "mumbai", "मुंबई": "mumbai", "calcutta": "kolkata", "कोलकाता": "kolkata",
    "dilli": "delhi", "new delhi": "delhi", "दिल्ली": "delhi", "लखनऊ": "lucknow", "पुणे": "pune",
    "हैदराबाद": "hyderabad", "चेन्नई": "chennai", "madras": "chennai", "नोएडा": "noida", "जयपुर": "jaipur",
    "इंदौर": "indore", "अहमदाबाद": "ahmedabad", "चंडीगढ़": "chandigarh", "चंडीगढ": "chandigarh",
    "online": "remote", "virtual": "remote", "wfh": "remote", "work from home": "remote",
}

# Ordered: first match wins.
_ENTITY_RULES: List[Tuple[str, EntityType]] = [
    (r"\b(jobs?|hiring|openings?|careers?|vacanc\w+|naukri|internships?)\b|नौकरी", EntityType.job),
    (r"hackathons?|hack\s?fest|हैकथॉन", EntityType.hackathon),
    (r"\b(labs?|bootcamps?|masterclass(es)?|courses?)\b", EntityType.lab),
    (r"\b(builds?|projects?|showcase|apps? built)\b", EntityType.build),
    (r"communit(y|ies)|\b(groups?|chapters?)\b|कम्युनिटी|समुदाय", EntityType.community),
    (r"\b(speakers?|mentors?)\b|स्पीकर", EntityType.speaker),
    (r"\b(events?|meetups?|workshops?|conferences?|talks?|sessions?|summits?|webinars?)\b|कार्यक्रम|वर्कशॉप", EntityType.event),
    (r"\b(developers?|engineers?|programmers?|experts?|people|devs?)\b|डेवलपर", EntityType.speaker),
]

_CONTENT_RULES = [
    (r"\bworkshops?\b|वर्कशॉप", "workshop"),
    (r"\bmeetups?\b", "meetup"),
    (r"\bconferences?\b|\bsummits?\b", "conference"),
    (r"\btalks?\b", "talk"),
    (r"\bprojects?\b", "project"),
]
_ROLE_RULES = [
    (r"\bspeakers?\b", "speaker"), (r"\borgani[sz]ers?\b", "organiser"), (r"\bmentors?\b", "mentor"),
    (r"\bvolunteers?\b", "volunteer"), (r"\b(developers?|engineers?|devs?)\b|डेवलपर", "developer"),
]
NEAR_ME_RE = re.compile(r"near\s*me|nearby|aas\s*paas|mere\s*(aas\s*paas|paas|shehar|city)|आस\s*पास|मेरे\s*(शहर|पास)", re.I)
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})


def _find(rules, text: str):
    for pattern, value in rules:
        if re.search(pattern, text, re.I):
            return value
    return None


def _technologies(text: str) -> List[str]:
    found: List[str] = []
    for pattern, tech in _TECH_RULES:
        if re.search(rf"(?<![\w])(?:{pattern})(?![\w])", text, re.I) and tech not in found:
            # "react native" must not also yield "react"; "java script" etc.
            if tech == "react" and "react-native" in found:
                continue
            found.append(tech)
    return found


def _location(text: str) -> Optional[str]:
    low = text.lower()
    for alias, city in sorted(_CITY_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", low):
            return city
    for city in KNOWN_CITIES:
        if re.search(rf"(?<![\w]){city}(?![\w])", low):
            return city
    return None


_SPOKE_RE = re.compile(
    r"(?:have\s+|has\s+|who\s+|jo\s+)?(?:spoken|spoke|speaking|talked|presented|delivered(?:\s+talks?)?|given\s+talks?|gave\s+talks?)"
    r"\s+(?:at|in|@)\s+(?:an?\s+)?(?:events?\s+in\s+)?",
    re.I,
)


def _spoken_in(text: str) -> Optional[str]:
    """City named right after 'spoken in / spoke at / gave talks in ...'."""
    m = _SPOKE_RE.search(text)
    if m:
        return _location(text[m.end():m.end() + 40])
    # Hinglish: "<city> mein bol chuke" / "<city> me talk de chuke"
    m = re.search(r"([\wऀ-ॿ]+)\s+(?:mein|me|में)\s+(?:bol|bola|boli|talk|baat|बोल)", text, re.I)
    return _location(m.group(1)) if m else None


def _month_range(year: int, month: int) -> DateRange:
    last = calendar.monthrange(year, month)[1]
    return DateRange(from_date=date(year, month, 1).isoformat(), to_date=date(year, month, last).isoformat())


def resolve_dates(text: str, today: date) -> Tuple[Optional[DateRange], SortOrder]:
    low = text.lower()
    if re.search(r"this\s+week|is\s+hafte", low):
        start = today - timedelta(days=today.weekday())
        return DateRange(from_date=start.isoformat(), to_date=(start + timedelta(days=6)).isoformat()), SortOrder.upcoming
    if re.search(r"next\s+month|agle\s+mahine", low):
        y, m = (today.year + (today.month == 12), today.month % 12 + 1)
        return _month_range(y, m), SortOrder.upcoming
    if re.search(r"this\s+month|is\s+mahine", low):
        return _month_range(today.year, today.month), SortOrder.upcoming
    if re.search(r"last\s+month|pichle\s+mahine|past\s+month", low):
        y, m = (today.year - (today.month == 1), (today.month - 2) % 12 + 1)
        return _month_range(y, m), SortOrder.recent
    if re.search(r"this\s+year", low):
        return DateRange(from_date=date(today.year, 1, 1).isoformat(), to_date=date(today.year, 12, 31).isoformat()), SortOrder.relevance
    m = re.search(r"\b(?:in\s+)?(january|february|march|april|may|june|july|august|september|october|november|december)\b(?:\s+(20\d\d))?", low)
    if m and (m.group(0).startswith("in ") or m.group(2)):
        month = _MONTHS[m.group(1)]
        year = int(m.group(2)) if m.group(2) else (today.year if month >= today.month else today.year + 1)
        return _month_range(year, month), SortOrder.upcoming
    if re.search(r"\bupcoming\b|\bnext\b|aane\s+wal[ei]|आने\s+वाल", low):
        return DateRange(from_date=today.isoformat()), SortOrder.upcoming
    if re.search(r"\b(recent|latest|newest|new)\b|naye|नए", low):
        return None, SortOrder.recent
    return None, SortOrder.relevance


def rule_based_intent(query: str, today: Optional[date] = None) -> SearchIntent:
    """Best-effort intent for `query`; entity_type is `unknown` when nothing recognisable is found."""
    today = today or date.today()
    text = (query or "")[:500]
    entity = _find(_ENTITY_RULES, text) or EntityType.unknown
    date_range, sort = resolve_dates(text, today)
    content_type = _find(_CONTENT_RULES, text)
    location = _location(text)
    spoken = _spoken_in(text) if entity == EntityType.speaker else None
    if spoken and location == spoken:
        location = None  # "spoken in Lucknow" is about where they spoke, not where they live
    return SearchIntent(
        entity_type=entity,
        technologies=_technologies(text),
        location=location,
        spoken_in=spoken,
        date_range=date_range,
        role=_find(_ROLE_RULES, text),
        content_type=content_type if content_type in KNOWN_CONTENT_TYPES else None,
        sort=sort,
        free_text_remainder=text.strip() or None,
    )
