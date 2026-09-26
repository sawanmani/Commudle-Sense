"""tests/test_fuzzy.py — typo tolerance, aliases, and (most important) no false positives."""

from datetime import date

import pytest

from app.config import KNOWN_CITIES, KNOWN_CONTENT_TYPES, KNOWN_ROLES, KNOWN_TECHNOLOGIES
from app.fallback_extraction import rule_based_intent
from app.fuzzy import CITY_ALIASES, TECH_ALIASES, match_value, scan
from app.schemas import SearchIntent
from app.validation import _fuzzy_match_or_none, validate_intent

TODAY = date(2026, 9, 26)


@pytest.mark.parametrize("typo,expected", [
    ("fluter", "flutter"), ("andriod", "android"), ("pyhton", "python"), ("kubernets", "kubernetes"),
    ("blockchian", "blockchain"), ("dokcer", "docker"), ("djnago", "django"), ("reactjs", "react"),
    ("React.js", "react"), ("react native", "react-native"), ("golang", "go"), ("k8s", "kubernetes"),
    ("AI", "ml"), ("machine learning", "ml"), ("Gen AI", "genai"), ("Spring Boot", "spring"), ("full-stack", "full stack"),
])
def test_technology_typos_and_aliases(typo, expected):
    assert match_value(typo, KNOWN_TECHNOLOGIES, TECH_ALIASES) == expected


@pytest.mark.parametrize("typo,expected", [
    ("lucknw", "lucknow"), ("delhii", "delhi"), ("mumbay", "mumbai"), ("bangalor", "bangalore"),
    ("hydrabad", "hyderabad"), ("chenai", "chennai"), ("Bengaluru", "bangalore"), ("Gurugram", "gurgaon"),
    ("Bombay", "mumbai"), ("New Delhi", "delhi"), ("Pune city", "pune"), ("online", "remote"), ("दिल्ली", "delhi"),
])
def test_city_typos_and_aliases(typo, expected):
    assert match_value(typo, KNOWN_CITIES, CITY_ALIASES) == expected


@pytest.mark.parametrize("value", ["ai", "js", "june", "pun", "xyz", "rest", "reach", "zzzzzzzzz", "", "   "])
def test_short_or_unrelated_values_do_not_match_cities(value):
    assert match_value(value, KNOWN_CITIES, CITY_ALIASES) is None


def test_old_substring_false_positives_are_gone():
    # the previous WRatio scorer mapped these to mumbai / nodejs
    assert _fuzzy_match_or_none("ai", KNOWN_CITIES) is None
    assert _fuzzy_match_or_none("js", KNOWN_TECHNOLOGIES) is None


def test_ambiguous_ties_fail_closed():
    assert match_value("abcde", ["abcdx", "abcdy"]) is None


def test_results_are_always_allow_list_members():
    for v in ["fluter", "Bengaluru", "k8s", "AI", "lucknw", "pyhton", "react native", "hakathon"]:
        for allowed, aliases in ((KNOWN_TECHNOLOGIES, TECH_ALIASES), (KNOWN_CITIES, CITY_ALIASES)):
            hit = match_value(v, allowed, aliases)
            assert hit is None or hit in allowed


def test_roles_and_content_types_plural():
    assert _fuzzy_match_or_none("developers", KNOWN_ROLES) == "developer"
    assert _fuzzy_match_or_none("Workshops", KNOWN_CONTENT_TYPES) == "workshop"


def test_validation_keeps_llm_aliases_it_used_to_drop():
    clean, dropped = validate_intent(SearchIntent(entity_type="speaker", technologies=["ReactJS", "k8s"], location="Bengaluru"))
    assert clean.technologies == ["react", "kubernetes"] and clean.location == "bangalore" and dropped == []


def test_suspicious_values_still_dropped():
    assert _fuzzy_match_or_none("flutter; DROP TABLE", KNOWN_TECHNOLOGIES) is None
    assert _fuzzy_match_or_none("lucknow' OR 1=1 --", KNOWN_CITIES) is None


# Everyday words that appear in search sentences must never be "corrected" into a technology or city.
EVERYDAY = """
about above after again against all also always among another answer any area around ask away back
because become before begin being best better between big book both bring build business call came
can care case change check city class close come could country course cover create day data dear
design different does done down during each early easy either else end enough even every example
face fact family far feel few field find fine first follow food form free friend from full game
gave give goes going good great group grow hand happen hard have head hear help here high hold home
hope house idea important include inside interest just keep kind know large last late learn least
leave less level life light like line list little live local long look lose lot love made make many
market matter mean meet might mind minute money month more most move much must name near need never
new next nice night nothing now number offer office often only open order other over own page paper
part party people person place plan play point power present price problem program public question
quick quite rather ready real really reason reach remember rest result right room round rule same
school second see seem sense serve service set several share short should show side simple since
small social some something space speak special spend spring stand start state still stop story
street strong student study such sure system table take talk team tell than thank their them then
there these they thing think those though three through time today together tonight topic toward
town tree true trust turn under understand until upon user using very view visit wait walk want
watch water week well what when where which while white whole why will with within without woman
word work world would write year young your june july march april august monday friday weekend
nearby around online meetups hackathon hackathons developers speakers events communities jobs labs
""".split()


def test_everyday_words_never_fuzz_into_technologies_or_cities():
    bad = {}
    for w in EVERYDAY:
        t = match_value(w, KNOWN_TECHNOLOGIES, TECH_ALIASES)
        c = match_value(w, KNOWN_CITIES, CITY_ALIASES)
        if (t and t != w and w not in ("spring",)) or (c and w != "online"):
            bad[w] = (t, c)
    assert not bad, f"false positives: {bad}"


@pytest.mark.parametrize("query,entity,techs,city", [
    ("fluter developers in lucknw", "speaker", ["flutter"], "lucknow"),
    ("andriod events in bangalor", "event", ["android"], "bangalore"),
    ("hakathons in delhii", "hackathon", [], "delhi"),
    ("pyhton labs in mumbay", "lab", ["python"], "mumbai"),
    ("kubernets workshops in pune", "event", ["kubernetes"], "pune"),
    ("nodejs devlopers in hydrabad", "speaker", ["nodejs"], "hyderabad"),
    ("machine lerning hackathon", "hackathon", ["ml"], None),
    ("blockchian communitys", "community", ["blockchain"], None),
    ("speakrs on flutter", "speaker", ["flutter"], None),
    ("flutter speakers in Bengaluru", "speaker", ["flutter"], "bangalore"),
    ("where to go for rust meetups", "event", ["rust"], None),
])
def test_rule_extractor_survives_typos(query, entity, techs, city):
    clean, _ = validate_intent(rule_based_intent(query, TODAY))
    assert (clean.entity_type.value, clean.technologies, clean.location) == (entity, techs, city)


def test_scan_prefers_bigrams():
    assert scan("machine lerning in new delhi", KNOWN_TECHNOLOGIES, TECH_ALIASES) == ["ml"]
    assert scan("machine lerning in new delhi", KNOWN_CITIES, CITY_ALIASES) == ["delhi"]
