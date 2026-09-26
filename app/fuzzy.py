"""
app/fuzzy.py — Typo-tolerant, allow-list-only matching (shared by validation and the rule extractor).

Order of attempts for a value: exact → alias → fuzzy. Fuzzy uses Optimal String Alignment distance
(Levenshtein + adjacent transpositions, so "andriod"/"pyhton" cost 1) with a budget that grows
with word length:

    length ≤ 4 → exact / alias only   ("ai" can't become "mumbai", "june" can't become "pune")
    5–7        → 1 edit                ("fluter", "lucknw", "delhii", "mumbay")
    8+         → 2 edits               ("kubernets", "hydrabad", "blockchian")

Ties at the best distance are ambiguous → None (fail closed). Every return value is a member of
the allow-list it was matched against, so matching can correct typos but never widen access.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from rapidfuzz.distance import OSA

# ── Aliases (single source of truth) ────────────────────────────────────────────
CITY_ALIASES: Dict[str, str] = {
    "bengaluru": "bangalore", "bengalore": "bangalore", "banglore": "bangalore", "blr": "bangalore",
    "बेंगलुरु": "bangalore", "बैंगलोर": "bangalore",
    "gurugram": "gurgaon", "bombay": "mumbai", "मुंबई": "mumbai", "calcutta": "kolkata", "कोलकाता": "kolkata",
    "dilli": "delhi", "new delhi": "delhi", "ncr": "delhi", "दिल्ली": "delhi", "लखनऊ": "lucknow", "पुणे": "pune",
    "poona": "pune", "हैदराबाद": "hyderabad", "hyd": "hyderabad", "चेन्नई": "chennai", "madras": "chennai",
    "नोएडा": "noida", "जयपुर": "jaipur", "इंदौर": "indore", "अहमदाबाद": "ahmedabad", "amdavad": "ahmedabad",
    "चंडीगढ़": "chandigarh", "चंडीगढ": "chandigarh",
    "online": "remote", "virtual": "remote", "wfh": "remote", "work from home": "remote", "anywhere": "remote",
}
TECH_ALIASES: Dict[str, str] = {
    "reactjs": "react", "react.js": "react", "react js": "react",
    "react native": "react-native", "reactnative": "react-native", "rn": "react-native",
    "vuejs": "vue", "vue.js": "vue", "vue js": "vue", "angularjs": "angular",
    "node": "nodejs", "node.js": "nodejs", "node js": "nodejs",
    "golang": "go", "go lang": "go", "k8s": "kubernetes", "kube": "kubernetes",
    "amazon web services": "aws", "google cloud": "gcp",
    "ai": "ml", "machine learning": "ml", "deep learning": "ml", "artificial intelligence": "ml",
    "gen ai": "genai", "generative ai": "genai", "llm": "genai", "llms": "genai",
    "spring boot": "spring", "springboot": "spring", "swiftui": "swift", "dart": "flutter",
    "front end": "frontend", "front-end": "frontend", "back end": "backend", "back-end": "backend",
    "full-stack": "full stack", "crypto": "web3", "defi": "web3", "ci/cd": "devops", "cicd": "devops",
    "मशीन लर्निंग": "ml", "एआई": "ml", "ब्लॉकचेन": "blockchain",
}

# Real words that sit one edit away from a vocabulary term — never fuzz these.
# (Found by sweeping everyday English against the vocabularies; see tests/test_fuzzy.py.)
FUZZ_STOPWORDS = frozenset("""
reach reacts great greet rest trust must just dust gust bust crust fast past last list lost
spring sprint string strong swift shift sift drift hello help heap node nodes code mode rode
june july jane lane line pine mine nine fine dine done none tone zone bone
learn lean clean dean mean bean jean near dear gear hear year wear bear pear
delhi goes gone good gold golf full stock stack block black track
event events there their these those other about after again could would should
""".split())

_WS = re.compile(r"\s+")
_EDGE_PUNCT = re.compile(r"^[^\wऀ-ॿ]+|[^\wऀ-ॿ]+$")


def normalize(value: Optional[str]) -> str:
    """Lowercase, NFKC, collapse whitespace, strip surrounding punctuation."""
    text = unicodedata.normalize("NFKC", value or "").lower()
    text = _WS.sub(" ", text).strip()
    return _EDGE_PUNCT.sub("", text)


def edit_budget(length: int) -> int:
    if length <= 4:
        return 0
    return 1 if length <= 7 else 2


def _best(value: str, candidates: Iterable[str], budget: int) -> Optional[str]:
    """Closest candidate within `budget` edits; None if nothing close or if the best is a tie."""
    best: List[Tuple[int, str]] = []
    for cand in candidates:
        d = OSA.distance(value, cand, score_cutoff=budget)
        if d <= budget:
            best.append((d, cand))
    if not best:
        return None
    best.sort()
    if len(best) > 1 and best[0][0] == best[1][0] and best[0][1] != best[1][1]:
        return None  # ambiguous
    return best[0][1]


def match_value(
    value: Optional[str],
    allowed: Sequence[str],
    aliases: Optional[Dict[str, str]] = None,
    min_len_for_fuzzy: int = 5,
) -> Optional[str]:
    """Map a free-form value onto the allow-list, tolerating typos. Returns an allow-list member or None."""
    v = normalize(value)
    v = re.sub(r"\s+(city|district)$", "", v)  # "Pune city" → "pune"
    if not v:
        return None
    allowed_set = set(allowed)
    aliases = aliases or {}
    if v in allowed_set:
        return v
    if v in aliases and aliases[v] in allowed_set:
        return aliases[v]
    squashed = v.replace(" ", "").replace("-", "")
    for cand in allowed:  # "full-stack" / "fullstack" / "react native"
        if cand.replace(" ", "").replace("-", "") == squashed:
            return cand
    # simple plural: "hackathons" → "hackathon", "cities" → "city"
    for stem in (v[:-3] + "y" if v.endswith("ies") else None, v[:-2] if v.endswith("es") else None,
                 v[:-1] if v.endswith("s") else None):
        if stem and len(stem) >= 4 and stem in allowed_set:  # never "goes" → "go"
            return stem
    if len(v) < min_len_for_fuzzy or v in FUZZ_STOPWORDS:
        return None
    # fuzzy against the allow-list AND the alias keys (so "bengaluruu" still lands on bangalore)
    pool = {c: c for c in allowed}
    pool.update({k: t for k, t in aliases.items() if t in allowed_set})
    hit = _best(v, pool.keys(), edit_budget(len(v)))
    return pool[hit] if hit else None


# ── Token scanning for the rule-based extractor ────────────────────────────────
_TOKEN = re.compile(r"[a-z0-9ऀ-ॿ][a-z0-9.+#\-ऀ-ॿ]*")


def tokens_with_bigrams(text: str) -> List[str]:
    """Words and adjacent word pairs (for "machine lerning", "new delhi", "spring boot")."""
    words = _TOKEN.findall(normalize(text))
    return [" ".join(p) for p in zip(words, words[1:])] + words


def scan(text: str, allowed: Sequence[str], aliases: Optional[Dict[str, str]] = None,
         min_len_for_fuzzy: int = 5, min_token_len: int = 1) -> List[str]:
    """Every allow-list value found in `text`, typo-tolerant, in order of first appearance, no duplicates.

    min_token_len skips short words entirely (the rule extractor handles those with context-aware rules,
    e.g. "go" is only a technology before "meetups/jobs/…", never in "where to go").
    """
    found: List[str] = []
    used_words: set = set()
    for tok in tokens_with_bigrams(text):
        parts = tok.split(" ")
        if any(p in used_words for p in parts) or len(tok) < min_token_len:
            continue  # a bigram already claimed this word / too short to scan
        hit = match_value(tok, allowed, aliases, min_len_for_fuzzy)
        if hit:
            used_words.update(parts)
            if hit not in found:
                found.append(hit)
    return found
