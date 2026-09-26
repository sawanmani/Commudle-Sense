"""
scripts/explain.py — Type a search, watch exactly how it is processed (in the terminal).

    python scripts/explain.py "Flutter developers in Lucknow"
    python scripts/explain.py                     # interactive: keeps asking

Shows each pipeline stage, what the extractor returned vs. what survived validation, the generated
SQL with its bound parameters, and the results. Needs the database (DATABASE_URL) like the API does.
"""

from __future__ import annotations

import json
import os
import sys

os.environ["ENABLE_TRACE"] = "true"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
COLOR = {"BLOCKED": "\033[91m", "stopped": "\033[91m", "asking": "\033[93m", "needs city": "\033[93m",
         "dropped some fields": "\033[93m", "skipped": "\033[90m"}
GREEN = "\033[92m"


def show(query: str, role: str = "member", city: str | None = None) -> None:
    client = TestClient(main.app)
    j = client.post("/search", json={"query": query, "context": {"auth_state": role, "city": city}, "debug": True}).json()
    print(f"\n{BOLD}QUERY:{RESET} {query}    {DIM}(role={role}, city={city}){RESET}\n")
    for s in j["trace"]:
        c = COLOR.get(s["status"], GREEN)
        print(f"{BOLD}{s['stage']}{RESET}  {c}[{s['status']}]{RESET}")
        if s.get("note"):
            print(f"   {DIM}{s['note']}{RESET}")
        if "produced_by" in s:
            print(f"   produced by: {s['produced_by']}")
            print(f"   extractor returned : {json.dumps({k: v for k, v in s['raw_intent'].items() if v not in (None, [], '')})}")
        if "validated_intent" in s:
            if s.get("dropped"):
                print(f"   removed            : {s['dropped']}")
            print(f"   after validation   : {json.dumps({k: v for k, v in s['validated_intent'].items() if v not in (None, [], '')})}")
        if "sql" in s:
            print(f"\n   {BOLD}SQL{RESET}")
            for line in s["sql"].splitlines():
                print(f"     {line}")
            print(f"   {BOLD}bound parameters{RESET}: {json.dumps(s.get('params', {}), default=str)}")
            print(f"   selected columns : {', '.join(s['allowed_columns'])}")
            print(f"   never selectable : {', '.join(h['column'] for h in s['hidden_columns']) or 'none'}")
            print(f"   rows returned    : {s['rows_returned']}")
        if s["stage"].startswith("7"):
            print(f"   ranking: {s['formula']}  sort={s['sort']}")
        print()
    if j["blocked"]:
        print(f"{COLOR['BLOCKED']}RESULT: blocked — {j['block_reason']}{RESET}")
    if j.get("clarifying_question"):
        print(f"{COLOR['asking']}The system asks: {j['clarifying_question']}{RESET}")
    if not j["blocked"]:
        print(f"{BOLD}📍 LOCAL ({len(j['results'])}){RESET}")
        for r in j["results"][:5]:
            print(f"   {r['score']:.2f}  {r['title']}")
        print(f"{BOLD}🌐 OTHER PLATFORMS ({len(j['external_results'])}){RESET}")
        for x in j["external_results"][:6]:
            print(f"   {x['source_platform']:11} {x['title'][:52]:52} {DIM}{x['redirect_url']}{RESET}")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        show(" ".join(sys.argv[1:]))
    else:
        while True:
            try:
                q = input("search> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if q:
                show(q)
