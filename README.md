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

```mermaid
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
```

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

```text
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
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # fill in OPENAI_API_KEY
python -m app.modules.scheduling.db_setup             # build data/tech.db (rebuildable)
python -m app.modules.embedding.build_index           # build the Chroma vector index
python -m app.main --check-config                     # sanity check
```

`.env` also carries `DEMO_NOW_OVERRIDE=2024-04-15T10:00:00Z` — the seeded DB's slots live in
2024, so date resolution needs "now" pinned there for a working demo (never edit
`.env.example` with a real key; only `.env` is git-ignored).

## Usage

**Terminal chat:**

```bash
python -m app.main
```

```
Recruiter bot ready. Type 'quit' to exit.
You: I've been using Python professionally for five years, mostly for data analysis.
Bot [continue]: ...
You: Can we schedule an interview for tomorrow?
Bot [schedule]: I can offer these interview times: 2024-04-16 at 10:00:00; ... Which works best for you?
You: The first one
Bot [end]: Great, you're all set! Your interview is confirmed for 2024-04-16 at 10:00:00.
```

**Streamlit UI** (registration form → SMS-style chat → toggleable dev trace panel showing every
advisor consulted, its decision/reason, and retrieved slots/chunks):

```bash
streamlit run streamlit_app/streamlit_main.py
```

## Evaluation

`tests/eval_replay.py` replays the labeled dataset conversations through the real graph/API and
reports accuracy, per-class precision/recall/F1, and a confusion matrix; `tests/test_evals.ipynb`
is the formal notebook deliverable (spec §9) with the full error analysis.

- **Isolated per-turn replay** (`--mode isolated`, the notebook's baseline methodology): **52.3%**
  (23/44). Confusion matrix: [`docs/eval_confusion_matrix.png`](docs/eval_confusion_matrix.png).
- **Sequential full-conversation replay** (`--mode sequential`, default — one real conversation
  state walked turn-by-turn, matching spec §9's "feed the system the history up to that point"
  literally): **65.9% raw (29/44), 82.9% adjusted (29/35)** once conversations where our bot's
  own generated offer necessarily diverges from the dataset's scripted one are excluded (tagged
  automatically — see `_is_divergence_artifact` in `tests/eval_replay.py`) — **exceeding the
  CORE-REV ≥75% adjusted target** for the first time. This number moves whenever routing/
  scheduling code changes, since the bot's own decisions shape the rest of each conversation —
  see `docs/DEVLOG.md`'s 2026-07-20/2026-07-21 entries for the full path here: a routing-prompt
  fix (re-deriving an escalation-timing pattern previously dismissed as "unresolvable ground
  truth" across the full 15-conversation dataset instead of 2, +4.5pp/+5.9pp), then a same-turn
  "double-consult inconsistency" fix in `app/graph.py` (+9.1pp/+9.4pp, crossed the target). A
  separately-investigated "slot confirmation" pattern turned out not to be a code bug at all —
  our system's real-time nearest-available-slot offering structurally can't always match a
  synthetic dataset's fixed script — confirmed via full replay and correctly tagged as a
  divergence artifact rather than patched.

Neither run meets the spec's 85% target; the honest gap analysis (ranked failure patterns, what
would actually close the gap) is in the notebook and `docs/DEVLOG.md`'s CORE-REV entries — the
largest remaining pattern turned out to have genuinely inconsistent ground truth in the dataset
itself (identical candidate messages carry opposite gold labels in different conversations), not
a fixable routing bug.

```bash
python -m tests.eval_replay              # sequential (default)
python -m tests.eval_replay --mode both  # both, for comparison
```

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

## Known open items

- **Ordinal/partial slot confirmation** (e.g. "the second one") — could not be reproduced in 3
  independent real-execution test paths; still needs a live-reproduced transcript (dev trace
  panel) before it can be diagnosed.
- **`continue`-vs-`schedule` action labeling** — a turn where the Sched Advisor correctly declines
  a vague confirmation and the bot restates the open offer is labeled `action="continue"`, but the
  eval gold expects `"schedule"` for that turn. Identified during the 2026-07-20 fix pass; not yet
  scoped or fixed.
- Spec's 85% eval accuracy target (S-1) is not met at either replay mode — see the Evaluation
  section above for the honest gap analysis.

## Live deployment

Not yet deployed — the Streamlit UI is built and verified locally (`streamlit run
streamlit_app/streamlit_main.py`), but connecting it to Streamlit Community Cloud requires an
account and a GitHub push that are outside this repo's own scope.

## Testing & lint

```bash
pytest              # full suite, zero real API calls (123 tests, all mocked)
pytest -m real_api  # scenario tests that DO call the real API/DB (see tests/test_scenarios.py)
ruff check .
```

## Current status

Epics E0–E2, E3, E4, E6 are done — E3 (fine-tuning) closed via its own documented-fallback
acceptance criterion, since the real fine-tune job is blocked by OpenAI's platform deprecation
(see the Evaluation section above), not by anything left undone here. E5 (evaluation) is done as
an honest-gap-analysis outcome; E7 (this document) is in progress. See
[`docs/PROJECT_TASKS.md`](docs/PROJECT_TASKS.md) §0 for the live per-task status table and
[`docs/DEVLOG.md`](docs/DEVLOG.md) for the full session-by-session history.
