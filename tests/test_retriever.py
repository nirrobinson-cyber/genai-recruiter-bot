"""Tests for the Info Advisor's retriever (query/document embedding-space parity).

Regression coverage for a real bug: retrieve_context always hash-embedded the
query while build_index embeds documents with real OpenAI embeddings whenever
an API key is present, so query and document vectors lived in unrelated
vector spaces and similarity search was effectively meaningless.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.info_advisor import retriever


class _FakeEmbeddingsResponse:
    def __init__(self, embedding: list[float]) -> None:
        self.data = [SimpleNamespace(embedding=embedding)]


class _FakeOpenAIClient:
    def __init__(
        self, embedding: list[float] | None = None, error: Exception | None = None
    ) -> None:
        self._embedding = embedding
        self._error = error
        self.calls: list[dict] = []
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, model: str, input: list[str]) -> _FakeEmbeddingsResponse:
        self.calls.append({"model": model, "input": input})
        if self._error is not None:
            raise self._error
        return _FakeEmbeddingsResponse(self._embedding)


def test_embed_query_uses_openai_when_api_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_embedding = [0.1, 0.2, 0.3]
    fake_client = _FakeOpenAIClient(embedding=fake_embedding)
    monkeypatch.setattr(
        retriever, "get_settings", lambda: SimpleNamespace(openai_api_key="test-key")
    )
    monkeypatch.setattr(retriever, "OpenAI", lambda api_key: fake_client)

    result = retriever._embed_query("which languages should I know?", "text-embedding-3-small")

    assert result == fake_embedding
    assert fake_client.calls == [
        {"model": "text-embedding-3-small", "input": ["which languages should I know?"]}
    ]


def test_embed_query_falls_back_to_hash_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retriever, "get_settings", lambda: SimpleNamespace(openai_api_key=""))

    result = retriever._embed_query("hello", "text-embedding-3-small")

    assert result == retriever._hash_query("hello")


def test_embed_query_falls_back_to_hash_on_openai_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeOpenAIClient(error=RuntimeError("simulated API failure"))
    monkeypatch.setattr(
        retriever, "get_settings", lambda: SimpleNamespace(openai_api_key="test-key")
    )
    monkeypatch.setattr(retriever, "OpenAI", lambda api_key: fake_client)

    result = retriever._embed_query("hello", "text-embedding-3-small")

    assert result == retriever._hash_query("hello")


def test_retrieve_context_queries_chroma_with_embed_query_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_embedding = [0.4, 0.5]
    captured: dict = {}

    class _FakeCollection:
        def query(self, query_embeddings: list[list[float]], n_results: int) -> dict:
            captured["query_embeddings"] = query_embeddings
            captured["n_results"] = n_results
            return {"documents": [["chunk text"]], "ids": [["chunk-4"]]}

    class _FakeChromaClient:
        def __init__(self, path: str) -> None:
            pass

        def get_collection(self, name: str) -> _FakeCollection:
            return _FakeCollection()

    monkeypatch.setattr(retriever, "chromadb", SimpleNamespace(PersistentClient=_FakeChromaClient))
    monkeypatch.setattr(retriever, "_embed_query", lambda question, model: fake_embedding)
    monkeypatch.setattr(
        retriever,
        "get_settings",
        lambda: SimpleNamespace(
            retrieval_top_k=4,
            chroma_persist_dir="data/chroma",
            chroma_collection="job_description",
            embedding_model="text-embedding-3-small",
        ),
    )

    result = retriever.retrieve_context("which languages should I know?")

    assert captured["query_embeddings"] == [fake_embedding]
    assert result["documents"] == ["chunk text"]
    assert result["ids"] == ["chunk-4"]
