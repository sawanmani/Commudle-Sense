"""
scripts/launch.py — One command to run the whole demo locally.

    python scripts/launch.py              # db (docker) -> seed -> API :8000 -> React UI :5180 -> browser
    python scripts/launch.py --no-db      # use the DATABASE_URL you already have
    python scripts/launch.py --no-browser
    python scripts/launch.py --streamlit  # also start the older Streamlit demo on :8501

Ctrl-C stops everything. The LLM is optional: without GROQ_API_KEY the rule-based extractor
handles English/Hinglish/Hindi queries.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PORT = os.getenv("DB_PORT", "5433")  # 5433 so it never collides with a Postgres you already run on 5432
API_PORT, UI_PORT = os.getenv("API_PORT", "8000"), os.getenv("UI_PORT", "5180")
STREAMLIT_PORT = os.getenv("STREAMLIT_PORT", "8501")
FRONTEND = ROOT / "frontend"
# More API processes = lower tail latency under concurrent load (p95 609 ms -> 185 ms at 32 clients with 4),
# but each one holds its own copy of the embedding model (~1.2 GB RAM). 2 is plenty for a demo.
WORKERS = os.getenv("WORKERS", str(min(2, os.cpu_count() or 1)))


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, **kw)


def wait_for(url: str, seconds: int = 60) -> bool:
    import httpx
    end = time.time() + seconds
    while time.time() < end:
        try:
            r = httpx.get(url, timeout=2)
            if r.status_code == 200 and "llm_extraction" in r.text:  # our /health, not some other app's
                return True
        except Exception:
            time.sleep(1)
    return False


def wait_for_page(url: str, seconds: int = 60) -> bool:
    import httpx
    end = time.time() + seconds
    while time.time() < end:
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return True
        except Exception:
            time.sleep(1)
    return False


def main() -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "ENABLE_TRACE": os.getenv("ENABLE_TRACE", "true")}
    if not (ROOT / ".env").exists() and (ROOT / ".env.example").exists():
        shutil.copy(ROOT / ".env.example", ROOT / ".env")
        print("• created .env from .env.example (add GROQ_API_KEY for LLM extraction — optional)")

    if "--no-db" not in sys.argv:
        if not shutil.which("docker"):
            print("Docker not found. Install Docker, or run with --no-db and set DATABASE_URL.")
            return 1
        print(f"• starting Postgres+pgvector on :{DB_PORT} ...")
        env["DB_PORT"] = DB_PORT
        if run(["docker", "compose", "up", "-d", "--wait", "db"], env=env).returncode != 0:
            return 1
        env["DATABASE_URL"] = f"postgresql+psycopg2://postgres:postgres@localhost:{DB_PORT}/commudle_safe_search"

    print("• seeding local dataset (1,239 records, skipped if already loaded) ...")
    if run([sys.executable, "-m", "seed.load_dummy_dataset", "--if-empty"], env=env).returncode != 0:
        return 1

    import socket
    for port in (API_PORT, UI_PORT):
        with socket.socket() as sk:
            if sk.connect_ex(("127.0.0.1", int(port))) == 0:
                print(f"Port {port} is already in use by another program. Free it or pick another, e.g.  API_PORT=8010 UI_PORT=8511 python scripts/launch.py")
                return 1
    print(f"• API  -> http://localhost:{API_PORT}/docs   ({WORKERS} workers)")
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", API_PORT, "--workers", WORKERS], cwd=ROOT, env=env)
    if not wait_for(f"http://127.0.0.1:{API_PORT}/health"):
        api.terminate()
        print("API failed to start.")
        return 1
    procs = [api]
    npm = shutil.which("npm")
    if not npm:
        print("npm not found — install Node.js 20+ for the React UI. The API is still running.")
    else:
        if not (FRONTEND / "node_modules").exists():
            print("• installing UI dependencies (first run) ...")
            if subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND).returncode != 0:
                return 1
        # 127.0.0.1, not "localhost": on Windows "localhost" can resolve to another app on ::1 (e.g. a Docker dashboard)
        print(f"• UI   -> http://127.0.0.1:{UI_PORT}")
        ui_env = {**env, "API_TARGET": f"http://127.0.0.1:{API_PORT}"}
        procs.append(subprocess.Popen([npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", UI_PORT, "--strictPort"],
                                      cwd=FRONTEND, env=ui_env))
    if "--streamlit" in sys.argv:
        print(f"• Streamlit demo -> http://127.0.0.1:{STREAMLIT_PORT}")
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "demo/streamlit_app.py", "--server.port", STREAMLIT_PORT,
             "--server.headless", "true", "--browser.gatherUsageStats", "false"],
            cwd=ROOT, env={**env, "API_URL": f"http://127.0.0.1:{API_PORT}"}))
    if npm and wait_for_page(f"http://127.0.0.1:{UI_PORT}/") and "--no-browser" not in sys.argv:
        webbrowser.open(f"http://127.0.0.1:{UI_PORT}")
    print("\nReady. Press Ctrl-C to stop.\n")
    try:
        api.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in reversed(procs):
            p.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
