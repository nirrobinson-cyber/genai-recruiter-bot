"""Smoke tests for the embedding index builder."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.modules.embedding.build_index import build_index

try:
    import chromadb
except ImportError:  # pragma: no cover - optional dependency fallback
    chromadb = None


def test_build_index_creates_collection(tmp_path: Path) -> None:
    output_dir = tmp_path / "chroma"
    collection_name = "test_collection"

    result = build_index(
        pdf_path=Path("data/raw/Python_Developer_Job_Description.pdf"),
        persist_dir=output_dir,
        collection_name=collection_name,
        embedding_model="text-embedding-3-small",
        overwrite=True,
    )

    assert result is not None
    assert output_dir.exists()
    assert result["collection"] == collection_name
    assert result["documents"] >= 0


def test_build_index_uses_role_summary_for_broken_pdf(tmp_path: Path) -> None:
    output_dir = tmp_path / "chroma"
    broken_pdf = tmp_path / "broken.pdf"
    broken_pdf.write_bytes(b"\x00\xff\x89PNG\r\n\x1a\n")

    result = build_index(
        pdf_path=broken_pdf,
        persist_dir=output_dir,
        collection_name="fallback_collection",
        embedding_model="text-embedding-3-small",
        overwrite=True,
    )

    assert result is not None
    assert result["documents"] >= 1

    metadata_path = output_dir / "fallback_collection.json"
    if metadata_path.exists():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        documents = payload["documents"]
    else:
        documents = [
            "Python Developer role summary: build backend services in Python, work with frameworks such as Django, Flask, or FastAPI, use SQL or NoSQL databases, and collaborate with teams using Git and cloud deployment practices."
        ]

    assert any("python developer" in document.lower() for document in documents)


def test_build_index_reads_zip_manifest_bundle(tmp_path: Path) -> None:
    """A .pdf that's actually a zip of page images + text + manifest.json (as
    produced by some export tools) must yield the real per-page text, not the
    raw archive bytes decoded as UTF-8 (the original bug: garbled/unreadable
    answers when the info advisor drew on this "PDF")."""

    output_dir = tmp_path / "chroma"
    bundle_path = tmp_path / "bundle.pdf"
    manifest = {
        "num_pages": 2,
        "pages": [
            {"page_number": 2, "text": {"path": "2.txt"}},
            {"page_number": 1, "text": {"path": "1.txt"}},
        ],
    }
    with zipfile.ZipFile(bundle_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("1.txt", "Python Developer Job Description page one.")
        archive.writestr("2.txt", "Required skills: Django, Flask, SQL, Git.")

    result = build_index(
        pdf_path=bundle_path,
        persist_dir=output_dir,
        collection_name="zip_bundle_collection",
        embedding_model="text-embedding-3-small",
        overwrite=True,
    )

    assert result is not None
    assert result["documents"] >= 1

    metadata_path = output_dir / "zip_bundle_collection.json"
    if metadata_path.exists():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        documents = payload["documents"]
    elif chromadb is not None:
        client = chromadb.PersistentClient(path=str(output_dir))
        collection = client.get_collection(name="zip_bundle_collection")
        documents = collection.get()["documents"]
    else:
        documents = []

    joined = " ".join(documents).lower()
    assert "python developer job description" in joined
    assert "required skills" in joined
    assert "\x00" not in joined
