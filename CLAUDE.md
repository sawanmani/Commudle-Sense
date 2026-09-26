# CLAUDE.md

@AGENTS.md

## Claude Code specifics
- Start by reading `AGENTS.md` (imported above) and skim `conflict.md` for this machine's port and shell quirks.
- To see what the search does with a query, run `python scripts/explain.py "<query>"` rather than guessing.
- When verifying UI changes, use `frontend/scripts/shot.mjs` and read the PNG — don't claim a UI works unseen.
- Prefer writing multi-line Python/JS edits to a scratch file and running it; inline heredocs with quotes
  fail in this shell.
- Ask a human before touching `app/models.py` / `app/permissions.py`, changing what a role can see, or
  deploying.
