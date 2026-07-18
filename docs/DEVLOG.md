# DEVLOG — GenAI Recruiter Bot

## 2026-07-18 — Epic E0 (Bootstrap)
- Repo initialized per spec §12: structure, .gitignore, pinned requirements, ruff+pytest config.
- app/config.py (pydantic-settings) + .env.example + logging (GRB-002).
- Data assets copied to data/raw/ and docs/ (GRB-003).
- CLAUDE.md created (GRB-004). CI workflow added (GRB-005).
- Next: Epic E1 — SQLite port of db_Tech.sql + Chroma index.
- Known issue (Windows): installing the evaluation stack for Phase 5 (notably pandas/scikit-learn-related build dependencies for test_evals.ipynb) hit local build-tool friction on this host. The exact install error was a Meson/compiler failure during metadata build for pandas (`Compiler cl cannot compile programs.`). These packages are deferred to Phase 5 and are not needed to complete Epic E0.
