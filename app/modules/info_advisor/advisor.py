"""Info Advisor (spec §5.4) — RAG-grounded answers, steering towards scheduling.

Retrieval (Chroma, local/free) always runs first so the LLM's info_needed
decision and its drafted answer can both be grounded in the same pass — a
local vector lookup isn't the kind of costly call rule R-3 is guarding
against (unlike a paid completion/embedding call), so this doesn't need a
separate decide-then-retrieve round trip.
"""

from __future__ import annotations

from app.config import get_settings
from app.llm_client import cached_parse, history_to_messages
from app.schemas import InfoAdvisorOutput
from app.structured_output import get_structured_output

from .retriever import retrieve_context

SYSTEM_PROMPT = """You are the Info Advisor for a recruiting SMS chatbot hiring for a \
Python Developer role. Given the complete chat history and retrieved job-description \
context, decide whether the candidate is asking something that needs a role-related \
answer ("info_needed") or not ("info_not_needed").

If info is needed: draft a short, honest answer grounded ONLY in the retrieved context. \
If the context doesn't cover the question, say so honestly instead of guessing, and \
pivot toward scheduling an interview so the recruiter can cover it directly. Whenever \
contextually appropriate, end your answer with a gentle nudge toward scheduling an \
interview. List the ids of any retrieved chunks you actually used in `sources`.

If info is not needed (e.g. the candidate is just acknowledging, scheduling, or ending \
the conversation), leave draft_answer null and sources empty.
"""


def _latest_user_message(history: list[dict[str, str]]) -> str:
    for turn in reversed(history):
        if turn["role"] == "user":
            return turn["content"]
    return ""


def _heuristic_fallback(documents: list[str], sources: list[str]) -> InfoAdvisorOutput:
    """Deterministic fallback if the LLM call fails: documents-found heuristic."""

    if documents:
        return InfoAdvisorOutput(
            decision="info_needed",
            draft_answer="Here is the most relevant information I found: "
            + " ".join(documents[:2]),
            sources=sources,
            reason="LLM call failed after retry; falling back to retrieved chunks directly",
        )
    return InfoAdvisorOutput(
        decision="info_not_needed",
        draft_answer="I can help with that. Please tell me more about the role and the interview process.",
        sources=[],
        reason="LLM call failed after retry; no matching chunks retrieved either",
    )


def _call_llm(
    history: list[dict[str, str]], documents: list[str], sources: list[str]
) -> InfoAdvisorOutput:
    settings = get_settings()
    messages = history_to_messages(SYSTEM_PROMPT, history)
    if documents:
        context_block = "\n\n".join(
            f"[{doc_id}] {text}" for doc_id, text in zip(sources, documents, strict=True)
        )
        messages.append(
            {"role": "system", "content": f"Retrieved job-description context:\n{context_block}"}
        )
    else:
        messages.append(
            {
                "role": "system",
                "content": "No job-description context was retrieved for this question.",
            }
        )

    return cached_parse(
        model=settings.advisor_model,
        temperature=settings.decision_temperature,
        messages=messages,
        response_format=InfoAdvisorOutput,
    )


def draft_answer(history: list[dict[str, str]], top_k: int = 4) -> InfoAdvisorOutput:
    """Return a grounded answer draft from the complete chat history (rule R-2, N-3)."""

    question = _latest_user_message(history)
    context = retrieve_context(question, top_k=top_k)
    documents = context.get("documents", []) if context else []
    sources = context.get("ids", []) if context else []

    fallback = _heuristic_fallback(documents, sources)
    return get_structured_output(lambda: _call_llm(history, documents, sources), fallback=fallback)
