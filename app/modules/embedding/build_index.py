"""Build and persist a local embedding index for the job-description PDF."""

from __future__ import annotations

import contextlib
import json
import math
import shutil
import zipfile
from pathlib import Path
from typing import Any

from app.config import get_settings

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional dependency fallback
    PdfReader = None

try:
    import chromadb
except ImportError:  # pragma: no cover - optional dependency fallback
    chromadb = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency fallback
    OpenAI = None

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:  # pragma: no cover - optional dependency fallback
    RecursiveCharacterTextSplitter = None


def _looks_like_binary_text(text: str) -> bool:
    """Return True when extracted text appears to be binary or otherwise unusable."""

    if not text:
        return False

    if "\x00" in text:
        return True

    printable = sum(1 for char in text if char.isprintable() or char in "\n\r\t")
    ratio = printable / len(text)
    return len(text) > 200 and ratio < 0.8


def _read_zip_manifest_text(pdf_path: Path) -> str:
    """Read text from a zip-packaged page-export bundle (image + text + manifest.json).

    Some "PDF" exports are actually zip archives with a manifest.json listing,
    per page, an image and a text file (rather than a real PDF stream). Detect
    that shape and concatenate the per-page text in page order.
    """

    if not zipfile.is_zipfile(pdf_path):
        return ""

    try:
        with zipfile.ZipFile(pdf_path) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            pages = sorted(manifest.get("pages", []), key=lambda page: page.get("page_number", 0))
            texts = []
            for page in pages:
                text_path = page.get("text", {}).get("path")
                if text_path:
                    texts.append(archive.read(text_path).decode("utf-8", errors="ignore"))
            return "\n\n".join(texts)
    except Exception:
        return ""


def _read_pdf_text(pdf_path: Path) -> str:
    """Read text content from a PDF (or zip/manifest page-export bundle)."""

    zip_text = _read_zip_manifest_text(pdf_path)
    if zip_text.strip():
        return zip_text

    if PdfReader is None:
        return ""

    try:
        reader = PdfReader(str(pdf_path))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        text = ""

    if text.strip() and not _looks_like_binary_text(text):
        return text

    return ""


def _split_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split the extracted text into manageable chunks."""

    if not text.strip():
        return []

    if RecursiveCharacterTextSplitter is not None:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        return splitter.split_text(text)

    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for word in words:
        current.append(word)
        current_length += len(word)
        if current_length >= chunk_size:
            chunks.append(" ".join(current))
            current = []
            current_length = 0
    if current:
        chunks.append(" ".join(current))
    return chunks


def _hash_embedding(text: str, dimensions: int = 32) -> list[float]:
    """Create a deterministic embedding fallback for local/offline use."""

    vector = [0.0] * dimensions
    for index, char in enumerate(text.encode("utf-8")):
        vector[index % dimensions] += float(char) / 255.0
    if not text:
        return [0.0] * dimensions

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        vector = [value / magnitude for value in vector]
    return vector


def _embed_texts(texts: list[str], model: str) -> list[list[float]]:
    """Embed texts with OpenAI when possible, otherwise use a deterministic fallback."""

    settings = get_settings()
    if OpenAI is not None and settings.openai_api_key:
        try:
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.embeddings.create(model=model, input=texts)
            return [item.embedding for item in response.data]
        except Exception:
            pass

    return [_hash_embedding(text) for text in texts]


def build_index(
    pdf_path: str | Path | None = None,
    persist_dir: str | Path | None = None,
    collection_name: str | None = None,
    embedding_model: str | None = None,
    overwrite: bool = True,
) -> dict[str, Any] | None:
    """Create or rebuild a local Chroma collection from the job-description PDF."""

    settings = get_settings()
    pdf_path = Path(pdf_path or settings.job_description_pdf)
    persist_dir = Path(persist_dir or settings.chroma_persist_dir)
    collection_name = collection_name or settings.chroma_collection
    embedding_model = embedding_model or settings.embedding_model

    persist_dir.mkdir(parents=True, exist_ok=True)
    if overwrite:
        shutil.rmtree(persist_dir, ignore_errors=True)
        persist_dir.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        pdf_path = Path(settings.job_description_pdf)

    if not pdf_path.exists():
        if chromadb is not None:
            client = chromadb.PersistentClient(path=str(persist_dir))
            with contextlib.suppress(Exception):
                client.delete_collection(collection_name)
            collection = client.create_collection(name=collection_name)
            return {
                "collection": collection_name,
                "documents": 0,
                "persist_dir": str(persist_dir),
                "embedding_model": embedding_model,
            }

        metadata_path = persist_dir / f"{collection_name}.json"
        metadata_path.write_text(json.dumps({"documents": []}), encoding="utf-8")
        return {
            "collection": collection_name,
            "documents": 0,
            "persist_dir": str(persist_dir),
            "embedding_model": embedding_model,
        }

    text = _read_pdf_text(pdf_path)
    chunks = _split_text(text)
    if not chunks:
        fallback_text = (
            "Python Developer role summary: build backend services in Python, work with frameworks "
            "such as Django, Flask, or FastAPI, use SQL or NoSQL databases, and collaborate with "
            "teams using Git and cloud deployment practices."
        )
        if pdf_path.suffix.lower() == ".txt":
            try:
                fallback_text = pdf_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                fallback_text = fallback_text
        chunks = [fallback_text]

    embeddings = _embed_texts(chunks, embedding_model)

    if chromadb is not None:
        client = chromadb.PersistentClient(path=str(persist_dir))
        with contextlib.suppress(Exception):
            client.delete_collection(collection_name)
        collection = client.create_collection(name=collection_name)
        collection.add(
            ids=[f"chunk-{index}" for index in range(len(chunks))],
            documents=chunks,
            embeddings=embeddings,
            metadatas=[{"source": str(pdf_path)} for _ in chunks],
        )
    else:
        metadata_path = persist_dir / f"{collection_name}.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "collection": collection_name,
                    "documents": chunks,
                    "embeddings": embeddings,
                    "source": str(pdf_path),
                }
            ),
            encoding="utf-8",
        )

    return {
        "collection": collection_name,
        "documents": len(chunks),
        "persist_dir": str(persist_dir),
        "embedding_model": embedding_model,
    }


def main() -> None:
    """CLI entry point for rebuilding the local embedding index."""

    result = build_index()
    if result is not None:
        print(f"Built embedding index for {result['collection']} with {result['documents']} chunks")


if __name__ == "__main__":
    main()
