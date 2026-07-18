# GenAI Recruiter Bot

Multi-agent SMS-style recruiting chatbot for a Python Developer position
(Main Agent + Exit / Scheduling / Info advisors). **GenAI course final project.**

> 🚧 Bootstrap stage (Epic E0). Full README arrives in Phase 7 (GRB-070).
> The source of truth is [`docs/PROJECT_SPECIFICATION.md`](docs/PROJECT_SPECIFICATION.md).

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # fill in OPENAI_API_KEY
python -m app.main --check-config
pytest && ruff check .
```
