"""Tests for the info-advisor retrieval layer."""

from __future__ import annotations

from app.modules.info_advisor.retriever import retrieve_context


def test_retrieve_context_returns_relevant_chunks() -> None:
    result = retrieve_context("What stack is required?", top_k=3)

    assert result is not None
    assert len(result["documents"]) <= 3
    assert result["documents"]
