"""Retrieve grounded context for the Info Advisor from the local index."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.config import get_settings

try:
    import chromadb
except ImportError:  # pragma: no cover - optional dependency fallback
    chromadb = None


def _hash_query(query: str, dimensions: int = 32) -> list[float]:
    """Create a deterministic embedding fallback for local/offline retrieval."""

    vector = [0.0] * dimensions
    for index, char in enumerate(query.encode("utf-8")):
        vector[index % dimensions] += float(char) / 255.0

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        vector = [value / magnitude for value in vector]
    return vector


def retrieve_context(question: str, top_k: int | None = None) -> dict[str, Any] | None:
    """Retrieve the most relevant chunks for a question from the local index."""

    settings = get_settings()
    top_k = top_k or settings.retrieval_top_k
    persist_dir = Path(settings.chroma_persist_dir)
    collection_name = settings.chroma_collection

    if chromadb is not None:
        try:
            client = chromadb.PersistentClient(path=str(persist_dir))
            collection = client.get_collection(name=collection_name)
            results = collection.query(query_embeddings=[_hash_query(question)], n_results=top_k)
            documents = results.get("documents", [[]])[0]
            ids = results.get("ids", [[]])[0]
            return {
                "question": question,
                "documents": documents,
                "ids": ids,
                "collection": collection_name,
                "top_k": top_k,
            }
        except Exception:
            pass

    metadata_path = persist_dir / f"{collection_name}.json"
    if metadata_path.exists():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        documents = payload.get("documents", [])[:top_k]
        return {
            "question": question,
            "documents": documents,
            "ids": [f"chunk-{index}" for index in range(len(documents))],
            "collection": collection_name,
            "top_k": top_k,
        }

    return {
        "question": question,
        "documents": [],
        "ids": [],
        "collection": collection_name,
        "top_k": top_k,
    }
