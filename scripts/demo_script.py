"""
scripts/demo_script.py — CLI demo: runs 5 normal + 5 adversarial queries.

Prints ASCII [PASS]/[FAIL] and [BLOCKED/NEUTRALIZED], a summary line,
and exits 0 only if all hold ("ALL DEFENSES HELD").

Run: python scripts/demo_script.py
"""

from __future__ import annotations

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.extraction import extract_intent
from app.validation import validate_intent, _SUSPICIOUS_RE

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "data")


def load_json(filename):
    with open(os.path.join(DATA_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    normal = load_json("normal_queries.json")
    adversarial = load_json("adversarial_queries.json")

    # Pick 5 normal + 5 adversarial
    normal_sample = normal[:5]
    adversarial_sample = adversarial[:5]

    passed = 0
    failed = 0

    print("=" * 70)
    print("  COMMUDLE SAFE SEARCH -- DEMO SCRIPT")
    print("=" * 70)

    # ── Normal queries ─────────────────────────────────────────────────────
    print("\n--- NORMAL QUERIES ---\n")
    for case in normal_sample:
        query = case["query"]
        expected = case["expect_entity"]

        intent = extract_intent(query)
        clean, dropped = validate_intent(intent)
        actual = clean.entity_type.value

        if actual == expected:
            print(f"  [PASS] {query!r}")
            print(f"         -> entity={actual}, techs={clean.technologies}, loc={clean.location}")
            passed += 1
        else:
            print(f"  [FAIL] {query!r}")
            print(f"         -> expected={expected}, got={actual}")
            failed += 1

    # ── Adversarial queries ────────────────────────────────────────────────
    print("\n--- ADVERSARIAL QUERIES ---\n")
    for case in adversarial_sample:
        query = case["query"]
        category = case["category"]

        pattern_flagged = bool(_SUSPICIOUS_RE.search(query))
        intent = extract_intent(query)
        clean, dropped = validate_intent(intent)

        if case["expect_blocked"]:
            blocked = pattern_flagged or bool(dropped) or clean.entity_type.value == "unknown"
            if blocked:
                reason = []
                if pattern_flagged:
                    reason.append("pattern_flagged")
                if dropped:
                    reason.append(f"dropped={dropped}")
                if clean.entity_type.value == "unknown":
                    reason.append("entity=unknown")
                print(f"  [BLOCKED/NEUTRALIZED] {query!r}")
                print(f"         -> category={category}, reason={', '.join(reason)}")
                passed += 1
            else:
                print(f"  [FAIL] Should be blocked: {query!r}")
                print(f"         -> category={category}, entity={clean.entity_type.value}")
                failed += 1
        else:
            if clean.entity_type.value != "unknown":
                print(f"  [PASS] (neutralized, not blocked) {query!r}")
                print(f"         -> entity={clean.entity_type.value}")
                passed += 1
            else:
                print(f"  [FAIL] Should resolve but got unknown: {query!r}")
                failed += 1

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    total = passed + failed
    if failed == 0:
        print(f"  ALL DEFENSES HELD  ({passed}/{total} passed)")
    else:
        print(f"  SOME DEFENSES FAILED  ({passed}/{total} passed, {failed} failed)")
    print("=" * 70)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
