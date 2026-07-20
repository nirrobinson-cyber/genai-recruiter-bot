# Acceptance Report — GenAI Recruiter Bot

Generated 2026-07-20. Every number below is from a fresh run against the current working tree
(commit `a84d44d`), not copied from prior docs — see "Notable finding" for one place where that
matters.

---

## 1. Git history (`git log --oneline -30`)

Repo has 6 commits total (fewer than 30 exist):

```
a84d44d feat: Epic E3 — Exit Advisor fine-tuning (GRB-030..033)
87ffce2 fix: stop re-offering rejected scheduling slots (infinite loop)
47da09b feat: v1.0 — full multi-agent recruiter bot (Epics E1-E7)
d1a80ba docs: log Windows dependency friction (deferred to Phase 5)
167b341 docs: add delivery plan (PROJECT_TASKS.md)
f402bfe feat: bootstrap repository — Epic E0 (GRB-001..005)
```

## 2. `git status` — nothing uncommitted or lost

```
On branch main
Untracked files:
  .claude/   (local tooling config, never part of the repo)
```

Working tree is clean. `.claude/` is the only untracked path and is intentionally not part of
this project (Claude Code's own local settings directory).

## 3. Delivery status dashboard (`docs/PROJECT_TASKS.md` §0, full contents)

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
| 030 | Fine-tuning dataset builder | ✅ | conversation-level split, no leakage; real run: 47 train / 10 val |
| 031 | Augment edge cases | ✅ | 13 hand-written examples, train-only |
| 032 | Launch & register fine-tune job | ✅ | fully implemented + tested; real launch attempted and blocked — OpenAI 403 `training_not_available` (org-wide fine-tuning platform deprecation, not a code/quota issue) |
| 033 | Baseline comparison (fine-tuned vs prompted) | 🟡 | prompted-only comparison run for real (end: P=0.50 R=0.33 F1=0.40, n=10 val); fine-tuned row can't be produced on this account — accepted per user, Exit Advisor stays on the prompted path |
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
| CORE-REV | **Core-flow revision** — booking-completion path + proactive escalation + slot rendering, target ≥75% eval accuracy | 🟡 | Ordinal/partial slot confirmation ("the second one", "Tuesday at 10 AM works") verified working live (3 independent test paths); meaningless-input guard ("f") shipped and tested. **Eval harness rebuilt to replay sequentially** (`tests/eval_replay.py --mode sequential`, default; `--mode isolated` kept for comparison), **plus divergence-artifact tagging** (raw vs. adjusted accuracy, every miss tagged GENUINE/DIVERGENCE). A numeral-years-of-experience date-parsing bug fixed (real win). An escalation-timing guard was tried, found to regress accuracy on the full dataset, and reverted — kept as an `xfail`-marked regression test (`tests/test_scenarios.py`) documenting why. Still below the ≥75% target — see the fresh accuracy numbers in §5 below, which differ from earlier docs; explained there. |

## 4. Full test run (`pytest -v`, 121 individual test names) + `ruff check .`

Command: `pytest -v -m "not real_api"` (the default suite; real-API scenario tests in
`tests/test_scenarios.py` are excluded by design and run separately via `pytest -m real_api`).

**Result: 121 passed, 0 failed, 8 deselected, in 18.22s.**

```
tests/test_compare.py::test_metrics_computes_precision_recall_f1 PASSED
tests/test_compare.py::test_metrics_handles_no_predictions_for_a_class PASSED
tests/test_compare.py::test_load_val_examples_strips_system_and_target PASSED
tests/test_compare.py::test_compare_models_skips_fine_tuned_when_not_configured PASSED
tests/test_date_resolver.py::test_tomorrow PASSED
tests/test_date_resolver.py::test_next_friday PASSED
tests/test_date_resolver.py::test_monday_at_3_pm PASSED
tests/test_date_resolver.py::test_in_two_weeks PASSED
tests/test_date_resolver.py::test_next_weekday_on_the_same_weekday_rolls_to_next_week PASSED
tests/test_date_resolver.py::test_month_and_year_resolves_to_tight_month_range PASSED
tests/test_date_resolver.py::test_month_and_year_full_range_when_month_is_entirely_future PASSED
tests/test_date_resolver.py::test_month_without_year_uses_current_year PASSED
tests/test_date_resolver.py::test_month_without_year_rolls_to_next_year_if_already_passed PASSED
tests/test_date_resolver.py::test_unrecognized_expression_returns_none_not_tomorrow PASSED
tests/test_date_resolver.py::test_numeric_date_d_m_yy_is_day_first PASSED
tests/test_date_resolver.py::test_numeric_date_dd_mm_yyyy PASSED
tests/test_date_resolver.py::test_numeric_date_future_day_not_clamped PASSED
tests/test_date_resolver.py::test_numeric_date_invalid_returns_none PASSED
tests/test_date_resolver.py::test_tomorrow_typo_tomororw PASSED
tests/test_date_resolver.py::test_tomorrow_typo_tommorow PASSED
tests/test_date_resolver.py::test_today_is_not_confused_with_tomorrow PASSED
tests/test_date_resolver.py::test_default_forward_window_starts_tomorrow PASSED
tests/test_date_resolver.py::test_default_forward_window_advances_past_after_date PASSED
tests/test_date_resolver.py::test_default_forward_window_after_in_the_past_still_clamps_to_tomorrow PASSED
tests/test_embedding_build_index.py::test_build_index_creates_collection PASSED
tests/test_embedding_build_index.py::test_build_index_uses_role_summary_for_broken_pdf PASSED
tests/test_embedding_build_index.py::test_build_index_reads_zip_manifest_bundle PASSED
tests/test_eval_replay_cases.py::test_total_evaluable_cases_across_dataset PASSED
tests/test_eval_replay_cases.py::test_conversation_opener_is_excluded PASSED
tests/test_eval_replay_cases.py::test_known_case_shape_matches_conversation_one_turn_three PASSED
tests/test_eval_replay_cases.py::test_history_prefix_never_includes_trigger_or_labeled_turn PASSED
tests/test_eval_replay_cases.py::test_sequential_total_evaluable_cases_matches_isolated_mode PASSED
tests/test_eval_replay_cases.py::test_sequential_anchor_shape_matches_conversation_one_turn_three PASSED
tests/test_eval_replay_cases.py::test_sequential_every_anchor_points_at_a_candidate_turn PASSED
tests/test_eval_replay_cases.py::test_sequential_gold_matches_the_immediately_following_recruiter_turn PASSED
tests/test_eval_replay_cases.py::test_sequential_anchor_carries_dataset_last_action PASSED
tests/test_eval_replay_cases.py::test_mentions_weekday_and_time PASSED
tests/test_eval_replay_cases.py::test_matches_any_offered_slot_by_weekday_or_time PASSED
tests/test_eval_replay_cases.py::test_divergence_artifact_when_trajectory_already_diverged PASSED
tests/test_eval_replay_cases.py::test_divergence_artifact_when_confirmation_does_not_match_our_offer PASSED
tests/test_eval_replay_cases.py::test_not_divergence_when_trajectory_matches_and_offer_matches PASSED
tests/test_eval_replay_cases.py::test_divergence_artifact_uses_pending_offer_not_literal_last_action PASSED
tests/test_eval_replay_cases.py::test_not_divergence_on_the_very_first_candidate_turn PASSED
tests/test_eval_replay_cases.py::test_not_divergence_for_a_non_confirmation_message_with_matching_trajectory PASSED
tests/test_exit_advisor.py::test_decide_returns_llm_result PASSED
tests/test_exit_advisor.py::test_decide_falls_back_when_llm_call_fails PASSED
tests/test_fine_tuning_dataset.py::test_label_mapping PASSED
tests/test_fine_tuning_dataset.py::test_split_has_no_conversation_overlap PASSED
tests/test_fine_tuning_dataset.py::test_build_dataset_splits_are_nonempty_and_stratified PASSED
tests/test_fine_tuning_dataset.py::test_hand_written_examples_are_train_only PASSED
tests/test_fine_tuning_dataset.py::test_write_jsonl_produces_valid_lines PASSED
tests/test_fine_tuning_dataset.py::test_real_dataset_builds_without_leakage PASSED
tests/test_graph.py::test_run_turn_handles_info_question PASSED
tests/test_graph.py::test_run_turn_handles_schedule_request PASSED
tests/test_graph.py::test_run_turn_next_friday_routes_to_sched_not_info PASSED
tests/test_graph.py::test_run_turn_after_slot_offer_ambiguous_reply_prefers_sched_over_info_decline PASSED
tests/test_graph.py::test_run_turn_after_slot_offer_ambiguous_reply_restates_the_actual_offered_slots PASSED
tests/test_graph.py::test_run_turn_second_consecutive_continue_still_restates_offered_slots PASSED
tests/test_graph.py::test_run_turn_now_override_reaches_sched_advisor PASSED
tests/test_graph.py::test_run_turn_sched_confirmed_ends_with_booking_message PASSED
tests/test_graph.py::test_run_turn_sets_qualifying_info_shared_and_threads_it_to_next_routing_call PASSED
tests/test_graph.py::test_run_turn_sched_routed_but_advisor_says_dont_sched PASSED
tests/test_graph.py::test_run_turn_handles_exit_request PASSED
tests/test_graph.py::test_run_turn_exit_routed_but_advisor_says_dont_end PASSED
tests/test_graph.py::test_run_turn_keeps_state_across_turns PASSED
tests/test_graph.py::test_run_turn_second_info_question_nudges_towards_scheduling PASSED
tests/test_graph.py::test_run_turn_returns_a_per_advisor_trace PASSED
tests/test_graph.py::test_run_turn_meaningless_input_skips_advisors_and_asks_to_clarify PASSED
tests/test_graph.py::test_run_turn_meaningless_input_variants[] PASSED
tests/test_graph.py::test_run_turn_meaningless_input_variants[   ] PASSED
tests/test_graph.py::test_run_turn_meaningless_input_variants[x] PASSED
tests/test_graph.py::test_run_turn_meaningless_input_variants[zz] PASSED
tests/test_graph.py::test_run_turn_short_but_meaningful_input_still_reaches_an_advisor[5] PASSED
tests/test_graph.py::test_run_turn_short_but_meaningful_input_still_reaches_an_advisor[ok] PASSED
tests/test_graph.py::test_run_turn_short_but_meaningful_input_still_reaches_an_advisor[no] PASSED
tests/test_graph.py::test_run_turn_short_but_meaningful_input_still_reaches_an_advisor[yes] PASSED
tests/test_graph.py::test_run_turn_guard_stops_loop_after_limit PASSED
tests/test_graph.py::test_run_turn_guard_does_not_trip_across_separate_messages PASSED
tests/test_graph.py::test_run_turn_respects_re_consult_guard_within_a_single_turn PASSED
tests/test_info_advisor.py::test_draft_answer_returns_llm_result_when_context_found PASSED
tests/test_info_advisor.py::test_draft_answer_falls_back_to_heuristic_when_llm_call_fails PASSED
tests/test_info_advisor.py::test_draft_answer_fallback_when_no_context_and_llm_fails PASSED
tests/test_info_retriever.py::test_retrieve_context_returns_relevant_chunks PASSED
tests/test_launch_job.py::test_launch_uploads_files_and_creates_job PASSED
tests/test_launch_job.py::test_check_status_surfaces_fine_tuned_model_when_succeeded PASSED
tests/test_llm_client.py::test_identical_calls_hit_the_cache_not_the_client PASSED
tests/test_llm_client.py::test_different_messages_are_not_cached_together PASSED
tests/test_main.py::test_settings_load_with_defaults PASSED
tests/test_main.py::test_settings_singleton PASSED
tests/test_main.py::test_demo_now_override_parsing PASSED
tests/test_main.py::test_cli_parser_builds PASSED
tests/test_main_agent.py::test_route_returns_llm_result PASSED
tests/test_main_agent.py::test_route_passes_last_action_through_to_the_llm_call PASSED
tests/test_main_agent.py::test_route_passes_maturity_signals_through_to_the_llm_call PASSED
tests/test_main_agent.py::test_route_falls_back_when_llm_call_fails PASSED
tests/test_sched_advisor.py::test_years_of_experience_with_a_numeral_is_not_a_date_attempt[Yes, 3 years' experience] PASSED
tests/test_sched_advisor.py::test_years_of_experience_with_a_numeral_is_not_a_date_attempt[I have 5 years of experience] PASSED
tests/test_sched_advisor.py::test_years_of_experience_with_a_numeral_is_not_a_date_attempt[3 years] PASSED
tests/test_sched_advisor.py::test_years_of_experience_with_a_numeral_is_not_a_date_attempt[5+ years in Python] PASSED
tests/test_sched_advisor.py::test_real_date_or_time_attempts_are_still_detected[14/4/24] PASSED
tests/test_sched_advisor.py::test_real_date_or_time_attempts_are_still_detected[Monday at 3 PM is good.] PASSED
tests/test_sched_advisor.py::test_real_date_or_time_attempts_are_still_detected[the 14th works] PASSED
tests/test_sched_advisor.py::test_real_date_or_time_attempts_are_still_detected[10am works for me] PASSED
tests/test_sched_advisor.py::test_decide_dont_sched_never_touches_db PASSED
tests/test_sched_advisor.py::test_decide_sched_overwrites_llm_slots_with_verified_db_slots PASSED
tests/test_sched_advisor.py::test_decide_sched_with_garbled_date_attempt_asks_to_clarify_and_never_touches_db PASSED
tests/test_sched_advisor.py::test_decide_sched_with_no_date_named_defaults_to_nearest_available_slots PASSED
tests/test_sched_advisor.py::test_decide_rejection_with_no_date_advances_past_previously_offered_slots PASSED
tests/test_sched_advisor.py::test_decide_sched_with_no_further_slots_after_exclusion_reports_empty PASSED
tests/test_sched_advisor.py::test_decide_falls_back_when_llm_call_fails PASSED
tests/test_sched_advisor.py::test_decide_confirmed_books_the_matched_slot PASSED
tests/test_sched_advisor.py::test_decide_confirmed_id_not_in_offered_slots_is_not_trusted PASSED
tests/test_sched_advisor.py::test_decide_confirmed_but_slot_no_longer_available PASSED
tests/test_scheduling_repository.py::test_repository_returns_only_available_slots PASSED
tests/test_scheduling_repository.py::test_booking_marks_slot_unavailable PASSED
tests/test_schemas.py::test_main_agent_output_rejects_invalid_action PASSED
tests/test_schemas.py::test_main_agent_output_defaults PASSED
tests/test_schemas.py::test_info_advisor_output_allows_null_draft_answer PASSED
tests/test_structured_output.py::test_returns_call_result_on_first_success PASSED
tests/test_structured_output.py::test_retries_once_then_succeeds PASSED
tests/test_structured_output.py::test_falls_back_after_two_failures PASSED
```

`ruff check .`: **All checks passed!** — `ruff format --check .`: **55 files already formatted.**

## 5. Real eval run (`python -m tests.eval_replay`) — final accuracy, and a notable finding

```
=== mode: sequential ===
Raw accuracy (all misses count): 24/44 (54.5%)
  continue: 4/10 (40.0%)
  schedule: 14/19 (73.7%)
  end: 6/15 (40.0%)

Adjusted accuracy (excluding 10 divergence-artifact misses):
Adjusted: 24/34 (70.6%)
  continue: 4/8 (50.0%)
  schedule: 14/19 (73.7%)
  end: 6/7 (85.7%)
```

**Notable finding — this run's numbers differ from what's currently written in `README.md` /
`CLAUDE.md` (59.1% raw / 72.2% adjusted).** That documented figure was captured on 2026-07-19,
*before* this session's `87ffce2` commit (the fix for rejected-slots-being-re-offered), which
touched `app/graph.py`, `sched_advisor/advisor.py`, `date_resolver.py`, and
`main_agent/prompts.py`. `eval_replay.py`'s sequential mode walks one real `ConversationState`
per conversation using the bot's own generated replies to build each turn's history (by design —
see the module docstring), so a routing/behavior change earlier in a conversation legitimately
changes every downstream turn's outcome. This is a real re-measurement of the current code, not
a bug, a stale cache, or a fluke — but it means the eval numbers in README.md/CLAUDE.md are now
stale and should be refreshed to **54.5% raw (24/44), 70.6% adjusted (24/34)** the next time
those docs are touched. Not changed automatically here since it wasn't asked for.

Still below the spec's 85% target either way; still below CORE-REV's own 75% adjusted goal too
(70.6% now vs. 72.2% before). The gap-analysis conclusion in `docs/DEVLOG.md` (2 of 3 remaining
failure patterns need a design decision, not another prompt patch) still holds — see "what's
next" discussion in the accompanying reply.

## 6. Full `README.md` (current contents)

> Reproduced in full below, current as of commit `a84d44d`. Note the Evaluation section here
> currently cites the pre-`87ffce2` numbers — see the "Notable finding" in §5 above.

```markdown
# GenAI Recruiter Bot

A multi-agent SMS-style recruiting chatbot for a Python Developer position. A **Main Agent**
orchestrates three specialist advisors — **Exit** (should the conversation end?), **Sched**
(should we offer/confirm an interview time?), **Info** (does the candidate need role/company
info?) — and is the only one that ever talks to the candidate. Built for a GenAI course final
project; full behavioral spec in [`docs/PROJECT_SPECIFICATION.md`](docs/PROJECT_SPECIFICATION.md).

## Architecture

Every turn: the Main Agent reads the complete chat history and decides which advisor(s) to
consult (up to 3 per turn), then synthesizes a single reply carrying exactly one action label —
`continue`, `schedule`, or `end`. Advisors never emit user-facing text themselves; scheduling
slots are always verified against the live DB in the same turn they're offered (never guessed).

\`\`\`mermaid
flowchart TD
    U[Candidate message] --> MA{Main Agent<br/>routes}
    MA -->|exit-ish| EX[Exit Advisor]
    MA -->|scheduling-ish| SC[Sched Advisor]
    MA -->|role/company question| IN[Info Advisor]
    EX -->|end / dont_end| MA
    SC -->|sched / dont_sched / confirmed| DB[(SQLite:<br/>verified slots)]
    DB --> MA
    IN -->|info_needed / not| VEC[(Chroma:<br/>job description)]
    VEC --> MA
    MA -->|up to 3 consults,<br/>then synthesize| OUT[Reply: continue / schedule / end]
\`\`\`

- **Main Agent** — `app/graph.py` (turn loop, guard R-1, synthesis) + `app/modules/main_agent/`
  (LLM routing decision)
- **Exit Advisor** — `app/modules/exit_advisor/` — disinterest/opt-out detection
- **Sched Advisor** — `app/modules/sched_advisor/` — relative-date resolution
  (`date_resolver.py`), DB-backed slot lookup/booking (`tools.py`, `repository.py`)
- **Info Advisor** — `app/modules/info_advisor/` — RAG over the job description (Chroma)
- Every LLM decision is parsed through a Pydantic schema (`app/schemas.py`), never free text —
  parse failure retries once, then falls back deterministically (`app/structured_output.py`)

This is a **plain-Python control-flow implementation** of the spec's turn-flowchart behavior,
not the literal `langgraph` `StateGraph` API the tech stack section mandates — a deliberate,
documented scope decision (see `CLAUDE.md`).

## Project structure

\`\`\`text
app/
├── main.py                        # terminal chat REPL
├── graph.py                       # turn loop: routing, guard, synthesis, trace
├── state.py                       # ConversationState
├── schemas.py                     # Pydantic AdvisorOutput contracts
├── structured_output.py           # retry-once-then-fallback wrapper
├── llm_client.py                  # shared OpenAI client + disk-cached structured calls
├── config.py                      # typed settings (.env)
└── modules/
    ├── main_agent/                # routing prompt + decision
    ├── exit_advisor/
    ├── sched_advisor/             # date_resolver.py, tools.py, repository.py
    ├── info_advisor/              # retriever.py (Chroma RAG)
    ├── embedding/                 # build_index.py — job-description vector index
    ├── scheduling/                # db_setup.py — SQLite seed
    └── fine_tuning/               # dataset_builder.py, launch_job.py, compare.py (Epic E3)
streamlit_app/streamlit_main.py    # registration form -> chat UI -> dev trace panel
tests/                             # pytest suite (mocked; zero real API calls by default)
docs/                              # spec, task plan, devlog, eval notebook + confusion matrix
data/                              # raw dataset/PDF/SQL seed + rebuildable DB/vector index
\`\`\`

## Setup

\`\`\`bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env                                 # fill in OPENAI_API_KEY
python -m app.modules.scheduling.db_setup             # build data/tech.db (rebuildable)
python -m app.modules.embedding.build_index           # build the Chroma vector index
python -m app.main --check-config                     # sanity check
\`\`\`

`.env` also carries `DEMO_NOW_OVERRIDE=2024-04-15T10:00:00Z` — the seeded DB's slots live in
2024, so date resolution needs "now" pinned there for a working demo (never edit
`.env.example` with a real key; only `.env` is git-ignored).

## Usage

**Terminal chat:**

\`\`\`bash
python -m app.main
\`\`\`

\`\`\`
Recruiter bot ready. Type 'quit' to exit.
You: I've been using Python professionally for five years, mostly for data analysis.
Bot [continue]: ...
You: Can we schedule an interview for tomorrow?
Bot [schedule]: I can offer these interview times: 2024-04-16 at 10:00:00; ... Which works best for you?
You: The first one
Bot [end]: Great, you're all set! Your interview is confirmed for 2024-04-16 at 10:00:00.
\`\`\`

**Streamlit UI** (registration form → SMS-style chat → toggleable dev trace panel showing every
advisor consulted, its decision/reason, and retrieved slots/chunks):

\`\`\`bash
streamlit run streamlit_app/streamlit_main.py
\`\`\`

## Evaluation

`tests/eval_replay.py` replays the labeled dataset conversations through the real graph/API and
reports accuracy, per-class precision/recall/F1, and a confusion matrix; `tests/test_evals.ipynb`
is the formal notebook deliverable (spec §9) with the full error analysis.

- **Isolated per-turn replay** (`--mode isolated`, the notebook's baseline methodology): **52.3%**
  (23/44). Confusion matrix: [`docs/eval_confusion_matrix.png`](docs/eval_confusion_matrix.png).
- **Sequential full-conversation replay** (`--mode sequential`, default — one real conversation
  state walked turn-by-turn, matching spec §9's "feed the system the history up to that point"
  literally): **59.1% raw (26/44), 72.2% adjusted (26/36)** once conversations where our bot's
  own generated offer necessarily diverges from the dataset's scripted one are excluded (tagged
  automatically — see `_is_divergence_artifact` in `tests/eval_replay.py`).

Neither run meets the spec's 85% target; the honest gap analysis (ranked failure patterns, what
would actually close the gap) is in the notebook and `docs/DEVLOG.md`'s CORE-REV entries — the
largest remaining pattern turned out to have genuinely inconsistent ground truth in the dataset
itself (identical candidate messages carry opposite gold labels in different conversations), not
a fixable routing bug.

\`\`\`bash
python -m tests.eval_replay              # sequential (default)
python -m tests.eval_replay --mode both  # both, for comparison
\`\`\`

### Exit Advisor: prompted vs fine-tuned (Epic E3)

`app/modules/fine_tuning/` builds a fine-tuning dataset from the same labeled
conversations (conversation-level 80/20 split, zero leakage — see
`tests/test_fine_tuning_dataset.py`) and can launch an OpenAI fine-tuning job
behind the same Strategy-pattern interface the prompted Exit Advisor already
implements. A real job was attempted on this account and blocked by OpenAI
with `403 training_not_available`: *"OpenAI is winding down the fine-tuning
platform and your organization is no longer able to create new fine-tuning
training jobs."* — an org-wide platform deprecation, not a code, cost, or
quota issue. `EXIT_ADVISOR_FINETUNED_MODEL` therefore stays empty and the
prompted advisor remains the default, an accepted outcome rather than a gap.

Baseline (prompted, `gpt-4o-mini`) on the held-out validation split
(n=10, from `python -m app.modules.fine_tuning.compare`):

| model | class | precision | recall | F1 |
|---|---|---|---|---|
| prompted | end | 0.50 | 0.33 | 0.40 |
| prompted | dont_end | 0.75 | 0.86 | 0.80 |

`end`-recall is the headline metric (spec §5.2: missing an `end` costs more
than a false one — it means continuing to message an uninterested
candidate). `compare.py` will score a fine-tuned row automatically if
`EXIT_ADVISOR_FINETUNED_MODEL` is ever set (e.g. fine-tuning access returns,
or a different account is used).

## Live deployment

Not yet deployed — the Streamlit UI is built and verified locally (`streamlit run
streamlit_app/streamlit_main.py`), but connecting it to Streamlit Community Cloud requires an
account and a GitHub push that are outside this repo's own scope.

## Testing & lint

\`\`\`bash
pytest              # full suite, zero real API calls (121 tests, all mocked)
pytest -m real_api  # scenario tests that DO call the real API/DB (see tests/test_scenarios.py)
ruff check .
\`\`\`

## Current status

Epics E0–E2, E4, E6 are done; E5 (evaluation) is done as an honest-gap-analysis outcome; E3
(fine-tuning) is implemented and tested end-to-end, but the real fine-tuning job is blocked by
OpenAI's platform deprecation (see the Evaluation section above) — the prompted Exit Advisor
stays the default, an accepted outcome; E7 (this document) is in progress. See
[`docs/PROJECT_TASKS.md`](docs/PROJECT_TASKS.md) §0 for the live per-task status table and
[`docs/DEVLOG.md`](docs/DEVLOG.md) for the full session-by-session history.
```

## 7. Fine-tuning job status

**No job exists.** `python -m app.modules.fine_tuning.launch_job launch` was run for real this
session: both training/validation files uploaded successfully to OpenAI (then deleted afterward,
since they could never be used), but `client.fine_tuning.jobs.create(...)` itself failed with:

```
openai.PermissionDeniedError: Error code: 403 - {'error': {'message': 'OpenAI is winding down
the fine-tuning platform and your organization is no longer able to create new fine-tuning
training jobs.', 'type': 'invalid_request_error', 'param': None, 'code': 'training_not_available'}}
```

The job was never created, so there is no job ID and no model ID. `launch_job.py`'s
`_write_status` (which would persist `data/fine_tuning/job_status.json`) never ran, because the
failure happens before that point in `launch()`. `EXIT_ADVISOR_FINETUNED_MODEL` in `.env` is
empty; the Exit Advisor uses the prompted path (`settings.advisor_model`, `gpt-4o-mini`) today,
and will continue to unless OpenAI's fine-tuning platform policy changes or a different
account/org is used.

---

*End of report.*
