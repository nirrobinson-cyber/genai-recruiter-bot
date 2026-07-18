# GenAI Recruiter Bot — Full Project Specification & Development Plan

| | |
|---|---|
| **Project** | SMS-Based Recruiting Chatbot for a Python Developer Position (Multi-Agent System) |
| **Document type** | Software Specification & Development Work Plan |
| **Version** | 1.0 |
| **Status** | Approved for development |
| **Development tooling** | VS Code + Claude Code (agentic development) |
| **Course context** | Final project — GenAI / AI course |

---

## 1. Executive Summary

We are building a conversational AI system that simulates an SMS chatbot interacting with job candidates for a **Python Developer** position. The bot's mission per conversation is to gather and verify candidate information, answer candidate questions about the role, and drive the conversation toward one of two terminal outcomes: **scheduling an interview** with a human recruiter, or **politely ending** the conversation when the candidate is not interested.

The system is implemented as a **multi-agent architecture**: a **Main Agent** orchestrates each conversational turn and consults three specialized **Advisor agents** (Exit, Scheduling, Info) before responding. The proof of concept (PoC) replaces real SMS with a **Streamlit** chat UI deployed to Streamlit Community Cloud.

The system is evaluated against a **labeled dataset of real conversations** (`sms_conversations.json`), where every bot turn is annotated with the correct action (`continue` / `schedule` / `end`). Performance is reported with **Accuracy** and a **Confusion Matrix**.

---

## 2. Goals & Success Criteria

### 2.1 Functional Goals

| ID | Goal |
|----|------|
| G-1 | Conduct a natural, engaging turn-by-turn dialogue with a job candidate |
| G-2 | At every turn, correctly choose one of three actions: **Continue**, **Schedule**, **End** |
| G-3 | Answer candidate questions about the position using the job-description document (RAG) |
| G-4 | Propose and validate interview time slots against the recruiter availability database (SQL, via function calling) |
| G-5 | Detect disinterest and end conversations gracefully, without unnecessary follow-ups |
| G-6 | Collect candidate registration details (registration form) at conversation entry |

### 2.2 Measurable Success Criteria (Definition of Success)

| ID | Criterion | Target |
|----|-----------|--------|
| S-1 | Action-classification accuracy on the labeled test set | ≥ 85% (stretch: ≥ 90%) |
| S-2 | Confusion matrix produced and analyzed per class (continue/schedule/end) | Delivered in `test_evals.ipynb` |
| S-3 | Scheduling Advisor returns only slots that are truly `available = 1` in the DB | 100% (hard constraint) |
| S-4 | End-to-end demo runs on Streamlit Community Cloud | Live URL |
| S-5 | Repository follows the mandated project structure (§12) | Code review checklist |

### 2.3 Non-Goals (Out of Scope)

- Real SMS gateway integration (Twilio, etc.) — Streamlit stands in for SMS.
- Multi-position support — only the Python Developer role is in scope (the DB contains other positions, but the bot handles one).
- Recruiter-side UI, authentication, or CRM integration.
- Production hardening (rate limiting, monitoring, HA). Noted in §17 as future work.

> **Note from the project brief:** the real bot process includes additional options and complexities that were deliberately simplified for the scope of this project.

---

## 3. System Overview

### 3.1 Actors

| Actor | Description |
|-------|-------------|
| **User (Candidate)** | Job applicant chatting via the (simulated) SMS channel; also fills the registration form |
| **Main Agent** | LLM orchestrator; owns the dialogue, routes to advisors, produces the final reply |
| **Exit Advisor** | Binary classifier-style agent: *End Conversation* / *Don't End*. Fine-tuned model |
| **Scheduling Advisor** | Decides *Schedule* / *Don't Schedule*; on Schedule, queries the SQL availability DB via function calling |
| **Info Advisor** | Decides *Info Needed* / *Not Needed*; on Needed, retrieves from the Chroma vector DB (RAG over the job description) and drives the conversation toward scheduling |

### 3.2 High-Level Architecture

```
                        ┌──────────────────────────────┐
                        │        Streamlit UI          │
                        │  (chat + registration form)  │
                        └──────────────┬───────────────┘
                                       │ user message / form data
                                       ▼
                        ┌──────────────────────────────┐
                        │          MAIN AGENT          │◄─────────────┐
                        │  receive → route → decide →  │              │
                        │  respond (Continue/Sched/End)│              │ advisor
                        └───────┬───────┬──────┬───────┘              │ outputs
                                │       │      │                      │
              ┌─────────────────┘       │      └───────────────┐      │
              ▼                         ▼                      ▼      │
   ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
   │    EXIT ADVISOR    │   │    SCHED ADVISOR   │   │    INFO ADVISOR    │
   │ (fine-tuned model) │   │  End? ──► SQL tool │   │ Need? ──► RAG      │
   │ End / Don't End    │   │  (function calling)│   │ (Chroma vector DB) │
   └────────────────────┘   └─────────┬──────────┘   └─────────┬──────────┘
                                      │                        │
                                      ▼                        ▼
                            ┌──────────────────┐     ┌──────────────────┐
                            │  SQL: Schedule   │     │ Chroma: Job-Desc │
                            │  (db_Tech.sql)   │     │    embeddings    │
                            └──────────────────┘     └──────────────────┘
```

### 3.3 Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| LLM provider | **OpenAI API** (chat, embeddings, fine-tuning) | Mandated by project brief |
| Agent framework | **LangChain** (+ **LangGraph** for orchestration graph) | Mandated (LangChain: Agents, Memories, Tools); LangGraph maps 1:1 to the turn flowchart |
| Vector DB | **Chroma** (local instance) | Mandated; simple, embeddable |
| Relational DB | SQL Server schema per `db_Tech.sql` → **SQLite port for local/PoC** (see A-1, §18) | The seed script is T-SQL; PoC needs a zero-install DB |
| UI / PoC | **Streamlit**, deployed to Streamlit Community Cloud | Mandated (SMS stand-in) |
| Evaluation | **pandas, scikit-learn, matplotlib/seaborn** in Jupyter (`test_evals.ipynb`) | Accuracy + confusion matrix, per brief |
| Config & secrets | `.env` + `python-dotenv`; `pydantic-settings` for typed config | Never commit keys |
| Quality | `pytest`, `ruff` (lint + format), type hints throughout | Professional baseline |
| Runtime | Python ≥ 3.10, `venv` + `requirements.txt` | Mandated |

---

## 4. Conversational Turn — Detailed Flow (per `one_turn_flowchart.json`)

This section is the **authoritative behavioral contract** of the system. It formalizes the provided flowchart *"One Turn in the Conversation"* and must be implemented exactly as a LangGraph state graph.

### 4.1 Entry Points

1. **User Initiates / Responds** — a chat message arrives.
2. **Fill Registration Form** — the candidate submits the registration form (name, phone, etc.). Form data is injected into the conversation state and processed as input by the Main Agent.

Both edges converge into the Main Agent's `receive_and_process_input` node.

### 4.2 Node-by-Node Flow

| # | Node (flowchart id) | Actor | Behavior |
|---|--------------------|-------|----------|
| 1 | `receive_input_1` | Main Agent | Normalizes input, appends to chat history, prepares routing context |
| 2 | `decide_3_options` | Main Agent | **Decision (1 of 3):** route to Exit Advisor / Sched Advisor / Info Advisor |
| 3a | `send_exit` → `process_history_exit` | Exit Advisor | Receives the **complete chat history** |
| 4a | `decide_exit` | Exit Advisor | **Decision (1 of 2):** `End Conversation` / `Don't End Conv` |
| 5a | `send_main_from_exit` | Exit Advisor | Returns verdict + rationale to Main Agent |
| 3b | `send_sched` → `process_history_sched` | Sched Advisor | Receives the **complete chat history** |
| 4b | `decide_sched` | Sched Advisor | **Decision (1 of 2):** `Sched` / `Don't Sched` |
| 5b | `sql_retrieve_sched` *(only if `Sched`)* | Sched Advisor | **Data store access:** function-call into the SQL Schedule table; retrieves candidate slots (see §7) |
| 6b | `send_main_from_sched` | Sched Advisor | Returns verdict (+ slots if retrieved) to Main Agent |
| 3c | `send_info` → `process_history_info` | Info Advisor | Receives the **complete chat history** |
| 4c | `decide_info` | Info Advisor | **Decision (1 of 2):** `Info Needed` / `Info Not Needed` |
| 5c | `vector_retrieve_info` *(only if `Info Needed`)* | Info Advisor | **Data store access:** semantic retrieval from Chroma over the job description |
| 6c | `send_main_from_info` | Info Advisor | Returns verdict (+ retrieved context / drafted answer) to Main Agent |
| 7 | `receive_input_2` | Main Agent | Aggregates advisor output into state |
| 8 | `decide_final` | Main Agent | **Decision (1 of 2):** `Consult Advisor Again` (loop back to step 2) **or** `Sends Output` |
| 9 | `send_user` | Main Agent | Emits the final user-facing message, tagged with the turn action: `continue` / `schedule` / `end` |
| 10 | `end` | — | Turn terminates; UI awaits next user message (unless action was `end`) |

### 4.3 Critical Behavioral Rules Derived from the Flowchart

- **R-1 (Advisor loop):** the Main Agent MAY consult multiple advisors within a single turn (`decide_final → Consult Advisor Again`). Implement a **max-iterations guard** (default: 3 advisor consultations per turn) to prevent infinite loops.
- **R-2 (Full history):** every advisor receives the *complete* chat history, not a summary. Memory implementation must preserve the raw transcript.
- **R-3 (Conditional data access):** the SQL DB is queried **only** when Sched Advisor rules `Sched`; the vector DB is queried **only** when Info Advisor rules `Info Needed`. No speculative retrieval.
- **R-4 (Single output):** exactly one user-facing message is emitted per turn, always by the Main Agent (advisors never talk to the user directly).
- **R-5 (Action labeling):** every emitted turn carries exactly one action label from `{continue, schedule, end}` — this is what the evaluation harness compares against ground truth.

---

## 5. Component Specifications

### 5.1 Main Agent

**Responsibility:** own the dialogue; decide, per turn, which advisor(s) to consult; synthesize advisor outputs into the final action and user message.

| Aspect | Specification |
|--------|---------------|
| Model | OpenAI chat model (e.g., `gpt-4o-mini` for cost-effective PoC; configurable via `.env`) |
| Input | Conversation state: full chat history, registration data, advisor outputs so far this turn |
| Output contract | Structured JSON: `{ "action": "continue" \| "schedule" \| "end", "message": str, "consulted": [advisor names], "rationale": str }` |
| Prompting | System prompt defines role, tone (professional, friendly recruiter), the three actions, and routing heuristics. Few-shot examples drawn from `sms_conversations.json` patterns |
| Temperature | Low (0–0.3) for the routing/decision step; moderate (0.7) allowed for message phrasing |
| Memory | LangChain conversation memory holding the raw transcript (R-2) |
| Guards | Max 3 advisor consultations per turn (R-1); deterministic fallback: if guard trips, default to `continue` with a clarifying question |

**Routing heuristics (encoded in the system prompt, refined during Phase 4 tuning):**
- Candidate expresses disinterest / asks to stop / says "found a job" → consult **Exit Advisor**.
- Candidate proposes/accepts/rejects a time, or the conversation has matured enough to offer one → consult **Sched Advisor**.
- Candidate asks about the role, stack, company, work model, compensation → consult **Info Advisor**.
- Ambiguous → Info Advisor first (it also owns "keep engagement & steer toward scheduling").

### 5.2 Exit Advisor (fine-tuned)

**Responsibility:** given the full history, decide whether ending the conversation is the correct move.

| Aspect | Specification |
|--------|---------------|
| Model | **Fine-tuned** OpenAI model (per brief). Base: smallest fine-tunable chat model available on the account |
| Training data | Derived from `sms_conversations.json`: each recruiter turn becomes an example — history-so-far → binary label (`end` vs `not-end`). Augment with hand-written edge cases (opt-out requests, "stop texting me", polite refusals, ghosting patterns) |
| Output contract | `{ "decision": "end" \| "dont_end", "confidence": float, "reason": str }` |
| Fallback | If the fine-tuned model is unavailable (quota/cost), a prompted base model with few-shot examples serves as a drop-in behind the same interface (Strategy pattern) |

**Fine-tuning sub-plan (Phase 3):**
1. Build `app/modules/fine_tuning/dataset_builder.py` — transforms conversations to JSONL (`{"messages": [...]}` format).
2. Train/validation split (stratified on label; conversations never straddle the split — prevent leakage).
3. Launch job via OpenAI fine-tuning API; persist job/model IDs to `.env` / config.
4. Validate: precision/recall on held-out `end` cases (missing an `end` = harassing an uninterested candidate → optimize for **recall on `end`** while keeping false-ends low).

### 5.3 Scheduling Advisor

**Responsibility:** decide if it is the right moment to schedule; if so, retrieve and validate concrete slots from the SQL DB.

| Aspect | Specification |
|--------|---------------|
| Model | OpenAI chat model with **function calling / tools** enabled |
| Tools | `get_available_slots(position: str, from_date: date, to_date: date, limit: int = 3)` → rows from `dbo.Schedule` where `available = 1`; `book_slot(schedule_id: int)` → marks slot unavailable (PoC-level booking) |
| Date inference (per brief) | The advisor resolves relative expressions ("next Friday", "tomorrow afternoon") using the **conversation timestamp** as "now", then calls the tool with concrete dates and proposes the **three nearest available slots** |
| Output contract | `{ "decision": "sched" \| "dont_sched", "proposed_slots": [ {schedule_id, date, time} ], "reason": str }` |
| Hard rule | Never present a slot not verified against the DB in this turn (S-3) |

### 5.4 Info Advisor (RAG)

**Responsibility:** answer role questions from the job description; keep engagement; **actively steer toward the end goal — scheduling an interview**.

| Aspect | Specification |
|--------|---------------|
| Model | OpenAI chat model |
| Knowledge base | `Python_Developer_Job_Description.pdf` → chunked → embedded (OpenAI embeddings) → **Chroma** collection `job_description` |
| Retrieval | Top-k (k=3–4) similarity search on the candidate's question; retrieved chunks injected as grounded context |
| Output contract | `{ "decision": "info_needed" \| "info_not_needed", "draft_answer": str \| null, "sources": [chunk ids], "reason": str }` |
| Grounding rule | Answers about the role must come from retrieved chunks; if not found, say so honestly and pivot ("Happy to have the recruiter cover that in the interview — shall we find a time?") |
| Behavior | Every drafted answer ends with a gentle push toward scheduling when contextually appropriate |

### 5.5 Embedding Pipeline (offline, one-time)

`app/modules/embedding/`:
1. Load PDF (`pypdf` / LangChain `PyPDFLoader`).
2. Split: `RecursiveCharacterTextSplitter`, chunk_size≈500 tokens, overlap≈50.
3. Embed with OpenAI embeddings (`text-embedding-3-small`).
4. Persist to local Chroma (`data/chroma/`). Idempotent: re-running rebuilds the collection.
5. CLI entry: `python -m app.modules.embedding.build_index`.

---

## 6. Data Assets

| Asset | Role in system |
|-------|----------------|
| `sms_conversations.json` | 15 labeled real conversations. **Ground truth** for evaluation; source for Exit-Advisor fine-tuning data and few-shot examples. Each recruiter turn is labeled `continue`/`schedule`/`end` |
| `Python_Developer_Job_Description.pdf` | Knowledge base for the Info Advisor (RAG source) |
| `db_Tech.sql` | T-SQL seed script: `Tech.dbo.Schedule(ScheduleID, date, time, position, available)`; full-year 2024 slots, Sun+Tue–Fri, 09:00–17:00, four positions, pseudo-random availability |
| `one_turn_flowchart.json` | Formal flowchart of a single turn — the behavioral contract implemented in §4 |
| `GenAI_Project.pdf` | The official project brief (requirements source of record) |

**Dataset governance:** `sms_conversations.json` serves double duty (fine-tuning + evaluation). To avoid contamination: split at the **conversation level** — e.g., conversations used to fine-tune the Exit Advisor are excluded from the final evaluation set, or use k-fold across conversations. Document the split in `test_evals.ipynb`.

---

## 7. SQL Integration & Function Calling

### 7.1 Database

- Canonical schema: `db_Tech.sql` (SQL Server). For the PoC we **port the schema + seed to SQLite** (`data/tech.db`) via `app/modules/scheduling/db_setup.py`, preserving semantics (same columns, same availability distribution, weekday rules Sun+Tue–Fri, hours 09–17).
- Access layer: `sqlite3`/SQLAlchemy behind a thin repository class `ScheduleRepository` — swapping back to SQL Server later means changing a connection string, not code (S/OLID: dependency inversion).

### 7.2 Tool Definitions (LangChain tools)

```python
@tool
def get_available_slots(position: str, from_date: str, to_date: str, limit: int = 3) -> list[Slot]:
    """Return up to `limit` earliest available interview slots for `position`
    between from_date and to_date (ISO dates), ordered by date, time."""

@tool
def book_slot(schedule_id: int) -> BookingResult:
    """Mark the slot as booked (available=0). Returns confirmation payload."""
```

### 7.3 Relative-Date Resolution

Requirement from the brief: *"if the user mentions 'next Friday', it infers the current date from the time the conversation took place and combines it with the user's input… then suggests the three nearest available time slots."*

- "Now" = timestamp of the current conversation (in the PoC UI: wall clock; in evaluation replays: `start_time_utc` of the conversation).
- Implement `resolve_relative_date(expression: str, now: datetime) -> date_range` (LLM-assisted parse constrained to a JSON schema, with `dateutil` verification).
- Unit-test with a fixed `now` across expressions: "tomorrow", "next Friday", "Monday at 3 PM", "in two weeks".

---

## 8. Streamlit PoC (UI)

| Requirement | Specification |
|-------------|---------------|
| Entry screen | **Registration form** (flowchart entry point): full name, phone, email, years of Python experience → stored in session state, injected into the conversation |
| Chat screen | `st.chat_message` / `st.chat_input` SMS-style thread; bot messages show the (dev-mode) action badge `continue/schedule/end` |
| Dev panel (sidebar, toggleable) | Shows per-turn trace: which advisors were consulted, their verdicts, retrieved chunks/slots — invaluable for the demo and for grading ("impressive & educational") |
| Session | One conversation per session; "End" action locks the input with a polite closing state; "Reset" button starts fresh |
| Secrets | On Community Cloud use `st.secrets`; locally `.env`. Never hardcode keys |
| Deployment | Push to GitHub → connect Streamlit Community Cloud → `streamlit_app/streamlit_main.py` as entry |

---

## 9. Evaluation Strategy (`tests/test_evals.ipynb`)

**Method (per brief):** replay the labeled conversations; at every labeled recruiter turn, feed the system the history up to that point and record the action the Main Agent chooses; compare to the gold label.

1. Load `sms_conversations.json`; build (history, gold_action) pairs for all labeled turns.
2. Run the full multi-agent pipeline per pair (advisors included; SQL/vector access active; `now` = conversation timestamp).
3. Compute: **Accuracy**, per-class precision/recall/F1, **Confusion Matrix** (3×3: continue/schedule/end), rendered as a heatmap.
4. Error analysis section: list every misclassified turn with history snippet, chosen vs gold action, and the advisor trace — then a short written analysis of failure patterns.
5. (Stretch) Ablations: Main Agent alone vs full advisor pipeline; base vs fine-tuned Exit Advisor — quantifies the value of the architecture. Excellent material for the final presentation.

**Determinism:** temperature=0 and fixed seeds where the API allows; cache LLM responses (LangChain cache) so the notebook is re-runnable and cheap.

---

## 10. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| N-1 **Modularity** | Each agent/advisor is an isolated module exposing a uniform interface (`respond(state) -> AdvisorOutput`); swapping models or prompts touches one file |
| N-2 **Configuration** | All model names, temperatures, k-values, paths, guards in a single typed config (`app/config.py` reading `.env`); zero magic constants in logic code |
| N-3 **Structured outputs** | Every LLM decision is parsed via Pydantic schemas (LangChain structured output); parse failures retry once, then fall back deterministically |
| N-4 **Observability** | Python `logging` (JSON-ish format) of every advisor call: inputs hash, decision, latency, token usage. The Streamlit dev panel reads the same trace |
| N-5 **Error handling** | API timeouts/rate limits → exponential backoff (max 3); DB errors → user-safe apology message + logged stack trace; the bot never crashes mid-conversation |
| N-6 **Security** | `.env` git-ignored; `.env.example` committed; no PII beyond the demo dataset; keys only via env/secrets |
| N-7 **Cost control** | Small models by default; LLM response caching in dev/eval; token usage logged per turn |
| N-8 **Scalability path** | Stateless turn processing (state passed in, not global) → horizontally scalable behind a real SMS webhook later; DB behind repository interface → SQL Server/Postgres swap; documented in §17 |
| N-9 **Code quality** | Type hints everywhere; `ruff` clean; docstrings on public functions; `pytest` unit tests for pure logic (date resolution, dataset builder, repositories, prompt formatting) |

---

## 11. Testing Strategy

| Layer | What | Tool |
|-------|------|------|
| Unit | `resolve_relative_date`, `ScheduleRepository`, chunker, dataset builder, output-schema parsing | `pytest` (no API calls; mock LLM) |
| Integration | Each advisor end-to-end against a tiny fixture history (mock or recorded LLM responses via cache) | `pytest` + cassette/cache |
| System / Eval | Full pipeline vs labeled dataset | `tests/test_evals.ipynb` (§9) |
| Manual / Demo | Scripted happy-path + edge-path walkthroughs in Streamlit (schedule flow, refusal flow, question flow, opt-out flow) | Demo checklist in README |

---

## 12. Repository Structure (mandated by the brief, refined)

```text
genai-recruiter-bot/
├── .gitignore                     # venv, .env, data/chroma, *.db, __pycache__, caches
├── .env.example                   # documented env vars (no secrets)
├── requirements.txt
├── README.md                      # purpose, install, run, usage examples, structure (§14)
├── CLAUDE.md                      # Claude Code project memory (§15)
├── docs/
│   ├── PROJECT_SPECIFICATION.md   # this document
│   ├── GenAI_Project.pdf          # official brief
│   └── one_turn_flowchart.json    # behavioral contract
├── data/
│   ├── raw/
│   │   ├── sms_conversations.json
│   │   ├── Python_Developer_Job_Description.pdf
│   │   └── db_Tech.sql
│   ├── chroma/                    # vector store (git-ignored, rebuildable)
│   └── tech.db                    # SQLite port (git-ignored, rebuildable)
├── app/
│   ├── __init__.py
│   ├── main.py                    # CLI entry point (run a conversation in terminal)
│   ├── config.py                  # typed settings from .env
│   ├── graph.py                   # LangGraph turn graph (implements §4)
│   ├── state.py                   # ConversationState schema
│   └── modules/
│       ├── __init__.py
│       ├── main_agent/
│       │   ├── __init__.py
│       │   ├── agent.py
│       │   └── prompts.py
│       ├── exit_advisor/
│       │   ├── __init__.py
│       │   ├── advisor.py         # fine-tuned + prompted fallback (Strategy)
│       │   └── prompts.py
│       ├── sched_advisor/
│       │   ├── __init__.py
│       │   ├── advisor.py
│       │   ├── tools.py           # get_available_slots, book_slot
│       │   ├── date_resolver.py
│       │   └── repository.py      # ScheduleRepository
│       ├── info_advisor/
│       │   ├── __init__.py
│       │   ├── advisor.py
│       │   └── retriever.py       # Chroma access
│       ├── embedding/
│       │   ├── __init__.py
│       │   └── build_index.py     # offline pipeline (§5.5)
│       ├── fine_tuning/
│       │   ├── __init__.py
│       │   ├── dataset_builder.py
│       │   └── launch_job.py
│       └── scheduling/
│           ├── __init__.py
│           └── db_setup.py        # SQLite port + seed
├── streamlit_app/
│   ├── __init__.py
│   ├── streamlit_main.py
│   └── components/                # form, chat, dev trace panel
└── tests/
    ├── test_main.py
    ├── test_date_resolver.py
    ├── test_repository.py
    ├── test_dataset_builder.py
    └── test_evals.ipynb           # accuracy + confusion matrix (§9)
```

---

## 13. Development Work Plan (Phases, Deliverables, Acceptance)

Each phase is a self-contained Claude Code work session with a clear "definition of done". Commit at every green checkpoint (conventional commits: `feat:`, `test:`, `docs:`…). **Order matters** — later phases depend on earlier interfaces.

### Phase 0 — Repository Bootstrap (~0.5 day)
- Init git, `.gitignore`, venv, `requirements.txt`, `.env.example`, `config.py`, logging setup.
- Copy data assets into `data/raw/` and `docs/`.
- Write `CLAUDE.md` (§15).
- ✅ **Done when:** `python -m app.main --help` runs; `pytest` runs (0 tests OK); repo pushed.

### Phase 1 — Data Layer (~1 day)
- `db_setup.py`: SQLite port of `db_Tech.sql` (schema + full-year seed, same rules).
- `ScheduleRepository` + unit tests.
- `build_index.py`: PDF → chunks → embeddings → Chroma; smoke-test retrieval ("what cloud platforms?" returns AWS/GCP/Azure chunk).
- ✅ **Done when:** `pytest tests/test_repository.py` green; a retrieval smoke script prints relevant chunks.

### Phase 2 — Advisors (prompted versions) (~2 days)
- Implement Info Advisor (RAG), Sched Advisor (tools + `date_resolver`, fully unit-tested), Exit Advisor (prompted baseline).
- Uniform `AdvisorOutput` Pydantic contracts; structured-output parsing with retry/fallback (N-3).
- ✅ **Done when:** each advisor answers a scripted fixture history correctly in an integration test; slots returned always verified available.

### Phase 3 — Exit Advisor Fine-Tuning (~1 day, parallelizable with Phase 4)
- `dataset_builder.py` (+ unit tests): conversations → JSONL, conversation-level split, no leakage.
- Launch fine-tune, record model ID, wire into advisor behind the Strategy interface.
- ✅ **Done when:** fine-tuned model beats the prompted baseline on held-out `end` recall; both selectable via config.

### Phase 4 — Main Agent & LangGraph Orchestration (~2 days)
- `state.py`, `graph.py`: implement §4 exactly — 3-way routing, advisor nodes, conditional data-access edges, re-consult loop with guard, final output node.
- `main.py`: terminal chat loop for fast iteration.
- Prompt iteration on the Main Agent using few-shot patterns from the dataset.
- ✅ **Done when:** all four canonical flows work in the terminal: Q&A flow, scheduling flow (incl. relative dates), refusal→end flow, opt-out→end flow.

### Phase 5 — Evaluation (~1 day)
- `test_evals.ipynb` per §9: replay harness, accuracy, 3×3 confusion matrix heatmap, error analysis, (stretch) ablations.
- Tune prompts/routing against failures; re-run; document before/after.
- ✅ **Done when:** S-1 target met or gap analyzed and documented.

### Phase 6 — Streamlit PoC & Deployment (~1 day)
- Registration form → chat UI → dev trace panel (§8).
- Deploy to Streamlit Community Cloud with `st.secrets`.
- ✅ **Done when:** live URL demo passes the manual demo checklist.

### Phase 7 — Documentation & Polish (~0.5 day)
- Real `README.md` (§14), final lint pass, screenshots/GIF of the demo, tag `v1.0`.
- ✅ **Done when:** a stranger can clone, install, run locally, and understand the architecture from the README alone.

**Total: ~8–9 focused days.** Critical path: 0 → 1 → 2 → 4 → 5; Phases 3 and 6 can overlap it.

---

## 14. README.md Requirements (per brief)

Must include: project purpose · installation & local run instructions (venv, `.env`, DB/index build commands, `streamlit run`) · basic usage examples (terminal + UI) · project structure · architecture summary with the turn-flow diagram · evaluation results (accuracy + confusion-matrix image) · link to the live Streamlit deployment.

---

## 15. Working with Claude Code (VS Code) — Project Conventions

Create `CLAUDE.md` at repo root with, at minimum:

```markdown
# GenAI Recruiter Bot — Claude Code Context

## What this is
Multi-agent SMS-style recruiting chatbot (Main Agent + Exit/Sched/Info advisors)
for a Python Developer role. Full spec: docs/PROJECT_SPECIFICATION.md — READ IT
before non-trivial changes. The turn behavior contract is docs/one_turn_flowchart.json.

## Commands
- Run terminal chat:  python -m app.main
- Build vector index: python -m app.modules.embedding.build_index
- Build SQLite DB:    python -m app.modules.scheduling.db_setup
- UI:                 streamlit run streamlit_app/streamlit_main.py
- Tests:              pytest        Lint: ruff check . && ruff format .

## Hard rules
- Never commit .env or API keys. Use config.py for all constants.
- Every LLM decision goes through a Pydantic schema (no free-text parsing).
- Advisors never emit user-facing text; only the Main Agent does.
- Sched slots must be verified against the DB in the same turn.
- Max 3 advisor consultations per turn.
- New logic ⇒ new/updated pytest tests in the same commit.

## Workflow
Explore → Plan → Implement → Test → Commit (conventional commits).
Work phase-by-phase per spec §13; do not skip acceptance criteria.
```

**Recommended session pattern per phase:** open Claude Code → ask it to read the spec section for the phase → request a plan → approve → implement with tests → run `pytest`/`ruff` → commit.

---

## 16. Risks & Mitigations

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| 1 | LLM misroutes actions → low accuracy | S-1 fails | Few-shot from dataset, temp=0 decisions, error-analysis loop (Phase 5), advisor architecture itself narrows each decision |
| 2 | Fine-tuning cost/quota/latency | Phase 3 blocked | Prompted Exit Advisor is a first-class fallback behind the same interface |
| 3 | Eval contamination (same data trains & tests) | Untrustworthy metrics | Conversation-level split, documented in notebook |
| 4 | 2024-only DB seed vs "today" demos | No slots found live | Demo mode pins `now` to a 2024 date via config; or reseed script parameterizes the year |
| 5 | Non-deterministic evals | Unreproducible grades | temp=0, seeds, LLM response cache |
| 6 | API cost during iteration | Budget | Small models, cache, token logging (N-7) |
| 7 | Advisor consult loop runs away | Latency/cost | Hard guard R-1 + logged trace |

---

## 17. Scalability & Future Extensions (documented, not built)

Real SMS gateway (Twilio webhook → the same stateless turn graph) · multi-position support (position-aware routing + per-role vector collections) · Postgres/SQL Server via the repository interface · recruiter dashboard · human-handoff escalation · conversation analytics · guardrails/moderation layer · A/B testing of prompts.

The architecture already supports these: stateless turn processing, repository-abstracted storage, config-driven models, uniform advisor interfaces.

---

## 18. Assumptions & Open Decisions

| ID | Assumption / Decision | Status |
|----|----------------------|--------|
| A-1 | SQLite port for the PoC instead of a live SQL Server instance (semantics preserved; T-SQL script kept as the canonical schema) | **Confirm** — if the course requires actual SQL Server, Phase 1 swaps the driver only |
| A-2 | OpenAI models per the brief (not Anthropic), exact model names configurable | Assumed |
| A-3 | English-language conversations (dataset is English) | Assumed |
| A-4 | "Booking" a slot = flipping `available` to 0 (no calendar invite integration) | Assumed |
| A-5 | Evaluation replays use conversation `start_time_utc` as "now" for date resolution | Assumed |

---

*End of specification — v1.0. This document is the single source of truth for development; changes go through a version bump and a short changelog entry below.*

## Changelog
- **v1.0** — Initial full specification, incorporating the project brief (`GenAI_Project.pdf`), the formal turn flowchart (`one_turn_flowchart.json`), and all provided data assets.
