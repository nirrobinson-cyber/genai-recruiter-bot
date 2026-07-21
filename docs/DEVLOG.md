# DEVLOG — GenAI Recruiter Bot

## 2026-07-18 — Epic E0 (Bootstrap)
- Repo initialized per spec §12: structure, .gitignore, pinned requirements, ruff+pytest config.
- app/config.py (pydantic-settings) + .env.example + logging (GRB-002).
- Data assets copied to data/raw/ and docs/ (GRB-003).
- CLAUDE.md created (GRB-004). CI workflow added (GRB-005).
- Next: Epic E1 — SQLite port of db_Tech.sql + Chroma index.
- Known issue (Windows): installing the evaluation stack for Phase 5 (notably pandas/scikit-learn-related build dependencies for test_evals.ipynb) hit local build-tool friction on this host. The exact install error was a Meson/compiler failure during metadata build for pandas (`Compiler cl cannot compile programs.`). These packages are deferred to Phase 5 and are not needed to complete Epic E0.

## 2026-07-19 — Epic E4 closed out (GRB-043, GRB-044); several real scheduling bugs found via manual REPL testing and fixed
- **GRB-043**: `run_turn` now returns a per-advisor `trace` (advisor, decision, reason) for every consultation this turn; `main.py`'s terminal loop prints it under each reply.
- **GRB-044**: `tests/verify_canonical_flows.py` — manual, real-API script (same convention as `tests/eval_replay.py`) scripting the 4 canonical flows (Q&A, scheduling incl. relative date, refusal→end, opt-out→end) against the live graph. All 4 pass.
- Epic E4 (GRB-040 through GRB-044) is now fully done, staying with the plain-Python control-flow graph (the literal `langgraph` StateGraph rewrite remains a deliberately deferred, separate task — not revisited this session).
- Real bugs found via manual terminal testing and fixed (each with a regression test):
  1. The scheduling offer/re-ask messages were hardcoded placeholders ("I can offer a few interview slots.") that never rendered the actual DB-verified slots the Sched Advisor already had — candidates were never told real dates/times.
  2. A 2nd consecutive `continue` reply in the same open-offer thread (e.g. "when" then a date) lost the offer context entirely, because the phase hint and offered-slots lookup only ever checked the single immediately-preceding turn's action. Fixed via `_in_schedule_phase`/`_pending_offered_slots`, which scan back to the last `schedule`/`end` action instead.
  3. The Sched Advisor's confirmation prompt only had "confirms an offered slot" vs. "vague/decline" branches — a genuinely different concrete date (e.g. "14/4/24") was misclassified as decline instead of triggering a fresh availability lookup. Added an explicit branch + few-shot example.
  4. `date_resolver.resolve_relative_date` had no numeric-date support (`dd/mm/yy` etc.) at all — added (day-first, per this project's IL calendar convention).
  5. `date_resolver` missed the literal-but-typo'd "tomorrow" (e.g. "tomororw") since it only did a substring check — added a narrow fuzzy-match fallback (difflib, cutoff 0.82) for "tomorrow" specifically. Deliberately *not* extended to weekday names (Tuesday/Thursday score too close at that cutoff to safely fuzz — wrong-day silently is worse than asking to clarify).
- **Known follow-up (explicitly deferred, not done this session)**: `date_resolver` is pure regex/dateutil pattern-matching, not the LLM-assisted-parse-then-dateutil-verify design spec §7.3 actually calls for. Bugs 3-5 above are symptoms of that same root cause (an ever-growing enumeration of hand-written patterns) — decided to keep patching narrowly for now and revisit the full LLM-assisted rewrite later rather than doing it as part of this session.
- `pytest`: 75/75 passing. `ruff check .`: clean.

## 2026-07-19 (cont.) — Epic E5 (evaluation): replay harness, metrics, error analysis, one tuning cycle
- Added a live status dashboard (`docs/PROJECT_TASKS.md` §0) mapping every GRB-id to ✅/🟡/❌ so "what's missing" is a single table lookup instead of scattered prose — update this table, not just prose, whenever a task's state changes.
- Built `tests/test_evals.ipynb` (GRB-050/051/052): replays all 44 evaluable labeled turns from `data/raw/sms_conversations.json` (reusing `tests/eval_replay.py`'s case-building logic) through the real graph + real API, computes accuracy, per-class precision/recall/F1, and a 3×3 confusion-matrix heatmap (saved to `docs/eval_confusion_matrix.png`), then lists every miss with its advisor trace (using GRB-043's trace field).
- **Baseline accuracy: 31.8% (14/44)** — far below the 85% (S-1) target.
- **Tuning iteration 1** (GRB-053): taught the Sched Advisor's classifier that qualifying-info-shared and declined-a-specific-time-without-a-new-one are both `sched` moments, and taught the Main Agent's router that plain affirmations ("Yes, absolutely!") right after an offer are scheduling replies. Result: **29.5% (13/44) — a regression.** Root cause: the classifier fix was correct, but `decide()` unconditionally tries to parse an actual date out of the *same* message via `resolve_relative_date` — a message like "I've been using Python for five years" has no date in it, so it fell through to the "date unclear, ask to clarify" branch anyway (net-unchanged), plus one genuinely new miss where the affirmation heuristic over-fired on a compound message.
- **Tuning iteration 2**: fixed the actual root cause — `decide()` now distinguishes "no date was named at all" (default to the nearest available slots; nothing to clarify) from "a date was attempted but is garbled" (still decline and ask to clarify, preserving the original anti-guessing protection). Result: **52.3% (23/44), +20.5pp vs. baseline.** This deliberately updated one existing test (`whenever works for you` now defaults to nearest-available instead of declining) — a reasoned product-behavior change, confirmed with the user before making it, not a silent regression.
- **Honest gap analysis (S-1 not met, spec's accepted alternative)** — 3 remaining failure patterns, written up in the notebook, ranked by impact: (1) over-eager `sched` on some "gold=continue" experience-sharing turns — the dataset has both "schedule right after one experience share" and "keep gathering info first" conversations, and a per-message heuristic can't tell them apart without richer context; (2) "confirmed booking" turns can't be recognized because this replay methodology evaluates each labeled turn against the *dataset's* own prior text, not our own bot's actual prior output — so there's never a real, DB-verified offer in-state for the confirmation-matching logic to check against (a methodology limitation, not an advisor bug); (3) a handful of one-off ambiguous cases. Patterns 1-2 need a design decision (richer routing signal; sequential full-conversation replay) rather than another prompt patch — flagged as deliberate follow-up work.
- `pytest`: 78/78 passing (2 new date-resolver tests, 1 updated + 1 new sched-advisor test). `ruff check .`: clean.

## 2026-07-19 (cont. 2) — Epic E6: Streamlit UI (GRB-060/061/062, GRB-063 partial)
- Added a tracked follow-up item to the dashboard: **CORE-REV** (booking-completion path + proactive escalation + slot rendering, target ≥75% eval accuracy) — deferred, not dropped, scheduled right after E6.
- Built `streamlit_app/streamlit_main.py` per spec §8: registration form (name/phone/email/years-experience → `ConversationState.registration_data` + a personalized opening greeting) → SMS-style chat (`st.chat_message`/`st.chat_input`) → dev-mode action badges → sidebar dev trace panel (toggleable; per-turn advisor trace incl. decisions, reasons, retrieved slots/chunks) → Reset button. Zero decision logic in the UI layer — every turn calls `app.graph.run_turn` exactly like `app/main.py` does.
- Extended `run_turn`'s trace entries (`app/graph.py`) with `slots` (sched) and `sources` (info) so the dev panel can show retrieved chunks/slots per spec, not just decisions.
- Found and fixed a real bug before it ever shipped: bridging `st.secrets` to env vars for Streamlit Community Cloud crashed locally with `StreamlitSecretNotFoundError` — accessing `st.secrets` at all raises when no `secrets.toml` exists, not just when a specific key is missing. Fixed with a try/except around the dict conversion.
- **Verification**: no `chromium-cli`/Playwright/Node available in this environment, so used Streamlit's own `AppTest` framework instead of a browser. (1) Confirmed the real launch command (`streamlit run streamlit_app/streamlit_main.py`) boots cleanly with zero exceptions. (2) Drove the full flow via `AppTest`: registration form fill+submit → personalized opening message rendered correctly; a real chat turn (real OpenAI + DB calls) correctly returned a live "schedule" action with real DB slots rendered in the message; dev-mode toggle correctly revealed the sidebar trace expander; Reset correctly returned to the registration form. Along the way, hit and diagnosed (not an app bug) a genuine limitation in Streamlit's own `AppTest`: a widget from a conditionally-removed `st.form` branch crashes AppTest's internal state collection on the next rerun — reproduced in a 12-line minimal script unrelated to this codebase; routed around it by pre-seeding session state to skip past the form in that one test step.
- **Not done**: GRB-063's actual deploy-to-Streamlit-Community-Cloud step needs the user's own account and a GitHub push — outside what can be done from this session.
- `pytest`: 78/78 passing. `ruff check .`: clean (incl. the new Streamlit module).

## 2026-07-19 (cont. 3) — fix: streamlit_main.py cwd-dependent ModuleNotFoundError
- User-reported bug: `streamlit run streamlit_app/streamlit_main.py` failed with `ModuleNotFoundError: No module named 'app'`. Could not reproduce from the repo root (tested fresh in both git-bash and PowerShell — both booted clean); reproduced it instead by launching from *inside* `streamlit_app/` — `streamlit run` only ever puts the script's own directory on `sys.path`, not its parent, so `app` (at the repo root) only resolved before this fix when the caller's cwd happened to already be the repo root.
- Fix: `streamlit_app/streamlit_main.py` now inserts its own parent directory onto `sys.path` at the very top, before any `app.*` import — makes the app launchable from any working directory, not just the repo root.
- **Process note**: `AppTest`-based verification (used for the rest of Epic E6) does not catch this class of bug — it loads the target module directly rather than through Streamlit's own `sys.path` setup for a subprocess launch. A real `streamlit run <path>` smoke check (ideally from more than one cwd) is required to catch cwd-dependent import issues in UI changes; AppTest alone is not sufficient.
- `pytest`: 78/78 passing. `ruff check .`: clean.

## 2026-07-19 (cont. 4) — CORE-REV: sequential eval harness (top priority), meaningless-input fix
- **FIX 2 (meaningless input)**: reproduced — a single stray char ("f") after a longer answer produced a near-duplicate of the previous answer, because the router/advisors just proceeded as if it were real input. Added `_looks_meaningless()` in `app/graph.py`: short-circuits to a clarification *before* consulting any advisor, but explicitly excludes short-but-real replies (a bare "5", "ok", "no", "yes") so real short answers still route normally. 4 new tests.
- **FIX 1 (ordinal/partial slot confirmation)**: could NOT reproduce the reported bug ("the second one" re-offering instead of booking) via 3 independent real-execution paths — direct advisor call, full `run_turn`, and the actual Streamlit app driven via `AppTest`. All three correctly matched ordinal ("the second one", "the first"), partial ("the 10am one"), and dataset-phrased ("Friday 11 AM sounds great") confirmations and booked the right slot. No speculative code changed; user will reproduce live with the dev trace panel and send the exact transcript.
- **Eval harness rebuilt to replay sequentially (CORE-REV top priority)**: `tests/eval_replay.py` now defaults to replaying each conversation turn-by-turn through ONE real `ConversationState`, letting offered slots/booking status/the proactive-escalation flag accumulate naturally exactly as spec §9 describes ("feed the system the history up to that point") — candidate turns come from the dataset (ground truth), but the "recruiter" side is now our own bot's real generated output, not the dataset's static text. The original per-turn-isolated design (fresh state per case, a bare `{"action": ...}` marker, no real slots — which structurally could never resolve a confirmed-booking turn) is kept as `--mode isolated` for direct comparison; `--mode both` runs and reports both.
- **Results, same 44 graded pairs in both modes:**

  | Mode | Accuracy | continue | schedule | end |
  |---|---|---|---|---|
  | isolated (old) | 52.3% (23/44) | 30.0% (3/10) | 84.2% (16/19) | 26.7% (4/15) |
  | **sequential (new, default)** | **59.1% (26/44)** | 60.0% (6/10) | 73.7% (14/19) | 40.0% (6/15) |

  +6.8pp overall, and `continue`/`end` recall roughly doubled — confirms the booking-path fixes are real and were simply invisible to the old harness. Still below the ≥75% CORE-REV target. New miss pattern surfaced by sequential replay: since our bot's own generated offers diverge from the dataset's original scripted offers, a few candidate replies written to react to the *original* offer no longer match cleanly against *our* bot's different offer (e.g. conversation 2 turn 7: "Sounds great! I'd be happy to schedule a meeting" got read as confirming a slot from our bot's own earlier turn, predicting `end` instead of gold `schedule`) — an inherent, expected complexity of sequential replay, not a new bug.
  - 8 new tests for the sequential mode's pure pairing logic (`_sequential_case_anchors`), no API calls.
- `pytest`: 90/90 passing. `ruff check .`: clean. Cache (`app/llm_client.cached_parse`) kept API cost bounded — same order of magnitude as prior notebook runs.

## 2026-07-19 (cont. 5) — CORE-REV directives: divergence tagging, escalation-timing investigation (tried, reverted)
- **Directive 1 (divergence-artifact tagging)**: `tests/eval_replay.py` now tags every sequential-mode miss GENUINE or DIVERGENCE — a documented heuristic (not ground truth): a miss is DIVERGENCE if (a) our bot's own action trajectory had already drifted from the dataset's script by this point, or (b) our bot has a pending real offer but the candidate's reply names a day/time matching none of it (written to accept the dataset's fictional offer, not ours). Reports raw AND adjusted accuracy (excluding divergence misses), with each printed miss tagged. Two refinements found while building this: (i) "pending offer" must use `graph._pending_offered_slots` (survives a `continue` restate), not the literal last action label; (ii) the very first candidate turn of every conversation has no prior action at all and must not be auto-tagged divergence just because the dataset's opener carried a real label. 8 new pure unit tests (no API calls).
- **Directive 2 (largest genuine pattern)**: with divergence excluded, inspected the actual conversation texts behind the remaining misses. Found and fixed a real, clean bug: `_looks_like_a_date_attempt`'s bare `\d` regex flagged ANY digit as a date attempt, so "Yes, 3 years' experience" / "5 years of experience" were wrongly declined as "garbled dates" instead of triggering the proactive nearest-slots offer — narrowed to date-shaped digit patterns only (`10am`, `14/4/24`, `14th`). Confirmed fix via new pure tests and a real-API scenario test.
- Investigated the "over-eager escalation" pattern (proactive scheduling firing on ANY first experience-mention) by reading the actual dataset conversations side by side. Found the ground truth is **genuinely inconsistent**: conversations 1 and 4 have the word-for-word IDENTICAL candidate first reply ("I've been using Python professionally for five years, mostly for data analysis.") but opposite gold labels for the next turn (conv1: schedule immediately; conv4: one more follow-up question first) — no message-content signal can perfectly resolve this. Tried a targeted fix anyway (prompt: don't escalate on the very first mention, only once the maturity flag was armed on an earlier turn; a deterministic code-level guard to enforce it, since the model didn't reliably self-enforce the prompt-only version on a same-turn re-consult) — a real, confirmed same-turn timing bug fix (`state.qualifying_info_shared` was being armed and consumed within the same turn's loop; now deferred to after the loop, with a regression test in `tests/test_scenarios.py`).
- **The deterministic guard itself was reverted**: full-dataset eval showed it was a net regression (schedule recall crashed 78.9%→31.6%) — the 5-conversation sample used to diagnose the pattern wasn't representative of the full dataset's actual majority (most gold=schedule conversations want IMMEDIATE escalation, matching conv1's pattern, not the delayed pattern the guard assumed). Reverted the guard; kept the flag-timing fix (independently correct) and the digit-fix (independently correct, confirmed win). The reverted guard's regression test is kept `xfail`-marked in `tests/test_scenarios.py` with the full explanation, rather than deleted — a documented, tracked gap to revisit with a richer signal, not deleted evidence.
- **New file, new convention**: `tests/test_scenarios.py` — real-API pytest cases (marked `@pytest.mark.real_api`) converting what would otherwise be ad-hoc `python -c` verification snippets into permanent regression coverage. Registered the `real_api` marker in `pyproject.toml` with `addopts = "-q -m 'not real_api'"` so the default bare `pytest` run stays at zero real API calls (unchanged invariant); run explicitly via `pytest -m real_api` or `pytest tests/test_scenarios.py`. **Going forward: prefer a `test_scenarios.py` pytest case over an ad-hoc `python -c` snippet whenever the check can be expressed as one** — ad-hoc snippets don't survive as regression coverage.
- **Current accuracy (sequential mode, reflects the digit-fix but NOT the reverted guard): raw 59.1% (26/44), adjusted 72.2% (26/36) excluding 8 divergence artifacts.** Still below the ≥75% CORE-REV target — deferred, not dropped, per the user's explicit instruction to stop tuning for now and return to it later.
- `pytest`: 105/105 passing (bare run, zero real API calls) + 4/4 passing under `-m real_api` (1 `xfail` for the reverted guard, expected). `ruff check .`: clean.

## 2026-07-19 (cont. 7) — fix: rejected scheduling slots got re-offered (infinite loop)
- User-reported live-transcript bug: bot offers Apr 18-19 slots -> candidate asks for 15/5/24 -> bot correctly offers May 15 slots -> candidate says "none" -> bot re-offers the OLD April slots -> candidate says "other dates" -> same April slots again. No progress, infinite loop.
- Reproduced via a new real-API scenario test (`tests/test_scenarios.py`) before touching any code. Found **two distinct bugs**, both real:
  1. **Routing bug**: "none" (rejecting a scheduling offer) got routed to the Exit Advisor, which decided `end` — treating "these times don't work" as disinterest in the role entirely, prematurely ending the conversation. Fixed: extended the Main Agent's "previous turn was schedule" routing rule to also cover rejection phrasings ("none", "those don't work", "other dates", "do you have anything else") — these mean "not these times", not "not interested", so they should route to Sched, never Exit.
  2. **The core reported bug**: `date_resolver.default_forward_window` always anchored its search at `now`, with no memory of how far the conversation had already progressed — so ANY rejection with no new date named (the Sched Advisor's own confirmation prompt was *also* misclassifying "none" as a vague `dont_sched` rather than a rejection warranting a fresh, later lookup) looped back to the same earliest available slots every time.
- **Fix** (`ConversationState.offered_slots_history`, `app/graph.py`, `app/modules/sched_advisor/{advisor.py,date_resolver.py}`):
  - `ConversationState` now accumulates every slot ever offered this conversation (not just the current pending batch).
  - `default_forward_window(now, after=...)` — new optional `after` param advances the window's start to the day after the latest previously-offered date, never re-searching from `now`.
  - `sched_advisor.decide(..., previously_offered_slots=...)` — excludes every previously-offered `schedule_id` from new results (over-fetches `3 + len(excluded)` to leave enough headroom after filtering) and passes the floor date into the "no date named" fallback. If nothing remains after exclusion, reports empty `proposed_slots` with an honest reason.
  - The Sched Advisor's own confirmation-prompt addendum gained an explicit third category: reject-the-batch-without-a-new-date ("none", "other dates") is `sched` (look up different/later availability), distinct from genuinely vague replies ("when", "not sure") which stay `dont_sched`.
  - The "no further slots" message now explicitly offers a recruiter follow-up instead of a vague "try another day".
- **Tests**: reproduced-then-fixed via the exact live transcript, plus the 3 directive scenarios (reject→new later slots; "other dates"→different slots; double rejection→keeps advancing, never repeats) as permanent `tests/test_scenarios.py` real-API cases, plus 2 new mocked unit tests in `tests/test_sched_advisor.py` and 2 in `tests/test_date_resolver.py` for the pure logic. All existing tests stayed green; the only non-test-file diff is `app/state.py` (+1 field), `app/graph.py` (thread the history through + accumulate), `app/modules/sched_advisor/advisor.py` (exclusion + floor date), `app/modules/sched_advisor/date_resolver.py` (`after` param), and `app/modules/main_agent/prompts.py` (routing rule).
- `pytest`: 111/111 passing (bare run) + 7/8 passing under `-m real_api` (1 pre-existing `xfail`, unrelated). `ruff check .` and `ruff format --check .`: both clean.

## 2026-07-19 (cont. 6) — Epic E7: README (GRB-070) + final quality pass (GRB-071)
- Wrote the real `README.md` per spec §14: purpose, architecture (Mermaid turn-flow diagram + module map), project structure, setup (venv/`.env`/DB+index build), usage (terminal + Streamlit examples), evaluation results (both isolated and sequential numbers, with the honest caveat that the confusion-matrix image reflects the older isolated-mode run), an honest "not yet deployed" note (no fabricated URL), testing/lint commands, and a current-status pointer to the dashboard/DEVLOG instead of duplicating it.
- Final quality pass: removed the stray untracked `tmp_verify_db.py` (flagged in CLAUDE.md as cleanup debt, never part of any task); ran `ruff format .` repo-wide for the first time this session (previously deliberately avoided during narrow bug fixes to keep diffs small — now in-scope as the actual quality-pass task) — 19 files reformatted, all mechanical, `pytest` reconfirmed 105/105 passing after; spot-checked for dead code (`sched_advisor/repository.py` vs `tools.py` — both genuinely used, not orphaned).
- **Not done**: demo screenshots/GIF (needs a real browser, unavailable in this environment); GRB-072 (tag v1.0 + presentation outline) — tagging is a git action pending explicit user confirmation, not done unprompted.
- `pytest`: 105/105 passing. `ruff check .` and `ruff format --check .`: both clean, repo-wide.

## 2026-07-19 (cont. 8) — Epic E3: Exit Advisor fine-tuning (GRB-030..033)

Started per explicit user request, deliberately context-switched off CORE-REV (different subsystem, no conflict; CORE-REV remains open, waiting on a user-supplied live-repro transcript).

- **GRB-030 (`app/modules/fine_tuning/dataset_builder.py`)**: builds train/val JSONL from `data/raw/sms_conversations.json` (15 conversations, 44 labeled recruiter turns: 25 `continue`, 19 `schedule`, 15 `end` — exactly one `end` per conversation). Two deliberate deviations from the task spec's literal pseudocode, both for train/serve parity with production: (1) assistant targets are the real `ExitAdvisorOutput` JSON shape (`{"decision","confidence","reason"}`), not a bare label token — production calls the model via `cached_parse(..., response_format=ExitAdvisorOutput)`, so training on bare tokens would train text the model is never actually asked to produce; (2) user-side history reuses the real `history_to_messages(SYSTEM_PROMPT, history)` + the real `SYSTEM_PROMPT`, truncated to everything strictly before the labeled turn (confirmed via `app/graph.py`: `state.add_message("user", ...)` happens before `exit_advisor.decide(state.history)`, so the candidate's triggering message is the last history item) — matches the exact message shape a real inference call sends, instead of a collapsed single string. Split is conversation-level (`split_conversation_ids`, seeded shuffle, 80/20) — zero turn-level leakage, asserted by test.
- **GRB-031**: 13 hand-written edge-case examples (`_HAND_WRITTEN_RAW` in `dataset_builder.py`) covering explicit opt-out, polite-but-ambiguous ("I'll be in touch"), booking-confirmation-as-end, and reschedule-not-end — appended to train only, never val.
- Real run: `python -m app.modules.fine_tuning.dataset_builder` → 47 train (34 dataset-derived + 13 hand-written; 19 end / 28 dont_end) / 10 val (3 conversations; 3 end / 7 dont_end).
- **GRB-032 (`app/modules/fine_tuning/launch_job.py`)**: upload + `fine_tuning.jobs.create` + local `data/fine_tuning/job_status.json` audit record; `check` subcommand polls status and never silently writes `.env` (prints the model ID + the line to add instead). New `settings.fine_tune_base_model` (default `gpt-4o-mini-2024-07-18`, confirmed available on this account via `client.models.list()` before committing to it).
- **Real job launch attempted and blocked — not a code bug**: `python -m app.modules.fine_tuning.launch_job launch` uploaded both files successfully, then `fine_tuning.jobs.create` returned **403 `training_not_available`**: *"OpenAI is winding down the fine-tuning platform and your organization is no longer able to create new fine-tuning training jobs."* This is an org-wide platform deprecation, not a quota/cost/retriable issue — confirmed by a prior successful `jobs.list()` call (read access ≠ write/create access). The two orphaned uploaded files were deleted afterward (`client.files.delete`) since they can never be used. **No fine-tuned model can be produced on this account going forward.**
- **GRB-033 (`app/modules/fine_tuning/compare.py`)**: added an optional `model` param to `exit_advisor.advisor.decide()`/`_call_llm()` (defaults to today's settings-based selection when `None`) so the comparison reuses the exact production call path — same retry/fallback/cache — for both sides instead of duplicating LLM-calling logic. `compare_models()` scores prompted vs fine-tuned (when configured) on the val split's precision/recall/F1 per class, end-recall as the headline metric per spec §5.2's cost asymmetry. Real run (prompted only, `gpt-4o-mini`, n=10 val examples — small sample, noisy):
  ```
  prompted (gpt-4o-mini):
    end       precision=0.50 recall=0.33 f1=0.40
    dont_end  precision=0.75 recall=0.86 f1=0.80
  fine_tuned: not available (no fine-tuned model configured)
  ```
  Fine-tuned row will populate automatically (`python -m app.modules.fine_tuning.compare`) if a fine-tuned model is ever obtained another way (org policy changes, different account/org) and set via `EXIT_ADVISOR_FINETUNED_MODEL`.
- **Epic outcome**: prompted stays the default (`EXIT_ADVISOR_FINETUNED_MODEL` remains empty) — not because it won a comparison, but because no fine-tuned model can be created on this account under OpenAI's current deprecated-platform policy. Per the user's explicit pre-confirmation, this is an accepted, documented outcome, not a gap to chase. All four GRB items are otherwise fully implemented, tested, and (where feasible) run for real.
- Tests: `tests/test_fine_tuning_dataset.py` (6), `tests/test_launch_job.py` (2, mocked `get_client`), `tests/test_compare.py` (4, mocked `decide`) — all new, zero real API calls in the default suite. `tests/test_exit_advisor.py`'s two existing mocked `_call_llm` lambdas updated for the new `model` parameter (mechanical, no behavior change).
- `pytest`: 121/121 passing. `ruff check .`: clean.

## 2026-07-20 — CORE-REV: 3 targeted eval misses fixed at the decision layer; aggregate score did not move (honest finding)

Triggered by a fresh `python -m tests.eval_replay` run (docs/ACCEPTANCE_REPORT.md), which itself surfaced a real methodology fact: the 2026-07-19 CORE-REV numbers (59.1%/72.2%) predate this session's infinite-loop fix (`87ffce2`), which touched routing/scheduling code — since sequential replay lets the bot's own decisions shape downstream turns, that fix alone shifted the honest current numbers to **raw 54.5% (24/44), adjusted 70.6% (24/34)** even before today's changes.

From that fresh miss list, picked 3 **genuine** (non-divergence-artifact) misses that looked like concrete, narrow bugs rather than the known ground-truth-inconsistency trap:

1. **Sched Advisor over-confirmed on vague enthusiasm** (conv 2 turn 7: *"Sounds great! I'd be happy to schedule a meeting"* — no day/time named — got classified `confirmed` and booked an arbitrary offered slot). Added an explicit negative few-shot example to `CONFIRMATION_PROMPT_ADDENDUM` (`app/modules/sched_advisor/advisor.py`): general enthusiasm without picking a specific offered slot is `dont_sched`, not `confirmed`.
2. **Confirmation matching failed on weekday-name references** (conv 6 turn 5: *"Friday 11 AM sounds great"* — a real offered slot existed on that day/time — got classified as a brand-new date proposal instead of a match). Root cause: the model had to compute day-of-week from a raw ISO date itself to recognize the match, an error-prone calculation for an LLM. Fixed by annotating every offered slot in the prompt with its weekday name in parentheses (`2024-04-19 (Friday) 11:00:00`), computed deterministically in Python (`calendar.day_name`), so the model never has to do that math.
3. **Exit Advisor over-fired on a soft, deferring decline** (conv 8 turn 7: *"I'm unavailable at that time... I'll reach out if it becomes relevant"* → `end`, when gold=`schedule` — declining this specific time isn't disinterest). Added an explicit few-shot example to `app/modules/exit_advisor/prompts.py` distinguishing a deferring decline from an explicit opt-out.

**Verification, and an honest result:**
- All 3 fixes were reproduced-then-fixed via dedicated new real-API scenario tests in `tests/test_scenarios.py` (`test_vague_enthusiasm_after_offer_does_not_falsely_confirm_a_booking`, `test_confirmation_matches_offered_slot_by_weekday_name`, `test_soft_decline_with_future_interest_does_not_trigger_exit`) — all 3 pass against the real API in isolation (one needed a retry: it failed once, passed on immediate re-run, consistent with known temperature=0 structured-output sampling variance, not a broken fix). Plus one new mocked unit test (`tests/test_sched_advisor.py::test_call_llm_annotates_offered_slots_with_weekday_name`) confirming the weekday annotation is actually in the prompt sent to the model.
- **Re-running the full eval afterward did NOT improve the aggregate score** — it moved to **raw 52.3% (23/44), adjusted 67.6% (23/34)**, slightly *below* the pre-fix number. This is a real, understood result, not a broken fix:
  - Conv 2 turn 7 now correctly avoids the false booking (verdict is `dont_sched`), but `app/graph.py`'s pre-existing "restate offered slots in schedule phase" branch labels that turn's action `continue`, not `schedule` — while gold says `schedule`. A different, pre-existing action-labeling gap, newly *exposed* by the fix, not caused by it (previously masked because the old `confirmed` bug produced a different, also-wrong answer).
  - Conv 6 turn 5 and conv 8 turn 7 **still fail in the full sequential run** despite the isolated real-API tests passing for the identical trigger phrasing — the surrounding conversation history differs between the isolated test and the real dataset conversation's actual trajectory, so it's a genuinely different LLM call each time; the fixes measurably help (proven in the controlled test) but don't guarantee every context, especially at the genuinely-ambiguous edge (soft decline) and under real LLM sampling variance.
  - Sequential mode's own cascading nature (one turn's changed outcome reshapes the rest of that conversation's real trajectory) surfaced 2 *new* misses elsewhere (conv 7 turn 7, conv 11 turn 7) that weren't misses before — an inherent property of this replay methodology, not a regression in the advisors themselves.
- **Decision: keep the 3 fixes (each is a real, independently-verified correctness improvement — see the passing real-API regression tests) and stop here.** Chasing the aggregate number further right now risks repeating the reverted-escalation-guard lesson from 2026-07-19 (a change that looked locally correct regressed the full dataset 78.9%→31.6% via the same sequential-cascade mechanism). The `continue`-vs-`schedule` action-labeling gap exposed by fix #1 is a legitimate new lead, explicitly not pursued today — needs its own scoped investigation, not a same-session follow-on patch.
- README.md/CLAUDE.md eval numbers refreshed to the current honest figure: **raw 52.3% (23/44), adjusted 67.6% (23/34)**, replacing the stale 59.1%/72.2%.
- `pytest`: 122/122 passing (bare run) + 10/11 passing under `-m real_api` (1 pre-existing `xfail`, unrelated). `ruff check .` and `ruff format --check .`: both clean.

## 2026-07-20 (cont. 2) — CORE-REV: real gain from re-deriving the "genuinely inconsistent ground truth" claim across all 15 conversations, not just 2

User pushed back on the "genuinely inconsistent, can't be resolved" framing from the previous entry, believing the escalation-timing pattern was more tractable than described. Re-derived it from scratch against the full dataset instead of trusting the earlier 2-conversation comparison — the framing was incomplete, not wrong about there being real ambiguity, but wrong about it being unresolvable.

**What re-deriving it found:**
- Across all 15 conversations, **10 (67%) schedule immediately** after the candidate's first substantive reply — no deferral. Only 5/15 defer. The router's actual instruction (`app/modules/main_agent/prompts.py`) hard-coded "don't escalate on the first reply" as the default — i.e. it encoded the *minority* behavior as the rule.
- Worse: the prompt's own worked example for that instruction used the literal phrase *"I've been using Python professionally for five years, mostly for data analysis."* — which is the real candidate reply in conversations 1, 4, **and** 9. Conversations 1 and 9 (the majority pattern) actually want immediate scheduling; only conversation 4 wants deferral. The prompt was teaching the wrong answer using 2 of its own 3 real occurrences as evidence for the opposite conclusion.
- A real, checkable distinguishing signal exists within the most common opener ("Could you share a bit about your Python experience?"): a **general/broad** reply (years of experience, a broad domain like "data analysis"/"ML"/"backend services", no new named technology) → recruiters schedule immediately (conversations 5, 9, 12, 14, 15 — 5/5 clean). A reply naming a **specific new technology** not already asked about (Django, Flask, SQL, AWS) → recruiters ask one follow-up first (conversations 2, 3, 11 — 3/3 clean). 8/8 clean under that opener. The rarer "How long have you been working with Python?" opener (6 conversations) does **not** follow this rule cleanly (4/6 immediate regardless of content) — deliberately left untouched, to avoid the exact over-generalization trap that caused the 78.9%→31.6% regression in the earlier attempt.

**Fix**: `app/modules/main_agent/prompts.py`'s `SYSTEM_PROMPT` only — replaced the unconditional "defer on first reply" instruction and its single (mis-teaching) example with a content-conditional version plus 3 contrasting examples (general → escalate; specific tech → defer; a compound case combining both).

**A real trade-off found during verification, not swept under the rug**: the first version of the fix correctly flipped conversations 1 and 9, but broke conversation 3 ("Sure, I have four years of Python experience **and two with SQL**") — a compound reply that leads with a general statement and only tacks on a named technology as a secondary clause. Two rounds of prompt strengthening (explicit "scan the whole reply" instruction, then a worked example using this exact sentence) still couldn't get the model to reliably weight the trailing SQL mention. Turns out not to matter for the final score: conversation 3's turn was *already* wrong before this fix too, via a separate, pre-existing same-turn re-consult mechanism (the same one behind the already-`xfail`-marked `test_run_turn_defers_escalation_to_the_next_turn_not_same_turn`) — so this fix neither helps nor hurts conversation 3's actual scored outcome. Kept as a new `xfail` test (`test_compound_reply_with_a_trailing_technology_mention_still_defers`) documenting the gap honestly rather than hiding it.

**As foreseen, the global (non-opener-scoped) prompt change also regressed conversation 4** (the one "how long" opener exception that wants deferral) — an accepted, predicted trade-off; scoping the instruction to only one opener's exact wording would overfit to this 15-conversation synthetic dataset rather than generalizing.

**Real, measured result — a genuine gain, not a wash like the previous session's 3 fixes**:
```
Before: raw 52.3% (23/44), adjusted 67.6% (23/34)
After:  raw 56.8% (25/44), adjusted 73.5% (25/34)
```
+4.5pp raw, +5.9pp adjusted — the largest single-step improvement since the original E5 tuning iterations. Still below CORE-REV's own 75% adjusted target (73.5%, close) and the spec's 85% target.

Verified via 5 new real-API regression tests in `tests/test_scenarios.py` (`test_general_experience_statement_escalates_on_first_reply`, `test_general_experience_statement_escalates_regardless_of_opener_wording`, `test_specific_technology_mention_still_defers_even_with_a_different_technology`, `test_compound_reply_with_a_trailing_technology_mention_still_defers` [xfail], `test_run_turn_general_experience_statement_schedules_on_the_first_reply` [end-to-end]) plus the two pre-existing tests for this area (`test_first_experience_mention_does_not_escalate_to_sched`, `test_second_round_with_qualifying_info_armed_escalates_to_sched`) confirmed still passing unchanged.

`pytest`: 122/122 passing (bare run, unchanged count — only real-API tests added) + 14/16 passing under `-m real_api` (2 `xfail`, both documented known gaps). `ruff check .` and `ruff format --check .`: both clean.

## 2026-07-21 — CORE-REV: two named root-cause bugs from the error-analysis doc — one real fix, one real non-bug, both investigated fully

User asked for a Hebrew-language visual report of the 9 real genuine misses first (published as an artifact — chat-bubble transcripts with gold-vs-predicted comparisons), then named two specific root causes to fix from it: BUG A ("double-consult inconsistency," conversations 2/3/11) and BUG B ("slot confirmation fails in full context but passes in isolation," conversations 6/7). Investigated both fully before writing any fix.

**BUG A — confirmed real, fixed.** `app/graph.py`'s consult loop can call `main_agent.route()` more than once per turn (guard R-1 allows up to 3). The `info` branch has no `break`, so after the info advisor declines, the loop re-consults routing with `consultations_so_far` now including that decline. On the first call the router correctly decides to defer scheduling (a specific named technology like Django/Flask/AWS — "ask one more question first"), reports `candidate_shared_experience=true` to arm escalation for later, but does NOT escalate this turn. On the second call, with the info-decline now in context, the router flip-flops to `sched` — contradicting its own first decision within the same turn. Fix: a new local `sched_deferred_this_turn` flag in `run_turn`'s loop — once routing decides not to escalate for the "wait one more exchange" reason (`candidate_shared_experience=true`, `next_step != "sched"`, no slots offered yet, qualifying info not already flagged from an earlier turn), that decision holds for the rest of THIS turn's consults; a later `sched` pick within the same turn is ignored (`break`s the loop) rather than acted on.

- Verified with a new mocked unit test (`tests/test_graph.py::test_run_turn_sched_deferral_holds_across_a_same_turn_re_consult`, asserts `sched_advisor.decide` is never even called) plus 2 new real-API regression tests using conversations 2 and 11's exact first replies (`test_run_turn_double_consult_does_not_escalate_after_deferring`, `test_run_turn_double_consult_does_not_escalate_for_a_different_technology`), replayed exactly as `tests/eval_replay.py` does — **empty `ConversationState`, no synthetic opener turn** (a real finding from this investigation: the sequential eval harness never adds the recruiter's turn-1 text to history at all, it starts directly from the candidate's first message — several earlier tests in this session had used a synthetic opener, which is not what the real harness does).
- The old `xfail`-marked `test_run_turn_defers_escalation_to_the_next_turn_not_same_turn` (tracking this exact scenario since 2026-07-19) now genuinely passes — un-marked, docstring updated to explain why this fix is narrower than the earlier reverted blanket guard it's easy to confuse it with (that guard blocked ALL same-turn escalation regardless of context and regressed schedule recall 78.9%→31.6%; this fix only blocks a flip-flop away from a decision the SAME turn's own routing already made).
- **Found and fixed 3 casualties of the fix**: `test_vague_enthusiasm_after_offer_does_not_falsely_confirm_a_booking`, `test_confirmation_matches_offered_slot_by_weekday_name`, and `test_soft_decline_with_future_interest_does_not_trigger_exit` (all from the 2026-07-20 Sched/Exit fixes) all started failing — not because the fix was wrong, but because their setup used `state.add_message("user", ...)` directly to seed history instead of a real `run_turn` call. Production code (`app/graph.py`, `streamlit_app/streamlit_main.py`) never calls `add_message("user", ...)` outside of `run_turn` itself — doing so in a test creates two consecutive "user" messages with no assistant reply between them, a conversation shape that can never occur in real usage, and it confused the router into misreporting `candidate_shared_experience=true` for an unrelated later message. Fixed by replacing the direct injection with a real `run_turn` call, matching how the app is actually driven.

**BUG B — investigated fully, turned out not to be a code bug.** Replaying conversation 6 exactly as the harness does (not a synthetic snippet) showed our bot's own real DB-verified offer for that turn was **2024-04-21 (Sunday) and 2024-04-25 (Thursday)** — never a Friday. The candidate's scripted reply "Friday 11 AM sounds great" was written to accept the *dataset's* fictional offer ("this Friday at 11 AM or next Monday at 9 AM"), which our system never actually made. Checked why: the nearest real Friday (4/19) had zero available slots left, fully booked out by this session's own cumulative real-API test runs across many hours of work. Per the user's direction, rebuilt `data/tech.db` (`python -m app.modules.scheduling.db_setup`, documented as rebuildable/gitignored) to reseed it — Friday 4/19 11:00 became available again, but replaying conversation 6 again still failed: the sched advisor's "nearest 3 available slots" logic naturally offers the chronologically closest slots, which happened to be Wednesday 4/17 (2 days earlier than Friday), so Friday still isn't in the offered set. Checked conversation 7 too (same pattern: offered Sunday, candidate says "Tuesday works") — identical structural cause. **Conclusion: this is not a weekday-parsing bug and never was — it's an inherent mismatch between our system's real-time nearest-available-slot offering and the synthetic dataset's fixed script, a genuine divergence artifact.** No fix applied; writing one would have been solving a problem that doesn't exist in the code.

**Real, measured result:**
```
Before: raw 56.8% (25/44), adjusted 73.5% (25/34)
After:  raw 65.9% (29/44), adjusted 82.9% (29/35)
```
+9.1pp raw, +9.4pp adjusted — **first time this project has exceeded the CORE-REV 75% adjusted target.** Exact per-conversation outcome: conversations 2 (turns 3 and 7) and 3 and 11 (turn 3) all flip to correct, as targeted. Conversations 6 and 7 remain misses but are now correctly tagged `DIVERGENCE` instead of `GENUINE` by the harness's own heuristic — consistent with the investigation finding, not a fix. Three *new* misses appeared (conversation 3 turn 7, conversation 7 turn 3, conversation 11 turn 5) — an expected consequence of sequential mode's cascading property (fixing one turn reshapes the rest of that conversation's real trajectory, per the same mechanism documented in the 2026-07-20 entries); conversation 7 turn 3 specifically is a new instance of the same "specific technology named, but gold wants immediate escalation anyway" exception already known from conversation 4 — not chased further, same reasoning as before (would require overfitting the prompt to this one dataset).

`pytest`: 123/123 passing (bare run) + real-API scenario suite all green (1 pre-existing documented `xfail` for the compound-sentence gap from 2026-07-20). `ruff check .` and `ruff format --check .`: both clean.

## 2026-07-21 (cont.) — Docs reconciliation: CORE-REV row overstated one open item as resolved

No code changes this session. `docs/PROJECT_TASKS.md`'s CORE-REV row had drifted out of sync with `CLAUDE.md`: it claimed ordinal/partial slot confirmation ("the second one") was "verified working live (3 independent test paths)," while `CLAUDE.md` (and the user, re-confirming live) both state the opposite — it could not be reproduced in those 3 paths and is still waiting on a user-supplied live-reproduced transcript from the dev trace panel. Corrected the CORE-REV row's status back to 🟡 and named both still-open items explicitly: BUG-1 (ordinal slot confirmation, unreproduced) and BUG-2 (the `continue`-vs-`schedule` action-labeling gap from the 2026-07-20 fix pass, not yet scoped). Added a matching "Known open items" section to `README.md` so the two docs can't silently diverge again without both being touched.

## 2026-07-21 (cont. 2) — GRB-063: closed the deploy data-bootstrap gap; descoped BUG-1/BUG-2 for submission

**Deploy gap found and fixed.** Writing the full Streamlit Community Cloud runbook (README's new
"Live deployment (GRB-063)" section) surfaced a real blocker that would have made the documented
deploy steps fail: Community Cloud clones a fresh, ephemeral checkout on every deploy/reboot, and
`data/tech.db`/`data/chroma/` are gitignored (rebuildable by design, spec §12) — so neither would
exist there, and Cloud gives no shell to run `db_setup`/`build_index` manually afterward. Fixed by
adding `_ensure_data_stores_built()` to `streamlit_app/streamlit_main.py`: builds both on first
run if missing, cached via `st.cache_resource` so it runs exactly once per container despite
Streamlit re-executing the whole script on every rerun. `build_index()` already fails gracefully
to a deterministic hash-embedding fallback with no `OPENAI_API_KEY` (pre-existing behavior), so
this can't crash the app even with a missing/bad key.

Verified for real: moved the actual `data/tech.db` (8352 rows, live test bookings from today's
session) and `data/chroma/` aside to simulate a fresh clone, ran the app via Streamlit's `AppTest`
harness, confirmed zero exceptions and both stores rebuilt (8352 fresh scheduling rows, a real
Chroma collection), then restored the original files exactly (not a reseed — moved back, not
rebuilt again, so today's live bookings weren't lost). Full suite re-run after: `pytest` 123/123,
`ruff check .` clean.

**BUG-1/BUG-2 explicitly descoped for this submission**, per user decision — not silently dropped.
`docs/PROJECT_TASKS.md`'s CORE-REV row and `README.md`'s "Known open items" both updated to say so
plainly rather than continuing to carry them as open blockers. Actual Streamlit Cloud account
connection remains the one GRB-063 sub-item that needs the user directly (GitHub push + Cloud
account) — everything code-side is now in place for it to work when they do.

## 2026-07-21 (cont. 3) — GRB-063: live deploy completed by the user, GRB-072's GitHub push done

User installed GitHub CLI (`winget install --id GitHub.cli`), authenticated (`gh auth login`), and
this repo now has a real GitHub remote for the first time this project (`git remote -v` had been
empty since bootstrap) — `origin` → `https://github.com/nirrobinson-cyber/genai-recruiter-bot`,
`main` and the `v1.0` tag both pushed.

Deployed to Streamlit Community Cloud from that repo. Hit one transient build error on first
attempt (`ModuleNotFoundError` for `pydantic_settings`, consistent with the known `chromadb`/
`hnswlib` native-build-on-Cloud risk flagged in the deploy runbook) — resolved itself on a
retry/redeploy without a packages.txt change, so left unaddressed rather than fixed speculatively.
User confirmed the app is set to "public and searchable" and manually verified all four flows
live: registration form, a real chat turn with a DB-verified bot reply, the dev trace panel,
and Reset.

**GRB-063 closed.** Live URL added to `README.md`'s "Live deployment" section (the old "not yet
deployed" note removed, deploy runbook kept collapsed under a `<details>` for reference) and
`docs/PROJECT_TASKS.md`'s GRB-063 row flipped to ✅. `README.md`'s "Current status" section
refreshed to match (E6 now includes the live deploy, E7 effectively done bar screenshots/GIF).

Remaining before this project can be called fully closed, all requiring the user directly (not
something further code changes can resolve): demo screenshots/GIF (needs the now-live app, a real
browser), a presentation decision (GRB-072's own AC calls for one; previously skipped for `v1.0`
per user request — whether the course still requires it is the user's call), a final re-tag once
those are done, the user's own review pass over commits since `v1.0`, and confirming the actual
course submission format/deadline.

## 2026-07-21 (cont. 4) — Project close-out: v1.1 tagged, BUG-1/BUG-2 formally closed, scope trimmed

User made several final scoping calls: demo screenshots/GIF (GRB-071) and a presentation outline
(GRB-072) both marked not relevant for this submission — dropped, not deferred. User's own commit
review is in progress on their end (not tracked here). Submission format confirmed as a zip file,
no near-term deadline pressure.

**BUG-1 and BUG-2 formally closed** (previously "descoped for this submission," now closed
outright, by explicit request): "if we see it in the future, open a ticket" — i.e. don't carry
these as tracked open work at all; a future real reproduction should be filed as a new, separate
issue rather than reopening this history. `README.md`'s "Known open items" section retitled
"Known limitations (closed, not tracked as open work)"; `docs/PROJECT_TASKS.md`'s CORE-REV row
updated to say CLOSED explicitly, with the same "reopen as new issue, don't reopen this line"
instruction. Worth noting for accuracy: the live transcript offered as possible BUG-1 evidence
(`"21/4/24/10 am look ok"`) was investigated and found to test a different code path (explicit
numeric-date matching, fixed 2026-07-19) rather than the ordinal/positional matching BUG-1 is
actually about — so BUG-1 closes as "never reproduced," not "verified fixed." That distinction is
preserved in the docs rather than smoothed over, in case it's ever revisited.

`v1.1` tagged at this point (`dcbdbd0` and now this commit) and pushed to
`github.com/nirrobinson-cyber/genai-recruiter-bot`, summarizing everything since `v1.0`: CORE-REV
target crossed, live Streamlit Cloud deploy, docs reconciliation, and this final scope trim.

**Where the project stands**: code/tests/lint all green, deployed and live, documented
consistently across README/PROJECT_TASKS/DEVLOG, GitHub remote and tags in place. Nothing left
requires further code changes — remaining steps (finishing the user's own review pass, packaging
for zip submission when ready) are entirely on the user's side.

## 2026-07-21 (cont. 5) — BUG-1 genuinely reproduced via a live transcript; deliberately left unfixed

User pasted a real transcript from the live Streamlit app that reproduced the ordinal-confirmation
gap for real: after 3 unnumbered slots were offered (Sep 15, 09:00/10:00/11:00), replying "ok
choose 1" did not book the first slot — it returned an entirely different batch (Sep 17) instead.
Reproduced cleanly in isolation (state seeded with the exact offered slots, single `run_turn` call)
to confirm root cause rather than trust the full-conversation replay, which itself diverged from
the live transcript at an earlier turn (see below) — same lesson as always: verify the specific
claim, don't assume a cascaded replay tells you why.

**Root cause, confirmed via real trace:** `CONFIRMATION_PROMPT_ADDENDUM`
(`app/modules/sched_advisor/advisor.py`) has instructions and worked examples for matching by
weekday name and by explicit date, but nothing for a numeric/positional reference ("1", "the first
one", "option 2"). The model's own returned reason for "ok choose 1" was literally *"Candidate
accepted a proposed time"* — it understood the intent — but it returned `decision="sched"` instead
of `"confirmed"` with a `confirmed_schedule_id`, because it has no instructed way to turn "1" into
a slot id. `decision="sched"` (not `"confirmed"`) then falls through to the plain date-lookup path,
which finds no date in "ok choose 1" and defaults to "nearest available slots after whatever was
already offered" — hence a silently different batch instead of a booking or an error.

**A concrete fix was scoped and reviewed, not implemented — user's explicit, deliberate choice**:
number the offered slots visibly in the message text (e.g. "1) Tue Sep 17 at 09:00  2) ..."), and
teach `CONFIRMATION_PROMPT_ADDENDUM` to match a bare number to the corresponding list position,
verified against the actual offered list the same way `confirmed_schedule_id` already is today —
additive alongside existing free-text matching, not a replacement. Also scoped: scenario tests for
"1"/"2"/"number 3", and a note that this almost certainly won't move the eval accuracy number since
none of the 15 dataset conversations use numbered replies — this is a real live-usage gap the
synthetic eval simply doesn't cover, not something the eval methodology would ever have caught.

**Two more things found while investigating, neither part of this bug:**
- A separate, smaller date-parsing gap: `date_resolver`'s month-name pattern matches "september
  2024 14" as month+year only, silently dropping the trailing "14" and defaulting to the 1st of
  the month. Confirmed via replay, not fixed, not in scope of BUG-1.
- The full-conversation replay of the user's transcript diverged from the live transcript at the
  bare "sep 2024" turn (month+year, no day) — my replay got a schedule offer, the live transcript
  got a decline, from the literal same input. Consistent with real LLM sampling variance at a
  genuinely ambiguous boundary case (this project has hit this before, e.g. the 2026-07-20 fix
  needing a retry due to "known temperature=0 structured-output sampling variance") — not chased,
  correctly attributed to variance rather than assumed to be a deterministic bug.

**Docs updated to reflect this honestly before submission**: `docs/PROJECT_TASKS.md`'s CORE-REV row
and `README.md`'s "Known limitations" section both corrected — BUG-1 was previously described as
"could not be reproduced"; that's no longer true, and leaving stale text in submitted
self-documentation would misrepresent the project's actual state. The decision to leave the fix
unimplemented is preserved as a deliberate choice, not confused with "couldn't find the bug." No
app/prompt code changed in this session; `git status` clean, everything already committed/pushed
before this entry.
