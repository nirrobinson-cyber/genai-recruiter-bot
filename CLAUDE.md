# GenAI Recruiter Bot — Claude Code Context

## What this is
Multi-agent SMS-style recruiting chatbot (Main Agent + Exit/Sched/Info advisors)
for a Python Developer role. Full spec: **docs/PROJECT_SPECIFICATION.md** — READ IT
before any non-trivial change. The turn behavior contract is **docs/one_turn_flowchart.json**
(implemented as a LangGraph state graph, spec §4). Task plan & IDs: **docs/PROJECT_TASKS.md**.

## Commands
- Run terminal chat:   `python -m app.main`   (config check: `python -m app.main --check-config`)
- Build vector index:  `python -m app.modules.embedding.build_index`   (Phase 1)
- Build SQLite DB:     `python -m app.modules.scheduling.db_setup`     (Phase 1)
- UI:                  `streamlit run streamlit_app/streamlit_main.py` (Phase 6)
- Tests:               `pytest`     Lint: `ruff check . && ruff format .`

## Hard rules
- Never commit `.env` or API keys. All constants live in `app/config.py` (from .env). Zero magic numbers in logic.
- Every LLM decision goes through a Pydantic schema (structured output; no free-text parsing). Parse failure → retry once → deterministic fallback.
- Advisors NEVER emit user-facing text; only the Main Agent talks to the user (rule R-4).
- Every advisor receives the COMPLETE chat history, never a summary (rule R-2).
- SQL is queried only when Sched Advisor rules `sched`; Chroma only when Info Advisor rules `info_needed` (rule R-3).
- Scheduling slots must be verified `available = 1` in the DB in the SAME turn they are offered (S-3, hard constraint).
- Max 3 advisor consultations per turn (guard R-1); guard trip → default `continue` + clarifying question.
- Every emitted turn carries exactly one action label: `continue` | `schedule` | `end` (rule R-5).
- "Now" for date resolution comes from `settings.now()` — never `datetime.now()` directly (demo override, risk #4).
- New logic ⇒ new/updated pytest tests in the same commit. Keep `ruff` clean.

## Workflow
Explore → Plan (show me first) → Implement → Test → Commit (conventional commits: feat/test/docs/fix).
Work task-by-task per docs/PROJECT_TASKS.md (GRB-xxx IDs); one task = one branch = one PR.
Do not skip acceptance criteria. Append a line to docs/DEVLOG.md at the end of each session.

## Current status
- ✅ Epic E0 (bootstrap) complete.
- ⏭️ Next: Epic E1 — GRB-010 (SQLite port of data/raw/db_Tech.sql) and GRB-012 (Chroma embedding pipeline).
