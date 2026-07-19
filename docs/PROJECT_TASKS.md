# GenAI Recruiter Bot — Work Breakdown & Delivery Plan

| | |
|---|---|
| **Companion to** | `docs/PROJECT_SPECIFICATION.md` v1.0 (source of truth for *what*; this document is the *when/who/how*) |
| **Version** | 1.0 |
| **Plan start** | Sunday, **19 July 2026** |
| **Target delivery** | Thursday, **6 August 2026** (v1.0 tag + live demo + eval report) |
| **Work week** | Sun–Thu (IL calendar) |
| **Tracking** | GitHub Issues + GitHub Projects board (columns: Backlog → Ready → In Progress → In Review → Done) |

---

## 0. Delivery Status Dashboard (live — update this table, not just prose, whenever a task's state changes)

Legend: ✅ done · 🟡 partial/behavioral-only gap noted · ❌ not started · ⏳ blocked

| GRB | Task | Status | Note |
|-----|------|--------|------|
| 001 | Init repo & tooling | ✅ | |
| 002 | Config & secrets | ✅ | |
| 003 | Assets in place | ✅ | |
| 004 | CLAUDE.md | ✅ | |
| 005 | CI-lite | ✅ | |
| 010 | SQLite port | ✅ | |
| 011 | ScheduleRepository | ✅ | |
| 012 | Embedding pipeline | ✅ | |
| 013 | Retrieval smoke test | ✅ | `tests/test_info_retriever.py` |
| 020 | AdvisorOutput contracts | ✅ | |
| 021 | Info Advisor | ✅ | |
| 022 | Date resolver | 🟡 | Core 4 expressions + numeric dates + a "tomorrow" typo done; still pure regex/dateutil, not the spec's LLM-assisted design — **deliberately deferred**, see CLAUDE.md 2026-07-19 note |
| 023 | Sched Advisor | ✅ | |
| 024 | Exit Advisor (prompted baseline) | ✅ | |
| 025 | Advisor integration tests | ✅ | |
| 030 | Fine-tuning dataset builder | ❌ | placeholder file only |
| 031 | Augment edge cases | ❌ | not started |
| 032 | Launch & register fine-tune job | ❌ | placeholder file only |
| 033 | Baseline comparison (fine-tuned vs prompted) | ❌ | not started — Exit Advisor always uses the prompted path |
| 040 | ConversationState | ✅ | |
| 041 | Turn graph | 🟡 | Behaviorally complete plain-Python control flow; **not** the literal `langgraph` `StateGraph` spec §3.3 mandates — discussed & declined twice, most recently 2026-07-19 |
| 042 | Main Agent prompts | ✅ | |
| 043 | Terminal chat loop (+ trace printing) | ✅ | |
| 044 | Canonical-flow verification | ✅ | `tests/verify_canonical_flows.py`, all 4 flows pass |
| 050 | Replay harness | ✅ | `tests/test_evals.ipynb`, reuses `tests/eval_replay.py`'s case-building logic |
| 051 | Metrics (accuracy, per-class P/R/F1, confusion matrix heatmap) | ✅ | `tests/test_evals.ipynb`; heatmap saved to `docs/eval_confusion_matrix.png` |
| 052 | Error analysis (miss table + written failure-pattern analysis) | ✅ | `tests/test_evals.ipynb` — 3 named failure patterns, ranked by impact |
| 053 | Tune & re-run | 🟡 | 2 tuning iterations run, before/after documented in-notebook: 31.8% → 29.5% (regression, diagnosed) → 52.3% final. **S-1's 85% not met** — honest gap analysis in notebook per spec's accepted alternative; 2 of 3 remaining patterns need a design decision (richer routing signal; sequential full-conversation replay), not another prompt patch |
| 054 | (Stretch) Ablations | ❌ | not started |
| 060 | Registration form | ✅ | `streamlit_app/streamlit_main.py`, feeds `ConversationState.registration_data` + a personalized opening greeting |
| 061 | Chat UI | ✅ | SMS-style `st.chat_message`/`st.chat_input` thread, reuses `app.graph.run_turn` verbatim (zero UI-layer logic); dev-mode action badges; `end` locks input; Reset button |
| 062 | Dev trace panel | ✅ | Sidebar, toggleable — per-turn advisor trace incl. decisions/reasons/retrieved slots+chunks |
| 063 | Deploy | 🟡 | App verified locally (real `streamlit run` boot + full AppTest-driven interaction incl. a real API call); actual Streamlit Community Cloud connection requires the user's own account/GitHub push — not something that can be done from here |
| 070 | README.md | ✅ | purpose, architecture (Mermaid turn-flow diagram), structure, setup, usage, eval results, honest "not yet deployed" note, current-status pointer |
| 071 | Final quality pass | 🟡 | `ruff check .` clean, `ruff format .` applied repo-wide (51 files, previously-drifted files now clean), stray `tmp_verify_db.py` removed, dead-code spot-check clean. Screenshots/GIF of the demo not done — needs a real browser, unavailable in this environment |
| 072 | Tag v1.0 + presentation outline | ✅ | `v1.0` tag created on commit `47da09b` (first commit of all E1-E7 work — everything had been sitting uncommitted). Presentation outline explicitly not needed, skipped per user request. |
| CORE-REV | **Core-flow revision** — booking-completion path + proactive escalation + slot rendering, target ≥75% eval accuracy | 🟡 | Ordinal/partial slot confirmation ("the second one", "Tuesday at 10 AM works") verified working live (3 independent test paths); meaningless-input guard ("f") shipped and tested. **Eval harness rebuilt to replay sequentially** (`tests/eval_replay.py --mode sequential`, default; `--mode isolated` kept for comparison), **plus divergence-artifact tagging** (raw vs. adjusted accuracy, every miss tagged GENUINE/DIVERGENCE). Current: **raw 59.1% (26/44), adjusted 72.2% (26/36)** excluding 8 divergence artifacts. A numeral-years-of-experience date-parsing bug fixed (real win). An escalation-timing guard was tried, found to regress accuracy on the full dataset (schedule recall 78.9%→31.6%), and reverted — kept as an `xfail`-marked regression test (`tests/test_scenarios.py`) documenting why. Still below the ≥75% target; the continue-vs-schedule ambiguity after qualifying-info-sharing has genuinely inconsistent ground truth for identical inputs across conversations (see CLAUDE.md) — needs a richer signal than a blanket rule, deferred. |

---

## 1. Effort & Duration Summary (the answer to "how long?")

| Scenario | Net effort | Calendar duration |
|----------|-----------|-------------------|
| **Full-time** (course sprint, ~6 focused h/day) | **~9 dev-days** | **~3 work weeks** (19 Jul → 6 Aug), incl. buffer & presentation prep |
| Part-time (evenings, ~2 h/day) | same ~55 net hours | ~5–6 calendar weeks |
| Absolute minimum (no fine-tune stretch, no ablations, local-only demo) | ~6 dev-days | ~2 weeks |

Net-effort breakdown: Bootstrap 0.5d · Data layer 1d · Advisors 2d · Fine-tuning 1d · Orchestration 2d · Evaluation 1d · UI & deploy 1d · Docs/polish 0.5d · **+15% risk buffer ≈ 1d** → **~9 days**.

The critical path is **E0 → E1 → E2 → E4 → E5**. E3 (fine-tuning) and E6 (UI) run off the critical path and can overlap.

---

## 2. Team, Roles & RACI

This is a solo project executed with **Claude Code** as the implementation pair. To work "like a real company," the single developer explicitly switches hats — never mixing them in one session:

| Role (hat) | Held by | Responsibility |
|-----------|---------|----------------|
| **Product/Spec Owner (PO)** | You | Owns the spec, approves scope changes, signs off acceptance criteria |
| **Tech Lead / Developer (DEV)** | You + Claude Code | Architecture decisions, implementation, code review of Claude Code's output |
| **ML Engineer (MLE)** | You + Claude Code | Fine-tuning dataset, training job, embeddings, model selection |
| **QA** | You | Runs acceptance checks *against the spec*, not against the code's own tests; owns the eval notebook results |
| **DevOps/Release** | You + Claude Code | Repo hygiene, secrets, Streamlit Cloud deployment, tagging |

**RACI rule of thumb:** Claude Code is *Responsible* (does the work), you are always *Accountable* (review every diff before commit), the spec is *Consulted*, the changelog is *Informed*.

---

## 3. Ways of Working (how every task is executed)

1. **One task = one branch = one PR (self-reviewed) = squash merge.** Branch naming: `feat/GRB-xxx-short-name`, `test/…`, `docs/…`. Conventional commits.
2. **Claude Code session pattern per task:** open task issue → prompt Claude Code with: *"Read docs/PROJECT_SPECIFICATION.md §<relevant> and CLAUDE.md. Plan the implementation of GRB-xxx. Do not write code yet."* → review the plan → approve → implement → Claude Code runs `pytest` + `ruff` → **you** review the diff → commit.
3. **Definition of Ready (DoR):** task has spec reference, acceptance criteria, and dependencies met.
4. **Definition of Done (DoD):** acceptance criteria pass · tests added/updated and green · `ruff` clean · no secrets in diff · issue closed with a one-line result note · CLAUDE.md updated if conventions changed.
5. **Daily log (5 min):** append to `docs/DEVLOG.md`: what moved, what's blocked, next step. This is your stand-up substitute and gold for the final presentation.
6. **Milestone review (end of each epic):** QA hat runs the epic's acceptance checklist against the spec before the board column moves to Done.
7. **Scope control:** anything not in the spec goes to a `backlog/ideas` label — never into the current milestone.

---

## 4. Timeline & Milestones (Gantt-style)

```
Week 1 (Jul 19–23)   Week 2 (Jul 26–30)   Week 3 (Aug 2–6)
Su Mo Tu We Th        Su Mo Tu We Th        Su Mo Tu We Th
E0 E1 E2 E2 E2        E3 E4 E4 E5 E5        E6 E7 BUF BUF DEMO
█  █  █  █  █         █  █  █  █  █         █  █  ░  ░  ★
```

| Milestone | Date | Gate (must be true) |
|-----------|------|---------------------|
| **M1 — Foundations** | Thu 23 Jul | Repo live, SQLite DB + Chroma index rebuildable by one command each; all three advisors pass integration fixtures |
| **M2 — Working Brain** | Wed 29 Jul | Full LangGraph turn loop works in terminal on all 4 canonical flows; fine-tuned Exit Advisor wired (or fallback documented) |
| **M3 — Proven** | Thu 30 Jul | `test_evals.ipynb` complete: accuracy ≥ 85% or gap analysis written; confusion matrix rendered |
| **M4 — Shipped** | Mon 3 Aug | Live Streamlit URL passes demo checklist; README complete |
| **M5 — Delivered** | Thu 6 Aug | v1.0 tag, presentation ready, buffer consumed or returned |

---

## 5. Epic & Task Breakdown (WBS)

Legend — **Est**: net hours · **Own**: role hat · **Dep**: blocking tasks · **AC**: acceptance criteria. Every task references its spec section.

### EPIC E0 — Repository Bootstrap  *(Sun 19 Jul, 4h)*  — Spec §12, §15

| ID | Task / Subtasks | Own | Est | Dep | Due |
|----|-----------------|-----|-----|-----|-----|
| GRB-001 | **Init repo & tooling** — git init, `.gitignore`, venv, `requirements.txt` (pinned), `ruff` config, `pytest` scaffold | DEV | 1h | — | 19 Jul |
| GRB-002 | **Config & secrets** — `app/config.py` (pydantic-settings), `.env.example`, logging setup (N-2, N-4, N-6) | DEV | 1h | 001 | 19 Jul |
| GRB-003 | **Assets in place** — copy data files to `data/raw/`, spec+flowchart+brief to `docs/` | DEV | 0.5h | 001 | 19 Jul |
| GRB-004 | **CLAUDE.md** — create from spec §15; verify Claude Code picks it up in a fresh session | DEV | 0.5h | 001 | 19 Jul |
| GRB-005 | **CI-lite (optional but impressive)** — GitHub Action: `ruff` + `pytest` on push | DevOps | 1h | 001 | 19 Jul |

**How to work:** single Claude Code session; prompt it to execute E0 as one plan. **AC:** `python -m app.main --help` runs; `pytest` and `ruff` green; first push passes CI; no secrets tracked.

### EPIC E1 — Data Layer  *(Mon 20 Jul, 6h)*  — Spec §5.5, §6, §7

| ID | Task / Subtasks | Own | Est | Dep | Due |
|----|-----------------|-----|-----|-----|-----|
| GRB-010 | **SQLite port of `db_Tech.sql`** — `db_setup.py`: schema + full-year seed (Sun+Tue–Fri, 09–17, 4 positions, pseudo-random availability); parameterize seed year (risk #4) | DEV | 2h | 002 | 20 Jul |
| GRB-011 | **ScheduleRepository** — `get_available_slots`, `book_slot`; unit tests incl. "never returns available=0" (S-3) | DEV | 1.5h | 010 | 20 Jul |
| GRB-012 | **Embedding pipeline** — `build_index.py`: PDF→chunks→OpenAI embeddings→Chroma; idempotent rebuild | MLE | 1.5h | 002 | 20 Jul |
| GRB-013 | **Retrieval smoke test** — scripted queries ("cloud platforms?", "required experience?") return the correct chunks | QA | 1h | 012 | 20 Jul |

**How to work:** two Claude Code sessions (SQL track, vector track). QA hat manually eyeballs retrieved chunks vs the PDF. **AC:** M1 gate items for data; both stores rebuildable from scratch with one command each.

### EPIC E2 — Advisors (prompted versions)  *(Tue 21 – Thu 23 Jul, 12h)*  — Spec §5.2–5.4

| ID | Task / Subtasks | Own | Est | Dep | Due |
|----|-----------------|-----|-----|-----|-----|
| GRB-020 | **AdvisorOutput contracts** — Pydantic schemas for all three advisors + structured-output parsing with retry/deterministic fallback (N-3) | DEV | 1.5h | 002 | 21 Jul |
| GRB-021 | **Info Advisor** — decision (`info_needed`/`not`), RAG retrieval (k=3–4), grounded draft answer, "steer to scheduling" behavior; prompts in `prompts.py` | DEV | 3h | 013, 020 | 21 Jul |
| GRB-022 | **Date resolver** — `resolve_relative_date(expr, now)`; unit tests with fixed `now` over: "tomorrow", "next Friday", "Monday 3 PM", "in two weeks" | DEV | 2h | 020 | 22 Jul |
| GRB-023 | **Sched Advisor** — decision (`sched`/`dont`), LangChain tools wired to repository, 3-nearest-slots proposal, `now` injected from state | DEV | 3h | 011, 022 | 22 Jul |
| GRB-024 | **Exit Advisor (prompted baseline)** — few-shot prompt built from dataset patterns (opt-out, disinterest, "stop texting") behind the Strategy interface | DEV | 1.5h | 020 | 23 Jul |
| GRB-025 | **Advisor integration tests** — fixture histories per advisor; cached/mocked LLM responses so tests are cheap & deterministic | QA | 1h | 021,023,024 | 23 Jul |

**How to work:** one Claude Code session per advisor; always start from the Output contract (GRB-020) so the Main Agent can be built against stable interfaces. **AC:** every advisor answers its fixture correctly; slots always DB-verified; parse-failure path exercised in a test.

### EPIC E3 — Exit Advisor Fine-Tuning  *(Sun 26 Jul, 6h — off critical path)*  — Spec §5.2

| ID | Task / Subtasks | Own | Est | Dep | Due |
|----|-----------------|-----|-----|-----|-----|
| GRB-030 | **Dataset builder** — conversations → JSONL (history-so-far → end/not-end); conversation-level split, zero leakage; unit tests on shapes & split integrity | MLE | 2h | 003 | 26 Jul |
| GRB-031 | **Augment edge cases** — hand-write 10–15 tricky examples (polite refusal vs. reschedule request, "I'll be in touch") | MLE | 1h | 030 | 26 Jul |
| GRB-032 | **Launch & register job** — fine-tune via OpenAI API; persist model ID to config; cost logged | MLE | 1h | 031 | 26 Jul |
| GRB-033 | **Baseline comparison** — held-out `end` recall/precision: fine-tuned vs prompted (GRB-024); pick winner via config flag | QA | 2h | 032 | 26 Jul |

**How to work:** run the training job early in the day (jobs take time); build GRB-033 while it trains. **AC:** fine-tuned model measurably beats baseline on `end` recall, or the fallback decision is documented — either outcome closes the epic (risk #2).

### EPIC E4 — Main Agent & LangGraph Orchestration  *(Mon 27 – Tue 28 Jul, 12h)*  — Spec §4, §5.1

| ID | Task / Subtasks | Own | Est | Dep | Due |
|----|-----------------|-----|-----|-----|-----|
| GRB-040 | **ConversationState** — `state.py`: history, registration data, advisor outputs this turn, consult counter, `now` | DEV | 1h | 020 | 27 Jul |
| GRB-041 | **Turn graph** — `graph.py`: implement flowchart §4 node-for-node — 3-way routing, advisor nodes, conditional data-access edges, re-consult loop, guard (max 3, R-1), single-output rule (R-4) | DEV | 4h | 040, E2 | 27 Jul |
| GRB-042 | **Main Agent prompts** — routing heuristics (§5.1) + few-shot from dataset; structured final decision `{action, message}` (R-5) | DEV | 3h | 041 | 28 Jul |
| GRB-043 | **Terminal chat loop** — `main.py`: interactive REPL with trace printing (advisors consulted, verdicts) | DEV | 1.5h | 041 | 28 Jul |
| GRB-044 | **Canonical-flow verification** — scripted runs: Q&A flow · scheduling incl. relative date · refusal→end · opt-out→end | QA | 2.5h | 042, 043 | 28 Jul |

**How to work:** implement the graph *before* polishing prompts — structure first, behavior second. Use the terminal loop for tight iteration; every prompt change re-runs GRB-044. **AC:** M2 gate; all four flows pass with correct action labels; guard trips gracefully in a forced-loop test.

### EPIC E5 — Evaluation  *(Wed 29 – Thu 30 Jul, 8h)*  — Spec §9

| ID | Task / Subtasks | Own | Est | Dep | Due |
|----|-----------------|-----|-----|-----|-----|
| GRB-050 | **Replay harness** — build (history, gold) pairs from all labeled turns; `now` = conversation `start_time_utc`; LLM cache on; temp=0 | MLE | 2h | E4 | 29 Jul |
| GRB-051 | **Metrics** — accuracy, per-class P/R/F1, 3×3 confusion-matrix heatmap | QA | 1.5h | 050 | 29 Jul |
| GRB-052 | **Error analysis** — table of every miss: history snippet, chosen vs gold, advisor trace; written failure-pattern analysis | QA | 2h | 051 | 29 Jul |
| GRB-053 | **Tune & re-run** — prompt/routing fixes driven by GRB-052; document before/after numbers | DEV | 2h | 052 | 30 Jul |
| GRB-054 | **(Stretch) Ablations** — Main-Agent-only vs full pipeline; base vs fine-tuned Exit | MLE | 1.5h* | 053 | 30 Jul |

**How to work:** the notebook must be **fully re-runnable top-to-bottom** — a grader will run it. Freeze the eval set before tuning (no peeking at test errors you then train on — respect the E3 split). **AC:** M3 gate; S-1 met (≥85%) or honest gap analysis; notebook reruns clean.

### EPIC E6 — Streamlit PoC & Deployment  *(Sun 2 Aug, 6h)*  — Spec §8

| ID | Task / Subtasks | Own | Est | Dep | Due |
|----|-----------------|-----|-----|-----|-----|
| GRB-060 | **Registration form** — entry screen per flowchart; data into ConversationState | DEV | 1h | E4 | 2 Aug |
| GRB-061 | **Chat UI** — SMS-style thread; action badge in dev mode; End action locks input; Reset button | DEV | 2h | 060 | 2 Aug |
| GRB-062 | **Dev trace panel** — sidebar showing per-turn advisor trace (the "wow" for the demo) | DEV | 1.5h | 061 | 2 Aug |
| GRB-063 | **Deploy** — Streamlit Community Cloud, `st.secrets`, demo-mode `now` pinned to seed year (risk #4) | DevOps | 1.5h | 061 | 2 Aug |

**How to work:** UI reuses the exact same graph entry point as the terminal loop — zero logic in the UI layer. **AC:** M4 gate; manual demo checklist passes on the **live URL**, not just locally.

### EPIC E7 — Documentation, Polish & Delivery  *(Mon 3 Aug, 4h)*  — Spec §14

| ID | Task / Subtasks | Own | Est | Dep | Due |
|----|-----------------|-----|-----|-----|-----|
| GRB-070 | **README.md** — purpose, install, run commands, usage, structure, architecture diagram, eval results image, live URL | DEV | 2h | E5, E6 | 3 Aug |
| GRB-071 | **Final quality pass** — `ruff` clean, dead code out, docstrings, screenshots/GIF | DEV | 1h | 070 | 3 Aug |
| GRB-072 | **Tag v1.0 + presentation outline** — architecture story, live demo script, eval numbers, ablation insight, "what I'd do next" (spec §17) | PO | 1h | 071 | 3 Aug |

**AC:** a stranger clones → installs → runs locally → understands the system from README alone. Tag pushed.

### BUFFER & DEMO PREP  *(Tue 4 – Thu 6 Aug)*

Reserved ~1.5 days for: eval-accuracy shortfall remediation, fine-tuning retries, deployment surprises, presentation rehearsal (twice, timed). If unused → pull one stretch item (ablations, CI badge, GIF walkthrough) from the `backlog/ideas` label.

---

## 6. Dependency Map (critical path in bold)

```
**E0 ──► E1 ──► E2 ──► E4 ──► E5 ──► E7 ──► M5**
              └─► E3 ────┘      └─► E6 ──┘
```

Slack: E3 has 1 day of float (fallback exists); E6 has 2 days of float (terminal demo is an acceptable worst case until M4).

---

## 7. Tracking, Reporting & Quality Gates

- **Board hygiene:** max 1 task In Progress at a time (solo WIP limit). Issues carry labels: `epic:E#`, `type:feat|test|docs`, `hat:DEV|MLE|QA`, `blocked`.
- **Weekly checkpoint (Thu):** compare board vs the Gantt; if >1 day behind on the critical path, cut from stretch items first (GRB-054 → GRB-005 → dev-panel polish), never from evaluation or the four canonical flows.
- **Quality gates (hard):** no merge with red tests · no merge with secrets · no epic closed without its AC checklist ticked by the QA hat · no prompt change after M3 without re-running the eval notebook.
- **Cost tracking:** token usage log reviewed at each milestone; alert threshold documented in DEVLOG.

---

## 8. Grading/Presentation Alignment (why this plan impresses)

The plan front-loads the hardest engineering (orchestration + eval) and produces graded artifacts continuously: a reproducible eval notebook (M3), a live demo with a visible advisor trace (M4), a DEVLOG telling the engineering story, ablations quantifying the architecture's value, and a spec→tasks→commits paper trail — exactly how a professional team ships.

---

*End of delivery plan v1.0 — update dates here if the start date shifts; effort estimates stay valid.*
